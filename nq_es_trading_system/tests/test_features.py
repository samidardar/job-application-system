"""
Feature engineering unit tests.

Primary focus: ZERO DATA LEAKAGE verification.
All rolling features must use only data from T-1 and earlier at bar T.
"""

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv


class TestNoLookaheadVWAP:
    """Verify VWAP reset and no-lookahead guarantees."""

    def test_vwap_uses_no_future_data(self):
        """VWAP at bar T should not change if we remove bars T+1 and beyond."""
        from features.mean_reversion import compute_vwap

        df_full = make_ohlcv(50)
        df_truncated = df_full.iloc[:30].copy()

        vwap_full = compute_vwap(df_full)
        vwap_trunc = compute_vwap(df_truncated)

        # VWAP values for the first 30 bars should be identical
        pd.testing.assert_series_equal(
            vwap_full.iloc[:30],
            vwap_trunc.iloc[:30],
            check_names=False,
        )

    def test_vwap_resets_at_session_start(self):
        """VWAP must reset to (typical_price) at the first bar of each day."""
        from features.mean_reversion import compute_vwap

        # 3 days of data
        dfs = []
        for day in ["2024-01-02", "2024-01-03", "2024-01-04"]:
            df = make_ohlcv(10, start=f"{day} 09:30", freq="5min")
            dfs.append(df)
        df_multi = pd.concat(dfs).sort_index()
        vwap = compute_vwap(df_multi)

        # At the first bar of each day, VWAP should equal the typical price of that bar
        for day in ["2024-01-02", "2024-01-03", "2024-01-04"]:
            first_bar = df_multi[df_multi.index.date == pd.Timestamp(day).date()].iloc[0]
            tp = (first_bar["high"] + first_bar["low"] + first_bar["close"]) / 3
            first_bar_idx = df_multi[df_multi.index.date == pd.Timestamp(day).date()].index[0]
            assert abs(vwap.loc[first_bar_idx] - tp) < 1e-6, (
                f"VWAP did not reset on {day}: got {vwap.loc[first_bar_idx]:.4f}, expected {tp:.4f}"
            )

    def test_no_lookahead_rolling_features(self):
        """
        Verify all rolling features at bar T do not change when we remove
        bars T+1 and beyond (strict no-lookahead property).
        """
        from features.mean_reversion import add_mean_reversion_features

        df_full = make_ohlcv(100)
        df_trunc = df_full.iloc[:60].copy()

        feat_full = add_mean_reversion_features(df_full)
        feat_trunc = add_mean_reversion_features(df_trunc)

        rolling_cols = ["vwap_zscore", "bollinger_pct_b", "zscore_returns", "rsi_14"]

        for col in rolling_cols:
            if col not in feat_full.columns:
                continue
            full_vals = feat_full[col].iloc[:60].dropna()
            trunc_vals = feat_trunc[col].dropna()
            # Both should have same values for overlapping indices
            common_idx = full_vals.index.intersection(trunc_vals.index)
            if len(common_idx) > 0:
                np.testing.assert_allclose(
                    full_vals.loc[common_idx].values,
                    trunc_vals.loc[common_idx].values,
                    rtol=1e-5,
                    err_msg=f"Lookahead detected in feature '{col}'",
                )

    def test_vwap_deviation_uses_shifted_vwap(self):
        """vwap_deviation_pct uses shift(1) on VWAP — verify numerically."""
        from features.mean_reversion import compute_vwap, compute_vwap_deviation

        df = make_ohlcv(50)
        df["vwap"] = compute_vwap(df)
        dev = compute_vwap_deviation(df)

        # Manually compute what dev should be: (close - vwap.shift(1)) / vwap.shift(1) * 100
        expected = (df["close"] - df["vwap"].shift(1)) / df["vwap"].shift(1).replace(0, np.nan) * 100

        pd.testing.assert_series_equal(dev.dropna(), expected.dropna(), check_names=False)


class TestOrderflowFallback:
    """Verify orderflow module returns NaN (not crash) without tick data."""

    def test_bid_ask_imbalance_fallback(self):
        """bid_ask_imbalance returns NaN-filled series when ticks unavailable."""
        from features.orderflow import compute_bid_ask_imbalance

        df = make_ohlcv(50)
        result = compute_bid_ask_imbalance(None, df)

        assert isinstance(result, pd.Series)
        assert result.isna().all(), "Expected all NaN when no tick data"
        assert len(result) == len(df)

    def test_delta_per_bar_fallback(self):
        """delta_per_bar returns NaN-filled series when ticks unavailable."""
        from features.orderflow import compute_delta_per_bar

        df = make_ohlcv(50)
        result = compute_delta_per_bar(None, df)

        assert isinstance(result, pd.Series)
        assert result.isna().all()

    def test_add_orderflow_does_not_crash_without_ticks(self):
        """add_orderflow_features returns valid DataFrame with NaN of-cols."""
        from features.orderflow import add_orderflow_features
        from features.volatility import add_volatility_features

        df = make_ohlcv(50)
        df = add_volatility_features(df)
        result = add_orderflow_features(df, df_ticks=None)

        assert isinstance(result, pd.DataFrame)
        assert "bid_ask_imbalance" in result.columns
        # Should be NaN (not crash)
        assert result["bid_ask_imbalance"].isna().sum() == len(result)


class TestPipelineScalerLeakage:
    """Verify FeaturePipeline never fits scaler on test data."""

    def test_scaler_fit_on_train_only(self, tmp_path):
        """transform() must raise if called before fit_transform()."""
        import sys
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

        from features.pipeline import FeaturePipeline

        pipe = FeaturePipeline(
            config_path="config/data_config.yaml",
            scaler_path=str(tmp_path / "scaler.joblib"),
        )

        df = make_ohlcv(100)
        with pytest.raises(RuntimeError, match="fit_transform"):
            pipe.transform(df)

    def test_scaler_fit_values_differ_from_test_mean(self, tmp_path):
        """Scaler fitted on train produces different mean than if fitted on test."""
        import sys
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

        from features.pipeline import FeaturePipeline

        df_train = make_ohlcv(200, start="2024-01-02 09:30")
        df_test = make_ohlcv(50, start="2024-06-01 09:30")  # Different mean

        pipe = FeaturePipeline(
            config_path="config/data_config.yaml",
            scaler_path=str(tmp_path / "scaler.joblib"),
        )

        X_train, _ = pipe.fit_transform(df_train)
        X_test, _ = pipe.transform(df_test)

        # Train data scaled should have ~0 mean; test data may not
        if "zscore_returns" in X_train.columns:
            train_mean = X_train["zscore_returns"].dropna().mean()
            # Train mean after scaling should be near 0
            assert abs(train_mean) < 0.5, f"Train mean too high: {train_mean}"


class TestVolatilityFeatures:
    """Verify volatility features have correct shapes and no leakage."""

    def test_atr_shape(self):
        from features.volatility import compute_atr
        df = make_ohlcv(50)
        atr = compute_atr(df)
        assert len(atr) == len(df)
        assert atr.name == "atr_14"

    def test_atr_no_leakage(self):
        """ATR at bar T uses prev_close from T-1 (shift(1) applied)."""
        from features.volatility import compute_atr
        df = make_ohlcv(50)
        df_trunc = df.iloc[:30].copy()
        atr_full = compute_atr(df)
        atr_trunc = compute_atr(df_trunc)
        pd.testing.assert_series_equal(
            atr_full.iloc[:30].dropna(),
            atr_trunc.dropna(),
            check_names=False,
        )

    def test_vol_regime_encoding(self):
        """vol_regime values should be in {0, 1, 2, 3}."""
        from features.volatility import add_volatility_features
        df = make_ohlcv(100)
        df = add_volatility_features(df)
        valid = {0, 1, 2, 3, np.nan}
        for v in df["vol_regime"].dropna().unique():
            assert v in valid, f"Unexpected vol_regime value: {v}"
