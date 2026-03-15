"""
Full training pipeline runner.

Steps:
    1. Load raw data (or generate synthetic in --dry-run mode)
    2. Run FeaturePipeline
    3. Run TripleBarrierLabeler
    4. Run Optuna tuning (RegimeClassifier)
    5. Run Optuna tuning (SignalModel)
    6. Run WalkForwardValidator with best params
    7. Generate HTML backtest report
    8. Print final metrics table
    9. Save all models to models/saved/

Usage:
    python scripts/train_full.py
    python scripts/train_full.py --dry-run      # Synthetic data, no API keys
    python scripts/train_full.py --skip-tuning  # Skip Optuna, use defaults
    python scripts/train_full.py --symbol NQ1!  # Single symbol
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
import structlog

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

logger = structlog.get_logger()


def load_or_generate_data(symbol: str, dry_run: bool) -> tuple:
    """
    Load raw parquet data or generate synthetic data for dry-run.

    Returns:
        Tuple of (df_bars, df_news, df_vix)
    """
    if dry_run:
        logger.info("DRY RUN: generating synthetic data")
        from scripts.download_data import _generate_synthetic_ohlcv, _generate_synthetic_vix
        ohlcv_dir = PROJECT_ROOT / "data/raw/ohlcv"
        vix_dir = PROJECT_ROOT / "data/raw/vix"
        ohlcv_dir.mkdir(parents=True, exist_ok=True)
        vix_dir.mkdir(parents=True, exist_ok=True)
        data = _generate_synthetic_ohlcv([symbol], 3, ohlcv_dir, "5Min")
        df_bars = data[symbol]
        df_vix = _generate_synthetic_vix(3, vix_dir)
        df_news = None
        return df_bars, df_news, df_vix

    ohlcv_path = list((PROJECT_ROOT / "data/raw/ohlcv").glob(f"{symbol.replace('!','')}_5Min*.parquet"))
    if not ohlcv_path:
        raise FileNotFoundError(
            f"No OHLCV data for {symbol}. Run: python scripts/download_data.py first."
        )
    df_bars = pd.read_parquet(ohlcv_path[0])

    vix_path = PROJECT_ROOT / "data/raw/vix/vix_daily.parquet"
    df_vix = pd.read_parquet(vix_path) if vix_path.exists() else None

    news_path = PROJECT_ROOT / "data/raw/news/news_with_sentiment.parquet"
    df_news = pd.read_parquet(news_path) if news_path.exists() else None

    return df_bars, df_news, df_vix


def resample_to_5min(df_1min: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min bars to 5-min bars."""
    return df_1min.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()


def main():
    parser = argparse.ArgumentParser(description="NQ/ES Full Training Pipeline")
    parser.add_argument("--symbol", default="NQ1!", help="Primary symbol to train on")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use synthetic data (no Alpaca API keys needed)")
    parser.add_argument("--skip-tuning", action="store_true",
                        help="Skip Optuna tuning, use default hyperparams")
    parser.add_argument("--n-trials-regime", type=int, default=50)
    parser.add_argument("--n-trials-signal", type=int, default=30)
    args = parser.parse_args()

    t_start = time.time()

    print("=" * 65)
    print("NQ/ES DEEP LEARNING TRADING SYSTEM — FULL TRAINING PIPELINE")
    print("=" * 65)

    # ---- Step 1: Load data ----
    print(f"\n[1/8] Loading data for {args.symbol}...")
    df_bars_raw, df_news, df_vix = load_or_generate_data(args.symbol, args.dry_run)

    # Resample to 5-min if needed
    if df_bars_raw.index.freq is not None and "T" in str(df_bars_raw.index.freq):
        if df_bars_raw.index.freqstr in ["T", "1T", "1min"]:
            print("  Resampling 1-min → 5-min bars...")
            df_bars = resample_to_5min(df_bars_raw)
        else:
            df_bars = df_bars_raw
    else:
        df_bars = df_bars_raw

    # Filter to trading session
    if df_bars.index.tzinfo is not None:
        et_bars = df_bars.index.tz_convert("America/New_York")
        session_mask = (et_bars.time >= pd.Timestamp("09:30").time()) & \
                       (et_bars.time <= pd.Timestamp("16:15").time()) & \
                       (et_bars.index.dayofweek < 5)
        df_bars = df_bars[session_mask]

    print(f"  Loaded {len(df_bars)} 5-min bars ({df_bars.index[0].date()} → {df_bars.index[-1].date()})")

    # ---- Step 2: Feature engineering (full dataset) ----
    print("\n[2/8] Computing features (full dataset)...")
    from features.pipeline import FeaturePipeline

    pipe_full = FeaturePipeline(scaler_path="models/saved/feature_scaler_full.joblib")
    X_full, meta_full = pipe_full.fit_transform(df_bars, df_news, df_vix)
    print(f"  Features computed: {X_full.shape[1]} cols × {len(X_full)} rows")

    # Save processed features
    processed_dir = PROJECT_ROOT / "data/processed"
    processed_dir.mkdir(exist_ok=True)
    X_full.to_parquet(processed_dir / f"{args.symbol.replace('!','')}_features.parquet")
    meta_full.to_parquet(processed_dir / f"{args.symbol.replace('!','')}_meta.parquet")

    # ---- Step 3: Labels ----
    print("\n[3/8] Computing triple barrier labels...")
    from labels.triple_barrier import TripleBarrierLabeler

    df_for_labels = df_bars.join(X_full[["atr_14", "vol_regime", "macro_event_flag"]], how="left")
    labeler = TripleBarrierLabeler()
    df_labeled = labeler.fit_transform(df_for_labels)
    labeler.plot_barrier_distribution(
        df_labeled["label"],
        save_path=PROJECT_ROOT / "data/labels/label_distribution.png",
    )
    df_labeled[["label"]].to_parquet(PROJECT_ROOT / "data/labels/labels.parquet")

    # ---- Step 4: Regime classifier tuning ----
    regime_params = None
    if not args.skip_tuning:
        print(f"\n[4/8] Tuning RegimeClassifier (Optuna, {args.n_trials_regime} trials)...")
        from models.regime_classifier import auto_label_regime
        from training.optuna_tuning import tune_regime_classifier

        y_regime = auto_label_regime(X_full)
        regime_params = tune_regime_classifier(
            X_full, y_regime, n_trials=args.n_trials_regime
        )
        print(f"  Best regime params: {regime_params}")
    else:
        print("\n[4/8] Skipping regime tuning (--skip-tuning)")

    # ---- Step 5: Signal model tuning ----
    signal_model_kwargs = {}
    training_config = {}
    if not args.skip_tuning:
        print(f"\n[5/8] Tuning SignalModel (Optuna, {args.n_trials_signal} trials)...")
        from training.optuna_tuning import tune_signal_model

        n = len(X_full)
        split = int(n * 0.8)
        y_labels = df_labeled["label"].reindex(X_full.index).fillna(0).astype(int)
        X_tr = X_full.iloc[:split]
        y_tr = y_labels.iloc[:split]
        X_vl = X_full.iloc[split:]
        y_vl = y_labels.iloc[split:]

        best = tune_signal_model(X_tr, y_tr, X_vl, y_vl, n_trials=args.n_trials_signal)
        signal_model_kwargs = best["model_kwargs"]
        training_config = best["training_config"]
        print(f"  Best signal model kwargs: {signal_model_kwargs}")
    else:
        print("\n[5/8] Skipping signal model tuning (--skip-tuning)")

    # ---- Step 6: Walk-forward validation ----
    print("\n[6/8] Running 5-fold walk-forward validation...")
    from training.walk_forward import WalkForwardValidator

    validator = WalkForwardValidator(n_folds=5, initial_train_months=18, test_months=3)
    wf_results = validator.run(
        df=df_bars,
        df_news=df_news,
        df_vix=df_vix,
        regime_clf_params=regime_params,
        signal_model_params=signal_model_kwargs,
        training_config=training_config,
    )

    # ---- Step 7: HTML report ----
    print("\n[7/8] Generating HTML backtest report...")
    from backtesting.report import generate_html_report
    generate_html_report(wf_results, output_path="backtesting/reports/walk_forward_report.html")

    # Save metrics for dashboard
    metrics_df = wf_results.summary_table()
    metrics_df.to_parquet("backtesting/reports/metrics.parquet")

    # Save aggregate trade log
    all_trades = pd.concat(
        [f.trade_log for f in wf_results.folds if not f.trade_log.empty],
        ignore_index=True,
    )
    if not all_trades.empty:
        all_trades.to_parquet("backtesting/reports/trade_log.parquet")
        # Save equity curve (last fold)
        last_fold = wf_results.folds[-1]
        last_fold.equity_curve.to_frame("equity").to_parquet("backtesting/reports/equity_curve.parquet")

    # ---- Step 8: Print summary ----
    print("\n[8/8] Training complete!\n")
    wf_results.print_summary()

    print(metrics_df.to_string(index=False))
    elapsed = time.time() - t_start
    print(f"\n⏱  Total time: {elapsed/60:.1f} minutes")

    if wf_results.passed:
        print("\n✅ Walk-forward validation PASSED. System ready for paper trading.")
        print("   Run: python scripts/run_paper_trading.py")
    else:
        print("\n❌ Walk-forward validation FAILED. Review metrics before live deployment.")


if __name__ == "__main__":
    main()
