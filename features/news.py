"""
News and macro feature module.

FinBERT sentiment is computed offline and cached to parquet. This prevents:
1. API rate limit issues during training
2. Lookahead (news articles are aligned by publish_time, not event_time)
3. GPU memory conflicts with main training loop

All news features use strict lookback windows (no future articles).
"""

import os
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()

# Hardcoded major macro event dates (FOMC, CPI, NFP) — extend as needed
# Format: list of (date_string, event_name, blackout_minutes_pre, blackout_minutes_post)
_MACRO_EVENTS_2022_2025 = [
    # FOMC dates (approximate — update with actual release times)
    ("2022-01-26 14:00", "FOMC", 120, 60),
    ("2022-03-16 14:00", "FOMC", 120, 60),
    ("2022-05-04 14:00", "FOMC", 120, 60),
    ("2022-06-15 14:00", "FOMC", 120, 60),
    ("2022-07-27 14:00", "FOMC", 120, 60),
    ("2022-09-21 14:00", "FOMC", 120, 60),
    ("2022-11-02 14:00", "FOMC", 120, 60),
    ("2022-12-14 14:00", "FOMC", 120, 60),
    ("2023-02-01 14:00", "FOMC", 120, 60),
    ("2023-03-22 14:00", "FOMC", 120, 60),
    ("2023-05-03 14:00", "FOMC", 120, 60),
    ("2023-06-14 14:00", "FOMC", 120, 60),
    ("2023-07-26 14:00", "FOMC", 120, 60),
    ("2023-09-20 14:00", "FOMC", 120, 60),
    ("2023-11-01 14:00", "FOMC", 120, 60),
    ("2023-12-13 14:00", "FOMC", 120, 60),
    ("2024-01-31 14:00", "FOMC", 120, 60),
    ("2024-03-20 14:00", "FOMC", 120, 60),
    ("2024-05-01 14:00", "FOMC", 120, 60),
    ("2024-06-12 14:00", "FOMC", 120, 60),
    ("2024-07-31 14:00", "FOMC", 120, 60),
    ("2024-09-18 14:00", "FOMC", 120, 60),
    ("2024-11-07 14:00", "FOMC", 120, 60),
    ("2024-12-18 14:00", "FOMC", 120, 60),
    # CPI (typically 08:30 ET)
    ("2022-02-10 08:30", "CPI", 30, 30),
    ("2022-03-10 08:30", "CPI", 30, 30),
    ("2022-04-12 08:30", "CPI", 30, 30),
    ("2022-05-11 08:30", "CPI", 30, 30),
    ("2022-06-10 08:30", "CPI", 30, 30),
    ("2022-07-13 08:30", "CPI", 30, 30),
    ("2022-08-10 08:30", "CPI", 30, 30),
    ("2022-09-13 08:30", "CPI", 30, 30),
    ("2022-10-13 08:30", "CPI", 30, 30),
    ("2022-11-10 08:30", "CPI", 30, 30),
    ("2022-12-13 08:30", "CPI", 30, 30),
    ("2023-01-12 08:30", "CPI", 30, 30),
    ("2023-02-14 08:30", "CPI", 30, 30),
    ("2023-03-14 08:30", "CPI", 30, 30),
    ("2023-04-12 08:30", "CPI", 30, 30),
    ("2023-05-10 08:30", "CPI", 30, 30),
    ("2023-06-13 08:30", "CPI", 30, 30),
    ("2023-07-12 08:30", "CPI", 30, 30),
    ("2023-08-10 08:30", "CPI", 30, 30),
    ("2023-09-13 08:30", "CPI", 30, 30),
    ("2023-10-12 08:30", "CPI", 30, 30),
    ("2023-11-14 08:30", "CPI", 30, 30),
    ("2023-12-12 08:30", "CPI", 30, 30),
    ("2024-01-11 08:30", "CPI", 30, 30),
    ("2024-02-13 08:30", "CPI", 30, 30),
    ("2024-03-12 08:30", "CPI", 30, 30),
    ("2024-04-10 08:30", "CPI", 30, 30),
    ("2024-05-15 08:30", "CPI", 30, 30),
    ("2024-06-12 08:30", "CPI", 30, 30),
    ("2024-07-11 08:30", "CPI", 30, 30),
    ("2024-08-14 08:30", "CPI", 30, 30),
    ("2024-09-11 08:30", "CPI", 30, 30),
    ("2024-10-10 08:30", "CPI", 30, 30),
    ("2024-11-13 08:30", "CPI", 30, 30),
    ("2024-12-11 08:30", "CPI", 30, 30),
    # NFP (first Friday of each month, 08:30 ET)
    ("2022-02-04 08:30", "NFP", 30, 30),
    ("2022-03-04 08:30", "NFP", 30, 30),
    ("2022-04-01 08:30", "NFP", 30, 30),
    ("2022-05-06 08:30", "NFP", 30, 30),
    ("2022-06-03 08:30", "NFP", 30, 30),
    ("2022-07-08 08:30", "NFP", 30, 30),
    ("2022-08-05 08:30", "NFP", 30, 30),
    ("2022-09-02 08:30", "NFP", 30, 30),
    ("2022-10-07 08:30", "NFP", 30, 30),
    ("2022-11-04 08:30", "NFP", 30, 30),
    ("2022-12-02 08:30", "NFP", 30, 30),
    ("2023-01-06 08:30", "NFP", 30, 30),
    ("2023-02-03 08:30", "NFP", 30, 30),
    ("2023-03-10 08:30", "NFP", 30, 30),
    ("2023-04-07 08:30", "NFP", 30, 30),
    ("2023-05-05 08:30", "NFP", 30, 30),
    ("2023-06-02 08:30", "NFP", 30, 30),
    ("2023-07-07 08:30", "NFP", 30, 30),
    ("2023-08-04 08:30", "NFP", 30, 30),
    ("2023-09-01 08:30", "NFP", 30, 30),
    ("2023-10-06 08:30", "NFP", 30, 30),
    ("2023-11-03 08:30", "NFP", 30, 30),
    ("2023-12-08 08:30", "NFP", 30, 30),
    ("2024-01-05 08:30", "NFP", 30, 30),
    ("2024-02-02 08:30", "NFP", 30, 30),
    ("2024-03-08 08:30", "NFP", 30, 30),
    ("2024-04-05 08:30", "NFP", 30, 30),
    ("2024-05-03 08:30", "NFP", 30, 30),
    ("2024-06-07 08:30", "NFP", 30, 30),
    ("2024-07-05 08:30", "NFP", 30, 30),
    ("2024-08-02 08:30", "NFP", 30, 30),
    ("2024-09-06 08:30", "NFP", 30, 30),
    ("2024-10-04 08:30", "NFP", 30, 30),
    ("2024-11-01 08:30", "NFP", 30, 30),
    ("2024-12-06 08:30", "NFP", 30, 30),
]


def fetch_alpaca_news(
    symbol: str, start: str, end: str, api_key: str = None, api_secret: str = None
) -> pd.DataFrame:
    """
    Fetch news articles from Alpaca Markets API.

    Returns DataFrame with columns: ['published_at', 'headline', 'summary', 'symbols']
    Uses article publish_time (NOT release_time) to avoid Bloomberg-style delays.

    Args:
        symbol: Ticker symbol (e.g., 'SPY' for ES proxy)
        start: Start date string (ISO format)
        end: End date string (ISO format)
        api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
        api_secret: Alpaca secret key (defaults to ALPACA_SECRET_KEY env var)

    Returns:
        pd.DataFrame of news articles sorted by published_at ascending
    """
    api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
    api_secret = api_secret or os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        logger.warning("news.fetch_alpaca_news: no API keys found, returning empty DataFrame")
        return pd.DataFrame(columns=["published_at", "headline", "summary", "symbols"])

    try:
        from alpaca.data.historical import NewsClient
        from alpaca.data.requests import NewsRequest

        client = NewsClient(api_key=api_key, secret_key=api_secret)
        request = NewsRequest(symbols=[symbol], start=start, end=end, limit=10000)
        news_response = client.get_news(request)

        articles = []
        for article in news_response.news:
            articles.append(
                {
                    "published_at": article.created_at,
                    "headline": article.headline or "",
                    "summary": article.summary or "",
                    "symbols": article.symbols or [],
                }
            )
        df = pd.DataFrame(articles)
        df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
        return df.sort_values("published_at").reset_index(drop=True)

    except Exception as e:
        logger.error(f"news.fetch_alpaca_news: failed with {e}")
        return pd.DataFrame(columns=["published_at", "headline", "summary", "symbols"])


def compute_finbert_sentiment(
    texts: list,
    model_name: str = "ProsusAI/finbert",
    batch_size: int = 16,
    device: str = "cpu",
    dtype: str = "float32",
    cache_path: Path = None,
) -> list:
    """
    Compute FinBERT sentiment scores for a list of texts.

    Returns scores in [-1, +1]:
        positive → +1, negative → -1, neutral → 0, weighted by confidence.

    Runs on CPU for GTX 1650 (4GB VRAM insufficient for FinBERT + training).
    Results are cached to `cache_path` if provided (parquet format).

    No look-ahead risk: this is called on historical article texts only,
    never on future data. Caching ensures reproducibility.

    Args:
        texts: List of strings (headlines + summaries)
        model_name: HuggingFace model ID
        batch_size: Inference batch size (16 on CPU — FinBERT is ~420MB)
        device: 'cpu' for GTX 1650 (leave GPU VRAM free for signal model)
        dtype: 'float32' for CPU inference
        cache_path: Path to parquet cache file (skip if already exists)

    Returns:
        List of float sentiment scores [-1, +1]
    """
    if cache_path and Path(cache_path).exists():
        cached = pd.read_parquet(cache_path)
        return cached["sentiment"].tolist()

    try:
        import torch
        from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

        # GTX 1650: always use CPU for FinBERT to keep 4GB VRAM free for training
        use_device = "cpu"
        torch_dtype = torch.float32

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name, torch_dtype=torch_dtype
        ).to(use_device)
        model.eval()

        label_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
        scores = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Truncate to 512 tokens
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(use_device)

            with torch.no_grad():
                # CPU inference — no autocast needed
                outputs = model(**encoded)

            probs = torch.softmax(outputs.logits.float(), dim=-1).cpu().numpy()
            labels = model.config.id2label

            for prob_row in probs:
                # Weighted sentiment: positive_prob - negative_prob
                pos = prob_row[_get_label_idx(labels, "positive")]
                neg = prob_row[_get_label_idx(labels, "negative")]
                scores.append(float(pos - neg))

        if cache_path:
            pd.DataFrame({"sentiment": scores}).to_parquet(cache_path, index=False)

        return scores

    except Exception as e:
        logger.error(f"news.compute_finbert_sentiment: failed with {e}, returning zeros")
        return [0.0] * len(texts)


def _get_label_idx(id2label: dict, target: str) -> int:
    """Find index of target label in id2label mapping."""
    for idx, label in id2label.items():
        if label.lower() == target.lower():
            return idx
    return 0


def compute_news_sentiment_score(
    df_news: pd.DataFrame, df_bars: pd.DataFrame, window_min: int = 60
) -> pd.Series:
    """
    Compute rolling 60-minute sentiment score aligned to 5-minute bars.

    For each bar T, the sentiment score = mean FinBERT score of all articles
    published in the window [T - window_min, T) — strictly no lookahead.

    If no news in window: returns 0.0 (neutral).

    Args:
        df_news: DataFrame with 'published_at' (UTC tz-aware) and 'sentiment' columns
        df_bars: 5-min bar DataFrame with DatetimeIndex (UTC or ET tz-aware)
        window_min: Lookback window in minutes (default 60)

    Returns:
        pd.Series of rolling sentiment scores aligned to df_bars.index
    """
    if df_news is None or df_news.empty or "sentiment" not in df_news.columns:
        return pd.Series(0.0, index=df_bars.index, name="news_sentiment_score")

    df_news = df_news.copy()
    df_news["published_at"] = pd.to_datetime(df_news["published_at"], utc=True)
    df_news = df_news.set_index("published_at").sort_index()

    # Ensure bars are UTC
    bar_index = df_bars.index.tz_convert("UTC") if df_bars.index.tzinfo else df_bars.index

    scores = []
    window = pd.Timedelta(minutes=window_min)

    for bar_ts in bar_index:
        window_news = df_news.loc[bar_ts - window : bar_ts - pd.Timedelta(seconds=1)]
        if window_news.empty:
            scores.append(0.0)
        else:
            scores.append(float(window_news["sentiment"].mean()))

    return pd.Series(scores, index=df_bars.index, name="news_sentiment_score")


def compute_news_event_flag(
    df_bars: pd.DataFrame,
    df_news: pd.DataFrame,
    lookahead_min: int = 60,
    min_articles: int = 3,
) -> pd.Series:
    """
    Binary flag: 1 if unusually high news volume in next `lookahead_min` minutes.

    NOTE: This uses FORWARD-looking window intentionally — it models the
    market's uncertainty about upcoming events. The flag is used only as a
    FILTER (forces skip label), not as a directional predictor.
    The model does NOT use this as an input feature for directional prediction.

    "High-impact" = more than `min_articles` articles in the forward window.

    Args:
        df_bars: 5-min bar DataFrame
        df_news: DataFrame with 'published_at' column
        lookahead_min: Forward window for event detection
        min_articles: Threshold for "high-impact" event

    Returns:
        pd.Series of binary flags (0/1)
    """
    if df_news is None or df_news.empty:
        return pd.Series(0, index=df_bars.index, name="news_event_flag")

    df_news = df_news.copy()
    df_news["published_at"] = pd.to_datetime(df_news["published_at"], utc=True)
    news_times = df_news["published_at"].sort_values()

    bar_index = df_bars.index.tz_convert("UTC") if df_bars.index.tzinfo else df_bars.index
    window = pd.Timedelta(minutes=lookahead_min)

    flags = []
    for bar_ts in bar_index:
        count = ((news_times >= bar_ts) & (news_times < bar_ts + window)).sum()
        flags.append(1 if count >= min_articles else 0)

    return pd.Series(flags, index=df_bars.index, name="news_event_flag")


def compute_news_count_1h(
    df_bars: pd.DataFrame, df_news: pd.DataFrame
) -> pd.Series:
    """
    Count news articles published in the trailing 60 minutes for each bar.

    No look-ahead: counts articles in [T - 60min, T).

    Args:
        df_bars: 5-min bar DataFrame
        df_news: DataFrame with 'published_at' column

    Returns:
        pd.Series of article counts
    """
    if df_news is None or df_news.empty:
        return pd.Series(0, index=df_bars.index, name="news_count_1h")

    df_news = df_news.copy()
    df_news["published_at"] = pd.to_datetime(df_news["published_at"], utc=True)
    news_times = df_news["published_at"].sort_values()

    bar_index = df_bars.index.tz_convert("UTC") if df_bars.index.tzinfo else df_bars.index
    window = pd.Timedelta(hours=1)

    counts = []
    for bar_ts in bar_index:
        count = ((news_times >= bar_ts - window) & (news_times < bar_ts)).sum()
        counts.append(int(count))

    return pd.Series(counts, index=df_bars.index, name="news_count_1h")


def compute_macro_event_flag(df_bars: pd.DataFrame) -> pd.Series:
    """
    Binary flag: 1 if bar is within macro event blackout window (FOMC/CPI/NFP).

    Blackout window per event type:
        FOMC: 120 min before, 60 min after
        CPI:  30 min before, 30 min after
        NFP:  30 min before, 30 min after

    Hardcoded from _MACRO_EVENTS_2022_2025. Update annually.

    Args:
        df_bars: 5-min bar DataFrame with DatetimeIndex (ET or UTC tz-aware)

    Returns:
        pd.Series of binary flags (0/1)
    """
    import pytz
    et_tz = pytz.timezone("America/New_York")

    # Parse macro event times to UTC
    events = []
    for dt_str, name, pre_min, post_min in _MACRO_EVENTS_2022_2025:
        event_dt = pd.Timestamp(dt_str, tz="America/New_York")
        events.append((event_dt.tz_convert("UTC"), pre_min, post_min))

    bar_index = df_bars.index
    if bar_index.tzinfo is None:
        bar_index_utc = bar_index.tz_localize("UTC")
    else:
        bar_index_utc = bar_index.tz_convert("UTC")

    flags = np.zeros(len(df_bars), dtype=int)
    for event_utc, pre_min, post_min in events:
        window_start = event_utc - pd.Timedelta(minutes=pre_min)
        window_end = event_utc + pd.Timedelta(minutes=post_min)
        in_window = (bar_index_utc >= window_start) & (bar_index_utc <= window_end)
        flags |= in_window.astype(int).values

    return pd.Series(flags, index=df_bars.index, name="macro_event_flag")


def compute_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute cyclical time features: sin/cos encoded hour, minute, day_of_week.

    Cyclical encoding prevents discontinuities at boundaries (23:59 → 00:00).
    No look-ahead: these are deterministic calendar features.

    Produces 5 columns:
        - hour_sin, hour_cos
        - minute_sin, minute_cos
        - dow_sin (day of week)

    Args:
        df: DataFrame with DatetimeIndex (timezone-aware ET preferred)

    Returns:
        pd.DataFrame with 5 time feature columns
    """
    idx = df.index
    if idx.tzinfo is not None:
        local_idx = idx.tz_convert("America/New_York")
    else:
        local_idx = idx

    hour = local_idx.hour
    minute = local_idx.minute
    dow = local_idx.dayofweek  # Monday=0, Friday=4

    time_df = pd.DataFrame(index=df.index)
    time_df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    time_df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    time_df["minute_sin"] = np.sin(2 * np.pi * minute / 60)
    time_df["minute_cos"] = np.cos(2 * np.pi * minute / 60)
    time_df["dow_sin"] = np.sin(2 * np.pi * dow / 5)
    return time_df


def add_news_features(
    df_bars: pd.DataFrame,
    df_news: pd.DataFrame = None,
    sentiment_cache_path: Path = None,
) -> pd.DataFrame:
    """
    Compute and attach all 5+ news/macro/time features to df_bars.

    Feature computation order:
        1. news_sentiment_score (needs pre-computed sentiment in df_news)
        2. news_event_flag (forward window — used as filter only)
        3. news_count_1h
        4. macro_event_flag (hardcoded dates)
        5. time_features (sin/cos encoded: hour, minute, dow)

    Args:
        df_bars: OHLCV DataFrame
        df_news: News DataFrame with 'published_at' and 'sentiment' columns
        sentiment_cache_path: Path to cached FinBERT scores parquet

    Returns:
        df with all news/macro/time columns appended (in-place copy)
    """
    df = df_bars.copy()

    df["news_sentiment_score"] = compute_news_sentiment_score(df_news, df)
    df["news_event_flag"] = compute_news_event_flag(df, df_news)
    df["news_count_1h"] = compute_news_count_1h(df, df_news)
    df["macro_event_flag"] = compute_macro_event_flag(df)

    time_feats = compute_time_features(df)
    df = pd.concat([df, time_feats], axis=1)

    return df
