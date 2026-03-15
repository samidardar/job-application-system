"""
Backtest HTML report generator.

Generates a self-contained HTML report with embedded matplotlib charts,
trade log table, and metrics summary.
"""

import base64
import io
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()


def _fig_to_base64(fig: plt.Figure) -> str:
    """Convert matplotlib figure to base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{encoded}"


def _plot_equity_curve(equity_curve: pd.Series, fold_num: int) -> str:
    """Plot equity curve and return base64 image."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity_curve.index, equity_curve.values, color="#2ecc71", linewidth=1.5)
    ax.fill_between(equity_curve.index, equity_curve.values,
                    equity_curve.iloc[0], alpha=0.15, color="#2ecc71")
    ax.axhline(equity_curve.iloc[0], color="gray", linestyle="--", linewidth=0.8)
    ax.set_title(f"Fold {fold_num} — Equity Curve", fontsize=12, fontweight="bold")
    ax.set_ylabel("Account Equity ($)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=30)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _plot_drawdown(drawdown_series: pd.Series, fold_num: int) -> str:
    """Plot underwater drawdown chart and return base64 image."""
    fig, ax = plt.subplots(figsize=(10, 3))
    pct = drawdown_series * 100
    ax.fill_between(pct.index, pct.values, 0, color="#e74c3c", alpha=0.6)
    ax.plot(pct.index, pct.values, color="#c0392b", linewidth=0.8)
    ax.set_title(f"Fold {fold_num} — Drawdown (%)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Drawdown (%)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=30)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _plot_pnl_distribution(trade_log: pd.DataFrame, fold_num: int) -> str:
    """Plot P&L distribution histogram and return base64 image."""
    fig, ax = plt.subplots(figsize=(8, 4))
    if not trade_log.empty and "pnl" in trade_log.columns:
        pnl = trade_log["pnl"]
        ax.hist(pnl[pnl >= 0], bins=20, color="#2ecc71", alpha=0.7, label="Wins")
        ax.hist(pnl[pnl < 0], bins=20, color="#e74c3c", alpha=0.7, label="Losses")
        ax.axvline(0, color="black", linewidth=1)
        ax.legend()
    ax.set_title(f"Fold {fold_num} — P&L Distribution", fontsize=12, fontweight="bold")
    ax.set_xlabel("Trade P&L ($)")
    ax.set_ylabel("Count")
    fig.tight_layout()
    return _fig_to_base64(fig)


def _plot_pnl_by_hour(trade_log: pd.DataFrame) -> str:
    """Plot P&L heatmap by hour of day and return base64 image."""
    fig, ax = plt.subplots(figsize=(10, 4))
    if not trade_log.empty and "entry_time" in trade_log.columns:
        tl = trade_log.copy()
        tl["hour"] = pd.to_datetime(tl["entry_time"]).dt.hour
        by_hour = tl.groupby("hour")["pnl"].sum()
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in by_hour.values]
        ax.bar(by_hour.index, by_hour.values, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_title("P&L by Hour of Day (ET)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Hour (ET)")
    ax.set_ylabel("Total P&L ($)")
    ax.axhline(0, color="black", linewidth=0.8)
    fig.tight_layout()
    return _fig_to_base64(fig)


def generate_html_report(
    walk_forward_results,
    output_path: str = "backtesting/reports/walk_forward_report.html",
) -> None:
    """
    Generate a self-contained HTML backtest report.

    Args:
        walk_forward_results: WalkForwardResults object
        output_path: Path to write the HTML file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wfr = walk_forward_results
    summary_df = wfr.summary_table()

    # Build fold sections HTML
    fold_html = ""
    all_trades = []
    for fold in wfr.folds:
        eq_img = _plot_equity_curve(fold.equity_curve, fold.fold) if not fold.equity_curve.empty else ""
        dd_img = _plot_drawdown(
            (fold.equity_curve - fold.equity_curve.cummax()) / fold.equity_curve.cummax().replace(0, np.nan),
            fold.fold,
        ) if not fold.equity_curve.empty else ""
        pnl_img = _plot_pnl_distribution(fold.trade_log, fold.fold)

        if not fold.trade_log.empty:
            tl = fold.trade_log.copy()
            tl["fold"] = fold.fold
            all_trades.append(tl)

        status_color = "#27ae60" if fold.passed else "#e74c3c"
        status_text = "PASS ✅" if fold.passed else "FAIL ❌"

        fold_html += f"""
        <div class='fold-section'>
            <h2>Fold {fold.fold}: {fold.test_start.date()} → {fold.test_end.date()}
                <span style='color:{status_color};font-size:0.8em;margin-left:12px'>{status_text}</span>
            </h2>
            <div class='metrics-grid'>
                <div class='metric'><b>Sharpe</b><br>{fold.sharpe:.3f}</div>
                <div class='metric'><b>Sortino</b><br>{fold.sortino:.3f}</div>
                <div class='metric'><b>Max DD</b><br>{fold.max_drawdown*100:.1f}%</div>
                <div class='metric'><b>Win Rate</b><br>{fold.win_rate*100:.1f}%</div>
                <div class='metric'><b>Profit Factor</b><br>{fold.profit_factor:.3f}</div>
                <div class='metric'><b>Trades</b><br>{fold.total_trades}</div>
                <div class='metric'><b>Avg Daily P&L</b><br>${fold.avg_daily_pnl:.0f}</div>
            </div>
            {"<img src='" + eq_img + "' style='width:100%;'>" if eq_img else ""}
            {"<img src='" + dd_img + "' style='width:100%;margin-top:12px;'>" if dd_img else ""}
            {"<img src='" + pnl_img + "' style='width:60%;margin-top:12px;'>" if pnl_img else ""}
        </div>
        """

    # Hour-of-day chart from all trades
    all_trades_df = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    hour_img = _plot_pnl_by_hour(all_trades_df)

    # Trade log HTML
    if not all_trades_df.empty:
        trade_html = all_trades_df.head(500).to_html(
            classes="trade-table", index=False, float_format="{:.2f}".format
        )
    else:
        trade_html = "<p>No trades.</p>"

    # Summary table HTML
    summary_html = summary_df.to_html(classes="summary-table", index=False)

    overall_color = "#27ae60" if wfr.passed else "#e74c3c"
    overall_text = "PASS ✅" if wfr.passed else "FAIL ❌"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>NQ/ES Walk-Forward Backtest Report</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background:#1a1a2e; color:#eee; margin:0; padding:20px; }}
        h1 {{ color:#00d2ff; border-bottom:2px solid #00d2ff; padding-bottom:10px; }}
        h2 {{ color:#00d2ff; margin-top:30px; }}
        h3 {{ color:#a0c4ff; }}
        .fold-section {{ background:#16213e; border-radius:8px; padding:20px; margin:20px 0; border:1px solid #0f3460; }}
        .metrics-grid {{ display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }}
        .metric {{ background:#0f3460; border-radius:6px; padding:12px 18px; text-align:center; min-width:100px; }}
        .metric b {{ display:block; color:#00d2ff; margin-bottom:4px; }}
        .summary-table, .trade-table {{ border-collapse:collapse; width:100%; font-size:0.85em; margin:16px 0; }}
        .summary-table th, .trade-table th {{ background:#0f3460; color:#00d2ff; padding:8px 12px; text-align:left; }}
        .summary-table td, .trade-table td {{ padding:6px 12px; border-bottom:1px solid #0f3460; }}
        .summary-table tr:hover, .trade-table tr:hover {{ background:#0f3460; }}
        .overall-status {{ font-size:1.5em; color:{overall_color}; font-weight:bold; margin:20px 0; }}
        img {{ border-radius:6px; display:block; }}
    </style>
</head>
<body>
    <h1>NQ/ES Deep Learning Trading System — Walk-Forward Report</h1>
    <div class='overall-status'>Overall Status: {overall_text}</div>

    <h2>Aggregate Metrics</h2>
    {summary_html}

    <h2>P&L by Hour of Day</h2>
    <img src="{hour_img}" style="width:80%;">

    <h2>Per-Fold Results</h2>
    {fold_html}

    <h2>Trade Log (First 500 Trades)</h2>
    {trade_html}

    <p style="color:#666;font-size:0.8em;margin-top:40px;">
        Generated by NQ/ES Trading System | Slippage: 1 tick/side | Commission: $4.50/RT
    </p>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    logger.info(f"HTML report saved to {output_path}")
