"""
NinjaTrader 8 TCP socket bridge.

Sends JSON trade signals to NT8 NinjaScript strategy on localhost:5555.
The NT8 strategy (NQ_ES_SignalReceiver.cs) listens on this port and
executes bracket orders in the trading platform.

Signal format (JSON):
{
    "timestamp": "2024-01-15T10:30:00",
    "instrument": "NQ",
    "action": "BUY" | "SELL" | "CLOSE",
    "contracts": 1,
    "entry_price": 18500.25,
    "take_profit": 18545.25,
    "stop_loss": 18481.50,
    "confidence": 0.78,
    "regime": "mean_reversion"
}
"""

import json
import socket
import threading
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger()


class NinjaTraderBridge:
    """
    Simple TCP socket client that sends trade signals to NinjaTrader 8.

    NT8 runs the NQ_ES_SignalReceiver.cs strategy which binds a TCP server
    on localhost:5555. This bridge connects as a client and sends JSON signals.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5555, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Connect to NT8 TCP server. Returns True if successful."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            self._connected = True
            logger.info(f"NinjaTraderBridge: connected to {self.host}:{self.port}")
            return True
        except (ConnectionRefusedError, OSError) as e:
            logger.warning(f"NinjaTraderBridge: could not connect to NT8 ({e}). Signals will be logged only.")
            self._connected = False
            return False

    def send_signal(self, signal_dict: dict) -> bool:
        """
        Send a trade signal to NT8 via TCP.

        If not connected, logs the signal and returns False.

        Args:
            signal_dict: Signal payload (will be JSON-serialized + newline-terminated)

        Returns:
            True if sent successfully
        """
        if not self._connected or self._sock is None:
            logger.info("NinjaTraderBridge.send_signal (not connected, logging only)", signal=signal_dict)
            return False

        with self._lock:
            try:
                payload = json.dumps(signal_dict) + "\n"
                self._sock.sendall(payload.encode("utf-8"))
                logger.info("NinjaTraderBridge.send_signal: sent", signal=signal_dict)
                return True
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                logger.error(f"NinjaTraderBridge.send_signal: failed — {e}")
                self._connected = False
                return False

    def send_trade_signal(
        self,
        instrument: str,
        action: str,
        contracts: int,
        entry_price: float,
        take_profit: float,
        stop_loss: float,
        confidence: float,
        regime: str = "mean_reversion",
    ) -> bool:
        """
        Helper to send a structured trade signal.

        Args:
            instrument: 'NQ' or 'ES'
            action: 'BUY', 'SELL', or 'CLOSE'
            contracts: Number of contracts
            entry_price: Estimated entry price
            take_profit: Take-profit price level
            stop_loss: Stop-loss price level
            confidence: Model confidence [0, 1]
            regime: Regime label string

        Returns:
            True if sent successfully
        """
        signal = {
            "timestamp": datetime.now().isoformat(),
            "instrument": instrument,
            "action": action.upper(),
            "contracts": contracts,
            "entry_price": round(entry_price, 2),
            "take_profit": round(take_profit, 2),
            "stop_loss": round(stop_loss, 2),
            "confidence": round(confidence, 4),
            "regime": regime,
        }
        return self.send_signal(signal)

    def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._connected = False
            logger.info("NinjaTraderBridge: disconnected")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
