"""
Master feature pipeline.

Orchestrates all 5 feature modules in the correct dependency order with
strict no-leakage guarantees:

  1. StandardScaler is NEVER fit on test data — fit_transform() on train only.
  2. All rolling features use .shift(1) before joining labels.
  3. Orderflow NaN columns are imputed with 0 (neutral assumption) after logging.
  4. Scaler artifacts are saved to disk for live inference consistency.

Usage:
    pipe = FeaturePipeline(config_path="config/data_config.yaml")
    X_train, meta_train = pipe.fit_transform(df_train, df_news_train, df_vix)
    X_test, meta_test  = pipe.transform(df_test, df_news_test, df_vix)
"""

import warnings
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import structlog
import yaml
from sklearn.preprocessing import StandardScaler

from features.volatility import add_volatility_features
from features.mean_reversion import add_mean_reversion_features
from features.volume import add_volume_features
from features.orderflow import add_orderflow_features
from features.news import add_news_features

logger = structlog.get_logger()

# Canonical feature column names (35 total)
TEMPORAL_FEATURES = [
    "vwap_deviation_pct",
    "vwap_zscore",
    "bollinger_pct_b",
    "zscore_returns",
    "rsi_14",
    "mean_rev_strength",
    "rvol",
    "obv_slope",
]  # 8 features for TCN Branch A

ORDERFLOW_FEATURES = [
    "bid_ask_imbalance",
    "stacked_imbalance_bull",
    "stacked_imbalance_bear",
    "delta_per_bar",
    "delta_divergence",
    "absorption_score",
    "footprint_poc_dist",
]  # 7 features for CNN Branch B

VOLATILITY_FEATURES = [
    "atr_14",
    "atr_ratio",
    "realized_vol_20",
    "vol_of_vol",
    "vix_daily",
    "vol_regime",
]  # 6 features for MLP Branch C

NEWS_FEATURES = [
    "news_sentiment_score",
    "news_event_flag",
    "news_count_1h",
    "macro_event_flag",
    "hour_sin",
]  # 5 features for Embedding Branch D
# (hour_sin is the primary time feature; others are in metadata)

REGIME_EXTRA_FEATURES = [
    "half_life_ou",
    "rsi_divergence",
    "cvd",
    "cvd_divergence",
    "vw_momentum_5",
    "volume_regime",
    "hour_cos",
    "minute_sin",
    "minute_cos",
    "dow_sin",
]  # Extra features used by regime classifier (vol_of_vol/vix_daily already in VOLATILITY_FEATURES)

ALL_MODEL_FEATURES = (
    TEMPORAL_FEATURES + ORDERFLOW_FEATURES + VOLATILITY_FEATURES + NEWS_FEATURES
)

METADATA_COLS = [
    "open", "high", "low", "close", "volume",
    "vwap", "atr_14", "vol_regime", "macro_event_flag",
    "news_event_flag",
]


class FeaturePipeline:
    """
    Orchestrates feature engineering + scaling for the full trading pipeline.

    Strict no-leakage contract:
        - fit_transform() fits scaler on train data only
        - transform() applies fitted scaler to new data
        - Never call fit() or fit_transform() on test data
    """

    def __init__(
        self,
        config_path: str = "config/data_config.yaml",
        scaler_path: str = "models/saved/feature_scaler.joblib",
        max_nan_pct: float = 0.30,
    ):
        """
        Args:
            config_path: Path to data_config.yaml
            scaler_path: Where to save/load the fitted StandardScaler
            max_nan_pct: Drop feature rows where NaN fraction exceeds this
        """
        self.config_path = Path(config_path)
        self.scaler_path = Path(scaler_path)
        self.max_nan_pct = max_nan_pct
        self._scaler: Optional[StandardScaler] = None
        self._is_fitted = False

        if self.config_path.exists():
            with open(self.config_path) as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit_transform(
        self,
        df_bars: pd.DataFrame,
        df_news: pd.DataFrame = None,
        df_vix: pd.DataFrame = None,
        df_ticks: pd.DataFrame = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Compute all features, fit scaler on this data, return scaled features.

        IMPORTANT: Call this ONLY on training data. Never on test/validation data.

        Args:
            df_bars: OHLCV DataFrame (DatetimeIndex, tz-aware ET)
            df_news: News DataFrame with pre-computed 'sentiment' column
            df_vix: Daily VIX DataFrame
            df_ticks: Tick data DataFrame (optional, graceful fallback)

        Returns:
            Tuple of (X_scaled: pd.DataFrame, metadata: pd.DataFrame)
            X_scaled contains ALL_MODEL_FEATURES + REGIME_EXTRA_FEATURES
        """
        logger.info("FeaturePipeline.fit_transform: computing features on training data")
        df_features = self._compute_all_features(df_bars, df_news, df_vix, df_ticks)
        df_features = self._clean(df_features)

        feature_cols = self._get_feature_cols(df_features)
        X = df_features[feature_cols].copy()

        logger.info(f"FeaturePipeline: fitting scaler on {len(X)} training rows")
        self._scaler = StandardScaler()
        X_scaled = pd.DataFrame(
            self._scaler.fit_transform(X.values),
            index=X.index,
            columns=X.columns,
        )
        self._is_fitted = True
        self._save_scaler()

        metadata = self._extract_metadata(df_features)
        return X_scaled, metadata

    def transform(
        self,
        df_bars: pd.DataFrame,
        df_news: pd.DataFrame = None,
        df_vix: pd.DataFrame = None,
        df_ticks: pd.DataFrame = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Compute all features and apply pre-fitted scaler.

        IMPORTANT: Scaler must be fitted via fit_transform() first.
        Raises RuntimeError if called before fit_transform().

        Args:
            df_bars: OHLCV DataFrame
            df_news: News DataFrame
            df_vix: Daily VIX DataFrame
            df_ticks: Tick data DataFrame (optional)

        Returns:
            Tuple of (X_scaled: pd.DataFrame, metadata: pd.DataFrame)
        """
        if not self._is_fitted:
            raise RuntimeError(
                "FeaturePipeline.transform() called before fit_transform(). "
                "Always call fit_transform() on training data first."
            )

        logger.info("FeaturePipeline.transform: computing features on test/live data")
        df_features = self._compute_all_features(df_bars, df_news, df_vix, df_ticks)
        df_features = self._clean(df_features)

        feature_cols = self._get_feature_cols(df_features)
        X = df_features[feature_cols].copy()

        X_scaled = pd.DataFrame(
            self._scaler.transform(X.values),
            index=X.index,
            columns=X.columns,
        )

        metadata = self._extract_metadata(df_features)
        return X_scaled, metadata

    def load_scaler(self) -> None:
        """Load previously saved scaler from disk."""
        if not self.scaler_path.exists():
            raise FileNotFoundError(f"Scaler not found at {self.scaler_path}")
        self._scaler = joblib.load(self.scaler_path)
        self._is_fitted = True
        logger.info(f"FeaturePipeline: loaded scaler from {self.scaler_path}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_all_features(
        self,
        df_bars: pd.DataFrame,
        df_news: pd.DataFrame,
        df_vix: pd.DataFrame,
        df_ticks: pd.DataFrame,
    ) -> pd.DataFrame:
        """Run all feature modules in dependency order."""
        # 1. Volatility first (ATR needed by other modules)
        df = add_volatility_features(df_bars, df_vix)

        # 2. Mean reversion (needs OHLCV + vol columns)
        df = add_mean_reversion_features(df)

        # 3. Volume features
        df = add_volume_features(df)

        # 4. Order flow (graceful fallback if no ticks)
        df = add_orderflow_features(df, df_ticks)

        # 5. News / macro / time features
        df = add_news_features(df, df_news)

        return df

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Impute and clean features:
            - Orderflow NaN → 0 (neutral assumption) with warning
            - Drop rows with > max_nan_pct NaN across critical features
            - Forward-fill remaining NaN (max 3 bars per PRD spec)
        """
        df = df.copy()

        # Impute orderflow NaN with 0 (neutral)
        of_cols = [c for c in ORDERFLOW_FEATURES if c in df.columns]
        nan_of_counts = df[of_cols].isna().sum()
        if nan_of_counts.any():
            logger.warning(
                "FeaturePipeline: imputing orderflow NaN with 0 (tick data unavailable)",
                counts=nan_of_counts[nan_of_counts > 0].to_dict(),
            )
            df[of_cols] = df[of_cols].fillna(0)

        # Forward-fill up to 3 bars for other features
        all_feat_cols = self._get_feature_cols(df)
        present = [c for c in all_feat_cols if c in df.columns]
        for col in present:
            df[col] = df[col].ffill(limit=3)

        # Drop rows where > 30% of critical features are still NaN
        nan_frac = df[present].isna().mean(axis=1)
        n_before = len(df)
        df = df[nan_frac <= self.max_nan_pct]
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.warning(f"FeaturePipeline: dropped {n_dropped} rows (>{self.max_nan_pct*100:.0f}% NaN)")

        return df

    def _get_feature_cols(self, df: pd.DataFrame) -> list:
        """Return all model feature columns present in df."""
        target = ALL_MODEL_FEATURES + REGIME_EXTRA_FEATURES
        return [c for c in target if c in df.columns]

    def _extract_metadata(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract non-scaled metadata columns for backtesting/monitoring."""
        cols = [c for c in METADATA_COLS if c in df.columns]
        return df[cols].copy()

    def _save_scaler(self) -> None:
        """Save fitted scaler to disk."""
        self.scaler_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._scaler, self.scaler_path)
        logger.info(f"FeaturePipeline: saved scaler to {self.scaler_path}")
