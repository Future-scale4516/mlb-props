import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from mlb_core import *

setup_page("MLB Prop Analyser — Player Props")
sel_date = sidebar_date()

# Fixed thresholds — these used to be sidebar sliders, but they sat at these exact
# permissive defaults untouched, so removing the sliders changes nothing about
# what shows up: min_pa/min_avg/min_obp just screen out tiny, unreliable samples;
# max_era/max_ord were already effectively no-ops at their default settings.
min_avg, min_obp, min_pa, max_era, max_ord = 0.180, 0.280, 30, 10.0, 9

st.title("🎰 Player Props")
st.caption("Load the slate for matchup context, then explore prop edges (best value) and "
           "the most-likely view.")
st.divider()
col_btn, col_info = st.columns([2, 3])
with col_btn:
    load_btn = st.button("Load Today's Slate")
with col_info:
    st.markdown("""
    **Auto-loads:** MLB schedule · probable pitchers · **all 500+ batters** (MLB Stats API) · confirmed lineups · live ballpark weather
    """)

st.markdown("## 🎰 Player Prop Edges")
st.caption("Pulls US-book player props per game, estimates each batter's probability with the "
           "opposing starter and ballpark factored in, and surfaces green/amber value bets "
           "(edge 2–15 pts). Each game analysed costs 4 quota credits.")
pc1, pc2 = st.columns([2, 3])
with pc1:
    prop_max_games = st.slider("Games to analyse (4 credits each)", 1, 20, 6)
with pc2:
    st.caption(f"Projected cost: up to {prop_max_games * 4} credits. "
               "Cached 15 min, so re-viewing the same games is free.")
if st.button("Find player prop edges (US books)"):
    with st.spinner("Pulling props, starters and park factors per game..."):
        prop_df, prop_meta, prop_note = build_prop_edges(sel_date, prop_max_games)
    if prop_df is None:
        st.warning(prop_note)
        st.session_state.pop("prop_edges", None)
    else:
        # Fetch + store only — this block only runs on the actual button click.
        # Interacting with the "Sort by" dropdown OR the "show form" checkbox
        # below both trigger their own rerun, in which st.button() evaluates to
        # False again — so nothing nested under this `if` (including those two
        # widgets) would fire on that rerun. That's exactly what was causing
        # both the sort dropdown and the form checkbox to appear to collapse
        # the whole picks list. Fetch here; display lives in the persistent
        # block below, gated on session_state instead of the button's return.
        prop_df = prop_df.copy()
        if not prop_df.empty:
            prop_df["Game"] = prop_df["Game"] + " · " + prop_df["Start"]
        st.session_state["prop_edges"] = prop_df
        st.session_state["prop_edges_meta"] = prop_meta
        st.session_state["prop_edges_note"] = prop_note

if isinstance(st.session_state.get("prop_edges"), pd.DataFrame):
    prop_df = st.session_state["prop_edges"]
    prop_meta = st.session_state.get("prop_edges_meta") or {}
    prop_note = st.session_state.get("prop_edges_note")

    if prop_meta.get("remaining"):
        st.caption(f"Quota — used {prop_meta.get('used')}, "
                   f"remaining {prop_meta.get('remaining')}")
    if prop_note:
        st.info(prop_note)
    if prop_df.empty:
        st.write("No green/amber prop edges found in the analysed games.")
    else:
        ng = int((prop_df["Edge"] < 8).sum())
        na = int((prop_df["Edge"] >= 8).sum())
        st.markdown(f"### 🟢 {ng} green · 🟡 {na} amber value props")

        show_form = st.checkbox(
            f"Show last-{FORM_GAMES} games form (slower — one lookup per player)",
            key="prop_form_toggle")
        st.caption(f"Checks whether each player actually cleared *this pick's line* "
                   f"in each of their last {FORM_GAMES} games — so a 2+ Total Bases "
                   "pick is judged on clearing 2 bases, not just on playing. Free "
                   "MLB data, but it's one call per player — the first check each "
                   "session takes a few seconds; results are cached for 3 hours "
                   "after that.")

        def show_prop_market(tab, label):
            with tab:
                sub = prop_df[prop_df["Market"] == label].copy()
                if sub.empty:
                    st.write("No value bets in this market today.")
                    return
                sub = sort_picker(sub, [
                    ("Edge (high to low)", "Edge", False),
                    ("Model % (high to low)", "Model %", False),
                    ("Odds (high to low)", "Best over", False),
                ], key=f"sort_prop_{label}")
                for _, row in sub.iterrows():
                    metrics = [("Model %", f"{row['Model %']:.1f}%"),
                               ("Market %", f"{row['Market %']:.1f}%"),
                               ("Edge", f"{row['Edge']:.1f} pts"),
                               ("Odds", f"{row['Best over']:.2f}")]
                    detail = row["Reason"]
                    if show_form and row.get("PlayerID") and row.get("MarketKey"):
                        try:
                            hits, played, syms = form_streak(
                                int(row["PlayerID"]), sel_date.year,
                                row["MarketKey"], row.get("Point", 0.5))
                            if hits is not None and played:
                                metrics.append(("Form", f"{hits}/{played}"))
                                detail = f"{syms}  —  {detail}"
                        except Exception:
                            # One player's form lookup failing (timeout, missing
                            # data) must not take the rest of the list down with it.
                            pass
                    render_pick_card(
                        row["Light"], f"{row['Player']} {row['Line']}", row["Game"],
                        metrics, reason=detail, conditions=row.get("Conditions"))

        hr_t, hit_t, rbi_t, run_t, tb_t = st.tabs(
            ["💥 Home Run", "🎯 Hits", "📥 RBI", "🏃 Runs", "📦 Total Bases"])
        show_prop_market(hr_t, "Home Run")
        show_prop_market(hit_t, "Hits")
        show_prop_market(rbi_t, "RBI")
        show_prop_market(run_t, "Runs")
        show_prop_market(tb_t, "Total Bases")
        st.caption("🟢 edge 2–8 · 🟡 8–15. Reds (15+) and no-signal (<2) are hidden. "
                   "Model %: our probability · Market %: de-vigged book probability · "
                   "Best over: best decimal price across US books. The model is still "
                   "uncalibrated — paper-trade until it's backtested.")


st.markdown("## 🔮 Most Likely — best hitters to achieve a market")
st.caption("Ranks batters by the model's raw probability of recording at least one "
           "HR / hit / RBI / run, using confirmed lineups, the opposing starter and the "
           "ballpark. This is the 'most likely' lens (ignores odds) — pair it with Player "
           "Prop Edges, the 'best value' lens. Free — no odds or quota used.")
if st.button("Rank most likely hitters"):
    with st.spinner("Reading lineups, starters and parks..."):
        ml_df, ml_note = build_most_likely(sel_date)
    if ml_df is None:
        st.warning(ml_note)
        st.session_state.pop("most_likely_df", None)
    else:
        # Fetch + store only — see the comment on the prop-edges button above
        # for why the display can't live nested under this `if`.
        ml_df = ml_df.copy()
        ml_df["Game"] = ml_df["Game"] + " · " + ml_df["Start"]
        st.session_state["most_likely_df"] = ml_df
        st.session_state["most_likely_note"] = ml_note

if isinstance(st.session_state.get("most_likely_df"), pd.DataFrame):
    ml_df = st.session_state["most_likely_df"]
    ml_note = st.session_state.get("most_likely_note")
    if ml_note:
        st.caption(ml_note)

    show_form_ml = st.checkbox(
        f"Show last-{FORM_GAMES} games form (slower — one lookup per player)",
        key="ml_form_toggle")
    st.caption(f"Checks whether each player actually cleared this market's line "
               f"(1+ for HR/Hits/RBI/Runs, 2+ for Total Bases) in each of their "
               f"last {FORM_GAMES} games. Not available for the Runs+Hits+RBI "
               "combo tab — it isn't a single box-score stat, so there's no one "
               "line to check form against. Free MLB data, but it's one call "
               "per player — the first check each session takes a few seconds; "
               "results are cached for 3 hours after that.")

    def show_ml(tab, label, is_tb=False):
        with tab:
            sub = ml_df[ml_df["Market"] == label].copy()
            if sub.empty:
                st.write("No ranked batters for this market.")
                return
            value_label = "Expected TB" if is_tb else "Model prob %"
            sub = sort_picker(sub, [
                (f"{value_label} (high to low)", "Value", False),
                ("Batting slot (low to high)", "Order", True),
            ], key=f"sort_ml_{label}")
            for _, row in sub.head(40).iterrows():
                value_str = f"{row['Value']:.2f}" if is_tb else f"{row['Value']:.1f}%"
                metrics = [(value_label, value_str)]
                if show_form_ml and row.get("PlayerID") and row.get("MarketKey"):
                    try:
                        point = 1.5 if is_tb else 0.5
                        hits, played, syms = form_streak(
                            int(row["PlayerID"]), sel_date.year, row["MarketKey"], point)
                        if hits is not None and played:
                            metrics.append(("Form", f"{hits}/{played}"))
                    except Exception:
                        # One player's form lookup failing must not take the
                        # rest of the list down with it.
                        pass
                render_pick_card(
                    None, row["Player"], f"{row['Game']} · Slot #{int(row['Order'])}",
                    metrics, conditions=row.get("Conditions"))

    ml_hr, ml_hit, ml_rbi, ml_run, ml_combo, ml_tb = st.tabs(
        ["💥 Home Run", "🎯 Hits", "📥 RBI", "🏃 Runs", "🎰 Runs+Hits+RBI", "📦 Total Bases"])
    show_ml(ml_hr, "Home Run")
    show_ml(ml_hit, "Hits")
    show_ml(ml_rbi, "RBI")
    show_ml(ml_run, "Runs")
    show_ml(ml_combo, "Runs+Hits+RBI (1+)")
    show_ml(ml_tb, "Total Bases (expected)", is_tb=True)
    st.caption("Most likely is not the same as best bet: a player can be very likely yet "
               "fairly priced (no value). Cross-reference with Player Prop Edges. "
               "RBI and Runs probabilities include a calibration correction based on "
               "backtest data. The Runs+Hits+RBI market estimates probability of achieving "
               "at least one of the three, treating them as approximately independent. "
               "Total Bases is shown as an expected value, not a '1+' probability — since "
               "any hit already counts as 1+ total base, a threshold framing here would "
               "just duplicate the Hits market; compare the expected value against the "
               "book's line (often 1.5 or 2.5) yourself, or check Player Prop Edges for "
               "the priced-in version.")


if load_btn:
    with st.status("Loading today's slate...", expanded=True) as status:
        st.write("Fetching MLB schedule and probable pitchers...")
        sched = fetch_schedule(str(sel_date))
        if sched.empty:
            st.error("No games found for " + str(sel_date)); st.stop()
        st.write(f"Found {len(sched)} games")

        st.write("Loading all MLB batting stats (MLB Stats API — covers every player)...")
        mlb_all = fetch_all_mlb_batting_stats(sel_date.year)
        st.write(f"MLB batting stats: {len(mlb_all)} players")

        all_rows = []
        for _, g in sched.iterrows():
            st.write(f"Processing {g['away_team']} @ {g['home_team']}...")
            wx       = fetch_weather(g["venue"])
            lineups  = fetch_live_lineups(int(g["gamePk"]))
            away_conf = not lineups.get("away",pd.DataFrame()).empty
            home_conf = not lineups.get("home",pd.DataFrame()).empty

            away_roster = fetch_active_roster(int(g["away_team_id"]))
            home_roster = fetch_active_roster(int(g["home_team_id"]))
            away_batters = away_roster[away_roster["pos_type"] != "Pitcher"]
            home_batters = home_roster[home_roster["pos_type"] != "Pitcher"]

            away_ids = lineups["away"]["player_id"].tolist() if away_conf else away_batters["player_id"].tolist()
            home_ids = lineups["home"]["player_id"].tolist() if home_conf else home_batters["player_id"].tolist()

            away_stats_map = {row["player_id"]: row for _, row in lineups["away"].iterrows()} if away_conf else {}
            home_stats_map = {row["player_id"]: row for _, row in lineups["home"].iterrows()} if home_conf else {}

            away_pitch = fetch_pitcher_stats(g["away_prob_id"])
            home_pitch = fetch_pitcher_stats(g["home_prob_id"])
            away_pitch["name"] = g["away_prob_name"]
            home_pitch["name"] = g["home_prob_name"]

            total_env = wx["factor"] * wx_modifier(wx["temp"], wx["wind"], wx["dome"])
            if total_env >= 1.06:
                env_symbol = "🟢 Hitter-Friendly"
            elif total_env >= 0.97:
                env_symbol = "🟡 Neutral"
            else:
                env_symbol = "🔴 Pitcher-Friendly"

            game_status_label = g["status"]

            for side_label, player_ids, stats_map, opp_pitch, conf in [
                ("Away", away_ids, away_stats_map, home_pitch, away_conf),
                ("Home", home_ids, home_stats_map, away_pitch, home_conf),
            ]:
                p_era = opp_pitch.get("era", 4.5)
                p_whip = opp_pitch.get("whip", 1.35)

                if p_era >= 4.5 or p_whip >= 1.35:
                    p_rating = "🟢 Target"
                elif p_era <= 3.4 and p_whip <= 1.20:
                    p_rating = "🔴 Avoid"
                else:
                    p_rating = "🟡 Neutral"

                for pid in player_ids:
                    pid = int(pid)
                    player_live_data = stats_map.get(pid, {})
                    order = int(player_live_data.get("order", 9) or 9)
                    if order > max_ord: continue

                    mlb_row = mlb_all[mlb_all["player_id"] == pid] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty: continue
                    base = mlb_row.iloc[0].to_dict()
                    pname = base.get("name","")

                    if base.get("plateAppearances",0) < min_pa: continue
                    if float(base.get("avg",0)) < min_avg: continue
                    if float(base.get("obp",0)) < min_obp: continue
                    if opp_pitch.get("era",4.5) > max_era: continue

                    avg_v  = float(base.get("avg",0))
                    obp_v  = float(base.get("obp",0))
                    iso_v  = float(base.get("iso",0))

                    live_hits = player_live_data.get("live_hits", 0)
                    live_runs = player_live_data.get("live_runs", 0)
                    live_rbi = player_live_data.get("live_rbi", 0)
                    live_hr = player_live_data.get("live_hr", 0)

                    all_rows.append({
                        "Game":          g["away_team"] + " @ " + g["home_team"],
                        "Game Status":   game_status_label,
                        "Game Datetime": g["game_date_raw"],
                        "Game Time BST": g["game_time_bst"],
                        "Side":          side_label,
                        "Batter":        pname,
                        "Order":         order,
                        "PA":            base.get("plateAppearances",0),
                        "AVG":           round(avg_v,3),
                        "OBP":           round(obp_v,3),
                        "ISO":           round(iso_v,3),
                        "Opp Pitcher":   opp_pitch.get("name","TBD"),
                        "Pitcher Rating": p_rating,
                        "Pitcher ERA":   opp_pitch.get("era",4.5),
                        "Pitcher WHIP":  opp_pitch.get("whip",1.35),
                        "Venue":         wx["venue"],
                        "Park Factor":   wx["factor"],
                        "Env Rating":    env_symbol,
                        "Temp":          wx["temp"],
                        "Wind":          wx["wind"],
                        "Dome":          wx["dome"],
                        "Lineup Status": "Confirmed" if conf else "Projected",
                        "Live Hits":     live_hits,
                        "Live Runs":     live_runs,
                        "Live RBI":      live_rbi,
                        "Live HR":       live_hr,
                    })

        if not all_rows:
            st.error("No batters matched filters."); status.update(label="No results", state="error")
        else:
            df = pd.DataFrame(all_rows).sort_values(["Game Datetime", "Order"])
            st.session_state["auto_df"] = df
            status.update(label=f"Done — {len(df)} batters loaded across {len(sched)} games", state="complete")

if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    if df.empty:
        st.info("No results. Adjust filters and reload.")
    else:
        games_c = df["Game"].nunique()
        conf_c = len(df[df["Lineup Status"]=="Confirmed"])

        k1,k2,k3 = st.columns(3)
        for col,val,lbl in [(k1,str(len(df)),"Batters Loaded"),(k2,str(games_c),"Games"),
                            (k3,str(conf_c),"Confirmed Lineups")]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{val}</div>'
                            f'<div class="metric-label">{lbl}</div></div>', unsafe_allow_html=True)

        st.subheader("🗂️ Matchup Breakdown")
        st.caption("Expand a matchup below to view confirmed lineups, park/weather "
                   "conditions, and pitching variables for that specific game.")

        sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")
        unique_chrono_games = sorted_games["Game"].tolist()

        for game_matchup in unique_chrono_games:
            game_df = df[df["Game"] == game_matchup].sort_values("Order", ascending=True)
            sample_row = game_df.iloc[0]
            venue = sample_row["Venue"]
            temp = int(sample_row["Temp"])
            wind = int(sample_row["Wind"])
            is_dome = sample_row["Dome"]
            bst_time = sample_row["Game Time BST"]
            env_badge = sample_row["Env Rating"]

            weather_str = "🏟️ Dome" if is_dome else f"🌡️ {temp}°F | 💨 {wind} mph"
            lineup_badge = "✅ Confirmed" if sample_row["Lineup Status"] == "Confirmed" else "⏳ Projected"

            with st.expander(f"⚾ {game_matchup}  🕒 {bst_time}  |  {venue} ({weather_str})  |  Conditions: {env_badge}  |  Lineups: {lineup_badge}"):
                col_away, col_home = st.columns(2)

                with col_away:
                    away_team_name = game_matchup.split(" @ ")[0]
                    away_df = game_df[game_df["Side"] == "Away"]
                    away_pitcher = away_df["Opp Pitcher"].iloc[0] if not away_df.empty else "TBD"
                    away_p_rating = away_df["Pitcher Rating"].iloc[0] if not away_df.empty else ""
                    st.markdown(f"### 🚀 {away_team_name}")
                    if not away_df.empty:
                        st.caption(f"Facing Pitcher: **{away_pitcher}** ({away_p_rating}) · "
                                   f"ERA {away_df['Pitcher ERA'].iloc[0]:.2f} · "
                                   f"WHIP {away_df['Pitcher WHIP'].iloc[0]:.2f}")
                        st.dataframe(
                            away_df[["Order", "Batter", "AVG", "OBP", "ISO"]].reset_index(drop=True),
                            use_container_width=True, hide_index=True,
                            column_config={
                                "AVG": st.column_config.NumberColumn(format="%.3f"),
                                "OBP": st.column_config.NumberColumn(format="%.3f"),
                                "ISO": st.column_config.NumberColumn(format="%.3f"),
                            }
                        )
                    else:
                        st.info("No batter data met filter criteria for this side.")

                with col_home:
                    home_team_name = game_matchup.split(" @ ")[1]
                    home_df = game_df[game_df["Side"] == "Home"]
                    home_pitcher = home_df["Opp Pitcher"].iloc[0] if not home_df.empty else "TBD"
                    home_p_rating = home_df["Pitcher Rating"].iloc[0] if not home_df.empty else ""
                    st.markdown(f"### 🏠 {home_team_name}")
                    if not home_df.empty:
                        st.caption(f"Facing Pitcher: **{home_pitcher}** ({home_p_rating}) · "
                                   f"ERA {home_df['Pitcher ERA'].iloc[0]:.2f} · "
                                   f"WHIP {home_df['Pitcher WHIP'].iloc[0]:.2f}")
                        st.dataframe(
                            home_df[["Order", "Batter", "AVG", "OBP", "ISO"]].reset_index(drop=True),
                            use_container_width=True, hide_index=True,
                            column_config={
                                "AVG": st.column_config.NumberColumn(format="%.3f"),
                                "OBP": st.column_config.NumberColumn(format="%.3f"),
                                "ISO": st.column_config.NumberColumn(format="%.3f"),
                            }
                        )
                    else:
                        st.info("No batter data met filter criteria for this side.")
