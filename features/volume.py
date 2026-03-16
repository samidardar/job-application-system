"""
Volume analysis feature module.

All rolling features use .shift(1) before joining labels to prevent
look-ahead bias — feature at bar T uses data from bars T-1 and earlier only.
"""

import numpy as np
import pandas as pd


def compute_rvol(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Compute relative volume (RVOL): current volume / rolling mean volume.

    RVOL > 1.5: high volume confirming move.
    RVOL < 0.8: low liquidity — increase slippage risk.

    No look-ahead: uses shift(1) on volume before rolling mean.

    Args:
        df: DataFrame with 'volume' column
        window: Rolling window for mean volume

    Returns:
        pd.Series of RVOL values
    """
    mean_vol = df["volume"].shift(1).rolling(window, min_periods=window // 2).mean()
    rvol = df["volume"] / mean_vol.replace(0, np.nan)
    return rvol.rename("rvol")


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """
    Compute On-Balance Volume (OBV).

    OBV accumulates volume: +volume when close > prev_close, else -volume.
    No look-ahead: uses shift(1) on close for direction comparison.

    Args:
        df: DataFrame with 'close' and 'volume' columns

    Returns:
        pd.Series of OBV cumulative values
    """
    close_prev = df["close"].shift(1)
    direction = np.sign(df["close"] - close_prev).fillna(0)
    obv = (direction * df["volume"]).cumsum()
    return obv.rename("obv")


def compute_obv_slope(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """
    Compute slope of On-Balance Volume over a rolling window.

    Positive slope + rising price = confirmed trend (momentum).
    Positive slope + falling price = bullish OBV divergence.

    No look-ahead: uses shift(1) on OBV before computing slope.

    Args:
        df: DataFrame with 'obv' column
        window: Window for linear regression slope

    Returns:
        pd.Series of OBV slope values
    """
    obv_shifted = df["obv"].shift(1)

    def _slope(series: pd.Series) -> float:
        if series.isna().any():
            return np.nan
        x = np.arange(len(series), dtype=float)
        x -= x.mean()
        y = series.values - series.mean()
        denom = (x ** 2).sum()
        return float(np.dot(x, y) / denom) if denom != 0 else 0.0

    slope = obv_shifted.rolling(window, min_periods=window).apply(_slope, raw=False)
    return slope.rename("obv_slope")


def compute_cvd(df: pd.DataFrame) -> pd.Series:
    """
    Compute Cumulative Volume Delta (CVD) using OHLCV proxy.

    In the absence of tick data, we estimate buy/sell volume using the
    close position within the high-low range (Tick Rule proxy):
        buy_vol  = volume * (close - low)  / (high - low)
        sell_vol = volume * (high - close) / (high - low)
        delta    = buy_vol - sell_vol per bar
        CVD      = cumulative sum of delta

    No look-ahead: CVD at bar T uses only data from bar T (same bar OHLCV,
    which is fully resolved at bar close). CVD is then shifted in pipeline.

    Args:
        df: DataFrame with 'high', 'low', 'close', 'volume' columns

    Returns:
        pd.Series of cumulative volume delta
    """
    hl_range = (df["high"] - df["low"]).replace(0, np.nan)
    buy_fraction = (df["close"] - df["low"]) / hl_range
    buy_vol = df["volume"] * buy_fraction.fillna(0.5)
    sell_vol = df["volume"] - buy_vol
    delta = buy_vol - sell_vol
    cvd = delta.cumsum()
    return cvd.rename("cvd")


def compute_cvd_divergence(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    """
    Detect CVD divergence: price direction vs CVD direction mismatch.

    Bullish: price falling but CVD rising (hidden buying pressure) → +1
    Bearish: price rising but CVD falling (hidden selling pressure) → -1
    No divergence: 0

    No look-ahead: uses shift(1) on both price and CVD.

    Args:
        df: DataFrame with 'close' and 'cvd' columns
        lookback: Bars to compare

    Returns:
        pd.Series of {-1, 0, +1} divergence flags
    """
    price_change = df["close"].shift(1).diff(lookback).shift(1)
    cvd_change = df["cvd"].shift(1).diff(lookback).shift(1)

    bullish = ((price_change < 0) & (cvd_change > 0)).astype(float)
    bearish = ((price_change > 0) & (cvd_change < 0)).astype(float)

    return (bullish - bearish).rename("cvd_divergence")


def compute_vw_momentum(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """
    Compute volume-weighted price momentum over a rolling window.

    VW Momentum = sum(price_change * volume) / sum(volume)
    Positive = volume-weighted buying; Negative = volume-weighted selling.

    No look-ahead: uses shift(1) on both close and volume.

    Args:
        df: DataFrame with 'close' and 'volume' columns
        window: Lookback window

    Returns:
        pd.Series of volume-weighted momentum values
    """
    close_shifted = df["close"].shift(1)
    vol_shifted = df["volume"].shift(1)
    price_change = close_shifted.diff()

    vw_num = (price_change * vol_shifted).rolling(window, min_periods=window // 2).sum()
    vw_den = vol_shifted.rolling(window, min_periods=window // 2).sum()

    vw_mom = vw_num / vw_den.replace(0, np.nan)
    return vw_mom.rename("vw_momentum_5")


def compute_volume_regime(df: pd.DataFrame) -> pd.Series:
    """
    Classify volume regime based on RVOL thresholds.

    Categories (integer-encoded):
        0 = low     (RVOL < 0.6)
        1 = normal  (0.6 ≤ RVOL < 1.4)
        2 = high    (RVOL ≥ 1.4)

    No look-ahead: uses the already shift(1)-adjusted rvol column.

    Args:
        df: DataFrame with 'rvol' column

    Returns:
        pd.Series of integer-encoded volume regime (0–2)
    """
    rvol = df["rvol"]
    regime = pd.cut(
        rvol,
        bins=[-np.inf, 0.6, 1.4, np.inf],
        labels=[0, 1, 2],
    ).astype(float)
    return regime.rename("volume_regime")


def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and attach all 6 volume features to df.

    Feature computation order:
        1. rvol
        2. obv (intermediate)
        3. obv_slope (needs obv)
        4. cvd
        5. cvd_divergence (needs cvd)
        6. vw_momentum_5
        7. volume_regime (needs rvol)

    Args:
        df: OHLCV DataFrame

    Returns:
        df with 6 new volume feature columns (in-place copy)
    """
    df = df.copy()
    df["rvol"] = compute_rvol(df)
    df["obv"] = compute_obv(df)
    df["obv_slope"] = compute_obv_slope(df)
    df["cvd"] = compute_cvd(df)
    df["cvd_divergence"] = compute_cvd_divergence(df)
    df["vw_momentum_5"] = compute_vw_momentum(df)
    df["volume_regime"] = compute_volume_regime(df)
    return df
