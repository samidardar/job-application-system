"""
Risk manager circuit breaker unit tests.
"""

import datetime
import pytest
import pytz

ET_TZ = pytz.timezone("America/New_York")


def _make_rm(config: dict = None):
    """Create RiskManager with test config."""
    from execution.risk_manager import RiskManager

    default_config = {
        "daily_loss_limit": 500.0,
        "max_drawdown_pct": 0.05,
        "max_drawdown_abs": 2500.0,
        "max_trades_per_day": 8,
        "news_blackout_pre_min": 5,
        "session_end_cutoff": "15:45",
        "max_simultaneous_positions": 2,
        "account_size": 50000.0,
    }
    if config:
        default_config.update(config)
    return RiskManager(config=default_config)


def _et_time(hour: int, minute: int) -> datetime.datetime:
    """Return today's date at given ET time."""
    now = datetime.datetime.now(ET_TZ)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


class TestDailyLossLimit:
    def test_rejects_when_daily_loss_limit_hit(self):
        """Trade should be rejected when daily P&L <= -$500."""
        rm = _make_rm()
        rm.update_pnl(-501.0)  # Exceed daily limit

        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert not approved
        assert reason == "daily_loss_limit"

    def test_approves_when_within_limit(self):
        """Trade should be approved when daily P&L is above limit."""
        rm = _make_rm()
        rm.update_pnl(-300.0)  # Within limit

        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert approved
        assert reason == "approved"

    def test_exactly_at_limit_rejects(self):
        """Exactly at -$500 should reject."""
        rm = _make_rm()
        rm.update_pnl(-500.0)

        approved, _ = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert not approved


class TestDrawdownStop:
    def test_rejects_when_drawdown_exceeds_5pct(self):
        """Trade rejected when drawdown > 5% of account."""
        rm = _make_rm()
        rm.update_pnl(-2600.0)  # > 5% of 50000

        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert not approved
        assert reason in {"drawdown_limit", "daily_loss_limit"}

    def test_approves_within_drawdown_limit(self):
        """Trade approved when drawdown < 5%."""
        rm = _make_rm()
        rm.update_pnl(-100.0)  # 0.2% drawdown

        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert approved


class TestMaxTradesLimit:
    def test_rejects_when_max_trades_reached(self):
        """8th trade and beyond should be rejected."""
        rm = _make_rm()
        rm.trades_today = 8  # Set directly
        rm._last_reset_date = datetime.date.today()  # Prevent auto-reset

        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert not approved
        assert reason == "max_trades"

    def test_approves_before_max_trades(self):
        """7 trades should still be OK."""
        rm = _make_rm()
        rm.trades_today = 7
        rm._last_reset_date = datetime.date.today()

        approved, _ = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert approved


class TestTimeFilter:
    def test_rejects_after_session_end(self):
        """No new trades after 15:45 ET."""
        rm = _make_rm()
        # 15:50 ET = after session end
        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(15, 50),
        )
        assert not approved
        assert reason == "session_ended"

    def test_approves_before_session_end(self):
        """Trades approved at 10:30 ET."""
        rm = _make_rm()
        approved, _ = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 30),
        )
        assert approved

    def test_rejects_at_exactly_session_end(self):
        """No trades at exactly 15:46."""
        rm = _make_rm()
        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(15, 46),
        )
        assert not approved


class TestMacroBlackout:
    def test_rejects_during_macro_event(self):
        """macro_event_flag=1 should block the trade."""
        rm = _make_rm()
        approved, reason = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            macro_event_flag=1,
            current_time=_et_time(10, 30),
        )
        assert not approved
        assert reason == "macro_blackout"

    def test_approves_outside_macro_event(self):
        """macro_event_flag=0 should not block."""
        rm = _make_rm()
        approved, _ = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            macro_event_flag=0,
            current_time=_et_time(10, 30),
        )
        assert approved


class TestDailyReset:
    def test_reset_clears_daily_state(self):
        """reset_daily() should zero out pnl and trade count."""
        rm = _make_rm()
        rm.update_pnl(-400.0)
        rm.trades_today = 5

        rm.reset_daily()

        assert rm.daily_pnl_realized == 0.0
        assert rm.trades_today == 0

    def test_auto_reset_on_new_day(self):
        """check_trade auto-resets counters on new calendar day."""
        rm = _make_rm()
        rm.daily_pnl_realized = -400.0
        rm.trades_today = 7
        # Set last reset to yesterday
        rm._last_reset_date = datetime.date.today() - datetime.timedelta(days=1)

        approved, _ = rm.check_trade(
            signal=1, symbol="NQ", contracts=1, confidence=0.8,
            current_time=_et_time(10, 0),
        )
        # After auto-reset, should approve (counter cleared)
        assert rm.daily_pnl_realized == 0.0
        assert rm.trades_today == 0
