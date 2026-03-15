# NQ/ES Deep Learning Day Trading System — Setup Guide

## Prerequisites

- **OS**: Windows 11 (for NinjaTrader 8) or Linux/macOS (for cloud training)
- **Python**: 3.11+
- **GPU**: NVIDIA RTX 5070 (Blackwell, 12GB GDDR7) — **CUDA 12.6+ required**
- **NinjaTrader 8**: For live execution (optional for training/backtesting)
- **Alpaca Markets Account**: Paper trading account (free at alpaca.markets)

---

## 1. Environment Setup

### Option A — pip (recommended)

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# Install PyTorch with CUDA 12.6 support for RTX 5070
pip install torch==2.5.1+cu126 torchvision==0.20.1+cu126 \
    --index-url https://download.pytorch.org/whl/cu126

# Install all other dependencies
pip install -r requirements.txt
```

### Option B — conda

```bash
conda create -n trading python=3.11
conda activate trading
pip install torch==2.5.1+cu126 --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
```

### Verify GPU

```python
import torch
print(torch.cuda.is_available())          # True
print(torch.cuda.get_device_name(0))      # NVIDIA GeForce RTX 5070
print(torch.cuda.get_device_capability()) # (10, 0) for Blackwell
```

---

## 2. Environment Variables

Create a `.env` file in the project root (never commit this file):

```bash
# .env
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
```

Or export directly:

```bash
export ALPACA_API_KEY=your_alpaca_api_key
export ALPACA_SECRET_KEY=your_alpaca_secret_key
```

Get your API keys at: https://app.alpaca.markets → API Keys

---

## 3. Step-by-Step Run Instructions

### Step 1 — Download Data

```bash
cd nq_es_trading_system

# Full download (requires Alpaca API keys)
python scripts/download_data.py --years 3

# Dry run (no API keys needed — uses synthetic data)
python scripts/download_data.py --dry-run
```

**Expected output:**
```
✅ Download complete. Data saved to data/raw/
   - data/raw/ohlcv/NQ1_5Min_3y.parquet  (~45MB)
   - data/raw/ohlcv/ES1_5Min_3y.parquet  (~45MB)
   - data/raw/vix/vix_daily.parquet
   - data/raw/news/news_with_sentiment.parquet
```

### Step 2 — Run Tests

```bash
cd nq_es_trading_system
pytest tests/ -v
```

All tests must pass before proceeding to training.

**Expected output:**
```
tests/test_features.py::TestNoLookaheadVWAP::test_vwap_uses_no_future_data PASSED
tests/test_features.py::TestNoLookaheadVWAP::test_vwap_resets_at_session_start PASSED
...
tests/test_risk.py::TestDailyReset::test_auto_reset_on_new_day PASSED
============================== X passed in X.Xs ==============================
```

### Step 3 — Train the Full Pipeline

```bash
# Full training (3 years, Optuna tuning, walk-forward validation)
python scripts/train_full.py

# Dry run (synthetic data, skip Optuna tuning — ~10 minutes)
python scripts/train_full.py --dry-run --skip-tuning

# Single symbol
python scripts/train_full.py --symbol NQ1!
```

**Expected RTX 5070 training times:**
| Step | Time |
|------|------|
| FinBERT preprocessing | ~10 min (first run, cached after) |
| Feature engineering | ~5 min |
| Optuna regime tuning (50 trials) | ~15 min |
| Optuna signal model (30 trials) | ~20 min |
| Walk-forward validation (5 folds) | ~45 min |
| **Total** | **~95 min** |

**Expected output:**
```
┌───────────────────────────────────────────────┐
│  WALK-FORWARD VALIDATION RESULTS              │
│  Fold 1: Sharpe X.XX | DD X.X% ✅             │
│  Fold 2: Sharpe X.XX | DD X.X% ✅             │
│  Fold 3: Sharpe X.XX | DD X.X% ✅             │
│  Fold 4: Sharpe X.XX | DD X.X% ✅             │
│  Fold 5: Sharpe X.XX | DD X.X% ✅             │
│  AGGREGATE: Sharpe X.XX | Sortino X.XX        │
│  Status: ✅ PASS                              │
└───────────────────────────────────────────────┘
```

### Step 4 — View Backtest Report

```bash
# Open in browser
open backtesting/reports/walk_forward_report.html
```

### Step 5 — Launch Streamlit Dashboard

```bash
streamlit run dashboard/app.py
# Open: http://localhost:8501
```

### Step 6 — Start Paper Trading

```bash
# Paper trading only
python scripts/run_paper_trading.py

# With Streamlit dashboard
python scripts/run_paper_trading.py --dashboard

# With NT8 bridge (NT8 must be running with strategy loaded)
python scripts/run_paper_trading.py --nt8 --dashboard

# Dry run replay (historical bars)
python scripts/run_paper_trading.py --dry-run
```

---

## 4. NinjaTrader 8 Installation

### Install NinjaScript Strategy

1. Open NinjaTrader 8
2. Go to: **Tools → Edit NinjaScript → Strategy**
3. Click **Import** and select `ninjatrader/NQ_ES_SignalReceiver.cs`
4. Alternatively: Copy the file to:
   ```
   Documents\NinjaTrader 8\bin\Custom\Strategies\NQ_ES_SignalReceiver.cs
   ```
5. In NinjaTrader: **Tools → Edit NinjaScript → Compile NinjaScript**

### Configure the Strategy

1. Open a NQ or ES chart (5-min bars, CME session)
2. Right-click chart → **Strategies → Add Strategy**
3. Select **NQ_ES_SignalReceiver**
4. Set parameters:
   - `BridgeHost`: 127.0.0.1
   - `BridgePort`: 5555
   - `MaxDailyLoss`: 500
   - `MaxContractsPerTrade`: 2

### Start the Python Bridge

```bash
# Start Python system with NT8 bridge enabled
python scripts/run_paper_trading.py --nt8

# The strategy in NT8 will receive signals as JSON over TCP
```

**Signal format sent by Python:**
```json
{
  "timestamp": "2024-01-15T10:30:00",
  "instrument": "NQ",
  "action": "BUY",
  "contracts": 1,
  "entry_price": 18500.25,
  "take_profit": 18545.25,
  "stop_loss": 18481.50,
  "confidence": 0.78,
  "regime": "mean_reversion"
}
```

---

## 5. Project Structure Reference

```
nq_es_trading_system/
├── config/                   # YAML configuration files
├── data/                     # Raw + processed data
├── features/                 # Feature engineering modules (no lookahead)
├── labels/                   # Triple barrier labeling
├── models/                   # ML model architectures
│   └── saved/                # Trained model artifacts
├── training/                 # Training loops + walk-forward validation
├── backtesting/              # Simulation engine + metrics + HTML reports
│   └── reports/              # Generated reports
├── execution/                # Alpaca broker + risk manager + NT8 bridge
├── dashboard/                # Streamlit web dashboard
├── tests/                    # pytest unit tests
├── scripts/                  # CLI scripts
└── ninjatrader/              # NinjaScript C# strategy
```

---

## 6. Configuration Overview

| File | Purpose |
|------|---------|
| `config/model_config.yaml` | Model hyperparams, TCN channels, attention heads |
| `config/risk_config.yaml` | Daily loss limits, Kelly fraction, circuit breakers |
| `config/data_config.yaml` | Symbols, timeframes, API endpoints |

**Key risk parameters** (edit `config/risk_config.yaml`):
```yaml
daily_loss_limit: 500          # Stop trading after -$500/day
max_drawdown_pct: 0.05         # Stop after -5% account drawdown
max_contracts_per_instrument: 2
max_trades_per_day: 8
kelly_fraction: 0.25           # Conservative 25% Kelly
```

---

## 7. GPU Memory Usage (RTX 5070 - 12GB)

| Component | VRAM Usage |
|-----------|------------|
| SignalModel (BF16) | ~0.5 GB |
| FinBERT (FP16, inference only) | ~1.5 GB |
| Training batch (256 × [20×8]) | ~0.3 GB |
| **Total peak** | **~3 GB** |

The system uses well under 12GB VRAM — no memory issues expected.

---

## 8. Troubleshooting

**`torch.compile` fails on first run:**
```bash
# Compile cache needs ~2 minutes to build on first run
# Subsequent runs are fast (~20% speedup)
```

**Alpaca API rate limit:**
```
AlpacaAPIError: 429 Too Many Requests
```
→ `download_data.py` includes automatic rate-limit handling (0.3s sleep between calls)

**CUDA not available:**
```python
import torch
print(torch.version.cuda)  # Should be 12.6+
# If wrong version: pip install torch==2.5.1+cu126 --index-url https://download.pytorch.org/whl/cu126
```

**NT8 bridge connection refused:**
→ Make sure NT8 strategy is loaded and running on a chart before starting `run_paper_trading.py --nt8`

---

## 9. Live Deployment Checklist

Before switching from paper to live trading:

- [ ] Paper trading for minimum 200 trades
- [ ] Live slippage within 50% of simulated slippage
- [ ] Win rate within 5pp of backtest
- [ ] No unhandled exceptions in 2-week paper run
- [ ] Start with 1 contract maximum (never 2 in first month)
- [ ] Hard stop at $2,500 drawdown = system OFF, manual review required
- [ ] Monthly model retraining scheduled
- [ ] Kill switch tested: `broker.close_all_positions()` executes in < 10s
