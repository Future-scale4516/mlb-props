import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Today's Picks")
sel_date = sidebar_date()

st.title("🎯 Today's Picks")
st.caption("The strongest edges across game bets and player props, combined and ranked in "
           "one place. 🟢 green (edge 2–8 pts) is the believable-value band; 🟡 amber (8–15) "
           "is worth a look but treat with caution. Reds and no-signal are hidden.")

pc1, pc2 = st.columns([2, 3])
with pc1:
    tp_max_games = st.slider("Prop games to analyse (4 credits each)", 1, 20, 6)
with pc2:
    st.caption(f"Projected quota cost: up to {tp_max_games * 4} credits for the prop scan. "
               "Game-line scan is quota-free. Cache saves repeats within 15 minutes, so "
               "re-running with the same date and game count costs nothing.")

if st.button("Load today's picks"):
    with st.spinner("Scanning game lines and player props..."):
        gdf, gnote, gmeta = build_game_edges(sel_date)
        pdf, pmeta, pnote = build_prop_edges(sel_date, tp_max_games)

    rows = []

    # Game-line edges — pull green + amber (band varies slightly by market)
    if isinstance(gdf, pd.DataFrame) and not gdf.empty:
        for _, r in gdf.iterrows():
            _lo, _mid, _hi = MARKET_EDGE_BANDS.get(r["Market"], (2, 8, 15))
            if _lo <= r["Edge"] < _hi:
                rows.append({
                    "Light": classify_pick(r["Edge"], r["Model %"], r["Market"]),
                    "Type": "Game",
                    "Market": r["Market"],
                    "Selection": r["Selection"],
                    "Game": r["Game"],
                    "Start": r.get("Start", ""),
                    "Model %": r["Model %"],
                    "Market %": r["Fair %"],
                    "Edge": r["Edge"],
                    "Odds": r["Odds"],
                    "Note": r.get("Reason", ""),
                })

    # Prop edges — build_prop_edges already filters to green + amber
    if isinstance(pdf, pd.DataFrame) and not pdf.empty:
        for _, r in pdf.iterrows():
            rows.append({
                "Light": r["Light"],
                "Type": "Prop",
                "Market": r["Market"],
                "Selection": f"{r['Player']} {r['Line']}",
                "Game": r["Game"],
                "Start": r.get("Start", ""),
                "Model %": r["Model %"],
                "Market %": r["Market %"],
                "Edge": r["Edge"],
                "Odds": r["Best over"],
                "Note": r["Reason"],
            })

    if not rows:
        msgs = []
        if gnote: msgs.append(f"Game bets: {gnote}")
        if pnote: msgs.append(f"Player props: {pnote}")
        st.warning("No green or amber picks found today. "
                   + (" ".join(msgs) if msgs else "Try loading with a bigger games count."))
    else:
        picks_df = pd.DataFrame(rows).sort_values("Edge", ascending=False).reset_index(drop=True)
        greens = int((picks_df["Edge"] < 8).sum())
        ambers = int((picks_df["Edge"] >= 8).sum())
        gc = int((picks_df["Type"] == "Game").sum())
        pc = int((picks_df["Type"] == "Prop").sum())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🟢 Green picks", greens)
        m2.metric("🟡 Amber picks", ambers)
        m3.metric("Game bets", gc)
        m4.metric("Player props", pc)

        if pmeta and pmeta.get("remaining"):
            st.caption(f"Odds API quota — used {pmeta.get('used')}, "
                       f"remaining {pmeta.get('remaining')}")
        if pnote:
            st.info(f"Player props note: {pnote}")

        pcfg = {
            "Light": st.column_config.TextColumn("", width="small"),
            "Type": st.column_config.TextColumn("Type", width="small"),
            "Market": st.column_config.TextColumn("Market", width="small"),
            "Selection": st.column_config.TextColumn("Selection", width="large"),
            "Game": st.column_config.TextColumn("Game", width="small"),
            "Start": st.column_config.TextColumn("Start (BST)", width="small"),
            "Model %": st.column_config.NumberColumn("Model %", format="%.1f"),
            "Market %": st.column_config.NumberColumn("Market %", format="%.1f"),
            "Edge": st.column_config.NumberColumn("Edge (pts)", format="%.1f"),
            "Odds": st.column_config.NumberColumn("Odds", format="%.2f"),
            "Note": st.column_config.TextColumn("Why it's a pick", width="large"),
        }
        cols = ["Light", "Type", "Market", "Selection", "Game", "Start",
                "Model %", "Market %", "Edge", "Odds", "Note"]

        def show(tab, df_):
            with tab:
                if df_.empty:
                    st.write("No picks in this section.")
                    return
                st.dataframe(df_[cols], use_container_width=True, hide_index=True,
                             column_config=pcfg)

        t_all, t_games, t_props, t_green = st.tabs(
            ["All picks", "Game bets only", "Player props only", "Green only"])
        show(t_all, picks_df)
        show(t_games, picks_df[picks_df["Type"] == "Game"].reset_index(drop=True))
        show(t_props, picks_df[picks_df["Type"] == "Prop"].reset_index(drop=True))
        show(t_green, picks_df[picks_df["Edge"] < 8].reset_index(drop=True))

        st.caption("Sorted by edge descending. Cross-reference the Game Bets and Player "
                   "Props pages for full context, US date, and reasons. The accumulator "
                   "builder lives on the Game Bets page. Model is uncalibrated until the "
                   "backtest shows the dots hugging the diagonal — paper-trade for now.")
