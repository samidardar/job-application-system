"""
Realistic bar-by-bar backtesting engine.

Simulation rules:
    - Market orders fill at next bar's open + slippage (1 tick per side)
    - Commission: $4.50 per round-trip per contract
    - Session filter: only trade 09:30–15:45 ET
    - News blackout: no entries 5 min before / 10 min after macro events
    - Daily circuit breakers: daily loss > $500 → stop

NO vectorized lookahead. The loop processes bars strictly left-to-right.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd
import pytz
import structlog

logger = structlog.get_logger()

ET_TZ = pytz.timezone("America/New_York")

# Default instrument params
DEFAULT_TICK_VALUE = {"NQ": 5.0, "ES": 12.50}
DEFAULT_TICK_SIZE = {"NQ": 0.25, "ES": 0.25}
DEFAULT_SLIPPAGE_TICKS = {"NQ": 1, "ES": 1}
COMMISSION_PER_RT = 4.50
DAILY_LOSS_LIMIT = 500.0
SESSION_START = "09:30"
SESSION_END = "15:45"


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    side: int        # +1 = long, -1 = short
    contracts: int
    entry_price: float
    entry_time: pd.Timestamp
    upper_barrier: float
    lower_barrier: float
    time_limit_bar: int  # Bar index at which time barrier triggers


@dataclass
class BacktestResults:
    """Container for backtesting output."""
    equity_curve: pd.Series = field(default_factory=pd.Series)
    trade_log: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_pnl: pd.Series = field(default_factory=pd.Series)
    drawdown_series: pd.Series = field(default_factory=pd.Series)
    initial_capital: float = 50_000.0


class BacktestEngine:
    """
    Realistic bar-by-bar backtesting engine for NQ/ES futures.

    Each bar processed strictly left-to-right — no vectorized lookahead.
    """

    def __init__(
        self,
        initial_capital: float = 50_000.0,
        slippage_ticks: dict = None,
        commission_per_rt: float = COMMISSION_PER_RT,
        tick_value: dict = None,
        tick_size: dict = None,
        daily_loss_limit: float = DAILY_LOSS_LIMIT,
        session_start: str = SESSION_START,
        session_end: str = SESSION_END,
        symbol: str = "NQ",
    ):
        self.initial_capital = initial_capital
        self.slippage_ticks = slippage_ticks or DEFAULT_SLIPPAGE_TICKS
        self.commission_per_rt = commission_per_rt
        self.tick_value = tick_value or DEFAULT_TICK_VALUE
        self.tick_size = tick_size or DEFAULT_TICK_SIZE
        self.daily_loss_limit = daily_loss_limit
        self.session_start = session_start
        self.session_end = session_end
        self.symbol = symbol

    def run(
        self,
        df_bars: pd.DataFrame,
        signals_df: pd.DataFrame,
        metadata: pd.DataFrame = None,
    ) -> BacktestResults:
        """
        Run full bar-by-bar backtest simulation.

        Args:
            df_bars: OHLCV DataFrame with DatetimeIndex (ET or UTC tz-aware)
                     Must have columns: open, high, low, close
            signals_df: DataFrame indexed same as df_bars with columns:
                        'signal' {-1, 0, +1}, 'confidence' [0, 1]
            metadata: Optional metadata DataFrame with 'macro_event_flag'

        Returns:
            BacktestResults with equity_curve, trade_log, daily_pnl
        """
        bars = df_bars.copy()
        if bars.index.tzinfo is None:
            bars.index = bars.index.tz_localize("America/New_York")

        equity = self.initial_capital
        equity_series = {}
        daily_pnl: Dict[str, float] = {}

        open_position: Optional[Position] = None
        trades = []

        # State
        current_date = None
        daily_pnl_today = 0.0
        daily_trades_today = 0
        day_stopped = False

        slippage_val = self.slippage_ticks.get(self.symbol, 1) * self.tick_size.get(self.symbol, 0.25)
        tv = self.tick_value.get(self.symbol, 5.0)
        ts = self.tick_size.get(self.symbol, 0.25)

        n = len(bars)
        signals_aligned = signals_df.reindex(bars.index)

        for i in range(n):
            bar_ts = bars.index[i]
            bar_et = bar_ts.tz_convert("America/New_York")
            bar_date = bar_et.date()
            bar_time = bar_et.time()

            # ---- Daily reset ----
            if bar_date != current_date:
                if current_date is not None:
                    daily_pnl[str(current_date)] = daily_pnl_today
                current_date = bar_date
                daily_pnl_today = 0.0
                daily_trades_today = 0
                day_stopped = False

            equity_series[bar_ts] = equity

            # ---- Manage open position ----
            if open_position is not None:
                pos = open_position
                high = bars["high"].iloc[i]
                low = bars["low"].iloc[i]
                close = bars["close"].iloc[i]

                exit_price = None
                exit_reason = None

                # Check upper barrier (TP)
                if pos.side == 1 and high >= pos.upper_barrier:
                    exit_price = pos.upper_barrier - slippage_val
                    exit_reason = "tp"
                elif pos.side == -1 and low <= pos.upper_barrier:
                    exit_price = pos.upper_barrier + slippage_val
                    exit_reason = "tp"

                # Check lower barrier (SL)
                if exit_price is None:
                    if pos.side == 1 and low <= pos.lower_barrier:
                        exit_price = pos.lower_barrier - slippage_val
                        exit_reason = "sl"
                    elif pos.side == -1 and high >= pos.lower_barrier:
                        exit_price = pos.lower_barrier + slippage_val
                        exit_reason = "sl"

                # Check time barrier
                if exit_price is None and i >= pos.time_limit_bar:
                    exit_price = close - (slippage_val * pos.side)
                    exit_reason = "time"

                if exit_price is not None:
                    # Compute P&L
                    price_diff = (exit_price - pos.entry_price) * pos.side
                    ticks = price_diff / ts
                    gross_pnl = ticks * tv * pos.contracts
                    commission = self.commission_per_rt * pos.contracts
                    net_pnl = gross_pnl - commission

                    equity += net_pnl
                    daily_pnl_today += net_pnl
                    daily_trades_today += 1

                    trades.append({
                        "entry_time": pos.entry_time,
                        "exit_time": bar_ts,
                        "symbol": pos.symbol,
                        "side": "long" if pos.side == 1 else "short",
                        "contracts": pos.contracts,
                        "entry_price": pos.entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "gross_pnl": round(gross_pnl, 2),
                        "commission": commission,
                        "pnl": round(net_pnl, 2),
                        "bars_held": i - bars.index.get_loc(pos.entry_time),
                    })
                    open_position = None

            # ---- Circuit breakers ----
            if day_stopped:
                continue
            if daily_pnl_today <= -self.daily_loss_limit:
                logger.debug(f"Circuit breaker: daily loss limit hit on {bar_date}")
                day_stopped = True
                continue
            if daily_trades_today >= 8:
                continue

            # ---- Session filter ----
            session_s = pd.Timestamp(SESSION_START).time()
            session_e = pd.Timestamp(SESSION_END).time()
            if not (session_s <= bar_time <= session_e):
                continue

            # ---- No new position if one open ----
            if open_position is not None:
                continue

            # ---- Check for signal ----
            if i + 1 >= n:  # No next bar to enter on
                continue

            sig_row = signals_aligned.iloc[i] if not signals_aligned.empty else None
            if sig_row is None or pd.isna(sig_row.get("signal", np.nan)):
                continue

            signal = int(sig_row["signal"])
            confidence = float(sig_row.get("confidence", 0.5))

            if signal == 0:
                continue

            # ---- Macro blackout ----
            macro_flag = 0
            if metadata is not None and "macro_event_flag" in metadata.columns:
                macro_flag = metadata["macro_event_flag"].reindex(bars.index).iloc[i]
                if pd.isna(macro_flag):
                    macro_flag = 0
                macro_flag = int(macro_flag)
            if macro_flag == 1:
                continue

            # ---- Enter position on next bar open ----
            next_open = bars["open"].iloc[i + 1]
            entry_price = next_open + slippage_val * signal  # buy high / sell low

            # Barrier levels from current bar ATR
            atr = None
            if metadata is not None and "atr_14" in metadata.columns:
                atr_series = metadata["atr_14"].reindex(bars.index)
                atr = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else None
            if atr is None or atr <= 0:
                atr = float((bars["high"].iloc[i] - bars["low"].iloc[i]) * 2)

            upper = entry_price + atr * 1.5 * signal
            lower = entry_price - atr * 0.75 * signal

            # For shorts, swap: upper=SL, lower=TP
            if signal == -1:
                upper, lower = lower, upper

            open_position = Position(
                symbol=self.symbol,
                side=signal,
                contracts=1,  # Base size (Kelly sizer called upstream)
                entry_price=entry_price,
                entry_time=bars.index[i + 1],
                upper_barrier=upper,
                lower_barrier=lower,
                time_limit_bar=i + 1 + 6,
            )

        # Close any open position at end
        if open_position is not None:
            last_close = bars["close"].iloc[-1]
            price_diff = (last_close - open_position.entry_price) * open_position.side
            ticks = price_diff / ts
            net_pnl = ticks * tv * open_position.contracts - self.commission_per_rt
            equity += net_pnl
            daily_pnl_today += net_pnl
            trades.append({
                "entry_time": open_position.entry_time,
                "exit_time": bars.index[-1],
                "symbol": open_position.symbol,
                "side": "long" if open_position.side == 1 else "short",
                "contracts": open_position.contracts,
                "entry_price": open_position.entry_price,
                "exit_price": last_close,
                "exit_reason": "end_of_data",
                "gross_pnl": round(price_diff / ts * tv, 2),
                "commission": self.commission_per_rt,
                "pnl": round(net_pnl, 2),
                "bars_held": n - 1,
            })

        # Final daily record
        if current_date is not None:
            daily_pnl[str(current_date)] = daily_pnl_today
        equity_series[bars.index[-1]] = equity

        equity_curve = pd.Series(equity_series).sort_index()
        trade_log = pd.DataFrame(trades) if trades else pd.DataFrame()
        daily_pnl_series = pd.Series(daily_pnl)

        # Drawdown
        rolling_max = equity_curve.cummax()
        drawdown_series = (equity_curve - rolling_max) / rolling_max.replace(0, np.nan)

        logger.info(
            "BacktestEngine.run complete",
            total_trades=len(trades),
            final_equity=round(equity, 2),
            total_pnl=round(equity - self.initial_capital, 2),
        )

        return BacktestResults(
            equity_curve=equity_curve,
            trade_log=trade_log,
            daily_pnl=daily_pnl_series,
            drawdown_series=drawdown_series,
            initial_capital=self.initial_capital,
        )
