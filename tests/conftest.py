"""
Shared test fixtures for the NQ/ES trading system test suite.
"""

import numpy as np
import pandas as pd
import pytest
import pytz

ET_TZ = pytz.timezone("America/New_York")


def make_ohlcv(n_bars: int = 200, start: str = "2024-01-02 09:30",
               freq: str = "5min") -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    idx = pd.date_range(start=start, periods=n_bars, freq=freq, tz="America/New_York")
    rng = np.random.default_rng(42)
    close = 18000 + np.cumsum(rng.normal(0, 5, n_bars))
    high = close + rng.uniform(1, 15, n_bars)
    low = close - rng.uniform(1, 15, n_bars)
    open_ = close + rng.normal(0, 3, n_bars)
    volume = rng.integers(1000, 10000, n_bars).astype(float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=idx)


@pytest.fixture
def sample_ohlcv():
    return make_ohlcv(300)


@pytest.fixture
def sample_ohlcv_multi_day():
    """Multi-day OHLCV: 3 sessions × 78 bars (09:30–16:00)."""
    dfs = []
    for day in ["2024-01-02", "2024-01-03", "2024-01-04"]:
        df = make_ohlcv(78, start=f"{day} 09:30", freq="5min")
        dfs.append(df)
    return pd.concat(dfs).sort_index()
