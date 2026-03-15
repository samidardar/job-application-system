"""
Alpaca Markets API broker integration (paper + live).

Supports:
    - Market + bracket orders for NQ/ES futures
    - Real-time 5-min bar streaming
    - Full inference pipeline on each new bar
"""

import asyncio
import os
from datetime import datetime
from typing import Callable, Optional

import structlog

logger = structlog.get_logger()


class AlpacaBroker:
    """
    Alpaca Markets API integration using alpaca-py SDK.

    Switch between paper and live by setting paper=True/False.
    API keys loaded from environment: ALPACA_API_KEY, ALPACA_SECRET_KEY.
    """

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        paper: bool = True,
    ):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        self.paper = paper
        self._trading_client = None
        self._data_client = None
        self._stream_client = None

    def connect(self) -> None:
        """Initialize Alpaca TradingClient and DataClient."""
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient

            self._trading_client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
            account = self._trading_client.get_account()
            logger.info(
                "AlpacaBroker.connect: connected",
                paper=self.paper,
                equity=account.equity,
            )
        except ImportError:
            logger.error("AlpacaBroker: alpaca-py not installed. Run: pip install alpaca-py")
            raise
        except Exception as e:
            logger.error(f"AlpacaBroker.connect: failed — {e}")
            raise

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "market",
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Submit a market or bracket order.

        Args:
            symbol: Alpaca ticker (e.g., 'NQ1!')
            side: 'buy' or 'sell'
            qty: Number of contracts
            order_type: 'market' or 'limit'
            take_profit_price: TP limit price (bracket order)
            stop_loss_price: SL stop price (bracket order)

        Returns:
            Order dict with id, fill_price, status
        """
        if self._trading_client is None:
            raise RuntimeError("AlpacaBroker not connected. Call connect() first.")

        try:
            from alpaca.trading.requests import MarketOrderRequest, OrderClass
            from alpaca.trading.requests import TakeProfitRequest, StopLossRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

            if take_profit_price and stop_loss_price:
                # Bracket order
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.GTC,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=take_profit_price),
                    stop_loss=StopLossRequest(stop_price=stop_loss_price),
                )
            else:
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=TimeInForce.DAY,
                )

            order = self._trading_client.submit_order(order_request)
            result = {
                "order_id": str(order.id),
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "status": str(order.status),
                "submitted_at": str(order.submitted_at),
            }
            logger.info("AlpacaBroker.submit_order", **result)
            return result

        except Exception as e:
            logger.error(f"AlpacaBroker.submit_order: failed — {e}")
            return None

    def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position for a symbol."""
        if self._trading_client is None:
            return None
        try:
            pos = self._trading_client.get_open_position(symbol)
            return {
                "symbol": symbol,
                "qty": float(pos.qty),
                "side": str(pos.side),
                "avg_entry_price": float(pos.avg_entry_price),
                "unrealized_pnl": float(pos.unrealized_pl),
                "current_price": float(pos.current_price),
            }
        except Exception:
            return None  # No position

    def get_account(self) -> dict:
        """Get account summary."""
        if self._trading_client is None:
            return {}
        try:
            acct = self._trading_client.get_account()
            return {
                "equity": float(acct.equity),
                "buying_power": float(acct.buying_power),
                "cash": float(acct.cash),
                "daily_pnl": float(getattr(acct, "equity_previous_close", 0) or 0),
            }
        except Exception as e:
            logger.error(f"AlpacaBroker.get_account: {e}")
            return {}

    def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        if self._trading_client:
            self._trading_client.cancel_orders()
            logger.info("AlpacaBroker: cancelled all orders")

    def close_all_positions(self) -> None:
        """Close all open positions."""
        if self._trading_client:
            self._trading_client.close_all_positions(cancel_orders=True)
            logger.info("AlpacaBroker: closed all positions")

    def stream_bars(
        self,
        symbols: list,
        callback: Callable,
        bar_timeframe: str = "5Min",
    ) -> None:
        """
        Stream real-time bars and call `callback` on each new bar.

        The callback receives a bar dict and should run the full inference
        pipeline → check risk → submit order if approved.

        Args:
            symbols: List of ticker symbols
            callback: Async callable(bar: dict) → None
            bar_timeframe: Bar timeframe string
        """
        try:
            from alpaca.data.live import StockDataStream

            stream = StockDataStream(api_key=self.api_key, secret_key=self.secret_key)

            async def _bar_handler(bar):
                bar_dict = {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
                await callback(bar_dict)

            for sym in symbols:
                stream.subscribe_bars(_bar_handler, sym)

            logger.info(f"AlpacaBroker: starting bar stream for {symbols}")
            stream.run()

        except ImportError:
            logger.error("AlpacaBroker.stream_bars: alpaca-py not installed")
            raise
        except Exception as e:
            logger.error(f"AlpacaBroker.stream_bars: failed — {e}")
            raise
