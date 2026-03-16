"""
LightGBM Regime Classifier (Level 1).

Classifies each 5-min bar as:
    0 = mean_reversion   (ATR compressed + price stretched from VWAP)
    1 = momentum         (high volume + directional flow)
    2 = chop             (everything else)

Only bars with P(mean_reversion) > 0.60 are passed to the signal model.

Rule-based auto-labeling is used for training (no manual annotation needed).
SHAP values provide feature importance for the dashboard.
"""

from pathlib import Path
from typing import Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()

REGIME_NAMES = {0: "mean_reversion", 1: "momentum", 2: "chop"}
REGIME_MEAN_REV = 0
REGIME_MOMENTUM = 1
REGIME_CHOP = 2


def auto_label_regime(
    df: pd.DataFrame,
    atr_ratio_max: float = 0.80,
    vwap_zscore_min: float = 1.50,
    rvol_min_mr: float = 0.80,
    rvol_min_mom: float = 1.50,
) -> pd.Series:
    """
    Generate rule-based regime labels from features.

    Rules (applied in order, first match wins):
        mean_reversion: atr_ratio < atr_ratio_max
                        AND |vwap_zscore| > vwap_zscore_min
                        AND rvol > rvol_min_mr
        momentum:       rvol > rvol_min_mom
                        AND cvd_divergence == 0
                        AND obv_slope > 0
        chop:           everything else

    No look-ahead: all input columns are already shift(1)-adjusted
    by the feature pipeline before this function is called.

    Args:
        df: Feature DataFrame with regime-relevant columns
        atr_ratio_max: Max ATR ratio for mean-rev regime
        vwap_zscore_min: Min |VWAP z-score| for mean-rev regime
        rvol_min_mr: Min RVOL for mean-rev regime
        rvol_min_mom: Min RVOL for momentum regime

    Returns:
        pd.Series of integer regime labels {0, 1, 2}
    """
    labels = pd.Series(REGIME_CHOP, index=df.index, dtype=int)

    # Require these columns; if missing, return all chop
    needed = ["atr_ratio", "vwap_zscore", "rvol"]
    if not all(c in df.columns for c in needed):
        logger.warning("auto_label_regime: missing required columns, returning all chop")
        return labels

    atr_ratio = df["atr_ratio"].fillna(1.0)
    vwap_zscore = df["vwap_zscore"].fillna(0.0).abs()
    rvol = df["rvol"].fillna(1.0)
    cvd_div = df.get("cvd_divergence", pd.Series(0, index=df.index)).fillna(0)
    obv_slope = df.get("obv_slope", pd.Series(0, index=df.index)).fillna(0)

    mean_rev_mask = (atr_ratio < atr_ratio_max) & (vwap_zscore > vwap_zscore_min) & (rvol > rvol_min_mr)
    momentum_mask = (~mean_rev_mask) & (rvol > rvol_min_mom) & (cvd_div == 0) & (obv_slope > 0)

    labels[mean_rev_mask] = REGIME_MEAN_REV
    labels[momentum_mask] = REGIME_MOMENTUM
    # chop = default (0 already set, overrides where needed)

    dist = labels.value_counts().sort_index()
    logger.info(
        "auto_label_regime: regime distribution",
        mean_rev=int(dist.get(0, 0)),
        momentum=int(dist.get(1, 0)),
        chop=int(dist.get(2, 0)),
    )
    return labels


class RegimeClassifier:
    """
    LightGBM multi-class regime classifier.

    Uses flattened features from the last `lookback_bars` bars as input.
    Trained with walk-forward validation; hyperparams tuned via Optuna.
    """

    def __init__(
        self,
        lookback_bars: int = 30,
        min_regime_probability: float = 0.60,
        model_path: str = "models/saved/regime_classifier.joblib",
    ):
        """
        Args:
            lookback_bars: Number of past bars to use as context (flattened)
            min_regime_probability: Minimum P(mean_rev) to pass to signal model
            model_path: Where to save/load the model
        """
        self.lookback_bars = lookback_bars
        self.min_regime_probability = min_regime_probability
        self.model_path = Path(model_path)
        self._model: Optional[lgb.LGBMClassifier] = None
        self._feature_names: list = []

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame = None,
        y_val: pd.Series = None,
        params: dict = None,
    ) -> None:
        """
        Fit LightGBM classifier on training data.

        Args:
            X_train: Feature DataFrame (rows = bars, columns = features)
            y_train: Regime labels {0, 1, 2}
            X_val: Optional validation set for early stopping
            y_val: Validation labels
            params: LightGBM hyperparams (uses defaults if None)
        """
        default_params = {
            "n_estimators": 300,
            "num_leaves": 63,
            "learning_rate": 0.05,
            "max_depth": 6,
            "min_child_samples": 50,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "class_weight": "balanced",
            "objective": "multiclass",
            "num_class": 3,
            "metric": "multi_logloss",
            "device": "cpu",
            "verbose": -1,
            "random_state": 42,
        }
        if params:
            default_params.update(params)

        self._model = lgb.LGBMClassifier(**default_params)
        self._feature_names = list(X_train.columns)

        callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)]

        if X_val is not None and y_val is not None:
            self._model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                callbacks=callbacks,
            )
        else:
            self._model.fit(X_train, y_train)

        logger.info(
            "RegimeClassifier.fit: training complete",
            n_estimators=self._model.best_iteration_ or default_params["n_estimators"],
        )

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict class probabilities.

        Args:
            X: Feature DataFrame

        Returns:
            np.ndarray of shape [n_samples, 3] with [P_mean_rev, P_momentum, P_chop]
        """
        if self._model is None:
            raise RuntimeError("RegimeClassifier not fitted. Call fit() first.")
        return self._model.predict_proba(X)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict most likely regime class."""
        return self._model.predict(X)

    def is_mean_reversion(self, X: pd.DataFrame) -> np.ndarray:
        """
        Return boolean mask: True where P(mean_reversion) > min_regime_probability.

        Args:
            X: Feature DataFrame

        Returns:
            Boolean array of shape [n_samples]
        """
        proba = self.predict_proba(X)
        return proba[:, REGIME_MEAN_REV] > self.min_regime_probability

    def get_feature_importance(self) -> pd.DataFrame:
        """
        Return feature importances as a sorted DataFrame.

        Returns:
            pd.DataFrame with columns ['feature', 'importance'] sorted descending
        """
        if self._model is None:
            raise RuntimeError("Model not fitted.")
        importances = self._model.feature_importances_
        return (
            pd.DataFrame(
                {"feature": self._feature_names, "importance": importances}
            )
            .sort_values("importance", ascending=False)
            .reset_index(drop=True)
        )

    def compute_shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """
        Compute SHAP values for interpretability dashboard.

        Args:
            X: Feature DataFrame (can be a sample, e.g., 200 rows)

        Returns:
            np.ndarray of SHAP values [n_samples, n_features, n_classes]
        """
        try:
            import shap
            explainer = shap.TreeExplainer(self._model)
            shap_values = explainer.shap_values(X)
            return shap_values
        except ImportError:
            logger.warning("shap not installed; skipping SHAP computation")
            return np.array([])

    def save(self) -> None:
        """Serialize model + feature names to disk."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self._model, "feature_names": self._feature_names},
            self.model_path,
        )
        logger.info(f"RegimeClassifier saved to {self.model_path}")

    def load(self) -> None:
        """Load model + feature names from disk."""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found at {self.model_path}")
        data = joblib.load(self.model_path)
        self._model = data["model"]
        self._feature_names = data["feature_names"]
        logger.info(f"RegimeClassifier loaded from {self.model_path}")
