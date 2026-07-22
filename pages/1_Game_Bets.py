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
        _lights = gdf.apply(lambda r: classify_pick(r["Edge"], r["Model %"], r["Market"]), axis=1)
        green = int((_lights == "🟢").sum())
        amber = int((_lights == "🟡").sum())
        red = int((_lights == "🔴").sum())
        st.markdown(f"### 🟢 {green} green · 🟡 {amber} amber · 🔴 {red} red")
        st.caption("🟢 2–8 pts = believable value · 🟡 8–15 = treat with caution · "
                   "🔴 15+ = almost certainly a missing model input, not a real edge · "
                   "⚪ under 2 = no signal. A suspiciously high raw model probability is "
                   "also flagged red on its own, even with a small edge. (Player props like "
                   "Runs/RBI/Total Bases use slightly wider bands — see the Player Props page.)")

        def show_market(tab, market_name):
            with tab:
                sub = gdf[gdf["Market"] == market_name].sort_values(
                    ["_ct", "Game"]).reset_index(drop=True)
                if sub.empty:
                    st.write("No odds available for this market today.")
                    return
                sub = sub.copy()
                for _, row in sub.iterrows():
                    light = classify_pick(row["Edge"], row["Model %"], market_name)
                    render_pick_card(
                        light, f"{row['Selection']} @ {row['Odds']:.2f}",
                        f"{row['Game']} · {row['Start']} ({row['US Date']})",
                        [("Model %", f"{row['Model %']:.1f}%"),
                         ("Fair %", f"{row['Fair %']:.1f}%"),
                         ("Edge", f"{row['Edge']:.1f} pts"),
                         ("EV %", f"{row['EV %']:.1f}%")],
                        reason=row["Reason"])

        def show_most_likely(tab):
            with tab:
                st.caption("Pure model confidence, ignoring the market entirely — this is "
                           "'who/what does the model predict', not 'where's the value'. "
                           "Ignore Fair %, Edge, and odds for this question; Model % alone "
                           "answers it. A high % here is still not a guarantee — see the "
                           "backtest for how often the model's confidence bands actually hit.")
                mkt_pick = st.multiselect("Markets to include:",
                                          ["Moneyline", "Run line", "Total"],
                                          default=["Moneyline", "Run line", "Total"],
                                          key="ml_market_pick")
                sub = gdf[gdf["Market"].isin(mkt_pick)].sort_values(
                    "Model %", ascending=False).reset_index(drop=True)
                if sub.empty:
                    st.write("No selections match the chosen markets.")
                    return
                for _, row in sub.iterrows():
                    render_pick_card(
                        None, f"{row['Selection']} · {row['Market']}",
                        f"{row['Game']} · {row['Start']} ({row['US Date']})",
                        [("Model %", f"{row['Model %']:.1f}%")])

        ml_tab, rl_tab, tot_tab, most_likely_tab = st.tabs(
            ["💰 Money Line", "📏 Run Line", "📊 Totals", "🎯 Most Likely"])
        show_market(ml_tab, "Moneyline")
        show_market(rl_tab, "Run line")
        show_market(tot_tab, "Total")
        show_most_likely(most_likely_tab)
        st.caption("Model %: our probability · Fair %: book's de-vigged probability · "
                   "Edge: model minus fair · EV %: expected return per unit stake at best "
                   "odds. Heads-up: very large edges (15+ pts) usually mean the model is "
                   "missing an input for that game (e.g. ballpark) rather than real value.")

if isinstance(st.session_state.get("game_edges"), pd.DataFrame) and not st.session_state["game_edges"].empty:
    _ge = st.session_state["game_edges"]
    _greens = _ge[_ge.apply(
        lambda r: MARKET_EDGE_BANDS.get(r["Market"], (2, 8, 15))[0] <= r["Edge"]
                  < MARKET_EDGE_BANDS.get(r["Market"], (2, 8, 15))[1], axis=1)].copy()
    st.markdown("### 🎟️ Accumulator builder")
    st.caption("Builds a multi-fold from 🟢 green selections only — ambers and reds are "
               "deliberately excluded. Green's edge range varies slightly by market (see "
               "the traffic-light explanation above). Combined odds and the model's "
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
            for _, row in _sel.iterrows():
                light = classify_pick(row["Edge"], row["Model %"], row["Market"])
                render_pick_card(
                    light, f"{row['Selection']} @ {row['Odds']:.2f}",
                    f"{row['Game']} · {row['Market']}",
                    [("Model %", f"{row['Model %']:.1f}%"),
                     ("Fair %", f"{row['Fair %']:.1f}%"),
                     ("Edge", f"{row['Edge']:.1f} pts")],
                    reason=row["Reason"])
            st.caption("Model chance assumes legs are independent (true across different "
                       "games). A multi needs every leg to win, so it is high-variance even "
                       "when each leg has an edge — stake accordingly, and remember the model "
                       "is uncalibrated until the backtest says the dots hug the diagonal.")
