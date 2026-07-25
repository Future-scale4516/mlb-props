import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Results")
sel_date = sidebar_date()

st.title("📋 Results")
st.caption("How the model's player-prop predictions actually turned out for the selected "
           "date — what it projected for each batter, what they actually did, and whether "
           "it landed. Free MLB data, no Odds API quota used.")

mode = st.radio(
    "Results mode",
    ["Model reads only (free)", "Priced-up picks (uses historical odds credits)"],
    help="Model reads scores every batter the model projected against what they "
         "actually did — costs nothing. Priced-up reconstructs the real value "
         "picks using the bookmaker odds that were actually available, so you "
         "get the true edge, colour and price — but it spends credits.")
priced = mode.startswith("Priced")

if priced:
    max_g = st.slider("Games to reconstruct", 1, 15, 8)
    st.warning(
        f"**Credit cost:** historical game lines bill 10 credits per region per "
        f"market — about **30 per distinct start time** on the slate — plus roughly "
        f"5 credits per game for props. Reconstructing {max_g} games typically lands "
        f"somewhere around **{30 * 3 + max_g * 5}–{30 * 6 + max_g * 5} credits**, "
        "depending on how spread out the start times are. Results are cached for a "
        "day, so re-opening the same date is free.")
    st.caption("Odds are taken from a snapshot **1 hour before each game's own first "
               "pitch** — so every pick is priced at what was genuinely available "
               "shortly before it started, rather than one blanket time for the slate.")
else:
    with st.expander("Why this mode can't show edges or prices", expanded=False):
        st.markdown("""
This mode rebuilds only the **model's own probability** for each batter, using the real
lineup and starter from that game, and checks it against the box score. It answers
*"were the model's reads right?"* — it doesn't know what price was on offer.

Switch to **Priced-up picks** for the real edge, traffic-light colour and odds. That
uses the historical odds endpoint, which costs credits but gives you genuine
closed-loop tracking: what the model flagged, at what price, and whether it landed.
""")

st.caption("Game bets aren't included here — you track those separately.")

if st.button("Load results"):
    with st.spinner("Rebuilding picks and checking them against box scores..."):
        if priced:
            rdf, rnote, rcost = build_priced_results(sel_date, max_games=max_g)
            st.session_state["results_cost"] = rcost
        else:
            rdf, rnote = build_prop_results(sel_date)
            st.session_state["results_cost"] = None
    st.session_state["results_df"] = rdf
    st.session_state["results_note"] = rnote
    st.session_state["results_for_date"] = str(sel_date)
    st.session_state["results_priced"] = priced

rdf = st.session_state.get("results_df")
if st.session_state.get("results_for_date") == str(sel_date) and rdf is not None:
    st.caption(st.session_state.get("results_note", ""))

    conf_floor = st.slider(
        "Only show picks the model rated at least this likely (%)", 0, 90, 50, 5,
        help="The model makes a prediction for every batter in every market. Filtering "
             "to its more confident calls shows how the picks you'd actually have "
             "considered performed, rather than every low-probability projection.")

    sub_all = rdf[rdf["Model %"] >= conf_floor]
    if sub_all.empty:
        st.warning("No picks at or above that confidence level on this date.")
    else:
        is_priced = st.session_state.get("results_priced", False)
        hits = int(sub_all["Hit"].sum())
        total = len(sub_all)
        rate = hits / total * 100 if total else 0
        avg_model = sub_all["Model %"].mean()
        if is_priced and "P/L (1u)" in sub_all.columns:
            pl = sub_all["P/L (1u)"].sum()
            roi = pl / total * 100 if total else 0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Landed", f"{hits}/{total}")
            c2.metric("Hit rate", f"{rate:.1f}%")
            c3.metric("P/L (1u stakes)", f"{pl:+.2f}u")
            c4.metric("ROI", f"{roi:+.1f}%")
            st.caption("P/L assumes a flat 1-unit stake on every pick shown, settled at "
                       "the price that was actually available an hour before first pitch. "
                       "This is the closest the app gets to 'would following it have made "
                       "money' — but it's one slate, so treat it as a data point, not a verdict.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Landed", f"{hits}/{total}")
            c2.metric("Actual hit rate", f"{rate:.1f}%")
            c3.metric("Model predicted", f"{avg_model:.1f}%")
        if abs(rate - avg_model) <= 5:
            st.success(f"Model said {avg_model:.1f}%, reality was {rate:.1f}% — closely calibrated on this slate.")
        elif rate < avg_model:
            st.warning(f"Model said {avg_model:.1f}% but only {rate:.1f}% landed — overconfident on this slate.")
        else:
            st.info(f"Model said {avg_model:.1f}% and {rate:.1f}% landed — underconfident on this slate.")
        st.caption("One slate is a small sample — a single day swinging either way is "
                   "normal variance, not a verdict on the model. The Backtest page is "
                   "where calibration is judged properly, over many days.")

        MARKETS = ["Home Run", "Hits", "RBI", "Runs", "Total Bases"]
        tabs = st.tabs([f"📊 All"] + [f"{mk}" for mk in MARKETS])

        def show_results_table(tab, market=None):
            with tab:
                sub = sub_all if market is None else sub_all[sub_all["Market"] == market]
                if sub.empty:
                    st.write("No picks in this market at that confidence level.")
                    return
                h, t = int(sub["Hit"].sum()), len(sub)
                am = sub["Model %"].mean()
                hdr = f"**{h}/{t} landed ({h/t*100:.1f}%)** · model predicted {am:.1f}%"
                if "P/L (1u)" in sub.columns:
                    hdr += f" · P/L {sub['P/L (1u)'].sum():+.2f}u"
                st.markdown(hdr)
                disp = sub.copy()
                disp["Result"] = disp["Hit"].map({True: "✅", False: "❌"})
                if "P/L (1u)" in disp.columns:
                    cols = ["Result", "Light", "Player", "Market", "Line", "Model %",
                            "Market %", "Edge", "Odds", "Actual", "P/L (1u)", "Game"]
                else:
                    cols = ["Result", "Player", "Market", "Line", "Model %", "Actual",
                            "Game", "Score"]
                cols = [c for c in cols if c in disp.columns]
                if market is not None and "Market" in cols:
                    cols.remove("Market")
                st.dataframe(
                    disp[cols].sort_values("Model %", ascending=False).reset_index(drop=True),
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Result": st.column_config.TextColumn("", width="small"),
                        "Player": st.column_config.TextColumn("Player", width="medium"),
                        "Model %": st.column_config.NumberColumn("Model %", format="%.1f"),
                        "Actual": st.column_config.NumberColumn("Actual", format="%d"),
                    })

        show_results_table(tabs[0], None)
        for tab, mk in zip(tabs[1:], MARKETS):
            show_results_table(tab, mk)

        st.download_button(
            "Download results CSV",
            data=sub_all.to_csv(index=False).encode("utf-8"),
            file_name=f"mlb_prop_results_{sel_date}.csv", mime="text/csv")
elif st.session_state.get("results_for_date") == str(sel_date):
    st.warning(st.session_state.get("results_note", "No results available."))
else:
    st.info("Pick a date in the sidebar and click **Load results**.")
