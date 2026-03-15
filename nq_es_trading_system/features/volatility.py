"""
Volatility feature module.

All rolling features use .shift(1) before joining labels to prevent
look-ahead bias — feature at bar T uses data from bars T-1 and earlier only.
"""

import numpy as np
import pandas as pd


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR).

    Uses .shift(1) on close to ensure the previous close is from bar T-1
    when computing ATR at bar T. Returns series aligned to df.index.

    Args:
        df: OHLCV DataFrame with columns ['high', 'low', 'close']
        period: ATR smoothing period

    Returns:
        pd.Series of ATR values (NaN for first `period` bars)
    """
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)

    tr = pd.concat(
        [high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return atr.rename("atr_14")


def compute_atr_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Compute ATR ratio: current ATR / rolling mean ATR.

    Values > 1 indicate expanding volatility (momentum regime).
    Values < 0.8 suggest compression (mean reversion opportunity).

    No look-ahead: uses shift(1) before rolling mean.

    Args:
        df: DataFrame with 'atr_14' column
        window: Rolling window for mean ATR

    Returns:
        pd.Series of ATR ratio values
    """
    atr = df["atr_14"]
    rolling_mean = atr.shift(1).rolling(window, min_periods=window // 2).mean()
    ratio = atr / rolling_mean.replace(0, np.nan)
    return ratio.rename("atr_ratio")


def compute_realized_vol(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Compute annualized realized volatility from log returns.

    Uses shift(1) on log returns so feature at T is computed from returns
    ending at T-1 (no current bar contamination).

    Args:
        df: OHLCV DataFrame with 'close' column
        window: Lookback window in bars (5-min bars → 20 bars = 100 min)

    Returns:
        pd.Series of annualized realized volatility
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    # shift(1): at bar T, rolling std uses returns up to T-1
    realized = (
        log_returns.shift(1)
        .rolling(window, min_periods=window // 2)
        .std()
        * np.sqrt(252 * 78)  # 78 five-minute bars per trading day
    )
    return realized.rename("realized_vol_20")


def compute_vol_of_vol(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    Compute volatility of realized volatility (vol-of-vol).

    Higher values indicate unstable volatility regime — reduce position sizing.
    No look-ahead: uses shift(1) before rolling std.

    Args:
        df: DataFrame with 'realized_vol_20' column
        window: Lookback window for vol-of-vol

    Returns:
        pd.Series of vol-of-vol values
    """
    rv = df["realized_vol_20"].shift(1)
    vov = rv.rolling(window, min_periods=window // 2).std()
    return vov.rename("vol_of_vol")


def compute_vix_aligned(
    df_vix: pd.DataFrame, df_bars: pd.DataFrame
) -> pd.Series:
    """
    Align daily VIX close to 5-minute bar timestamps.

    Each bar gets the VIX close from the PREVIOUS trading day to avoid
    same-day lookahead (VIX daily close occurs after market close).

    Args:
        df_vix: Daily VIX DataFrame with DatetimeIndex and 'close' column
        df_bars: 5-min bar DataFrame with DatetimeIndex (timezone-aware ET)

    Returns:
        pd.Series of VIX values aligned to df_bars.index
    """
    # Extract session date from bar timestamps
    bar_dates = df_bars.index.normalize().tz_localize(None)

    # Shift VIX by 1 day: bar on 2024-01-10 gets VIX from 2024-01-09
    vix_shifted = df_vix["close"].shift(1)
    vix_shifted.index = pd.to_datetime(vix_shifted.index).normalize()

    # Reindex to bar dates (forward-fill for weekends/holidays)
    aligned = vix_shifted.reindex(bar_dates, method="ffill")
    aligned.index = df_bars.index
    return aligned.rename("vix_daily")


def compute_vol_regime(df: pd.DataFrame) -> pd.Series:
    """
    Classify volatility regime into 4 categories.

    Uses ATR ratio and realized vol thresholds. No look-ahead:
    all source columns must already be shift(1)-adjusted.

    Categories:
        0 = low      (ATR ratio < 0.7)
        1 = normal   (0.7 ≤ ATR ratio < 1.3)
        2 = high     (1.3 ≤ ATR ratio < 1.8)
        3 = extreme  (ATR ratio ≥ 1.8)

    Args:
        df: DataFrame with 'atr_ratio' column

    Returns:
        pd.Series of integer-encoded regime (0–3)
    """
    atr_ratio = df["atr_ratio"]
    regime = pd.cut(
        atr_ratio,
        bins=[-np.inf, 0.7, 1.3, 1.8, np.inf],
        labels=[0, 1, 2, 3],
    ).astype(float)
    return regime.rename("vol_regime")


def add_volatility_features(df: pd.DataFrame, df_vix: pd.DataFrame = None) -> pd.DataFrame:
    """
    Compute and attach all 6 volatility features to df.

    Feature computation order (dependencies respected):
        1. atr_14
        2. atr_ratio (needs atr_14)
        3. realized_vol_20
        4. vol_of_vol (needs realized_vol_20)
        5. vix_daily (needs df_vix, optional)
        6. vol_regime (needs atr_ratio)

    Args:
        df: OHLCV DataFrame
        df_vix: Daily VIX DataFrame (optional; fills NaN if not provided)

    Returns:
        df with 6 new volatility columns appended (in-place copy)
    """
    df = df.copy()
    df["atr_14"] = compute_atr(df)
    df["atr_ratio"] = compute_atr_ratio(df)
    df["realized_vol_20"] = compute_realized_vol(df)
    df["vol_of_vol"] = compute_vol_of_vol(df)

    if df_vix is not None:
        df["vix_daily"] = compute_vix_aligned(df_vix, df)
    else:
        df["vix_daily"] = np.nan

    df["vol_regime"] = compute_vol_regime(df)
    return df
