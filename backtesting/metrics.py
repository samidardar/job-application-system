"""
Backtesting metrics computation.

All metrics computed on out-of-sample equity curve and trade log.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


def compute_sharpe(
    returns: pd.Series,
    risk_free: float = 0.05,
    periods_per_year: int = 252,
) -> float:
    """
    Compute annualized Sharpe Ratio.

    Args:
        returns: Daily return series
        risk_free: Annual risk-free rate
        periods_per_year: Trading days per year

    Returns:
        Annualized Sharpe ratio
    """
    if len(returns) < 2:
        return 0.0
    rf_per_period = risk_free / periods_per_year
    excess = returns - rf_per_period
    mean = excess.mean()
    std = excess.std()
    if std == 0:
        return 0.0
    return float(mean / std * np.sqrt(periods_per_year))


def compute_sortino(
    returns: pd.Series,
    risk_free: float = 0.05,
    periods_per_year: int = 252,
) -> float:
    """
    Compute annualized Sortino Ratio (uses downside deviation only).

    Args:
        returns: Daily return series
        risk_free: Annual risk-free rate
        periods_per_year: Trading days per year

    Returns:
        Annualized Sortino ratio
    """
    if len(returns) < 2:
        return 0.0
    rf_per_period = risk_free / periods_per_year
    excess = returns - rf_per_period
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf")
    downside_std = np.sqrt((downside ** 2).mean())
    if downside_std == 0:
        return 0.0
    return float(excess.mean() / downside_std * np.sqrt(periods_per_year))


def compute_max_drawdown(equity_curve: pd.Series) -> float:
    """
    Compute maximum drawdown as a fraction of peak equity.

    Args:
        equity_curve: Cumulative equity Series

    Returns:
        Maximum drawdown fraction (e.g., 0.05 = 5% drawdown)
    """
    if len(equity_curve) < 2:
        return 0.0
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max.replace(0, np.nan)
    return float(drawdown.min().item()) if not drawdown.empty else 0.0


def compute_calmar(equity_curve: pd.Series) -> float:
    """
    Compute Calmar Ratio: annualized return / max drawdown.

    Args:
        equity_curve: Cumulative equity Series

    Returns:
        Calmar ratio
    """
    if len(equity_curve) < 2:
        return 0.0
    total_return = (equity_curve.iloc[-1] - equity_curve.iloc[0]) / equity_curve.iloc[0]
    n_years = len(equity_curve) / 252
    annualized_return = (1 + total_return) ** (1 / max(n_years, 1e-6)) - 1
    max_dd = abs(compute_max_drawdown(equity_curve))
    if max_dd == 0:
        return float("inf")
    return float(annualized_return / max_dd)


def compute_profit_factor(trade_log: pd.DataFrame) -> float:
    """
    Compute Profit Factor: sum of wins / sum of losses.

    Args:
        trade_log: DataFrame with 'pnl' column

    Returns:
        Profit factor (values > 1 are profitable)
    """
    if trade_log.empty or "pnl" not in trade_log.columns:
        return 0.0
    wins = trade_log["pnl"][trade_log["pnl"] > 0].sum()
    losses = abs(trade_log["pnl"][trade_log["pnl"] < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def compute_win_rate(trade_log: pd.DataFrame) -> float:
    """
    Compute win rate: fraction of profitable trades.

    Args:
        trade_log: DataFrame with 'pnl' column

    Returns:
        Win rate [0, 1]
    """
    if trade_log.empty or "pnl" not in trade_log.columns:
        return 0.0
    wins = (trade_log["pnl"] > 0).sum()
    return float(wins / len(trade_log))


def compute_avg_rr(trade_log: pd.DataFrame) -> float:
    """
    Compute average reward:risk ratio.

    R:R = avg_win / avg_loss (magnitudes)

    Args:
        trade_log: DataFrame with 'pnl' column

    Returns:
        Average R:R ratio
    """
    if trade_log.empty or "pnl" not in trade_log.columns:
        return 0.0
    wins = trade_log["pnl"][trade_log["pnl"] > 0]
    losses = trade_log["pnl"][trade_log["pnl"] < 0]
    if losses.empty or wins.empty:
        return 0.0
    return float(wins.mean() / abs(losses.mean()))


def compute_all_metrics(backtest_results) -> dict:
    """
    Compute all performance metrics from a BacktestResults object.

    Args:
        backtest_results: BacktestResults with equity_curve, trade_log, daily_pnl

    Returns:
        Dict of all metrics
    """
    equity = backtest_results.equity_curve
    trades = backtest_results.trade_log
    daily = backtest_results.daily_pnl

    if equity.empty or daily.empty:
        return {
            "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0,
            "max_drawdown": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
            "avg_rr": 0.0, "total_trades": 0, "avg_daily_pnl": 0.0,
        }

    daily_returns = daily / equity.iloc[0]

    return {
        "sharpe": compute_sharpe(daily_returns),
        "sortino": compute_sortino(daily_returns),
        "calmar": compute_calmar(equity),
        "max_drawdown": compute_max_drawdown(equity),
        "win_rate": compute_win_rate(trades),
        "profit_factor": compute_profit_factor(trades),
        "avg_rr": compute_avg_rr(trades),
        "total_trades": len(trades),
        "avg_daily_pnl": float(daily.mean()),
        "total_pnl": float(equity.iloc[-1] - equity.iloc[0]) if len(equity) > 0 else 0.0,
        "trades_per_day": len(trades) / max(len(daily), 1),
    }


def generate_metrics_report(all_fold_results: list) -> pd.DataFrame:
    """
    Pretty-print metrics DataFrame from multiple fold results.

    Args:
        all_fold_results: List of metric dicts

    Returns:
        Formatted DataFrame
    """
    rows = []
    for i, m in enumerate(all_fold_results):
        rows.append({
            "Fold": i + 1,
            "Sharpe": round(m.get("sharpe", 0), 3),
            "Sortino": round(m.get("sortino", 0), 3),
            "Calmar": round(m.get("calmar", 0), 3),
            "MaxDD": f"{m.get('max_drawdown', 0)*100:.1f}%",
            "WinRate": f"{m.get('win_rate', 0)*100:.1f}%",
            "PF": round(m.get("profit_factor", 0), 3),
            "AvgRR": round(m.get("avg_rr", 0), 2),
            "Trades": m.get("total_trades", 0),
            "AvgDailyPnL": f"${m.get('avg_daily_pnl', 0):.0f}",
        })

    df = pd.DataFrame(rows)

    # Add aggregate row
    agg = {
        "Fold": "AGG",
        "Sharpe": round(np.mean([m.get("sharpe", 0) for m in all_fold_results]), 3),
        "Sortino": round(np.mean([m.get("sortino", 0) for m in all_fold_results]), 3),
        "Calmar": round(np.mean([m.get("calmar", 0) for m in all_fold_results]), 3),
        "MaxDD": f"{max(m.get('max_drawdown', 0) for m in all_fold_results)*100:.1f}%",
        "WinRate": f"{np.mean([m.get('win_rate', 0) for m in all_fold_results])*100:.1f}%",
        "PF": round(np.mean([m.get("profit_factor", 0) for m in all_fold_results if m.get('profit_factor', 0) < 100]), 3),
        "AvgRR": round(np.mean([m.get("avg_rr", 0) for m in all_fold_results]), 2),
        "Trades": sum(m.get("total_trades", 0) for m in all_fold_results),
        "AvgDailyPnL": f"${np.mean([m.get('avg_daily_pnl', 0) for m in all_fold_results]):.0f}",
    }
    return pd.concat([df, pd.DataFrame([agg])], ignore_index=True)
