"""
Kelly Fractional Position Sizing Model (Level 3).

Computes optimal position size based on:
    - Kelly criterion (25% fraction, conservative)
    - Signal confidence
    - Volatility regime
    - Macro event flag
    - Relative volume

Hard limits: max 2 contracts, min 0 contracts.
"""

from collections import deque
from typing import Deque

import numpy as np
import structlog

logger = structlog.get_logger()


class KellySizer:
    """
    Conservative fractional Kelly position sizer.

    Maintains a rolling window of trade results to update win rate
    and average win/loss statistics in real time.

    Kelly formula:
        K% = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
        Fractional Kelly = K% * kelly_fraction  (default 0.25)

    If Kelly < 0 (losing edge), returns 0 contracts.
    """

    def __init__(
        self,
        kelly_fraction: float = 0.25,
        max_contracts: int = 2,
        account_size: float = 50_000,
        min_trades_for_kelly: int = 20,
        rolling_window: int = 100,
    ):
        """
        Args:
            kelly_fraction: Conservative multiplier on full Kelly (default 0.25)
            max_contracts: Hard cap on contracts per signal
            account_size: Starting account equity for sizing calculations
            min_trades_for_kelly: Min trades before Kelly is trusted (use base=1 before)
            rolling_window: Number of recent trades to use for stats
        """
        self.kelly_fraction = kelly_fraction
        self.max_contracts = max_contracts
        self.account_size = account_size
        self.min_trades_for_kelly = min_trades_for_kelly

        self._results: Deque[float] = deque(maxlen=rolling_window)
        self._trade_count = 0

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------

    def update_stats(self, trade_pnl: float) -> None:
        """
        Record a completed trade P&L for rolling statistics.

        Args:
            trade_pnl: Realized P&L in dollars (positive = win, negative = loss)
        """
        self._results.append(trade_pnl)
        self._trade_count += 1

    def reset(self) -> None:
        """Reset all rolling statistics (e.g., after model retraining)."""
        self._results.clear()
        self._trade_count = 0

    # ------------------------------------------------------------------
    # Kelly calculation
    # ------------------------------------------------------------------

    def compute_kelly(
        self,
        win_rate: float = None,
        avg_win: float = None,
        avg_loss: float = None,
    ) -> float:
        """
        Compute fractional Kelly percentage from stats.

        If arguments are None, uses rolling window stats.

        Args:
            win_rate: Fraction of winning trades [0, 1]
            avg_win: Average win in dollars (positive)
            avg_loss: Average loss in dollars (positive magnitude)

        Returns:
            Fractional Kelly as a fraction of account (capped at kelly_fraction)
        """
        if win_rate is None or avg_win is None or avg_loss is None:
            win_rate, avg_win, avg_loss = self._compute_rolling_stats()

        if win_rate is None or avg_win is None or avg_loss is None:
            return 0.0

        loss_rate = 1.0 - win_rate
        if avg_win <= 0:
            return 0.0

        full_kelly = (win_rate * avg_win - loss_rate * avg_loss) / avg_win

        if full_kelly <= 0:
            logger.debug("KellySizer: negative Kelly, returning 0")
            return 0.0

        fractional = min(full_kelly * self.kelly_fraction, self.kelly_fraction)
        return fractional

    def _compute_rolling_stats(self):
        """Compute win rate, avg win, avg loss from rolling results buffer."""
        if len(self._results) < self.min_trades_for_kelly:
            return None, None, None

        results = list(self._results)
        wins = [r for r in results if r > 0]
        losses = [r for r in results if r <= 0]

        if not wins or not losses:
            return None, None, None

        win_rate = len(wins) / len(results)
        avg_win = np.mean(wins)
        avg_loss = abs(np.mean(losses))
        return win_rate, avg_win, avg_loss

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def get_position_size(
        self,
        confidence: float,
        vol_regime: float,
        macro_flag: int,
        rvol: float,
    ) -> int:
        """
        Determine number of contracts to trade.

        Sizing rules (applied sequentially):
            1. macro_flag == 1 → 0 contracts (hard block)
            2. vol_regime == 3 (extreme) → 0 contracts
            3. Base = 1 contract
            4. confidence > 0.75 AND rvol > 1.2 AND vol_regime ∉ {2, 3} → 2 contracts
            5. Clip to [0, max_contracts]

        Args:
            confidence: Model confidence in best signal [0, 1]
            vol_regime: Volatility regime (0=low, 1=normal, 2=high, 3=extreme)
            macro_flag: Binary macro event flag (1 = blackout)
            rvol: Relative volume ratio

        Returns:
            Integer number of contracts (0, 1, or 2)
        """
        # Hard blocks
        if macro_flag == 1:
            logger.debug("KellySizer: macro event blackout, 0 contracts")
            return 0

        if vol_regime >= 3:  # extreme
            logger.debug("KellySizer: extreme vol regime, 0 contracts")
            return 0

        # Base size
        contracts = 1

        # Scale up on high-confidence, high-volume, normal vol signals
        if confidence > 0.75 and rvol > 1.2 and vol_regime < 2:
            contracts = 2

        return min(contracts, self.max_contracts)

    def get_stats_summary(self) -> dict:
        """Return current rolling statistics as a dict."""
        win_rate, avg_win, avg_loss = self._compute_rolling_stats()
        kelly = self.compute_kelly(win_rate, avg_win, avg_loss)

        results = list(self._results)
        wins = [r for r in results if r > 0]
        losses = [r for r in results if r <= 0]

        return {
            "trade_count": self._trade_count,
            "rolling_trades": len(results),
            "win_rate": round(win_rate or 0.0, 4),
            "avg_win": round(avg_win or 0.0, 2),
            "avg_loss": round(avg_loss or 0.0, 2),
            "kelly_fraction": round(kelly, 4),
            "profit_factor": round(
                sum(wins) / max(abs(sum(losses)), 1e-6), 3
            ) if wins and losses else None,
        }
