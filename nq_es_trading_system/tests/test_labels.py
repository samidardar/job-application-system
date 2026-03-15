"""
Triple Barrier Labeler unit tests.
"""

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv


def _make_labeled_df(n: int = 100, atr_val: float = 10.0) -> pd.DataFrame:
    """Create synthetic labeled DataFrame with constant ATR for predictable tests."""
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="5min", tz="America/New_York")
    close = np.ones(n) * 18000.0
    df = pd.DataFrame({
        "open": close,
        "high": close + atr_val * 2,
        "low": close - atr_val * 2,
        "close": close,
        "volume": np.ones(n) * 1000,
        "atr_14": np.ones(n) * atr_val,
        "macro_event_flag": np.zeros(n),
        "vol_regime": np.ones(n),  # 1 = normal
    }, index=idx)
    return df


class TestTripleBarrierLabels:
    def test_upper_barrier_hit_gives_long_label(self):
        """If price rises to upper barrier before lower, label should be +1."""
        from labels.triple_barrier import TripleBarrierLabeler

        n = 50
        close = np.ones(n) * 18000.0
        # Bar 5 onwards: price spikes to 18016 > upper barrier (18000 + 10*1.5=18015)
        close[5:] = 18016.0
        idx = pd.date_range("2024-01-02 09:30", periods=n, freq="5min", tz="America/New_York")
        df = pd.DataFrame({
            "open": close, "high": close + 5, "low": close - 3,
            "close": close, "volume": np.ones(n) * 1000,
            "atr_14": np.ones(n) * 10.0,
            "macro_event_flag": np.zeros(n),
            "vol_regime": np.ones(n),
        }, index=idx)

        labeler = TripleBarrierLabeler(atr_multiplier_tp=1.5, atr_multiplier_sl=0.75, time_bars=6)
        result = labeler.fit_transform(df, force_skip_macro=False, force_skip_extreme_vol=False)

        # Bar 0: upper=18015, price hits 18016 at bar 5 → label +1
        assert result["label"].iloc[0] == 1, f"Expected +1, got {result['label'].iloc[0]}"

    def test_lower_barrier_hit_gives_short_label(self):
        """If price drops to lower barrier first, label should be -1."""
        from labels.triple_barrier import TripleBarrierLabeler

        n = 50
        close = np.ones(n) * 18000.0
        # Price drops to 17992 at bar 3 < lower barrier (18000 - 10*0.75=17992.5)
        close[3:] = 17992.0
        idx = pd.date_range("2024-01-02 09:30", periods=n, freq="5min", tz="America/New_York")
        df = pd.DataFrame({
            "open": close, "high": close + 2, "low": close - 2,
            "close": close, "volume": np.ones(n) * 1000,
            "atr_14": np.ones(n) * 10.0,
            "macro_event_flag": np.zeros(n),
            "vol_regime": np.ones(n),
        }, index=idx)

        labeler = TripleBarrierLabeler(atr_multiplier_tp=1.5, atr_multiplier_sl=0.75, time_bars=6)
        result = labeler.fit_transform(df, force_skip_macro=False, force_skip_extreme_vol=False)

        assert result["label"].iloc[0] == -1, f"Expected -1, got {result['label'].iloc[0]}"

    def test_time_barrier_gives_skip_label(self):
        """If neither price barrier touched within time_bars, label should be 0."""
        from labels.triple_barrier import TripleBarrierLabeler

        n = 50
        # Flat price: no barriers touched, time barrier triggers
        df = _make_labeled_df(n, atr_val=100.0)  # Large ATR → price won't move enough

        labeler = TripleBarrierLabeler(atr_multiplier_tp=10.0, atr_multiplier_sl=5.0, time_bars=6)
        result = labeler.fit_transform(df, force_skip_macro=False, force_skip_extreme_vol=False)

        # All labels should be 0 (time barrier)
        non_zero = (result["label"] != 0).sum()
        assert non_zero == 0, f"Expected all 0 labels, got {non_zero} non-zero"

    def test_macro_event_forces_skip(self):
        """macro_event_flag == 1 must override label to 0."""
        from labels.triple_barrier import TripleBarrierLabeler

        n = 50
        close = np.ones(n) * 18000.0
        close[3:] = 18016.0  # Would normally be +1

        idx = pd.date_range("2024-01-02 09:30", periods=n, freq="5min", tz="America/New_York")
        df = pd.DataFrame({
            "open": close, "high": close + 5, "low": close - 3,
            "close": close, "volume": np.ones(n) * 1000,
            "atr_14": np.ones(n) * 10.0,
            "macro_event_flag": np.ones(n),  # All bars are macro events
            "vol_regime": np.ones(n),
        }, index=idx)

        labeler = TripleBarrierLabeler()
        result = labeler.fit_transform(df, force_skip_macro=True)

        assert (result["label"] == 0).all(), "Macro event should force all labels to 0"

    def test_class_weights_inverse_frequency(self):
        """Class weights must be inversely proportional to class frequency."""
        from labels.triple_barrier import TripleBarrierLabeler

        labeler = TripleBarrierLabeler()
        labels = pd.Series([1, 1, 1, 1, 0, 0, -1])  # freq: 1→4, 0→2, -1→1
        weights = labeler.get_class_weights(labels)

        # Class -1 (class_idx 0) should have highest weight (rarest)
        # Class 0 (class_idx 1) should have medium weight
        # Class 1 (class_idx 2) should have lowest weight (most common)
        assert weights[0] > weights[1] > weights[2], (
            f"Expected w[short] > w[skip] > w[long], got {weights}"
        )

    def test_label_values_in_valid_set(self):
        """All labels must be in {-1, 0, +1}."""
        from labels.triple_barrier import TripleBarrierLabeler

        df = _make_labeled_df(50)
        labeler = TripleBarrierLabeler()
        result = labeler.fit_transform(df)

        valid = {-1, 0, 1}
        unique = set(result["label"].unique())
        assert unique.issubset(valid), f"Invalid labels found: {unique - valid}"
