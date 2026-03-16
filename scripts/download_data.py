"""
Historical data downloader.

Downloads:
    - 3 years of NQ + ES 1-min OHLCV from Alpaca
    - 6 months of tick data
    - 2 years of news articles (with FinBERT sentiment pre-computation)
    - VIX daily from yfinance

Saves to data/raw/ as parquet.
API keys read from environment: ALPACA_API_KEY, ALPACA_SECRET_KEY.

Usage:
    python scripts/download_data.py
    python scripts/download_data.py --symbols NQ1! --years 1
    python scripts/download_data.py --skip-news --skip-ticks  # OHLCV only
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from tqdm import tqdm

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import structlog
logger = structlog.get_logger()


def _rate_limit_sleep(seconds: float = 0.3):
    time.sleep(seconds)


def download_ohlcv(
    symbols: list,
    years: int = 3,
    timeframe: str = "1Min",
    output_dir: Path = PROJECT_ROOT / "data/raw/ohlcv",
    api_key: str = None,
    api_secret: str = None,
) -> dict:
    """
    Download OHLCV bars from Alpaca.

    Args:
        symbols: List of Alpaca tickers
        years: Years of history to download
        timeframe: Bar timeframe (1Min, 5Min, etc.)
        output_dir: Output directory for parquet files
        api_key: Alpaca API key
        api_secret: Alpaca secret key

    Returns:
        Dict of {symbol: pd.DataFrame}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
    api_secret = api_secret or os.environ.get("ALPACA_SECRET_KEY", "")

    end = datetime.now()
    start = end - timedelta(days=365 * years)

    results = {}

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        client = StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
        tf_map = {
            "1Min": TimeFrame(1, TimeFrameUnit.Minute),
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        }
        tf = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Minute))

        for sym in tqdm(symbols, desc="Downloading OHLCV"):
            logger.info(f"Downloading {sym} {timeframe} bars ({years} years)...")
            try:
                req = StockBarsRequest(
                    symbol_or_symbols=sym,
                    timeframe=tf,
                    start=start,
                    end=end,
                )
                bars = client.get_stock_bars(req)
                df = bars.df

                if isinstance(df.index, pd.MultiIndex):
                    df = df.loc[sym] if sym in df.index.get_level_values(0) else df.droplevel(0)

                df = df.rename(columns={
                    "open": "open", "high": "high", "low": "low",
                    "close": "close", "volume": "volume",
                })
                df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")

                out_path = output_dir / f"{sym.replace('!', '')}_{timeframe}_{years}y.parquet"
                df.to_parquet(out_path)
                results[sym] = df
                logger.info(f"Saved {len(df)} bars → {out_path}")
                _rate_limit_sleep()

            except Exception as e:
                logger.error(f"Failed to download {sym}: {e}")

    except ImportError:
        logger.warning("alpaca-py not installed. Using synthetic data for dry-run.")
        results = _generate_synthetic_ohlcv(symbols, years, output_dir, timeframe)

    return results


def download_vix(
    years: int = 3,
    output_dir: Path = PROJECT_ROOT / "data/raw/vix",
) -> pd.DataFrame:
    """Download VIX daily from yfinance."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yfinance as yf
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
        vix = yf.download("^VIX", start=start, end=end, progress=False)
        vix = vix[["Close"]].rename(columns={"Close": "close"})
        out_path = output_dir / "vix_daily.parquet"
        vix.to_parquet(out_path)
        logger.info(f"VIX downloaded: {len(vix)} days → {out_path}")
        return vix
    except Exception as e:
        logger.warning(f"VIX download failed: {e}. Using synthetic VIX.")
        return _generate_synthetic_vix(years, output_dir)


def download_news(
    symbols: list,
    years: int = 2,
    output_dir: Path = PROJECT_ROOT / "data/raw/news",
    api_key: str = None,
    api_secret: str = None,
) -> pd.DataFrame:
    """
    Download news articles from Alpaca and pre-compute FinBERT sentiment.

    Returns DataFrame with columns: published_at, headline, summary, sentiment
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "news_with_sentiment.parquet"

    if out_path.exists():
        logger.info(f"News already downloaded at {out_path}, loading cached...")
        return pd.read_parquet(out_path)

    from features.news import fetch_alpaca_news, compute_finbert_sentiment

    end = datetime.now().isoformat()
    start = (datetime.now() - timedelta(days=365 * years)).isoformat()

    all_news = []
    # Use SPY as ES proxy, QQQ as NQ proxy
    proxy_symbols = {"NQ1!": "QQQ", "ES1!": "SPY"}

    for sym in tqdm(symbols, desc="Downloading news"):
        proxy = proxy_symbols.get(sym, sym)
        df_news = fetch_alpaca_news(proxy, start, end, api_key, api_secret)
        if not df_news.empty:
            all_news.append(df_news)
            _rate_limit_sleep(0.5)

    if not all_news:
        logger.warning("No news articles downloaded. Using empty DataFrame.")
        empty = pd.DataFrame(columns=["published_at", "headline", "summary", "sentiment"])
        empty.to_parquet(out_path)
        return empty

    df_all = pd.concat(all_news, ignore_index=True).drop_duplicates("headline")

    # Pre-compute FinBERT sentiment and cache
    texts = (df_all["headline"].fillna("") + " " + df_all["summary"].fillna("")).tolist()
    cache_path = output_dir / "finbert_cache.parquet"
    logger.info(f"Computing FinBERT sentiment for {len(texts)} articles...")
    sentiments = compute_finbert_sentiment(texts, cache_path=cache_path)
    df_all["sentiment"] = sentiments

    df_all.to_parquet(out_path)
    logger.info(f"News saved: {len(df_all)} articles → {out_path}")
    return df_all


def _generate_synthetic_ohlcv(
    symbols: list, years: int, output_dir: Path, timeframe: str
) -> dict:
    """Generate synthetic OHLCV for dry-run testing (no API keys needed)."""
    import numpy as np

    results = {}
    n_bars_per_day = 78  # 5-min bars in 09:30-16:00 session
    n_days = years * 252

    for sym in symbols:
        logger.info(f"Generating synthetic {sym} data ({n_days * n_bars_per_day} bars)...")

        # Generate only trading-session bars (09:30-16:00 ET, weekdays)
        all_dates = pd.bdate_range(start="2022-01-03", periods=n_days)
        bar_times = []
        for d in all_dates:
            session_start = pd.Timestamp(d.strftime("%Y-%m-%d") + " 09:30",
                                         tz="America/New_York")
            day_bars = pd.date_range(session_start, periods=n_bars_per_day, freq="5min")
            bar_times.extend(day_bars)
        idx = pd.DatetimeIndex(bar_times)
        n_bars = len(idx)

        rng = np.random.default_rng(42)
        base = 18000 if "NQ" in sym else 4500
        close = base + np.cumsum(rng.normal(0, 10, n_bars))
        high = close + rng.uniform(1, 20, n_bars)
        low = close - rng.uniform(1, 20, n_bars)
        open_ = close + rng.normal(0, 5, n_bars)
        volume = rng.integers(1000, 20000, n_bars).astype(float)

        df = pd.DataFrame({
            "open": open_, "high": high, "low": low,
            "close": close, "volume": volume,
        }, index=idx)

        out_path = output_dir / f"{sym.replace('!', '')}_5Min_{years}y.parquet"
        df.to_parquet(out_path)
        results[sym] = df
        logger.info(f"Synthetic data saved → {out_path}")

    return results


def _generate_synthetic_vix(years: int, output_dir: Path) -> pd.DataFrame:
    """Generate synthetic VIX data for dry-run."""
    import numpy as np

    n = years * 252
    idx = pd.bdate_range(start="2022-01-03", periods=n)
    rng = np.random.default_rng(42)
    vix = pd.DataFrame(
        {"close": 20 + rng.normal(0, 5, n).cumsum() * 0.1},
        index=idx,
    ).clip(lower=10, upper=80)

    out_path = output_dir / "vix_daily.parquet"
    vix.to_parquet(out_path)
    return vix


def main():
    parser = argparse.ArgumentParser(description="Download NQ/ES trading system data")
    parser.add_argument("--symbols", nargs="+", default=["NQ1!", "ES1!"])
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--news-years", type=int, default=2)
    parser.add_argument("--skip-news", action="store_true")
    parser.add_argument("--skip-ticks", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use synthetic data (no API keys required)")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    api_key = None if args.dry_run else os.environ.get("ALPACA_API_KEY", "")
    api_secret = None if args.dry_run else os.environ.get("ALPACA_SECRET_KEY", "")

    if args.dry_run:
        logger.info("DRY RUN: generating synthetic data")
        _generate_synthetic_ohlcv(args.symbols, args.years, PROJECT_ROOT / "data/raw/ohlcv", "5Min")
        _generate_synthetic_vix(args.years, PROJECT_ROOT / "data/raw/vix")
        return

    print("=" * 60)
    print("NQ/ES Trading System — Data Downloader")
    print("=" * 60)

    print("\n[1/3] Downloading OHLCV bars...")
    download_ohlcv(args.symbols, years=args.years, api_key=api_key, api_secret=api_secret)

    print("\n[2/3] Downloading VIX...")
    download_vix(years=args.years)

    if not args.skip_news:
        print("\n[3/3] Downloading news + FinBERT sentiment...")
        download_news(args.symbols, years=args.news_years, api_key=api_key, api_secret=api_secret)

    print("\n✅ Download complete. Data saved to data/raw/")


if __name__ == "__main__":
    main()
