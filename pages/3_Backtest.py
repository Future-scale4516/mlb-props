import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Backtest")
sel_date = sidebar_date()

st.title("📊 Model Backtest")


def render_calibration(recs, market_name):
    c = _calib(recs, market_name)
    if not c:
        return
    st.markdown(f"#### {market_name}")
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Brier score", c["brier"])
    mc2.metric("Accuracy", f"{c['acc']}%")
    mc3.metric("Base rate", f"{c['base_rate']}%")
    cdf = pd.DataFrame(c["buckets"],
                       columns=["Predicted band", "Games", "Model avg %", "Actual %"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines",
                  line=dict(dash="dash", color="#aaa"), name="Perfect"))
    fig.add_trace(go.Scatter(x=cdf["Model avg %"], y=cdf["Actual %"],
                  mode="markers+lines", marker=dict(size=9, color="#a12c7b"),
                  name="Model"))
    fig.update_layout(height=300, xaxis_title="Model predicted %",
                  yaxis_title="Actual %", plot_bgcolor="#f9f8f5",
                  paper_bgcolor="#f7f6f2", margin=dict(l=10, r=10, t=10, b=10),
                  xaxis=dict(range=[0, 100]), yaxis=dict(range=[0, 100]),
                  font=dict(family="Inter"))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(cdf, use_container_width=True, hide_index=True)


st.divider()
st.markdown("## 📊 Game Bets Backtest — calibration")
st.caption("Checks the game model's probabilities against real final scores from recent "
           "completed games. Well-calibrated means: when it says 60%, that happens about "
           "60% of the time. Free (MLB results only) — no odds or quota needed.")
bt_days = st.slider("Days of completed games to test", 3, 30, 14, key="game_bt_days")
if st.button("Run game backtest"):
    with st.spinner("Fetching results and scoring the model against them..."):
        bt_recs, bt_days_done = run_backtest(sel_date, bt_days)
    if not bt_recs:
        st.warning("No completed games found in that window.")
    else:
        st.caption(f"Scored {len(bt_recs)//3} games across {bt_days_done} day(s). "
                   "Lower Brier = better; the model line should hug the dashed diagonal.")
        for bt_market in ["Moneyline (home win)", "Total Over 8.5", "Run line (home -1.5)"]:
            render_calibration(bt_recs, bt_market)
        st.caption("Caveats: uses current-season team/pitcher stats applied to past games "
                   "(mild lookahead), a fixed 8.5 totals line, and a league-average starter "
                   "when a probable isn't listed. This validates the model's calibration, "
                   "NOT whether you'd beat a bookmaker — a true profit backtest needs "
                   "historical odds (a paid feature) or forward-logged predictions over time.")

st.divider()
st.markdown("## 🎯 Player Prop Backtest — calibration")
st.caption("Checks the batter prop model (Home Run, Hits, RBI, Runs, and the combined "
           "'1+ of Runs/Hits/RBI' market) against real box scores from recent completed "
           "games — the same idea as the game backtest, but for props. This is the check "
           "that tells you whether prop edges are trustworthy the way game-bet edges are. "
           "Free — no odds or quota needed, but box scores mean more calls per game, so "
           "start with a smaller window.")
pbt_days = st.slider("Days of completed games to test", 3, 21, 7, key="prop_bt_days")
if st.button("Run player prop backtest"):
    with st.spinner("Fetching box scores and scoring the prop model against them "
                     "(this can take a little longer than the game backtest)..."):
        pbt_recs, pbt_days_done, pbt_games = run_prop_backtest(sel_date, pbt_days)
    if not pbt_recs:
        st.warning("No completed games with usable box scores found in that window.")
    else:
        st.caption(f"Scored {pbt_games} game(s) across {pbt_days_done} day(s) — "
                   f"{len(pbt_recs)} batter-market outcomes in total. Lower Brier = better; "
                   "the model line should hug the dashed diagonal.")
        for pbt_market in ["Home Run", "Hits", "RBI", "Runs", "Runs+Hits+RBI (1+)"]:
            render_calibration(pbt_recs, pbt_market)
        st.caption("Caveats: uses current-season batter/pitcher stats applied to past games "
                   "(mild lookahead), and each batter's real starting slot from the box score "
                   "(so plate-appearance estimates match what actually happened, not a "
                   "pre-game lineup guess). The '1+ of Runs/Hits/RBI' market is estimated by "
                   "combining the three single-market probabilities as if independent — a "
                   "reasonable approximation, not exact, since a hit that leads to a run isn't "
                   "fully independent of the run itself. This validates model calibration, NOT "
                   "whether you'd beat a bookmaker on props.")
