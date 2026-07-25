import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Results")
sel_date = sidebar_date()

st.title("📋 Results")
st.caption("Every game on the selected date — final scores, live scores for games in "
           "progress, and start times for anything not underway yet. Pulled straight "
           "from the MLB Stats API, so it's completely free — no Odds API quota is "
           "used by this page.")

if st.button("Load results"):
    with st.spinner("Fetching scores..."):
        st.session_state["results_rows"] = fetch_day_results(str(sel_date))
        st.session_state["results_date"] = str(sel_date)

rows = st.session_state.get("results_rows")
if rows is not None and st.session_state.get("results_date") == str(sel_date):
    if not rows:
        st.warning("No games found for this date.")
    else:
        finals = [r for r in rows if r["state"] == "Final"]
        live = [r for r in rows if r["state"] == "Live"]
        upcoming = [r for r in rows if r["state"] not in ("Final", "Live")]
        c1, c2, c3 = st.columns(3)
        c1.metric("Final", len(finals))
        c2.metric("In progress", len(live))
        c3.metric("Upcoming", len(upcoming))

        def _label(r):
            dh = ""
            if str(r.get("double_header", "N")) in ("Y", "S"):
                dh = f" ({r.get('game_number', 1)})"
            return f"{r['away_team']} @ {r['home_team']}{dh}"

        def show_group(title, group, show_score=True):
            if not group:
                return
            st.divider()
            st.markdown(f"### {title}")
            for r in group:
                if show_score and r["home_score"] is not None:
                    aw, hm = r["away_score"], r["home_score"]
                    winner = "away" if aw > hm else ("home" if hm > aw else None)
                    away_txt = f"**{r['away_team']} {aw}**" if winner == "away" else f"{r['away_team']} {aw}"
                    home_txt = f"**{r['home_team']} {hm}**" if winner == "home" else f"{r['home_team']} {hm}"
                    title_line = f"{away_txt}  @  {home_txt}"
                else:
                    title_line = f"{r['away_team']}  @  {r['home_team']}"
                if r["state"] == "Live":
                    sub = f"{r.get('inning_state','')} {r.get('inning','')} · {r['venue']}"
                elif r["state"] == "Final":
                    sub = f"{r.get('detail','Final')} · {r['venue']}"
                else:
                    sub = f"{_commence_to_bst(r.get('start_utc',''))} BST · {r['venue']}"
                with st.container(border=True):
                    st.markdown(title_line)
                    st.caption(sub)

        show_group("🔴 In progress", live)
        show_group("✅ Final", finals)
        show_group("⏳ Not started yet", upcoming, show_score=False)

        st.divider()
        st.caption("Scores refresh when you click Load results — click again for an "
                   "updated read on games still in progress. Nothing here is saved "
                   "between visits.")
else:
    st.info("Pick a date in the sidebar and click **Load results**.")
