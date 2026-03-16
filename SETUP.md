# NQ/ES Mean Reversion Deep Learning Trading System

## Prerequisites

- **OS**: Windows 11 (for NinjaTrader 8) or Linux/macOS (for training)
- **Python**: 3.11+
- **GPU**: NVIDIA GTX 1650 (Turing, 4GB GDDR5/6) — **CUDA 11.8+ required**
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

# Install PyTorch with CUDA 11.8 for GTX 1650
pip install torch==2.5.1+cu118 torchvision==0.20.1+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# Install all other dependencies
pip install -r requirements.txt
```

### Option B — conda

```bash
conda create -n trading python=3.11
conda activate trading
conda install pytorch torchvision pytorch-cuda=11.8 -c pytorch -c nvidia
pip install -r requirements.txt
```

### Verify GPU

```python
import torch
print(torch.cuda.is_available())          # True
print(torch.cuda.get_device_name(0))      # NVIDIA GeForce GTX 1650
print(torch.cuda.get_device_capability()) # (7, 5) for Turing
print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")  # ~4.0 GB
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

Get your API keys at: https://app.alpaca.markets

---

## 3. Step-by-Step Run Instructions

### Step 1 — Download Data

```bash
# Full download (requires Alpaca API keys)
python scripts/download_data.py --years 3

# Dry run (no API keys needed — uses synthetic data)
python scripts/download_data.py --dry-run
```

### Step 2 — Run Tests

```bash
pytest tests/ -v
```

All tests must pass before training.

### Step 3 — Train the Full Pipeline

```bash
# Full training (3 years, Optuna tuning, walk-forward validation)
python scripts/train_full.py

# Dry run (synthetic data, skip Optuna tuning)
python scripts/train_full.py --dry-run --skip-tuning

# Single symbol
python scripts/train_full.py --symbol NQ1!
```

**Expected GTX 1650 training times:**
| Step | Time |
|------|------|
| FinBERT preprocessing (CPU) | ~25 min (first run, cached after) |
| Feature engineering | ~5 min |
| Optuna regime tuning (50 trials) | ~20 min |
| Optuna signal model (30 trials) | ~35 min |
| Walk-forward validation (5 folds) | ~90 min |
| **Total** | **~175 min (~3 hours)** |

### Step 4 — View Backtest Report

```bash
open backtesting/reports/walk_forward_report.html
```

### Step 5 — Launch Streamlit Dashboard

```bash
streamlit run dashboard/app.py
# Open: http://localhost:8501
```

### Step 6 — Start Paper Trading

```bash
python scripts/run_paper_trading.py                    # Paper trading
python scripts/run_paper_trading.py --dashboard        # + Streamlit
python scripts/run_paper_trading.py --nt8 --dashboard  # + NT8 bridge
python scripts/run_paper_trading.py --dry-run          # Replay historical
```

---

## 4. NinjaTrader 8 Installation

1. Copy `ninjatrader/NQ_ES_SignalReceiver.cs` to:
   ```
   Documents\NinjaTrader 8\bin\Custom\Strategies\
   ```
2. In NinjaTrader: **Tools > Edit NinjaScript > Compile NinjaScript**
3. Add strategy to NQ/ES chart (5-min bars)
4. Set: `BridgeHost=127.0.0.1`, `BridgePort=5555`, `MaxDailyLoss=500`
5. Start Python: `python scripts/run_paper_trading.py --nt8`

---

## 5. GTX 1650 Memory Budget (4GB VRAM)

| Component | VRAM Usage |
|-----------|------------|
| SignalModel (FP16, ~2M params) | ~0.3 GB |
| Training batch (64 x [20x8]) | ~0.15 GB |
| Gradients + optimizer states | ~0.8 GB |
| PyTorch CUDA overhead | ~0.5 GB |
| **Total peak during training** | **~1.75 GB** |
| FinBERT | **0 GB** (runs on CPU) |

The model fits comfortably in 4GB. Key constraints:
- **Batch size capped at 64** (larger batches may OOM with gradients)
- **FinBERT on CPU** (420MB model — can't share 4GB with training)
- **FP16 autocast** with GradScaler (Turing supports FP16, not BF16)
- **torch.compile disabled** (Turing doesn't benefit, adds 2min compile overhead)

---

## 6. Configuration

| File | Purpose |
|------|---------|
| `config/model_config.yaml` | TCN channels, batch size, FP16 settings |
| `config/risk_config.yaml` | Daily loss limits, Kelly, circuit breakers |
| `config/data_config.yaml` | Symbols, timeframes, API endpoints |

**Key risk parameters** (`config/risk_config.yaml`):
```yaml
daily_loss_limit: 500          # Stop after -$500/day
max_drawdown_pct: 0.05         # Stop after -5% account drawdown
max_contracts_per_instrument: 2
max_trades_per_day: 8
kelly_fraction: 0.25           # Conservative 25% Kelly
```

---

## 7. Troubleshooting

**CUDA out of memory:**
→ Reduce batch_size in `config/model_config.yaml` from 64 to 32
→ Check no other process using GPU: `nvidia-smi`

**CUDA not available:**
```bash
pip install torch==2.5.1+cu118 --index-url https://download.pytorch.org/whl/cu118
```

**FinBERT slow on CPU:**
→ This is expected (~25 min for 2 years of news)
→ Results are cached — only runs once, subsequent runs load from parquet

**Alpaca API 429 rate limit:**
→ Automatic retry with sleep built into `download_data.py`

---

## 8. Live Deployment Checklist

- [ ] Paper trading for minimum 200 trades
- [ ] Live slippage within 50% of simulated slippage
- [ ] Win rate within 5pp of backtest
- [ ] No unhandled exceptions in 2-week paper run
- [ ] Start with 1 contract only (never 2 in first month)
- [ ] Hard stop at $2,500 drawdown = system OFF
- [ ] Monthly model retraining scheduled
- [ ] Kill switch tested: `broker.close_all_positions()` in < 10s
