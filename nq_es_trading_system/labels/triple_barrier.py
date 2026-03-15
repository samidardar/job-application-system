"""
Triple Barrier Labeling Engine.

For each bar i at price P_i:
    upper_barrier = P_i + ATR14_i * atr_multiplier_tp   → label +1 (Long)
    lower_barrier = P_i - ATR14_i * atr_multiplier_sl   → label -1 (Short/Stop)
    time_barrier  = i + time_bars                        → label  0 (No trade)

Resolution: first barrier touched wins. macro_event_flag and extreme vol
force label = 0 regardless of barrier outcome.

Reward:Risk = 1.5 / 0.75 = 2:1 by default.
Breakeven win rate at 2:1 R:R = 33.3%.
"""

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()


class TripleBarrierLabeler:
    """
    Labels each bar using the triple barrier method.

    No look-ahead: barrier levels are set at bar i using ATR from bar i-1
    (ATR is already shift(1)-adjusted from the feature pipeline). Forward
    scanning of barriers uses actual future prices (this is intentional —
    we're labeling historical data for model training, not leaking features).
    """

    def __init__(
        self,
        atr_multiplier_tp: float = 1.5,
        atr_multiplier_sl: float = 0.75,
        time_bars: int = 6,
    ):
        """
        Args:
            atr_multiplier_tp: ATR multiplier for take-profit barrier (upper)
            atr_multiplier_sl: ATR multiplier for stop-loss barrier (lower)
            time_bars: Number of bars before time barrier triggers (default 6 = 30 min)
        """
        self.atr_multiplier_tp = atr_multiplier_tp
        self.atr_multiplier_sl = atr_multiplier_sl
        self.time_bars = time_bars

    def fit_transform(
        self,
        df: pd.DataFrame,
        force_skip_macro: bool = True,
        force_skip_extreme_vol: bool = True,
    ) -> pd.DataFrame:
        """
        Compute triple barrier labels for every bar in df.

        Args:
            df: DataFrame with columns ['close', 'atr_14', 'macro_event_flag',
                'vol_regime'] — must be sorted ascending by time
            force_skip_macro: Override label to 0 during macro events
            force_skip_extreme_vol: Override label to 0 during extreme vol

        Returns:
            df with added columns:
                'label'         : {-1, 0, +1}
                'upper_barrier' : take-profit price level
                'lower_barrier' : stop-loss price level
                'bars_to_exit'  : how many bars until barrier was hit
        """
        df = df.copy().reset_index(drop=False)  # preserve index for alignment

        close = df["close"].values
        atr = df["atr_14"].values
        n = len(df)

        labels = np.zeros(n, dtype=int)
        upper_barriers = np.full(n, np.nan)
        lower_barriers = np.full(n, np.nan)
        bars_to_exit = np.full(n, self.time_bars, dtype=int)

        for i in range(n):
            atr_i = atr[i]
            if np.isnan(atr_i) or atr_i <= 0:
                labels[i] = 0
                continue

            p0 = close[i]
            upper = p0 + atr_i * self.atr_multiplier_tp
            lower = p0 - atr_i * self.atr_multiplier_sl
            upper_barriers[i] = upper
            lower_barriers[i] = lower

            # Scan forward bars i+1 ... i+time_bars
            label = 0
            for k in range(1, self.time_bars + 1):
                j = i + k
                if j >= n:
                    label = 0
                    bars_to_exit[i] = k
                    break
                p_j = close[j]
                if p_j >= upper:
                    label = 1
                    bars_to_exit[i] = k
                    break
                elif p_j <= lower:
                    label = -1
                    bars_to_exit[i] = k
                    break
            else:
                label = 0

            labels[i] = label

        df["label"] = labels
        df["upper_barrier"] = upper_barriers
        df["lower_barrier"] = lower_barriers
        df["bars_to_exit"] = bars_to_exit

        # Force skip on macro events
        if force_skip_macro and "macro_event_flag" in df.columns:
            macro_mask = df["macro_event_flag"].fillna(0).astype(bool)
            n_macro = macro_mask.sum()
            if n_macro > 0:
                logger.info(f"TripleBarrierLabeler: forced {n_macro} labels → 0 (macro event)")
            df.loc[macro_mask, "label"] = 0

        # Force skip on extreme volatility
        if force_skip_extreme_vol and "vol_regime" in df.columns:
            extreme_mask = df["vol_regime"] == 3  # 3 = extreme
            n_extreme = extreme_mask.sum()
            if n_extreme > 0:
                logger.info(f"TripleBarrierLabeler: forced {n_extreme} labels → 0 (extreme vol)")
            df.loc[extreme_mask, "label"] = 0

        # Restore original index
        if "index" in df.columns:
            df = df.set_index("index")
        df.index.name = None

        dist = df["label"].value_counts().sort_index()
        logger.info(
            "TripleBarrierLabeler: label distribution",
            long=int(dist.get(1, 0)),
            skip=int(dist.get(0, 0)),
            short=int(dist.get(-1, 0)),
        )
        return df

    def get_class_weights(self, labels: pd.Series) -> dict:
        """
        Compute inverse-frequency class weights for CrossEntropyLoss.

        Maps labels {-1, 0, +1} to class indices {0, 1, 2} as:
            class 0 → label -1 (short)
            class 1 → label  0 (skip)
            class 2 → label +1 (long)

        Args:
            labels: pd.Series of {-1, 0, +1} labels

        Returns:
            dict mapping class_index → weight (float)
        """
        label_to_class = {-1: 0, 0: 1, 1: 2}
        counts = labels.value_counts()
        total = len(labels)
        weights = {}
        for label_val, class_idx in label_to_class.items():
            count = counts.get(label_val, 1)
            weights[class_idx] = total / (3 * count)  # inverse frequency
        return weights

    def plot_barrier_distribution(
        self, labels: pd.Series, save_path: Optional[Path] = None
    ) -> None:
        """
        Plot histogram of label distribution.

        Args:
            labels: pd.Series of {-1, 0, +1} labels
            save_path: Optional path to save the figure
        """
        fig, ax = plt.subplots(figsize=(8, 5))
        counts = labels.value_counts().sort_index()
        colors = {-1: "#e74c3c", 0: "#95a5a6", 1: "#2ecc71"}
        label_names = {-1: "Short (-1)", 0: "Skip (0)", 1: "Long (+1)"}

        ax.bar(
            [label_names[k] for k in counts.index],
            counts.values,
            color=[colors[k] for k in counts.index],
            edgecolor="black",
            linewidth=0.8,
        )
        ax.set_title("Triple Barrier Label Distribution", fontsize=14, fontweight="bold")
        ax.set_ylabel("Count")
        ax.set_xlabel("Label")

        for i, (label_val, count) in enumerate(counts.items()):
            pct = count / len(labels) * 100
            ax.text(i, count + len(labels) * 0.005, f"{pct:.1f}%", ha="center", va="bottom")

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            logger.info(f"Label distribution plot saved to {save_path}")
        plt.show()
