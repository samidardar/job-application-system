"""
Anchored Walk-Forward Validation Engine.

Uses expanding training window (NOT k-fold) to avoid temporal data leakage.
Auto-rejects any fold where out-of-sample Sharpe < 0.8.

Fold structure (3 years of data):
    Fold 1: Train [months 1-18]  | Test [months 19-21]
    Fold 2: Train [months 1-21]  | Test [months 22-24]
    Fold 3: Train [months 1-24]  | Test [months 25-27]
    Fold 4: Train [months 1-27]  | Test [months 28-30]
    Fold 5: Train [months 1-30]  | Test [months 31-36]
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()


@dataclass
class FoldResult:
    """Results for a single walk-forward fold."""
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_daily_pnl: float
    total_trades: int
    passed: bool
    equity_curve: pd.Series = field(default_factory=pd.Series)
    trade_log: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class WalkForwardResults:
    """Aggregate results across all folds."""
    folds: List[FoldResult] = field(default_factory=list)
    passed: bool = False

    @property
    def aggregate_sharpe(self) -> float:
        sharpes = [f.sharpe for f in self.folds if not np.isnan(f.sharpe)]
        return float(np.mean(sharpes)) if sharpes else 0.0

    @property
    def aggregate_sortino(self) -> float:
        sortinos = [f.sortino for f in self.folds if not np.isnan(f.sortino)]
        return float(np.mean(sortinos)) if sortinos else 0.0

    @property
    def aggregate_max_dd(self) -> float:
        dds = [f.max_drawdown for f in self.folds]
        return float(np.max(dds)) if dds else 0.0

    @property
    def aggregate_win_rate(self) -> float:
        wr = [f.win_rate for f in self.folds if not np.isnan(f.win_rate)]
        return float(np.mean(wr)) if wr else 0.0

    def summary_table(self) -> pd.DataFrame:
        """Return per-fold + aggregate metrics as a DataFrame."""
        rows = []
        for f in self.folds:
            rows.append({
                "fold": f.fold,
                "train_period": f"{f.train_start.date()} → {f.train_end.date()}",
                "test_period": f"{f.test_start.date()} → {f.test_end.date()}",
                "sharpe": round(f.sharpe, 3),
                "sortino": round(f.sortino, 3),
                "max_drawdown": f"{f.max_drawdown*100:.1f}%",
                "win_rate": f"{f.win_rate*100:.1f}%",
                "profit_factor": round(f.profit_factor, 3),
                "avg_daily_pnl": f"${f.avg_daily_pnl:.0f}",
                "total_trades": f.total_trades,
                "passed": "✅" if f.passed else "❌",
            })
        rows.append({
            "fold": "AGGREGATE",
            "train_period": "",
            "test_period": "",
            "sharpe": round(self.aggregate_sharpe, 3),
            "sortino": round(self.aggregate_sortino, 3),
            "max_drawdown": f"{self.aggregate_max_dd*100:.1f}%",
            "win_rate": f"{self.aggregate_win_rate*100:.1f}%",
            "profit_factor": "",
            "avg_daily_pnl": "",
            "total_trades": sum(f.total_trades for f in self.folds),
            "passed": "✅ PASS" if self.passed else "❌ FAIL",
        })
        return pd.DataFrame(rows)

    def print_summary(self) -> None:
        """Print formatted walk-forward summary table."""
        print("\n" + "┌" + "─" * 47 + "┐")
        print("│  WALK-FORWARD VALIDATION RESULTS              │")
        print("├" + "─" * 47 + "┤")
        for f in self.folds:
            status = "✅" if f.passed else "❌"
            print(f"│  Fold {f.fold}: Sharpe {f.sharpe:5.2f} | DD {f.max_drawdown*100:4.1f}% {status}  │")
        print("├" + "─" * 47 + "┤")
        overall = "✅ PASS" if self.passed else "❌ FAIL"
        print(f"│  AGGREGATE: Sharpe {self.aggregate_sharpe:5.2f} | Sortino {self.aggregate_sortino:5.2f}  │")
        print(f"│  Status: {overall:<38}│")
        print("└" + "─" * 47 + "┘\n")


class WalkForwardValidator:
    """
    Anchored expanding-window walk-forward validator.

    For each fold:
        1. Split train/test by date
        2. Fit FeaturePipeline on train only
        3. Transform test
        4. Fit RegimeClassifier on train
        5. Filter: only mean_reversion bars for signal model
        6. Train SignalModel on train
        7. Run BacktestEngine on test
        8. Collect metrics
    """

    def __init__(
        self,
        n_folds: int = 5,
        initial_train_months: int = 18,
        test_months: int = 3,
        min_fold_sharpe: float = 0.80,
    ):
        self.n_folds = n_folds
        self.initial_train_months = initial_train_months
        self.test_months = test_months
        self.min_fold_sharpe = min_fold_sharpe

    def generate_folds(
        self, df: pd.DataFrame
    ) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
        """
        Generate anchored expanding train/test index pairs.

        Args:
            df: DataFrame with DatetimeIndex sorted ascending

        Returns:
            List of (train_idx, test_idx) tuples
        """
        start = df.index[0]
        folds = []

        for i in range(self.n_folds):
            train_end_month = self.initial_train_months + i * self.test_months
            test_end_month = train_end_month + self.test_months

            train_end = start + pd.DateOffset(months=train_end_month)
            test_end = start + pd.DateOffset(months=test_end_month)

            train_idx = df.index[df.index < train_end]
            test_idx = df.index[(df.index >= train_end) & (df.index < test_end)]

            if len(test_idx) == 0:
                logger.warning(f"Fold {i+1}: no test data, stopping at {i} folds")
                break

            folds.append((train_idx, test_idx))
            logger.info(
                f"Fold {i+1}: train {train_idx[0].date()}→{train_idx[-1].date()} "
                f"({len(train_idx)} bars) | test {test_idx[0].date()}→{test_idx[-1].date()} "
                f"({len(test_idx)} bars)"
            )

        return folds

    def run(
        self,
        df: pd.DataFrame,
        df_news: pd.DataFrame = None,
        df_vix: pd.DataFrame = None,
        df_ticks: pd.DataFrame = None,
        regime_clf_params: dict = None,
        signal_model_params: dict = None,
        training_config: dict = None,
        save_dir: str = "models/saved",
    ) -> WalkForwardResults:
        """
        Execute full walk-forward validation.

        Args:
            df: OHLCV DataFrame (full 3-year history)
            df_news: News DataFrame (pre-computed sentiment)
            df_vix: Daily VIX DataFrame
            df_ticks: Tick DataFrame (optional)
            regime_clf_params: LightGBM params for regime classifier
            signal_model_params: Kwargs for SignalModel constructor
            training_config: Training config dict for SignalModelTrainer
            save_dir: Directory to save per-fold models

        Returns:
            WalkForwardResults with per-fold and aggregate metrics
        """
        from features.pipeline import FeaturePipeline
        from labels.triple_barrier import TripleBarrierLabeler
        from models.regime_classifier import RegimeClassifier, auto_label_regime
        from models.signal_model import SignalModel
        from training.trainer import SignalModelTrainer
        from backtesting.engine import BacktestEngine
        from backtesting.metrics import compute_all_metrics

        folds = self.generate_folds(df)
        results = WalkForwardResults()
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        for fold_idx, (train_idx, test_idx) in enumerate(folds):
            fold_num = fold_idx + 1
            logger.info(f"=== Running Fold {fold_num}/{len(folds)} ===")

            df_train = df.loc[train_idx]
            df_test = df.loc[test_idx]

            # Slice news/vix to appropriate time ranges
            df_news_train = _slice_news(df_news, train_idx)
            df_news_test = _slice_news(df_news, test_idx)
            df_ticks_train = _slice_ticks(df_ticks, train_idx)
            df_ticks_test = _slice_ticks(df_ticks, test_idx)

            # 1. Feature pipeline (fit on train ONLY)
            pipe = FeaturePipeline(scaler_path=str(save_dir / f"scaler_fold{fold_num}.joblib"))
            X_train, meta_train = pipe.fit_transform(df_train, df_news_train, df_vix, df_ticks_train)
            X_test, meta_test = pipe.transform(df_test, df_news_test, df_vix, df_ticks_test)

            # 2. Labels (use unscaled metadata, not z-scored X_train)
            labeler = TripleBarrierLabeler()
            label_cols = ["atr_14", "vol_regime", "macro_event_flag"]
            label_src = meta_train[[c for c in label_cols if c in meta_train.columns]]
            df_train_labeled = labeler.fit_transform(
                df_train.join(label_src, how="left")
                if "atr_14" not in df_train.columns else df_train
            )
            y_train = df_train_labeled["label"].reindex(X_train.index).fillna(0).astype(int)

            # 3. Regime classifier
            regime_clf = RegimeClassifier(
                model_path=str(save_dir / f"regime_clf_fold{fold_num}.joblib")
            )
            y_regime_train = auto_label_regime(X_train)
            regime_clf.fit(X_train, y_regime_train, params=regime_clf_params)
            regime_clf.save()

            # 4. Filter: train signal model only on mean-rev bars
            mr_mask_train = regime_clf.is_mean_reversion(X_train)
            X_train_mr = X_train[mr_mask_train]
            y_train_mr = y_train[mr_mask_train]

            if len(X_train_mr) < 100:
                logger.warning(f"Fold {fold_num}: too few mean-rev bars ({len(X_train_mr)}), skipping")
                continue

            # 5. Train signal model
            model_kwargs = signal_model_params or {}
            model = SignalModel(**model_kwargs)
            class_weights = labeler.get_class_weights(y_train_mr)

            # Split last 10% of mean-rev train bars as validation
            n_val = max(int(len(X_train_mr) * 0.10), 50)
            X_tr = X_train_mr.iloc[:-n_val]
            y_tr = y_train_mr.iloc[:-n_val]
            X_vl = X_train_mr.iloc[-n_val:]
            y_vl = y_train_mr.iloc[-n_val:]

            trainer = SignalModelTrainer(model=model)
            trainer.fit(
                X_tr, y_tr, X_vl, y_vl,
                config=training_config,
                class_weights=class_weights,
                checkpoint_path=str(save_dir / f"signal_model_fold{fold_num}.pt"),
            )

            # 6. Backtest on test data
            engine = BacktestEngine()

            # Generate signals on test set
            mr_mask_test = regime_clf.is_mean_reversion(X_test)
            X_test_mr = X_test[mr_mask_test]
            meta_test_mr = meta_test.reindex(X_test_mr.index)

            if len(X_test_mr) > 0:
                from training.trainer import prepare_sequences
                import torch
                # Build signals dataframe (prepare_sequences drops first seq_len rows)
                SEQ_LEN = 20
                signals_list = _generate_signals(model, X_test_mr, trainer.device)
                if len(signals_list) > 0:
                    signals_df = pd.DataFrame(signals_list, index=X_test_mr.index[SEQ_LEN:])
                else:
                    signals_df = pd.DataFrame(columns=["signal", "confidence"])
            else:
                signals_df = pd.DataFrame(columns=["signal", "confidence"])

            bt_result = engine.run(df_test, signals_df, meta_test)

            # 7. Metrics
            metrics = compute_all_metrics(bt_result)
            sharpe = metrics.get("sharpe", 0.0)
            passed = sharpe >= self.min_fold_sharpe

            if not passed:
                logger.warning(f"Fold {fold_num}: Sharpe={sharpe:.3f} < {self.min_fold_sharpe} — FAIL")

            fold_result = FoldResult(
                fold=fold_num,
                train_start=train_idx[0],
                train_end=train_idx[-1],
                test_start=test_idx[0],
                test_end=test_idx[-1],
                sharpe=sharpe,
                sortino=metrics.get("sortino", 0.0),
                max_drawdown=metrics.get("max_drawdown", 0.0),
                win_rate=metrics.get("win_rate", 0.0),
                profit_factor=metrics.get("profit_factor", 0.0),
                avg_daily_pnl=metrics.get("avg_daily_pnl", 0.0),
                total_trades=metrics.get("total_trades", 0),
                passed=passed,
                equity_curve=bt_result.equity_curve,
                trade_log=bt_result.trade_log,
            )
            results.folds.append(fold_result)

        results.passed = all(f.passed for f in results.folds) and len(results.folds) > 0
        return results


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _slice_news(df_news: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Slice news DataFrame to the time range covered by idx."""
    if df_news is None or df_news.empty:
        return df_news
    start, end = idx[0], idx[-1]
    ts_col = "published_at"
    if ts_col in df_news.columns:
        mask = (df_news[ts_col] >= start) & (df_news[ts_col] <= end)
        return df_news[mask].copy()
    return df_news


def _slice_ticks(df_ticks: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Slice ticks DataFrame to the time range covered by idx."""
    if df_ticks is None or df_ticks.empty:
        return df_ticks
    if isinstance(df_ticks.index, pd.DatetimeIndex):
        return df_ticks.loc[idx[0]:idx[-1]].copy()
    return df_ticks


def _generate_signals(model, X_mr: pd.DataFrame, device: str) -> list:
    """Run batch inference on mean-rev bars and return signal list."""
    from training.trainer import prepare_sequences
    import torch

    # Use single-bar inference (no temporal window needed for current bar features)
    from features.pipeline import (
        TEMPORAL_FEATURES, ORDERFLOW_FEATURES, VOLATILITY_FEATURES, NEWS_FEATURES
    )

    SEQ_LEN = 20
    if len(X_mr) <= SEQ_LEN:
        return []

    t_cols = [c for c in TEMPORAL_FEATURES if c in X_mr.columns]
    of_cols = [c for c in ORDERFLOW_FEATURES if c in X_mr.columns]
    vol_cols = [c for c in VOLATILITY_FEATURES if c in X_mr.columns]
    n_cols = [c for c in NEWS_FEATURES if c in X_mr.columns]

    X_t, X_of, X_vol, X_n, _ = prepare_sequences(
        X_mr,
        pd.Series(0, index=X_mr.index),  # dummy labels
        seq_len=SEQ_LEN,
        temporal_cols=t_cols,
        orderflow_cols=of_cols,
        volatility_cols=vol_cols,
        news_cols=n_cols,
    )

    model.eval()
    results = []
    bs = 256
    with torch.no_grad():
        for i in range(0, len(X_t), bs):
            t = torch.tensor(X_t[i:i+bs], dtype=torch.float32).to(device)
            o = torch.tensor(X_of[i:i+bs], dtype=torch.float32).to(device)
            v = torch.tensor(X_vol[i:i+bs], dtype=torch.float32).to(device)
            n = torch.tensor(X_n[i:i+bs], dtype=torch.float32).to(device)

            log_probs = model(t, o, v, n)
            probs = torch.exp(log_probs)
            class_idx = probs.argmax(dim=-1).cpu().numpy()
            conf = probs.max(dim=-1).values.cpu().numpy()

            from models.signal_model import CLASS_TO_LABEL
            for cls, c in zip(class_idx, conf):
                results.append({"signal": CLASS_TO_LABEL[int(cls)], "confidence": float(c)})

    return results
