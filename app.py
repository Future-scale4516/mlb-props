import streamlit as st

import pandas as pd

import plotly.graph_objects as go

from datetime import date, datetime, timedelta

from mlb_core import *



setup_page("MLB Prop Analyser — Home")

sel_date = sidebar_date()



st.title("⚾ MLB Prop Analyser v2")
st.caption("Model-driven MLB betting analysis — game lines, player props, and a calibration backtest.")
st.divider()

st.markdown("""
### Welcome
Use the **sidebar on the left** to navigate between pages, and to set the **slate date** (shared across every page).

**Pages**
- **⚾ Game Bets** — moneyline, run line and totals edges vs the market, plus an accumulator builder.
- **🎰 Player Props** — load the slate for batter rankings, plus prop edges (best value) and the most-likely view.
- **📊 Backtest** — calibration check: does the model's % match reality?

Start by picking a date in the sidebar, then open a page.
""")

st.divider()

with st.expander("🔌 Odds API connection test (The Odds API)"):

    st.caption("Runs one request against your quota. Use it to confirm the key works "

               "and see which markets your plan returns.")

    if st.button("Run odds API test"):

        odds_data, odds_meta = fetch_mlb_odds()

        if odds_meta.get("error"):

            st.error(odds_meta["error"])

        else:

            st.success(f"Connected — {len(odds_data)} MLB games returned.")

            st.write(f"Quota — used: {odds_meta.get('used')} | "

                     f"remaining: {odds_meta.get('remaining')}")

            present = set()

            for g in odds_data:

                for b in g.get("bookmakers", []):

                    for m in b.get("markets", []):

                        present.add(m.get("key"))

            label = {"h2h": "moneyline", "spreads": "run line", "totals": "over/under"}

            shown = ", ".join(f"{k} ({label.get(k, k)})" for k in sorted(present)) or "none"

            st.write("Markets returned:", shown)

            if odds_data:

                g = odds_data[0]

                st.write(f"Sample game: {g.get('away_team')} @ {g.get('home_team')}  "

                         f"(start {g.get('commence_time')})")

                st.json((g.get("bookmakers") or [{}])[0])


st.divider()
st.caption("MLB Stats API (all batters via playerPool=ALL) · Baseball Savant via pybaseball (optional enrichment) · The Odds API · Open-Meteo weather")
