"""
Mean reversion feature module.

All rolling features use .shift(1) before joining labels to prevent
look-ahead bias. VWAP is computed incrementally per session, resetting
at 09:30 ET each trading day.
"""

import numpy as np
import pandas as pd


def compute_vwap(df: pd.DataFrame, session_start: str = "09:30") -> pd.Series:
    """
    Compute incremental session VWAP, resetting at session_start each day.

    VWAP at bar T = sum(typical_price * volume, bars 0..T) / sum(volume, bars 0..T)
    No look-ahead: VWAP at bar T uses only bars up to and including T (same bar).
    The VWAP value is then .shift(1) when used as a label feature (see pipeline.py).

    Args:
        df: OHLCV DataFrame with DatetimeIndex (timezone-aware ET) and
            columns ['high', 'low', 'close', 'volume']

    Returns:
        pd.Series of session VWAP values aligned to df.index
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical_price * df["volume"]

    # Group by session date (date portion of ET timestamp)
    session_date = df.index.normalize()

    cumvol = df.groupby(session_date)["volume"].cumsum()
    cumtpvol = tp_vol.groupby(session_date).cumsum()

    vwap = (cumtpvol / cumvol.replace(0, np.nan)).rename("vwap")
    return vwap


def compute_vwap_deviation(df: pd.DataFrame) -> pd.Series:
    """
    Compute VWAP deviation percentage: (close - vwap) / vwap * 100.

    Positive values: price above VWAP (potential short mean-rev).
    Negative values: price below VWAP (potential long mean-rev).

    No look-ahead: uses shift(1) on vwap before computing deviation.

    Args:
        df: DataFrame with 'close' and 'vwap' columns

    Returns:
        pd.Series of VWAP deviation (%)
    """
    vwap_prev = df["vwap"].shift(1)
    deviation = (df["close"] - vwap_prev) / vwap_prev.replace(0, np.nan) * 100
    return deviation.rename("vwap_deviation_pct")


def compute_vwap_zscore(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Compute rolling z-score of VWAP deviation.

    Z-score > +2: significantly overbought vs VWAP.
    Z-score < -2: significantly oversold vs VWAP.

    No look-ahead: uses shift(1) on vwap_deviation_pct before rolling stats.

    Args:
        df: DataFrame with 'vwap_deviation_pct' column
        window: Rolling window for z-score computation

    Returns:
        pd.Series of VWAP deviation z-scores
    """
    dev = df["vwap_deviation_pct"].shift(1)
    roll_mean = dev.rolling(window, min_periods=window // 2).mean()
    roll_std = dev.rolling(window, min_periods=window // 2).std()
    zscore = (df["vwap_deviation_pct"] - roll_mean) / roll_std.replace(0, np.nan)
    return zscore.rename("vwap_zscore")


def compute_bollinger_pct_b(
    df: pd.DataFrame, window: int = 20, std: float = 2.0
) -> pd.Series:
    """
    Compute Bollinger Band %B: position of close within the band.

    %B = (close - lower_band) / (upper_band - lower_band)
    %B = 0 → at lower band; %B = 1 → at upper band; %B = 0.5 → at SMA

    No look-ahead: uses shift(1) on close before computing rolling stats.

    Args:
        df: DataFrame with 'close' column
        window: Bollinger Band period
        std: Number of standard deviations for bands

    Returns:
        pd.Series of %B values
    """
    close_shifted = df["close"].shift(1)
    sma = close_shifted.rolling(window, min_periods=window // 2).mean()
    rolling_std = close_shifted.rolling(window, min_periods=window // 2).std()

    upper = sma + std * rolling_std
    lower = sma - std * rolling_std

    pct_b = (df["close"] - lower) / (upper - lower).replace(0, np.nan)
    return pct_b.rename("bollinger_pct_b")


def compute_zscore_returns(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Compute rolling z-score of 1-bar log returns.

    Extreme z-scores (+/-2.5) signal potential mean-reversion entries.
    No look-ahead: uses shift(1) on log_returns before rolling stats.

    Args:
        df: DataFrame with 'close' column
        window: Rolling window for z-score

    Returns:
        pd.Series of return z-scores
    """
    log_returns = np.log(df["close"] / df["close"].shift(1))
    lr_shifted = log_returns.shift(1)
    roll_mean = lr_shifted.rolling(window, min_periods=window // 2).mean()
    roll_std = lr_shifted.rolling(window, min_periods=window // 2).std()
    zscore = (log_returns - roll_mean) / roll_std.replace(0, np.nan)
    return zscore.rename("zscore_returns")


def compute_half_life_ou(df: pd.DataFrame, window: int = 60) -> pd.Series:
    """
    Estimate Ornstein-Uhlenbeck half-life using rolling OLS regression.

    Half-life = -ln(2) / lambda, where lambda is the mean-reversion speed
    estimated from: Δprice_t = lambda * price_{t-1} + epsilon

    Shorter half-life (< 20 bars) = faster mean reversion = higher signal quality.
    No look-ahead: regression uses only past bars via shift(1).

    Args:
        df: DataFrame with 'close' column
        window: Rolling window for OLS estimation

    Returns:
        pd.Series of OU half-life in bars (capped at 200)
    """
    close = df["close"]

    def _half_life(series: pd.Series) -> float:
        y = series.diff().dropna()
        x = series.shift(1).dropna()
        x = x.iloc[-len(y):]
        if len(y) < 10 or x.std() == 0:
            return np.nan
        # OLS: y = lambda * x + c
        beta = np.cov(y, x)[0, 1] / (np.var(x) + 1e-10)
        if beta >= 0:
            return np.nan  # No mean reversion
        return min(-np.log(2) / beta, 200.0)

    half_life = (
        close.shift(1)
        .rolling(window, min_periods=window // 2)
        .apply(_half_life, raw=False)
    )
    return half_life.rename("half_life_ou")


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute RSI using Wilder's smoothing method.

    RSI < 30: oversold; RSI > 70: overbought.
    No look-ahead: uses shift(1) on close differences.

    Args:
        df: DataFrame with 'close' column
        period: RSI period

    Returns:
        pd.Series of RSI values in [0, 100]
    """
    delta = df["close"].diff().shift(1)
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.rename("rsi_14")


def compute_rsi_divergence(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    """
    Detect RSI divergence: price direction vs RSI direction mismatch.

    Bullish divergence: price makes lower low, RSI makes higher low → +1
    Bearish divergence: price makes higher high, RSI makes lower high → -1
    No divergence: 0

    No look-ahead: uses shift(1) on both price and RSI before direction calc.

    Args:
        df: DataFrame with 'close' and 'rsi_14' columns
        lookback: Bars to compare for divergence detection

    Returns:
        pd.Series of {-1, 0, +1} divergence flags
    """
    price_change = df["close"].shift(1).diff(lookback).shift(1)
    rsi_change = df["rsi_14"].shift(1).diff(lookback).shift(1)

    bullish = ((price_change < 0) & (rsi_change > 0)).astype(float)
    bearish = ((price_change > 0) & (rsi_change < 0)).astype(float)

    divergence = bullish - bearish
    return divergence.rename("rsi_divergence")


def compute_mean_rev_strength(df: pd.DataFrame) -> pd.Series:
    """
    Composite mean reversion strength score.

    Score = (norm_vwap_dev + norm_bb_pct_b + norm_rsi) / 3
    Normalized so 0 = neutral, -1 = extreme oversold (long signal),
    +1 = extreme overbought (short signal).

    No look-ahead: all source columns must already be computed with shift(1).

    Args:
        df: DataFrame with 'vwap_deviation_pct', 'bollinger_pct_b', 'rsi_14'

    Returns:
        pd.Series of composite strength scores
    """
    # Normalize each to [-1, +1] range
    vwap_norm = df["vwap_deviation_pct"].clip(-5, 5) / 5
    bb_norm = (df["bollinger_pct_b"] - 0.5) * 2  # [0,1] → [-1,+1]
    rsi_norm = (df["rsi_14"] - 50) / 50           # [0,100] → [-1,+1]

    strength = (vwap_norm + bb_norm + rsi_norm) / 3
    return strength.rename("mean_rev_strength")


def add_mean_reversion_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and attach all 8 mean reversion features to df.

    Feature computation order (dependencies respected):
        1. vwap (incremental, session-reset)
        2. vwap_deviation_pct (needs vwap)
        3. vwap_zscore (needs vwap_deviation_pct)
        4. bollinger_pct_b
        5. zscore_returns
        6. half_life_ou
        7. rsi_14
        8. rsi_divergence (needs rsi_14)
        9. mean_rev_strength (needs vwap_deviation_pct, bollinger_pct_b, rsi_14)

    Args:
        df: OHLCV DataFrame with DatetimeIndex (timezone-aware ET)

    Returns:
        df with 8 new mean reversion columns (in-place copy)
    """
    df = df.copy()
    df["vwap"] = compute_vwap(df)
    df["vwap_deviation_pct"] = compute_vwap_deviation(df)
    df["vwap_zscore"] = compute_vwap_zscore(df)
    df["bollinger_pct_b"] = compute_bollinger_pct_b(df)
    df["zscore_returns"] = compute_zscore_returns(df)
    df["half_life_ou"] = compute_half_life_ou(df)
    df["rsi_14"] = compute_rsi(df)
    df["rsi_divergence"] = compute_rsi_divergence(df)
    df["mean_rev_strength"] = compute_mean_rev_strength(df)
    return df
