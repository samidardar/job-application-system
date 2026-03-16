"""
Order flow feature module.

Requires tick-level data for full accuracy. Provides graceful OHLCV fallback:
all functions return NaN-filled Series when tick data is unavailable, and the
pipeline.py layer imputes with 0 (neutral assumption) with a warning log.

No look-ahead: all per-bar aggregations are from completed bars only.
"""

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()


def _check_tick_data(df_ticks: pd.DataFrame, required_cols: list) -> bool:
    """Return True if tick data is a non-empty DataFrame with required columns."""
    if df_ticks is None or not isinstance(df_ticks, pd.DataFrame):
        return False
    if df_ticks.empty:
        return False
    return all(c in df_ticks.columns for c in required_cols)


def compute_bid_ask_imbalance(
    df_ticks: pd.DataFrame, df_bars: pd.DataFrame
) -> pd.Series:
    """
    Compute per-bar bid/ask volume imbalance aggregated from tick data.

    Imbalance = (ask_vol - bid_vol) / (ask_vol + bid_vol)
    Range: [-1, +1]. +1 = pure ask aggression (buying); -1 = pure bid aggression.

    If tick data unavailable, returns NaN-filled Series aligned to df_bars.index.

    No look-ahead: ticks are aggregated within each completed 5-min bar.
    We use the bar's open timestamp ≤ tick < bar's close timestamp.

    Args:
        df_ticks: Tick DataFrame with columns ['timestamp', 'price', 'size',
                  'side'] where side ∈ {'buy', 'sell'} or ['ask_size', 'bid_size']
        df_bars: 5-min bar DataFrame (for index alignment)

    Returns:
        pd.Series of imbalance values aligned to df_bars.index
    """
    required = ["timestamp", "size", "side"]
    if not _check_tick_data(df_ticks, required):
        logger.warning("orderflow.bid_ask_imbalance: tick data unavailable, returning NaN")
        return pd.Series(np.nan, index=df_bars.index, name="bid_ask_imbalance")

    df_ticks = df_ticks.copy()
    df_ticks["timestamp"] = pd.to_datetime(df_ticks["timestamp"])
    df_ticks = df_ticks.set_index("timestamp").sort_index()

    ask_vol = df_ticks[df_ticks["side"] == "buy"].resample("5min")["size"].sum()
    bid_vol = df_ticks[df_ticks["side"] == "sell"].resample("5min")["size"].sum()

    total = ask_vol + bid_vol
    imbalance = (ask_vol - bid_vol) / total.replace(0, np.nan)
    imbalance = imbalance.reindex(df_bars.index, method="nearest", tolerance="5min")
    imbalance.index = df_bars.index
    return imbalance.rename("bid_ask_imbalance")


def compute_stacked_imbalances(
    df_ticks: pd.DataFrame,
    df_bars: pd.DataFrame,
    threshold: float = 0.3,
    min_stack: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """
    Detect stacked bid/ask imbalances across consecutive price levels.

    Stacked bullish imbalance: min_stack or more consecutive bars with
    imbalance > threshold → +1 flag.
    Stacked bearish: imbalance < -threshold for min_stack bars → +1 flag.

    If tick data unavailable, returns NaN-filled Series.

    Args:
        df_ticks: Tick DataFrame
        df_bars: 5-min bar DataFrame (for index alignment)
        threshold: Minimum imbalance magnitude to count as directional
        min_stack: Minimum consecutive bars to qualify as "stacked"

    Returns:
        Tuple of (stacked_bull_flag, stacked_bear_flag) as pd.Series
    """
    if not _check_tick_data(df_ticks, ["timestamp", "size", "side"]):
        logger.warning("orderflow.stacked_imbalances: tick data unavailable, returning NaN")
        nan_series = pd.Series(np.nan, index=df_bars.index)
        return nan_series.rename("stacked_imbalance_bull"), nan_series.rename("stacked_imbalance_bear")

    imbalance = compute_bid_ask_imbalance(df_ticks, df_bars)

    bull_flag = imbalance > threshold
    bear_flag = imbalance < -threshold

    def _rolling_stack(series: pd.Series, n: int) -> pd.Series:
        result = series.rolling(n, min_periods=n).apply(
            lambda x: 1.0 if x.all() else 0.0, raw=True
        )
        return result

    stacked_bull = _rolling_stack(bull_flag, min_stack).rename("stacked_imbalance_bull")
    stacked_bear = _rolling_stack(bear_flag, min_stack).rename("stacked_imbalance_bear")
    return stacked_bull, stacked_bear


def compute_delta_per_bar(
    df_ticks: pd.DataFrame, df_bars: pd.DataFrame
) -> pd.Series:
    """
    Compute net volume delta per 5-minute bar from tick data.

    Delta = ask_volume - bid_volume per bar.
    Positive delta = net buying; Negative = net selling.

    If tick data unavailable, returns NaN-filled Series.

    Args:
        df_ticks: Tick DataFrame
        df_bars: 5-min bar DataFrame

    Returns:
        pd.Series of per-bar delta values
    """
    required = ["timestamp", "size", "side"]
    if not _check_tick_data(df_ticks, required):
        logger.warning("orderflow.delta_per_bar: tick data unavailable, returning NaN")
        return pd.Series(np.nan, index=df_bars.index, name="delta_per_bar")

    df_ticks = df_ticks.copy()
    df_ticks["timestamp"] = pd.to_datetime(df_ticks["timestamp"])
    df_ticks = df_ticks.set_index("timestamp").sort_index()

    df_ticks["signed_size"] = np.where(
        df_ticks["side"] == "buy", df_ticks["size"], -df_ticks["size"]
    )
    delta = df_ticks["signed_size"].resample("5min").sum()
    delta = delta.reindex(df_bars.index, method="nearest", tolerance="5min")
    delta.index = df_bars.index
    return delta.rename("delta_per_bar")


def compute_delta_divergence(df: pd.DataFrame, lookback: int = 3) -> pd.Series:
    """
    Detect delta divergence: price direction vs net delta direction mismatch.

    Bullish: price falling but delta rising (hidden accumulation) → +1
    Bearish: price rising but delta falling (hidden distribution) → -1
    No divergence: 0

    Uses already-computed delta_per_bar (NaN if ticks unavailable).
    No look-ahead: uses shift(1) on both price and delta.

    Args:
        df: DataFrame with 'close' and 'delta_per_bar' columns
        lookback: Bars to compare for divergence

    Returns:
        pd.Series of {-1, 0, +1} divergence flags
    """
    if df["delta_per_bar"].isna().all():
        return pd.Series(np.nan, index=df.index, name="delta_divergence")

    price_change = df["close"].shift(1).diff(lookback).shift(1)
    delta_change = df["delta_per_bar"].shift(1).diff(lookback).shift(1)

    bullish = ((price_change < 0) & (delta_change > 0)).astype(float)
    bearish = ((price_change > 0) & (delta_change < 0)).astype(float)

    return (bullish - bearish).rename("delta_divergence")


def compute_absorption_score(
    df_ticks: pd.DataFrame, df_bars: pd.DataFrame
) -> pd.Series:
    """
    Estimate iceberg/absorption: large volume at a price with minimal movement.

    Heuristic: high total bar volume AND small bar range (high - low) / ATR → likely absorption.
    Score = volume / (bar_range + 1e-6), normalized to [0, 1] rolling 20-bar percentile.

    If tick data unavailable, uses OHLCV fallback (less precise but non-crashing).

    Args:
        df_ticks: Tick DataFrame (optional for precision)
        df_bars: 5-min bar DataFrame with 'high', 'low', 'volume', 'atr_14'

    Returns:
        pd.Series of absorption score [0, 1] aligned to df_bars.index
    """
    bar_range = (df_bars["high"] - df_bars["low"]).replace(0, np.nan)
    atr = df_bars.get("atr_14", bar_range.rolling(14).mean())

    raw_score = df_bars["volume"] / (bar_range / atr.replace(0, np.nan) + 1e-6)

    # Normalize to percentile rank over rolling 20 bars (shift to avoid leakage)
    score = raw_score.shift(1).rolling(20, min_periods=10).rank(pct=True)
    return score.rename("absorption_score")


def compute_footprint_poc(
    df_ticks: pd.DataFrame, df_bars: pd.DataFrame
) -> pd.Series:
    """
    Estimate distance from current price to bar's Point of Control (POC).

    POC = price level with highest traded volume within the bar.
    Uses tick data for precision; falls back to VWAP proxy if unavailable.

    No look-ahead: POC is computed from the completed bar (T-1) and
    compared against close at T.

    Args:
        df_ticks: Tick DataFrame with ['timestamp', 'price', 'size']
        df_bars: 5-min bar DataFrame with 'close'

    Returns:
        pd.Series of (close - POC) / ATR distance, shifted to T-1
    """
    required = ["timestamp", "price", "size"]
    if not _check_tick_data(df_ticks, required):
        logger.warning("orderflow.footprint_poc: tick data unavailable, using VWAP proxy")
        # Fallback: use VWAP as POC proxy
        poc = df_bars.get("vwap", (df_bars["high"] + df_bars["low"] + df_bars["close"]) / 3)
        atr = df_bars.get("atr_14", (df_bars["high"] - df_bars["low"]).rolling(14).mean())
        dist = (df_bars["close"].shift(1) - poc.shift(1)) / atr.replace(0, np.nan)
        return dist.rename("footprint_poc_dist")

    df_ticks = df_ticks.copy()
    df_ticks["timestamp"] = pd.to_datetime(df_ticks["timestamp"])
    df_ticks = df_ticks.set_index("timestamp").sort_index()

    # Round price to tick grid (use 0.25 grid for NQ/ES)
    df_ticks["price_rounded"] = (df_ticks["price"] / 0.25).round() * 0.25

    poc_series = {}
    for bar_ts in df_bars.index:
        bar_end = bar_ts
        bar_start = bar_ts - pd.Timedelta(minutes=5)
        bar_ticks = df_ticks.loc[bar_start:bar_end]
        if bar_ticks.empty:
            poc_series[bar_ts] = np.nan
        else:
            poc = bar_ticks.groupby("price_rounded")["size"].sum().idxmax()
            poc_series[bar_ts] = poc

    poc_s = pd.Series(poc_series, name="poc")
    atr = df_bars.get("atr_14", (df_bars["high"] - df_bars["low"]).rolling(14).mean())
    dist = (df_bars["close"] - poc_s.shift(1)) / atr.replace(0, np.nan)
    return dist.rename("footprint_poc_dist")


def add_orderflow_features(
    df_bars: pd.DataFrame, df_ticks: pd.DataFrame = None
) -> pd.DataFrame:
    """
    Compute and attach all 7 order flow features to df_bars.

    Gracefully handles missing tick data: returns NaN for tick-based features.
    The pipeline.py layer will impute NaN with 0 (neutral assumption).

    Feature computation order:
        1. bid_ask_imbalance
        2. stacked_imbalance_bull / stacked_imbalance_bear
        3. delta_per_bar
        4. delta_divergence (needs delta_per_bar)
        5. absorption_score
        6. footprint_poc_dist

    Args:
        df_bars: OHLCV DataFrame (must have atr_14 from volatility module)
        df_ticks: Tick DataFrame (optional)

    Returns:
        df with 7 new order flow columns (in-place copy)
    """
    df = df_bars.copy()

    df["bid_ask_imbalance"] = compute_bid_ask_imbalance(df_ticks, df)
    bull, bear = compute_stacked_imbalances(df_ticks, df)
    df["stacked_imbalance_bull"] = bull
    df["stacked_imbalance_bear"] = bear
    df["delta_per_bar"] = compute_delta_per_bar(df_ticks, df)
    df["delta_divergence"] = compute_delta_divergence(df)
    df["absorption_score"] = compute_absorption_score(df_ticks, df)
    df["footprint_poc_dist"] = compute_footprint_poc(df_ticks, df)

    return df
