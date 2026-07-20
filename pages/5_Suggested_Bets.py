import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Suggested Bets")
sel_date = sidebar_date()

st.title("📋 Suggested Bets")
st.caption("Auto-built doubles and trebles across Moneyline, Run Line, Totals, Runs, RBI, "
           "Total Bases, and Home Run — ranked by the model's raw probability (Model %), "
           "not just green/amber colour. A bigger amber edge isn't automatically riskier if "
           "the underlying probability is still sane; this picks whichever legs give the best "
           "realistic combined chance, the same way we build these by hand. No two legs in "
           "the same combo ever come from the same game. Hits is excluded here — use the "
           "Player Props page for Hits edges. Stakes are suggested by market trust tier "
           "(built from backtest history and real results, not a guarantee).")

col1, col2 = st.columns(2)
with col1:
    bankroll = st.number_input("Bankroll to allocate (£)", min_value=1.0, value=40.0, step=1.0)
with col2:
    prop_games = st.slider("Prop games to analyse (4 credits each)", 1, 20, 6)
st.caption(f"Projected prop-scan cost: up to {prop_games * 4} credits. Game-line scan is "
           "quota-light. Cached 15 min, so re-running with the same date/game count is free.")

MARKET_ORDER = ["Moneyline", "Run Line", "Totals", "Runs", "RBI", "Total Bases", "Home Run"]
STATUS_BADGE = {"pending": "⏳ Pending", "winning": "🟢 Winning", "losing": "🔴 Losing",
                "won": "✅ Won", "lost": "❌ Lost", "unknown": "❓ Unknown"}
COMBO_BADGE = {"alive": "🟢 Still alive", "won": "✅ Combo won!",
               "lost": "❌ Combo lost", "unknown": "❓ Uncertain — check manually"}

if st.button("Build suggested bets"):
    with st.spinner("Scanning every market and building combos..."):
        results, quota_meta = build_suggested_bets(sel_date, prop_games)
    st.session_state["suggested_results"] = results
    st.session_state["suggested_bankroll"] = bankroll
    st.session_state["suggested_quota_meta"] = quota_meta
    st.session_state.pop("suggested_live_status", None)  # clear any stale live check

if "suggested_results" in st.session_state:
    results = st.session_state["suggested_results"]
    bankroll_used = st.session_state.get("suggested_bankroll", bankroll)
    quota_meta = st.session_state.get("suggested_quota_meta", {})
    available_markets = [mk for mk, r in results.items() if r["double"] or r["treble"]]
    pmeta = quota_meta.get("props", {})
    if pmeta.get("remaining"):
        st.caption(f"Odds API quota — used {pmeta.get('used')}, remaining {pmeta.get('remaining')}")

    if not available_markets:
        st.warning("No markets have enough qualifying picks right now. Try again closer to "
                   "first pitch, or once lineups/odds are posted.")
    else:
        stakes = suggest_stakes(bankroll_used, available_markets)

        live_col1, live_col2 = st.columns([2, 3])
        with live_col1:
            check_live = st.button("🔴 Check live status")
        with live_col2:
            st.caption("Checks today's games right now — pending, live winning/losing, or "
                       "already won/lost. One lost leg kills the whole combo, same as a "
                       "real bet. Re-click any time during the day for an updated read.")
        if check_live:
            with st.spinner("Checking live scores and box scores..."):
                live_status = {}
                for market, r in results.items():
                    live_status[market] = {}
                    for combo_type in ("double", "treble"):
                        combo = r.get(combo_type)
                        if combo:
                            live_status[market][combo_type] = evaluate_combo_status(combo)
            st.session_state["suggested_live_status"] = live_status
        live_status = st.session_state.get("suggested_live_status")

        for market in MARKET_ORDER:
            r = results.get(market)
            st.divider()
            if not r or (not r["double"] and not r["treble"]):
                st.markdown(f"### {market}")
                st.write(f"No qualifying picks today. {r['note'] if r else ''}")
                continue

            stake = stakes.get(market, 0.0)
            st.markdown(f"### {market} — suggested stake £{stake:.2f}")
            if market == "Home Run":
                st.caption("Treat this as a lottery ticket, not a real expectation — multi-"
                           "homer/home-run props are inherently low-probability. Stake is "
                           "deliberately small and capped regardless of bankroll size.")

            c1, c2 = st.columns(2)
            for col, combo_type, label in [(c1, "double", "Double"), (c2, "treble", "Treble")]:
                combo = r[combo_type]
                with col:
                    st.markdown(f"**{label}**")
                    if combo is None:
                        st.caption("Not enough distinct-game picks available for this size.")
                        continue

                    leg_live = None
                    if live_status and market in live_status and combo_type in live_status[market]:
                        overall, leg_live = live_status[market][combo_type]
                        st.markdown(f"**{COMBO_BADGE.get(overall, overall)}**")

                    for i, leg in enumerate(combo["legs"]):
                        st.write(f"• **{leg['label']}** ({leg['game']}) @ {leg['odds']:.2f} "
                                 f"— {leg['model_pct']:.1f}% model")
                        if leg.get("reason"):
                            st.caption(leg["reason"])
                        if leg_live:
                            status, detail = leg_live[i]
                            st.caption(f"{STATUS_BADGE.get(status, status)} — {detail}")

                    mc1, mc2 = st.columns(2)
                    mc1.metric("Combined odds", f"{combo['combined_odds']:.2f}")
                    mc2.metric("Chance to land", f"{combo['combined_prob']*100:.1f}%")
                    st.metric(f"Return on £{stake:.2f}",
                              f"£{stake * combo['combined_odds']:.2f}")

        st.divider()
        st.caption("Combined odds and stakes are starting points, not instructions — always "
                   "confirm live prices at your book before staking, lines move. This tool "
                   "doesn't know about doubleheader game numbers when picking legs across "
                   "markets, so if two suggested legs land on the same day for the same "
                   "teams, double-check which specific game (1)/(2) each one refers to. "
                   "Live status is a same-day read only — nothing here is saved between "
                   "visits. Model is a work in progress — treat suggestions as a starting "
                   "point for your own judgement, not a guarantee.")
