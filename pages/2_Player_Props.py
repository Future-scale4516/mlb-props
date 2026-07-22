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
# Same story for the model weights — baked in at their only-ever-used values.
w_era, w_whip = 0.55, 0.45

with st.sidebar:
    st.markdown("### Markets")
    s_hits = st.checkbox("Hits/Runs",   True)
    s_rbi  = st.checkbox("RBI",         True)
    s_hr   = st.checkbox("Home Run",    True)
    s_runs = st.checkbox("Runs Scored", True)
allowed_markets = [m for m,s in [
    ("Hits/Runs",s_hits),("RBI",s_rbi),("Home Run",s_hr),("Runs Scored",s_runs)] if s]

st.title("🎰 Player Props")
st.caption("Load the slate for batter rankings, then explore prop edges (best value) and the most-likely view.")
st.divider()
col_btn, col_info = st.columns([2,3])
with col_btn:
    load_btn = st.button("Load Today's Slate")
with col_info:
    st.markdown("""
    **Auto-loads:** MLB schedule · probable pitchers · **all 500+ batters** (MLB Stats API) · Savant advanced stats (if available) · confirmed lineups · live ballpark weather
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
    else:
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
            prop_df = prop_df.copy()
            prop_df["Game"] = prop_df["Game"] + " · " + prop_df["Start"]

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
                        render_pick_card(
                            row["Light"], f"{row['Player']} {row['Line']}", row["Game"],
                            [("Model %", f"{row['Model %']:.1f}%"),
                             ("Market %", f"{row['Market %']:.1f}%"),
                             ("Edge", f"{row['Edge']:.1f} pts"),
                             ("Odds", f"{row['Best over']:.2f}")],
                            reason=row["Reason"])

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
    else:
        st.caption(ml_note)
        ml_df = ml_df.copy()
        ml_df["Game"] = ml_df["Game"] + " · " + ml_df["Start"]

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
                    render_pick_card(
                        None, row["Player"], f"{row['Game']} · Slot #{int(row['Order'])}",
                        [(value_label, value_str)])

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

        st.write("Loading Baseball Savant advanced stats (xwOBA, Barrel%, HardHit%)...")
        fg_df = fetch_savant_stats(sel_date.year)
        savant_map = {}
        if fg_df.empty:
            reason = st.session_state.get("savant_error", "")
            st.warning(f"Savant unavailable — using MLB API derived metrics. {reason}")
        else:
            st.write(f"Savant loaded: {len(fg_df)} batters")
            if st.session_state.get("savant_error"):
                st.warning(st.session_state["savant_error"])
            tmp = fg_df.dropna(subset=["player_id"]).copy()
            tmp["player_id"] = tmp["player_id"].astype(int)
            savant_map = tmp.set_index("player_id").to_dict("index")

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
            g_pf = PARK_FACTORS.get(int(g["home_team_id"]), NEUTRAL_PARK)
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
                    
                    # NEW: Implement the OBP slider logic
                    if float(base.get("obp",0)) < min_obp: continue
                    
                    if opp_pitch.get("era",4.5) > max_era: continue

                    use_adv = False
                    wrc_plus = int(max(1, float(base.get("ops",0.700) or 0.700) * 152))
                    hard_hit = min(0.65, 0.28 + float(base.get("iso",0)) * 1.2)
                    barrel   = min(0.20, float(base.get("iso",0)) * 0.35)
                    srow = savant_map.get(pid)
                    if srow:
                        wv = srow.get("wrc_plus")
                        if wv is not None and not pd.isna(wv): wrc_plus = int(wv)
                        hv = srow.get("hard_hit_pct")
                        if hv is not None and not pd.isna(hv): hard_hit = float(hv)
                        bv = srow.get("barrel_pct")
                        if bv is not None and not pd.isna(bv): barrel = float(bv)
                        use_adv = True

                    avg_v  = float(base.get("avg",0))
                    obp_v  = float(base.get("obp",0))
                    slg_v  = float(base.get("slg",0))
                    iso_v  = float(base.get("iso",0))
                    ops_v  = float(base.get("ops",0))
                    k_pct  = float(base.get("k_pct",0.22))

                    scores = score_batter(
                        avg_v, obp_v, slg_v, iso_v, ops_v, k_pct, hard_hit, barrel, wrc_plus,
                        order, opp_pitch["era"], opp_pitch["whip"], opp_pitch["homeRunsPer9"],
                        opp_pitch.get("strikeoutsPer9Inn",8.5), wx["factor"], wx["temp"], wx["wind"],
                        wx["dome"], use_adv, w_era, w_whip,
                        g_pf["run"], g_pf["hr"]
                    )
                    flt = {k:v for k,v in scores.items() if k in allowed_markets}
                    if not flt: continue
                    best_market = max(flt, key=flt.get)
                    best_score  = flt[best_market]
                    
                    if best_score >= 70.0:
                        grade_badge = "🟢 Premium"
                    elif best_score >= 48.0:
                        grade_badge = "🟡 Playable"
                    else:
                        grade_badge = "🔴 Sub-optimal"

                    if best_market == "Home Run":
                        rationale = f"Elite power (ISO {iso_v:.3f}) matching up against a pitcher allowing {opp_pitch.get('homeRunsPer9', 1.2):.1f} HR/9."
                    elif best_market == "RBI":
                        rationale = f"Strong run-producer (wRC+ {wrc_plus}) hitting #{order} in the order with men likely on base."
                    elif best_market == "Runs Scored":
                        rationale = f"High on-base threat (OBP {obp_v:.3f}) batting #{order} facing a high-WHIP ({p_whip:.2f}) pitcher."
                    else:
                        rationale = f"Excellent contact profile (AVG {avg_v:.3f}) in a favourable offensive environment."

                    live_hits = player_live_data.get("live_hits", 0)
                    live_runs = player_live_data.get("live_runs", 0)
                    live_rbi = player_live_data.get("live_rbi", 0)
                    live_hr = player_live_data.get("live_hr", 0)
                    
                    is_final = game_status_label in ["Final", "Completed", "Game Over"]
                    bet_won = False
                    
                    if best_market == "Home Run" and live_hr >= 1: bet_won = True
                    elif best_market == "RBI" and live_rbi >= 1: bet_won = True
                    elif best_market == "Runs Scored" and live_runs >= 1: bet_won = True
                    elif best_market == "Hits/Runs" and (live_hits + live_runs) >= 2: bet_won = True
                    
                    if bet_won:
                        result_status = "✅ Won"
                    elif not bet_won and is_final:
                        result_status = "❌ Lost"
                    else:
                        result_status = "⏳ Pending"

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
                        "wRC+":          wrc_plus,
                        "Stats Source":  "Savant" if use_adv else "MLB API",
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
                        **scores,
                        "Best Market":   best_market,
                        "Best Score":    best_score,
                        "Grade":         grade_badge,
                        "Rationale":     rationale,
                        "Lineup Status": "Confirmed" if conf else "Projected",
                        "Live Hits":     live_hits,
                        "Live Runs":     live_runs,
                        "Live RBI":      live_rbi,
                        "Live HR":       live_hr,
                        "Slip Result":   result_status
                    })

        if not all_rows:
            st.error("No batters matched filters."); status.update(label="No results", state="error")
        else:
            df = pd.DataFrame(all_rows).sort_values("Best Score", ascending=False)
            st.session_state["auto_df"] = df
            status.update(label=f"Done — {len(df)} batters scored across {len(sched)} games", state="complete")

if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    if df.empty:
        st.info("No results. Adjust filters and reload.")
    else:
        top = df.iloc[0]
        fg_c  = len(df[df["Stats Source"]=="Savant"])
        mlb_c = len(df[df["Stats Source"]=="MLB API"])
        conf_c= len(df[df["Lineup Status"]=="Confirmed"])

        k1,k2,k3,k4 = st.columns(4)
        for col,val,lbl in [(k1,str(len(df)),"Batters Scored"),(k2,top["Batter"],"Top Batter"),
                            (k3,top["Best Market"],"Best Market"),(k4,f"{top['Best Score']:.2f}","Top Score")]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{val}</div>'
                            f'<div class="metric-label">{lbl}</div></div>', unsafe_allow_html=True)

        st.info(f"Savant: {fg_c} batters  |  MLB API: {mlb_c} batters  |  Confirmed lineups: {conf_c} batters")

        st.subheader("🗂️ Matchup Breakdown")
        st.caption("Expand a matchup below to view structural player rankings, confirmed lineups, and pitching variables for that specific game.")

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
                    st.caption(f"Facing Pitcher: **{away_pitcher}** ({away_p_rating})")

                    if not away_df.empty:
                        st.dataframe(
                            away_df[["Order", "Batter", "wRC+", "OBP", "ISO", "Grade", "Best Market", "Best Score"]].reset_index(drop=True),
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Best Score": st.column_config.NumberColumn("Score", format="%.1f"),
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
                    st.caption(f"Facing Pitcher: **{home_pitcher}** ({home_p_rating})")

                    if not home_df.empty:
                        st.dataframe(
                            home_df[["Order", "Batter", "wRC+", "OBP", "ISO", "Grade", "Best Market", "Best Score"]].reset_index(drop=True),
                            use_container_width=True, hide_index=True,
                            column_config={
                                "Best Score": st.column_config.NumberColumn("Score", format="%.1f"),
                                "OBP": st.column_config.NumberColumn(format="%.3f"),
                                "ISO": st.column_config.NumberColumn(format="%.3f"),
                            }
                        )
                    else:
                        st.info("No batter data met filter criteria for this side.")
