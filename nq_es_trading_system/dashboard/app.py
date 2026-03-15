"""
Streamlit Evaluation Dashboard for NQ/ES Trading System.

4 tabs:
    1. Model Performance — equity curve, Sharpe, confusion matrix, SHAP
    2. Trade Analysis   — trade log, P&L heatmaps, MAE/MFE scatter
    3. Risk Metrics     — VaR, Monte Carlo, sizing distribution
    4. Live Monitor     — real-time regime, positions, daily P&L, circuit breakers

Run: streamlit run dashboard/app.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---- Page config ----
st.set_page_config(
    page_title="NQ/ES Trading System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

RESULTS_PATH = Path("backtesting/reports")
MODELS_PATH = Path("models/saved")


# ---- Helpers ----

def _load_results() -> dict:
    """Load cached backtest results from disk (parquet/pickle)."""
    trade_path = RESULTS_PATH / "trade_log.parquet"
    equity_path = RESULTS_PATH / "equity_curve.parquet"
    metrics_path = RESULTS_PATH / "metrics.parquet"

    results = {}
    if trade_path.exists():
        results["trades"] = pd.read_parquet(trade_path)
    else:
        results["trades"] = pd.DataFrame()

    if equity_path.exists():
        results["equity"] = pd.read_parquet(equity_path).squeeze()
    else:
        results["equity"] = pd.Series(dtype=float)

    if metrics_path.exists():
        results["metrics"] = pd.read_parquet(metrics_path)
    else:
        results["metrics"] = pd.DataFrame()

    return results


def _load_live_state() -> dict:
    """Load live trading state from disk (written by run_paper_trading.py)."""
    live_path = Path("data/live_state.json")
    if live_path.exists():
        import json
        with open(live_path) as f:
            return json.load(f)
    return {
        "regime_probs": {"mean_reversion": 0.0, "momentum": 0.0, "chop": 1.0},
        "open_positions": [],
        "daily_pnl": 0.0,
        "daily_target": 500.0,
        "circuit_breakers": {
            "daily_stop": False,
            "drawdown_stop": False,
            "max_trades": False,
        },
        "last_signals": [],
        "account_equity": 50000.0,
    }


def _make_gauge(value: float, title: str, min_val: float = 0, max_val: float = 1) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value * 100,
            title={"text": title, "font": {"size": 13}},
            number={"suffix": "%", "font": {"size": 20}},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#00d2ff"},
                "steps": [
                    {"range": [0, 40], "color": "#2c2c54"},
                    {"range": [40, 70], "color": "#474787"},
                    {"range": [70, 100], "color": "#0f3460"},
                ],
                "threshold": {"line": {"color": "#e74c3c", "width": 3}, "value": 60},
            },
        )
    )
    fig.update_layout(
        height=180, margin=dict(t=40, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", font_color="white",
    )
    return fig


# ====================================================================
# MAIN APP
# ====================================================================

st.title("📈 NQ/ES Deep Learning Trading System")
st.markdown("*$50K Account | Mean Reversion | 5-min Bars*")

tab1, tab2, tab3, tab4 = st.tabs([
    "🏆 Model Performance",
    "📊 Trade Analysis",
    "⚠️ Risk Metrics",
    "🔴 Live Monitor",
])

results = _load_results()
trades = results["trades"]
equity = results["equity"]
metrics_df = results["metrics"]

# ====================================================================
# TAB 1 — MODEL PERFORMANCE
# ====================================================================
with tab1:
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("Equity Curve")
        if not equity.empty:
            fig_eq = px.area(
                x=equity.index, y=equity.values,
                labels={"x": "Date", "y": "Equity ($)"},
                color_discrete_sequence=["#2ecc71"],
            )
            fig_eq.update_layout(
                paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                font_color="white", height=350,
            )
            st.plotly_chart(fig_eq, use_container_width=True)
        else:
            st.info("No backtest results found. Run `scripts/train_full.py` first.")

    with col_right:
        st.subheader("Key Metrics")
        if not metrics_df.empty:
            agg = metrics_df[metrics_df["Fold"] == "AGG"]
            if not agg.empty:
                row = agg.iloc[0]
                st.metric("Sharpe Ratio", row.get("Sharpe", "—"))
                st.metric("Sortino Ratio", row.get("Sortino", "—"))
                st.metric("Max Drawdown", row.get("MaxDD", "—"))
                st.metric("Win Rate", row.get("WinRate", "—"))
                st.metric("Profit Factor", row.get("PF", "—"))
        else:
            st.info("Run walk-forward validation to see metrics.")

    st.divider()
    st.subheader("Per-Fold Metrics")
    if not metrics_df.empty:
        st.dataframe(metrics_df, use_container_width=True)

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Win/Loss Distribution")
        if not trades.empty and "pnl" in trades.columns:
            fig_hist = go.Figure()
            wins = trades["pnl"][trades["pnl"] >= 0]
            losses = trades["pnl"][trades["pnl"] < 0]
            fig_hist.add_trace(go.Histogram(x=wins, name="Wins", marker_color="#2ecc71", opacity=0.75, nbinsx=30))
            fig_hist.add_trace(go.Histogram(x=losses, name="Losses", marker_color="#e74c3c", opacity=0.75, nbinsx=30))
            fig_hist.update_layout(
                barmode="overlay", paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                font_color="white", height=300, legend=dict(bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    with col_b:
        st.subheader("Rolling 20-Trade Sharpe")
        if not trades.empty and "pnl" in trades.columns:
            rolling_returns = trades["pnl"].rolling(20, min_periods=5)
            rolling_sharpe = rolling_returns.mean() / rolling_returns.std().replace(0, np.nan) * np.sqrt(252)
            fig_rs = px.line(
                x=trades.index, y=rolling_sharpe,
                labels={"x": "Trade #", "y": "Rolling Sharpe"},
                color_discrete_sequence=["#00d2ff"],
            )
            fig_rs.add_hline(y=1.5, line_dash="dash", line_color="#f39c12", annotation_text="Target 1.5")
            fig_rs.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e", font_color="white", height=300)
            st.plotly_chart(fig_rs, use_container_width=True)

    st.subheader("Feature Importance (SHAP)")
    shap_path = MODELS_PATH / "shap_importance.parquet"
    if shap_path.exists():
        shap_df = pd.read_parquet(shap_path)
        fig_shap = px.bar(
            shap_df.head(20),
            x="importance", y="feature",
            orientation="h",
            color="importance",
            color_continuous_scale="Blues",
            labels={"importance": "Mean |SHAP|", "feature": "Feature"},
        )
        fig_shap.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                               font_color="white", height=500, showlegend=False)
        st.plotly_chart(fig_shap, use_container_width=True)
    else:
        st.info("SHAP values not computed yet. Train model first.")

# ====================================================================
# TAB 2 — TRADE ANALYSIS
# ====================================================================
with tab2:
    st.subheader("Trade Log")
    if not trades.empty:
        st.dataframe(
            trades.sort_values("entry_time", ascending=False).head(500),
            use_container_width=True,
        )
    else:
        st.info("No trades to display.")

    st.divider()
    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("P&L by Hour of Day")
        if not trades.empty and "entry_time" in trades.columns:
            tl = trades.copy()
            tl["hour"] = pd.to_datetime(tl["entry_time"]).dt.hour
            by_hour = tl.groupby("hour")["pnl"].sum().reset_index()
            by_hour["color"] = by_hour["pnl"].apply(lambda x: "#2ecc71" if x >= 0 else "#e74c3c")
            fig_h = px.bar(
                by_hour, x="hour", y="pnl",
                labels={"hour": "Hour (ET)", "pnl": "Total P&L ($)"},
                color="color", color_discrete_map="identity",
            )
            fig_h.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                                font_color="white", height=300, showlegend=False)
            st.plotly_chart(fig_h, use_container_width=True)

    with col_d:
        st.subheader("P&L by Day of Week")
        if not trades.empty and "entry_time" in trades.columns:
            tl = trades.copy()
            tl["dow"] = pd.to_datetime(tl["entry_time"]).dt.day_name()
            by_dow = tl.groupby("dow")["pnl"].sum().reindex(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            ).reset_index()
            fig_d = px.bar(
                by_dow, x="dow", y="pnl",
                color="pnl", color_continuous_scale=["#e74c3c", "#2ecc71"],
                labels={"dow": "Day", "pnl": "Total P&L ($)"},
            )
            fig_d.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                                font_color="white", height=300, showlegend=False)
            st.plotly_chart(fig_d, use_container_width=True)

    st.subheader("Drawdown (Underwater Equity Curve)")
    if not equity.empty:
        rolling_max = equity.cummax()
        dd = (equity - rolling_max) / rolling_max.replace(0, np.nan) * 100
        fig_dd = px.area(
            x=dd.index, y=dd.values,
            labels={"x": "Date", "y": "Drawdown (%)"},
            color_discrete_sequence=["#e74c3c"],
        )
        fig_dd.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                             font_color="white", height=280)
        st.plotly_chart(fig_dd, use_container_width=True)

# ====================================================================
# TAB 3 — RISK METRICS
# ====================================================================
with tab3:
    col_e, col_f = st.columns(2)

    with col_e:
        st.subheader("Historical VaR")
        if not trades.empty and "pnl" in trades.columns:
            pnl = trades["pnl"].dropna().sort_values()
            var_95 = float(np.percentile(pnl, 5))
            var_99 = float(np.percentile(pnl, 1))

            st.metric("VaR 95%", f"${var_95:.0f}")
            st.metric("VaR 99%", f"${var_99:.0f}")

            fig_var = px.histogram(
                pnl, nbins=40,
                labels={"value": "Trade P&L ($)", "count": "Frequency"},
                color_discrete_sequence=["#3498db"],
            )
            fig_var.add_vline(x=var_95, line_color="#f39c12", line_dash="dash",
                              annotation_text="VaR 95%")
            fig_var.add_vline(x=var_99, line_color="#e74c3c", line_dash="dash",
                              annotation_text="VaR 99%")
            fig_var.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                                  font_color="white", height=300)
            st.plotly_chart(fig_var, use_container_width=True)

    with col_f:
        st.subheader("Monte Carlo Simulation (1000 paths × 90 days)")
        if not trades.empty and "pnl" in trades.columns:
            pnl_vals = trades["pnl"].dropna().values
            n_paths = 1000
            n_days = 90
            trades_per_day = max(len(trades) / max(len(trades) // 5, 1), 1)

            rng = np.random.default_rng(42)
            paths = np.zeros((n_paths, n_days))

            for p in range(n_paths):
                daily_returns = []
                for d in range(n_days):
                    n_t = max(int(rng.poisson(trades_per_day)), 1)
                    daily_returns.append(rng.choice(pnl_vals, size=n_t, replace=True).sum())
                paths[p] = np.cumsum(daily_returns)

            percentiles = {
                "p5": np.percentile(paths, 5, axis=0),
                "p50": np.percentile(paths, 50, axis=0),
                "p95": np.percentile(paths, 95, axis=0),
            }
            days = np.arange(1, n_days + 1)

            fig_mc = go.Figure()
            fig_mc.add_trace(go.Scatter(
                x=days, y=percentiles["p95"],
                fill=None, mode="lines", line_color="#2ecc71", name="95th"
            ))
            fig_mc.add_trace(go.Scatter(
                x=days, y=percentiles["p5"],
                fill="tonexty", mode="lines", line_color="#e74c3c",
                fillcolor="rgba(52,152,219,0.2)", name="5th"
            ))
            fig_mc.add_trace(go.Scatter(
                x=days, y=percentiles["p50"],
                mode="lines", line=dict(color="#00d2ff", width=2, dash="dash"), name="Median"
            ))
            fig_mc.add_hline(y=0, line_color="white", line_width=0.5)
            fig_mc.update_layout(
                paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                font_color="white", height=300,
                legend=dict(bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_mc, use_container_width=True)

    st.subheader("Gross vs Net P&L (Slippage & Commission Impact)")
    if not trades.empty and "gross_pnl" in trades.columns and "pnl" in trades.columns:
        fig_gross_net = go.Figure()
        cumgross = trades["gross_pnl"].cumsum()
        cumnet = trades["pnl"].cumsum()
        fig_gross_net.add_trace(go.Scatter(x=trades.index, y=cumgross, name="Gross P&L",
                                            line=dict(color="#f39c12")))
        fig_gross_net.add_trace(go.Scatter(x=trades.index, y=cumnet, name="Net P&L",
                                            line=dict(color="#2ecc71")))
        fig_gross_net.update_layout(paper_bgcolor="#1a1a2e", plot_bgcolor="#16213e",
                                    font_color="white", height=300,
                                    legend=dict(bgcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig_gross_net, use_container_width=True)

# ====================================================================
# TAB 4 — LIVE MONITOR
# ====================================================================
with tab4:
    # Auto-refresh every 60 seconds
    refresh = st.checkbox("Auto-refresh (60s)", value=False)
    if refresh:
        import time
        time.sleep(60)
        st.rerun()

    live = _load_live_state()

    st.subheader("Regime Probabilities (Current Bar)")
    col_g, col_h, col_i = st.columns(3)
    regimes = live.get("regime_probs", {})

    with col_g:
        st.plotly_chart(
            _make_gauge(regimes.get("mean_reversion", 0), "Mean Reversion"),
            use_container_width=True,
        )
    with col_h:
        st.plotly_chart(
            _make_gauge(regimes.get("momentum", 0), "Momentum"),
            use_container_width=True,
        )
    with col_i:
        st.plotly_chart(
            _make_gauge(regimes.get("chop", 1), "Chop"),
            use_container_width=True,
        )

    st.divider()
    col_j, col_k = st.columns(2)

    with col_j:
        st.subheader("Open Positions")
        positions = live.get("open_positions", [])
        if positions:
            st.dataframe(pd.DataFrame(positions), use_container_width=True)
        else:
            st.info("No open positions.")

    with col_k:
        st.subheader("Daily P&L Progress")
        daily_pnl = live.get("daily_pnl", 0.0)
        target = live.get("daily_target", 500.0)
        progress = max(min(daily_pnl / target, 1.0), 0.0)

        st.metric(
            label="Daily P&L",
            value=f"${daily_pnl:.0f}",
            delta=f"${daily_pnl:.0f} / ${target:.0f} target",
        )
        st.progress(progress)

        # Circuit breaker status
        st.subheader("Circuit Breakers")
        cb = live.get("circuit_breakers", {})
        for name, triggered in cb.items():
            color = "🔴" if triggered else "🟢"
            label = name.replace("_", " ").title()
            st.write(f"{color} **{label}**: {'TRIGGERED' if triggered else 'OK'}")

    st.subheader("Last 10 Signals")
    last_signals = live.get("last_signals", [])
    if last_signals:
        st.dataframe(pd.DataFrame(last_signals), use_container_width=True)
    else:
        st.info("No signals logged yet.")

    st.caption(f"Account Equity: ${live.get('account_equity', 50000):.2f}")
