// NQ_ES_SignalReceiver.cs
// NinjaTrader 8 NinjaScript Strategy
//
// Receives JSON trade signals from the Python system via TCP on localhost:5555
// and executes bracket orders (market entry + TP + SL).
//
// INSTALLATION:
//   1. Copy to: Documents\NinjaTrader 8\bin\Custom\Strategies\
//   2. Compile in NinjaTrader: New > NinjaScript Editor > Compile
//   3. Add strategy to a chart (NQ or ES, 5-min bars)
//   4. Run Python bridge before starting the strategy
//
// Dependencies: Newtonsoft.Json (included in NT8 distribution)

#region Using declarations
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using NinjaTrader.Cbi;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using Newtonsoft.Json;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class NQ_ES_SignalReceiver : Strategy
    {
        // ----------------------------------------------------------------
        // Parameters
        // ----------------------------------------------------------------
        private string _host = "127.0.0.1";
        private int _port = 5555;
        private double _maxDailyLoss = 500.0;
        private int _maxContracts = 2;

        // ----------------------------------------------------------------
        // State
        // ----------------------------------------------------------------
        private TcpClient _tcpClient;
        private Thread _listenerThread;
        private volatile bool _isRunning;
        private readonly object _orderLock = new object();

        private double _dailyPnL = 0.0;
        private int _tradesPlaced = 0;
        private bool _dailyStopHit = false;
        private DateTime _lastResetDate = DateTime.MinValue;

        private double _entryPrice = 0.0;
        private string _pendingInstrument = "";
        private string _pendingAction = "";
        private int _pendingContracts = 0;
        private double _pendingTP = 0.0;
        private double _pendingSL = 0.0;
        private bool _hasPendingSignal = false;

        // ----------------------------------------------------------------
        // Strategy Properties (visible in UI)
        // ----------------------------------------------------------------
        [NinjaScriptProperty]
        public string BridgeHost { get => _host; set => _host = value; }

        [NinjaScriptProperty]
        public int BridgePort { get => _port; set => _port = value; }

        [NinjaScriptProperty]
        public double MaxDailyLoss { get => _maxDailyLoss; set => _maxDailyLoss = value; }

        [NinjaScriptProperty]
        public int MaxContractsPerTrade { get => _maxContracts; set => _maxContracts = value; }

        // ----------------------------------------------------------------
        // OnStateChange
        // ----------------------------------------------------------------
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "NQ_ES_SignalReceiver";
                Description = "Receives ML trading signals from Python system via TCP";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 900; // 15 min before close
            }
            else if (State == State.Configure)
            {
                SetProfitTarget("Long", CalculationMode.Price, 0); // Overridden per signal
                SetStopLoss("Long", CalculationMode.Price, 0, false);
            }
            else if (State == State.DataLoaded)
            {
                _isRunning = true;
                _listenerThread = new Thread(ListenForSignals)
                {
                    IsBackground = true,
                    Name = "SignalListenerThread"
                };
                _listenerThread.Start();
                Print("NQ_ES_SignalReceiver: started, listening on " + _host + ":" + _port);
            }
            else if (State == State.Terminated)
            {
                _isRunning = false;
                CloseConnection();
                if (Position.MarketPosition != MarketPosition.Flat)
                {
                    Print("NQ_ES_SignalReceiver: closing open positions on strategy stop");
                    ExitLong();
                    ExitShort();
                }
            }
        }

        // ----------------------------------------------------------------
        // OnBarUpdate — execute pending signals
        // ----------------------------------------------------------------
        protected override void OnBarUpdate()
        {
            // Reset daily state
            if (Time[0].Date != _lastResetDate)
            {
                _dailyPnL = 0.0;
                _tradesPlaced = 0;
                _dailyStopHit = false;
                _lastResetDate = Time[0].Date;
            }

            // Circuit breakers
            if (_dailyStopHit) return;
            if (_dailyPnL <= -_maxDailyLoss)
            {
                _dailyStopHit = true;
                Print($"NQ_ES_SignalReceiver: DAILY STOP HIT — P&L: ${_dailyPnL:F0}");
                return;
            }

            // Execute pending signal
            if (_hasPendingSignal && CurrentBar > 0)
            {
                lock (_orderLock)
                {
                    if (_hasPendingSignal)
                    {
                        ExecuteSignal();
                        _hasPendingSignal = false;
                    }
                }
            }
        }

        // ----------------------------------------------------------------
        // OnExecutionUpdate — track P&L
        // ----------------------------------------------------------------
        protected override void OnExecutionUpdate(
            Execution execution, string executionId, double price,
            int quantity, MarketPosition marketPosition,
            string orderId, DateTime time)
        {
            if (execution.Order.OrderState == OrderState.Filled)
            {
                _dailyPnL += execution.Profit;
                Print($"NQ_ES_SignalReceiver: execution P&L=${execution.Profit:F2} | DailyP&L=${_dailyPnL:F2}");
            }
        }

        // ----------------------------------------------------------------
        // ExecuteSignal — place bracket order
        // ----------------------------------------------------------------
        private void ExecuteSignal()
        {
            int qty = Math.Min(_pendingContracts, _maxContracts);
            if (qty <= 0) return;

            string tag = "ML_" + DateTime.Now.Ticks;

            if (_pendingAction == "BUY" && Position.MarketPosition == MarketPosition.Flat)
            {
                EnterLong(qty, tag);
                SetProfitTarget(tag, CalculationMode.Price, _pendingTP);
                SetStopLoss(tag, CalculationMode.Price, _pendingSL, false);
                _tradesPlaced++;
                Print($"NQ_ES_SignalReceiver: LONG {qty}x {Instrument.MasterInstrument.Name} " +
                      $"TP={_pendingTP} SL={_pendingSL}");
            }
            else if (_pendingAction == "SELL" && Position.MarketPosition == MarketPosition.Flat)
            {
                EnterShort(qty, tag);
                SetProfitTarget(tag, CalculationMode.Price, _pendingTP);
                SetStopLoss(tag, CalculationMode.Price, _pendingSL, false);
                _tradesPlaced++;
                Print($"NQ_ES_SignalReceiver: SHORT {qty}x {Instrument.MasterInstrument.Name} " +
                      $"TP={_pendingTP} SL={_pendingSL}");
            }
            else if (_pendingAction == "CLOSE")
            {
                ExitLong();
                ExitShort();
                Print("NQ_ES_SignalReceiver: CLOSE signal received");
            }
        }

        // ----------------------------------------------------------------
        // TCP Listener thread
        // ----------------------------------------------------------------
        private void ListenForSignals()
        {
            while (_isRunning)
            {
                try
                {
                    ConnectToServer();
                    if (_tcpClient == null || !_tcpClient.Connected)
                    {
                        Thread.Sleep(5000); // Retry after 5s
                        continue;
                    }

                    using var stream = _tcpClient.GetStream();
                    var buffer = new byte[4096];
                    var messageBuffer = new StringBuilder();

                    while (_isRunning && _tcpClient.Connected)
                    {
                        int bytesRead = stream.Read(buffer, 0, buffer.Length);
                        if (bytesRead == 0) break;

                        string chunk = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                        messageBuffer.Append(chunk);

                        // Process complete newline-terminated messages
                        string data = messageBuffer.ToString();
                        int nlIdx;
                        while ((nlIdx = data.IndexOf('\n')) >= 0)
                        {
                            string message = data.Substring(0, nlIdx).Trim();
                            data = data.Substring(nlIdx + 1);
                            if (!string.IsNullOrEmpty(message))
                            {
                                ProcessSignal(message);
                            }
                        }
                        messageBuffer.Clear();
                        messageBuffer.Append(data);
                    }
                }
                catch (Exception ex)
                {
                    if (_isRunning)
                    {
                        Print($"NQ_ES_SignalReceiver: listener error — {ex.Message}. Reconnecting in 5s...");
                        Thread.Sleep(5000);
                    }
                }
            }
        }

        private void ConnectToServer()
        {
            try
            {
                CloseConnection();
                _tcpClient = new TcpClient();
                _tcpClient.Connect(_host, _port);
                Print($"NQ_ES_SignalReceiver: connected to {_host}:{_port}");
            }
            catch (Exception ex)
            {
                Print($"NQ_ES_SignalReceiver: connection failed — {ex.Message}");
                _tcpClient = null;
            }
        }

        private void CloseConnection()
        {
            try { _tcpClient?.Close(); } catch { }
            _tcpClient = null;
        }

        // ----------------------------------------------------------------
        // ProcessSignal — parse JSON and queue for execution
        // ----------------------------------------------------------------
        private void ProcessSignal(string json)
        {
            try
            {
                dynamic signal = JsonConvert.DeserializeObject(json);
                if (signal == null) return;

                string action = (string)signal.action ?? "";
                int contracts = (int)(signal.contracts ?? 1);
                double entryPrice = (double)(signal.entry_price ?? 0.0);
                double tp = (double)(signal.take_profit ?? 0.0);
                double sl = (double)(signal.stop_loss ?? 0.0);
                double confidence = (double)(signal.confidence ?? 0.5);
                string regime = (string)(signal.regime ?? "unknown");
                string instrument = (string)(signal.instrument ?? "");

                Print($"NQ_ES_SignalReceiver: signal received — {action} {contracts}x {instrument} " +
                      $"conf={confidence:F2} regime={regime}");

                // Queue for OnBarUpdate execution (thread-safe)
                lock (_orderLock)
                {
                    _pendingAction = action;
                    _pendingContracts = contracts;
                    _entryPrice = entryPrice;
                    _pendingTP = tp;
                    _pendingSL = sl;
                    _pendingInstrument = instrument;
                    _hasPendingSignal = true;
                }
            }
            catch (Exception ex)
            {
                Print($"NQ_ES_SignalReceiver: failed to parse signal — {ex.Message}\nRaw: {json}");
            }
        }
    }
}
