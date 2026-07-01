import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Game Bets")
sel_date = sidebar_date()

st.markdown("## 🎯 Game Bets — Money Line · Run Line · Totals")
st.caption("Estimates each team's runs with a Poisson model (starting pitchers + team "
           "offence), then compares to de-vigged UK odds to surface edges. Positive edge = "
           "model rates the bet better than the market price. Always confirm the live price "
           "at your book before staking — lines move.")
if st.button("Analyse game bets (UK odds)"):
    with st.spinner("Fetching schedule, team stats, pitchers and UK odds..."):
        gdf, gnote, gmeta = build_game_edges(sel_date)
    if gdf is None:
        st.warning(gnote)
    else:
        st.session_state["game_edges"] = gdf
        if gmeta.get("remaining"):
            st.caption(f"Odds quota — used {gmeta.get('used')}, "
                       f"remaining {gmeta.get('remaining')}")
        if gnote:
            st.info(gnote)
        green = int(((gdf["Edge"] >= 2) & (gdf["Edge"] < 8)).sum())
        amber = int(((gdf["Edge"] >= 8) & (gdf["Edge"] < 15)).sum())
        red = int((gdf["Edge"] >= 15).sum())
        st.markdown(f"### 🟢 {green} green · 🟡 {amber} amber · 🔴 {red} red")
        st.caption("🟢 2–8 pts = believable value · 🟡 8–15 = treat with caution · "
                   "🔴 15+ = almost certainly a missing model input, not a real edge · "
                   "⚪ under 2 = no signal.")
        cfg = {
            "🚦": st.column_config.TextColumn("", width="small"),
            "Start": st.column_config.TextColumn("Start (BST)", width="small"),
            "US Date": st.column_config.TextColumn("US Date", width="small"),
            "Game": st.column_config.TextColumn("Game", width="small"),
            "Selection": st.column_config.TextColumn("Selection", width="large"),
            "Model %": st.column_config.NumberColumn("Model %", format="%.1f"),
            "Fair %": st.column_config.NumberColumn("Fair %", format="%.1f"),
            "Edge": st.column_config.NumberColumn("Edge (pts)", format="%.1f"),
            "Odds": st.column_config.NumberColumn("Best odds", format="%.2f"),
            "EV %": st.column_config.NumberColumn("EV %", format="%.1f"),
        }

        def show_market(tab, market_name):
            with tab:
                sub = gdf[gdf["Market"] == market_name].sort_values(
                    ["_ct", "Game"]).reset_index(drop=True)
                if sub.empty:
                    st.write("No odds available for this market today.")
                    return
                sub = sub.copy()
                sub.insert(0, "🚦", sub["Edge"].apply(_edge_light))
                
                # The ideal list of columns you want to display
                target_cols = ["🚦", "Start", "US Date", "Game", "Selection",
                               "Model %", "Fair %", "Edge", "Odds", "EV %"]
                
                # Filter out any columns that don't exist in the current dataframe
                display_cols = [col for col in target_cols if col in sub.columns]
                
                disp = sub[display_cols]
                st.dataframe(disp, use_container_width=True, hide_index=True,
                             column_config=cfg)

        ml_tab, rl_tab, tot_tab = st.tabs(["💰 Money Line", "📏 Run Line", "📊 Totals"])
        show_market(ml_tab, "Moneyline")
        show_market(rl_tab, "Run line")
        show_market(tot_tab, "Total")
        st.caption("Model %: our probability · Fair %: book's de-vigged probability · "
                   "Edge: model minus fair · EV %: expected return per unit stake at best "
                   "odds. Heads-up: very large edges (15+ pts) usually mean the model is "
                   "missing an input for that game (e.g. ballpark) rather than real value.")

if isinstance(st.session_state.get("game_edges"), pd.DataFrame) and not st.session_state["game_edges"].empty:
    _ge = st.session_state["game_edges"]
    _greens = _ge[(_ge["Edge"] >= 2) & (_ge["Edge"] < 8)].copy()
    st.markdown("### 🎟️ Accumulator builder")
    st.caption("Builds a multi-fold from 🟢 green selections only (believable 2–8 pt edges) — "
               "ambers and reds are deliberately excluded. Combined odds and the model's "
               "probability of the whole bet landing are worked out for you.")
    if _greens.empty:
        st.write("No green selections on the analysed slate to build an accumulator from.")
    else:
        _greens = _greens.sort_values("Edge", ascending=False).reset_index(drop=True)
        _greens["pick"] = _greens.apply(
            lambda r: f"{r['Selection']}  @ {r['Odds']:.2f}  ·  {r['Market']}  ·  "
                      f"{r['Game']}  (edge {r['Edge']:.1f})", axis=1)
        _chosen = st.multiselect("Choose your legs (each is one green selection):",
                                 _greens["pick"].tolist())
        _stake = st.number_input("Stake (£)", min_value=0.0, value=10.0, step=1.0)
        if _chosen:
            _sel = _greens[_greens["pick"].isin(_chosen)].copy()
            _odds = _model = _fair = 1.0
            for _, _r in _sel.iterrows():
                _odds *= float(_r["Odds"])
                _model *= float(_r["Model %"]) / 100.0
                _fair *= float(_r["Fair %"]) / 100.0
            _ret = _stake * _odds
            _implied = (1.0 / _odds) if _odds else 0.0
            _ev = (_model * _odds - 1.0) * 100

            _a1, _a2, _a3 = st.columns(3)
            _a1.metric("Legs", len(_sel))
            _a2.metric("Combined odds", f"{_odds:.2f}")
            _a3.metric(f"Return on £{_stake:.0f}", f"£{_ret:.2f}", f"+£{_ret - _stake:.2f}")
            _b1, _b2, _b3 = st.columns(3)
            _b1.metric("Model: chance it lands", f"{_model * 100:.1f}%")
            _b2.metric("Market-implied chance", f"{_implied * 100:.1f}%")
            _b3.metric("Combined EV", f"{_ev:+.1f}%")

            _dupes = [g for g, c in _sel["Game"].value_counts().items() if c > 1]
            if _dupes:
                st.warning("⚠️ Multiple legs from the same game (" + ", ".join(_dupes) +
                           "). Those outcomes are correlated, so the combined chance above "
                           "is optimistic and most bookmakers need a 'same-game multi' "
                           "rather than a standard accumulator.")
            _sel.insert(0, "🚦", _sel["Edge"].apply(_edge_light))
            st.dataframe(_sel[["🚦", "Game", "Selection", "Market", "Model %", "Fair %",
                               "Edge", "Odds"]], use_container_width=True, hide_index=True,
                         column_config={"🚦": st.column_config.TextColumn("", width="small"),
                                        "Odds": st.column_config.NumberColumn("Best odds", format="%.2f"),
                                        "Edge": st.column_config.NumberColumn("Edge (pts)", format="%.1f")})
            st.caption("Model chance assumes legs are independent (true across different "
                       "games). A multi needs every leg to win, so it is high-variance even "
                       "when each leg has an edge — stake accordingly, and remember the model "
                       "is uncalibrated until the backtest says the dots hug the diagonal.")
