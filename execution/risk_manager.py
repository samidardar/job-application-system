"""
Real-time risk manager with circuit breakers.

All limits from risk_config.yaml. State persists intra-day and resets
at each session open (09:30 ET).
"""

import datetime
from pathlib import Path
from typing import Optional

import pytz
import structlog
import yaml

logger = structlog.get_logger()

ET_TZ = pytz.timezone("America/New_York")


class RiskManager:
    """
    Enforces all real-time risk limits for live/paper trading.

    Circuit breakers checked in order:
        1. daily P&L stop ($-500)
        2. account drawdown stop (5% / $2,500)
        3. max trades per day (8)
        4. session end time filter (15:45 ET)
        5. macro event blackout (5 min pre-event)
        6. max simultaneous open positions (2)
    """

    def __init__(self, config: dict = None, config_path: str = "config/risk_config.yaml"):
        if config is not None:
            self.config = config
        elif Path(config_path).exists():
            with open(config_path) as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = {}

        self.daily_loss_limit = float(self.config.get("daily_loss_limit", 500.0))
        self.max_drawdown_pct = float(self.config.get("max_drawdown_pct", 0.05))
        self.max_drawdown_abs = float(self.config.get("max_drawdown_abs", 2500.0))
        self.max_trades_per_day = int(self.config.get("max_trades_per_day", 8))
        self.news_blackout_pre_min = int(self.config.get("news_blackout_pre_min", 5))
        self.session_end = self.config.get("session_end_cutoff", "15:45")
        self.max_open_positions = int(self.config.get("max_simultaneous_positions", 2))
        self.account_size = float(self.config.get("account_size", 50_000.0))

        # Intra-day state
        self.daily_pnl_realized: float = 0.0
        self.trades_today: int = 0
        self.open_positions_count: int = 0
        self.peak_equity: float = self.account_size
        self.current_equity: float = self.account_size
        self._last_reset_date: Optional[datetime.date] = None

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check_trade(
        self,
        signal: int,
        symbol: str,
        contracts: int,
        confidence: float,
        macro_event_flag: int = 0,
        current_time: Optional[datetime.datetime] = None,
    ) -> tuple[bool, str]:
        """
        Check if a new trade is approved.

        Args:
            signal: {-1, 0, +1}
            symbol: Instrument symbol
            contracts: Number of contracts to trade
            confidence: Model confidence [0, 1]
            macro_event_flag: 1 if within macro blackout window
            current_time: Current ET datetime (defaults to now)

        Returns:
            Tuple of (approved: bool, reason: str)
        """
        self._auto_reset(current_time)

        if signal == 0:
            return False, "signal_skip"

        if contracts <= 0:
            return False, "zero_contracts"

        # 1. Daily loss stop
        if self.daily_pnl_realized <= -self.daily_loss_limit:
            logger.warning("RiskManager: DAILY LOSS LIMIT HIT", pnl=self.daily_pnl_realized)
            return False, "daily_loss_limit"

        # 2. Account drawdown stop
        drawdown = (self.peak_equity - self.current_equity) / self.peak_equity
        if drawdown >= self.max_drawdown_pct:
            logger.warning("RiskManager: DRAWDOWN LIMIT HIT", drawdown=f"{drawdown*100:.1f}%")
            return False, "drawdown_limit"

        # 3. Max trades per day
        if self.trades_today >= self.max_trades_per_day:
            return False, "max_trades"

        # 4. Session time filter
        if not self._is_valid_session_time(current_time):
            return False, "session_ended"

        # 5. Macro blackout
        if macro_event_flag == 1:
            return False, "macro_blackout"

        # 6. Max simultaneous positions
        if self.open_positions_count >= self.max_open_positions:
            return False, "max_positions"

        return True, "approved"

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------

    def update_pnl(self, pnl_delta: float) -> None:
        """Record a realized P&L update."""
        self.daily_pnl_realized += pnl_delta
        self.current_equity += pnl_delta
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

    def on_order_submitted(self) -> None:
        """Increment trade counter when an order is submitted."""
        self.trades_today += 1

    def on_position_opened(self) -> None:
        """Increment open position count."""
        self.open_positions_count += 1

    def on_position_closed(self, pnl: float) -> None:
        """Decrement open position count and record P&L."""
        self.open_positions_count = max(0, self.open_positions_count - 1)
        self.update_pnl(pnl)

    def reset_daily(self) -> None:
        """Reset all intra-day counters at session open (09:30 ET)."""
        logger.info("RiskManager: daily reset", date=str(datetime.date.today()))
        self.daily_pnl_realized = 0.0
        self.trades_today = 0
        # Note: open_positions_count NOT reset (may carry overnight)

    def get_status(self) -> dict:
        """Return current risk state as a dict for the dashboard."""
        drawdown = (self.peak_equity - self.current_equity) / max(self.peak_equity, 1)
        return {
            "daily_pnl": round(self.daily_pnl_realized, 2),
            "daily_loss_limit": self.daily_loss_limit,
            "trades_today": self.trades_today,
            "max_trades": self.max_trades_per_day,
            "open_positions": self.open_positions_count,
            "current_equity": round(self.current_equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "drawdown_pct": round(drawdown * 100, 2),
            "max_drawdown_pct": self.max_drawdown_pct * 100,
            "circuit_breakers": {
                "daily_stop": self.daily_pnl_realized <= -self.daily_loss_limit,
                "drawdown_stop": drawdown >= self.max_drawdown_pct,
                "max_trades": self.trades_today >= self.max_trades_per_day,
            },
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_valid_session_time(self, current_time: Optional[datetime.datetime]) -> bool:
        """Return True if current time is within trading session."""
        if current_time is None:
            current_time = datetime.datetime.now(ET_TZ)
        if current_time.tzinfo is None:
            current_time = ET_TZ.localize(current_time)
        else:
            current_time = current_time.astimezone(ET_TZ)

        end_h, end_m = map(int, self.session_end.split(":"))
        cutoff = current_time.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        return current_time <= cutoff

    def _auto_reset(self, current_time: Optional[datetime.datetime]) -> None:
        """Auto-reset daily counters at session start."""
        if current_time is None:
            current_time = datetime.datetime.now(ET_TZ)
        today = current_time.date() if hasattr(current_time, "date") else datetime.date.today()

        if self._last_reset_date != today:
            self.reset_daily()
            self._last_reset_date = today
