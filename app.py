import streamlit as st
import pandas as pd
import requests as req
from datetime import date, datetime, timedelta
import time

st.set_page_config(page_title="MLB Prop Value Matrix v1.1", page_icon="⚾", layout="wide")

# ── MOBILE-FRIENDLY CSS ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:#f7f6f2;}
.value-card {background:#ffffff; border-radius:12px; padding:16px; border:1px solid #e5e5e5; box-shadow:0 2px 4px rgba(0,0,0,0.02); margin-bottom:12px;}
.vc-header {display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;}
.vc-name {font-size:1.1rem; font-weight:700; color:#111827;}
.vc-grade {font-size:0.8rem; font-weight:600; padding:2px 8px; border-radius:12px; background:#dcfce7; color:#166534;}
.vc-sub {font-size:0.85rem; color:#6b7280; margin-bottom:12px;}
.vc-why {font-size:0.9rem; color:#374151; background:#f9fafb; padding:10px; border-radius:8px; border-left:4px solid #01696f;}
section[data-testid="stSidebar"]{background:#1c1b19;}
section[data-testid="stSidebar"] *{color:#cdccca !important;}
</style>
""", unsafe_allow_html=True)

def safe_get(url, headers=None, params=None):
    for attempt in range(3):
        try:
            r = req.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except:
            if attempt == 2: return {}
            time.sleep(1)
    return {}

# ── DATA PIPELINE 1: TANK01 (DAILY CONTEXT & LINEUPS) ──
def tank01_get(endpoint, api_key, params=None):
    url = f"https://tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com/{endpoint}"
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"}
    return safe_get(url, headers=headers, params=params)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_daily_schedule_tank(target_date: str, api_key: str):
    data = tank01_get("getMLBGamesForDate", api_key, {"gameDate": target_date.replace("-", "")})
    columns_blueprint = ["game_id", "status", "away_team", "home_team", "away_pitcher", "home_pitcher", "venue", "game_time_bst", "epoch"]
    
    if not data or "body" not in data:
        return pd.DataFrame(columns=columns_blueprint)
        
    games = data.get("body", [])
    if not isinstance(games, list) or len(games) == 0:
        return pd.DataFrame(columns=columns_blueprint)
        
    rows = []
    for g in games:
        bst_time_str = "TBD"
        epoch = g.get("gameTimeEpoch")
        if epoch:
            try:
                utc_dt = datetime.fromtimestamp(float(epoch))
                bst_dt = utc_dt + timedelta(hours=1)
                bst_time_str = bst_dt.strftime("%H:%M")
            except:
                pass
            
        rows.append({
            "game_id": g.get("gameID"),
            "status": g.get("gameStatus", "Scheduled"),
            "away_team": g.get("away", ""),
            "home_team": g.get("home", ""),
            "away_pitcher": g.get("probableStartingPitchers", {}).get("away", "TBD"),
            "home_pitcher": g.get("probableStartingPitchers", {}).get("home", "TBD"),
            "venue": g.get("gameLocation", "TBD"),
            "game_time_bst": bst_time_str,
            "epoch": float(epoch) if epoch else 9999999999
        })
        
    if not rows:
        return pd.DataFrame(columns=columns_blueprint)
        
    return pd.DataFrame(rows).sort_values("epoch")

@st.cache_data(ttl=300, show_spinner=False)
def fetch_lineups_tank(target_date: str, api_key: str):
    data = tank01_get("getMLBLineups", api_key, {"gameDate": target_date.replace("-", "")})
    if not data or "body" not in data: return {}
    lineups = data.get("body", {})
    if not isinstance(lineups, dict): return {}
    
    out = {}
    for game_id, details in lineups.items():
        if not isinstance(details, dict): continue
        game_roster = {"away": pd.DataFrame(), "home": pd.DataFrame()}
        for side in ["away", "home"]:
            side_data = details.get(f"{side}Lineup", {})
            if not side_data or not isinstance(side_data, dict): continue
            
            rows = []
            for order_str, player_info in side_data.items():
                if order_str == "pitcher": continue
                try: order = int(order_str)
                except: continue
                
                if isinstance(player_info, dict):
                    rows.append({
                        "name": player_info.get("longName", ""),
                        "order": order,
                        "pos": player_info.get("pos", "")
                    })
            if rows:
                game_roster[side] = pd.DataFrame(rows).sort_values("order")
        out[game_id] = game_roster
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather_tank(target_date: str, api_key: str):
    data = tank01_get("getMLBWeather", api_key, {"gameDate": target_date.replace("-", "")})
    if not data or "body" not in data: return {}
    weather_dict = data.get("body", {})
    if not isinstance(weather_dict, dict): return {}
    
    out = {}
    for game_id, details in weather_dict.items():
        if not isinstance(details, dict): continue
        w = details.get("weather", {})
        if not isinstance(w, dict): w = {}
        try: temp = float(w.get("temp", 72))
        except: temp = 72.0
        try: wind = float(w.get("wind", 8))
        except: wind = 8.0
        dome = str(w.get("dome", "false")).lower() == "true"
        
        env_factor = 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004
        env_symbol = "🟢 Batter Friendly" if env_factor >= 1.05 else "🟡 50/50" if env_factor >= 0.98 else "🔴 Pitcher Friendly"
        weather_str = "🏟️ Dome" if dome else f"🌡️ {int(temp)}°F | 💨 {int(wind)} mph"
        
        out[game_id] = {"factor": env_factor, "symbol": env_symbol, "desc": weather_str}
    return out

# ── DATA PIPELINE 2: OFFICIAL MLB API (HISTORICAL MATHS) ──
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_mlb_historical_stats(season: int):
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {"stats":"season", "group":"hitting", "season":season, "sportId":1, "playerPool":"ALL", "limit":1500})
    rows = []
    splits = data.get("stats",[{}])[0].get("splits",[])
    
    total_ops, count = 0.0, 0
    for s in splits:
        ops_val = float(s.get("stat",{}).get("ops") or 0.0)
        if ops_val > 0.400:
            total_ops += ops_val; count += 1
    lg_ops = (total_ops / count) if count > 0 else 0.730

    for split in splits:
        p, stat = split.get("player",{}), split.get("stat",{})
        slg, avg, obp, ops = float(stat.get("slg") or 0), float(stat.get("avg") or 0), float(stat.get("obp") or 0), float(stat.get("ops") or 0)
        pa = int(stat.get("plateAppearances") or 1)
        iso_val = round(slg - avg, 3)
        wrc_plus = int((ops / lg_ops) * 100) if lg_ops > 0 else 100
        
        rows.append({
            "name": p.get("fullName",""),
            "avg": avg, "obp": obp, "iso": iso_val, "wrc_plus": wrc_plus,
            "plateAppearances": pa, "k_pct": float(stat.get("strikeOuts") or 0) / max(1, pa),
            "match_name": p.get("fullName","").lower().replace(".", "").replace("'", "")
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pitcher_historical_stats(season: int):
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {"stats":"season", "group":"pitching", "season":season, "sportId":1, "playerPool":"ALL", "limit":1000})
    rows = []
    splits = data.get("stats",[{}])[0].get("splits",[])
    for split in splits:
        p, stat = split.get("player",{}), split.get("stat",{})
        rows.append({
            "name": p.get("fullName",""),
            "era": float(stat.get("era") or 4.50), "whip": float(stat.get("whip") or 1.35),
            "hr9": float(stat.get("homeRunsPer9") or 1.20), "k9": float(stat.get("strikeoutsPer9Inn") or 8.50),
            "match_name": p.get("fullName","").lower().replace(".", "").replace("'", "")
        })
    return pd.DataFrame(rows)

# ── SCORING & LOGIC ENGINE ──
def score_batter(b_stats, p_stats, order, env_factor):
    avg, obp, iso, wrc_plus = b_stats["avg"], b_stats["obp"], b_stats["iso"], b_stats["wrc_plus"]
    era, whip, hr9, k9 = p_stats["era"], p_stats["whip"], p_stats["hr9"], p_stats["k9"]
    
    of  = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(order, 0.80)
    pv  = min(era/7.0,1.0)*0.55 + min(max((whip-0.8)/1.2,0.0),1.0)*0.45
    hrv = min(hr9/2.5,1.0)
    k_adj = 1.0 - min((k9-7.0)/14.0, 0.20)
    
    hits_runs_score = round((avg*0.65 + obp*0.35) * pv * of * k_adj * env_factor * 280, 2)
    rbi_score       = round((avg*0.65 + obp*0.35) * pv * (1.0 + max(0,(5-order)*0.04)) * k_adj * env_factor * 260, 2)
    hr_score        = round(iso * hrv * env_factor * 280, 2)
    runs_score      = round(obp * pv * (1.0 + max(0,(4-order)*0.05)) * k_adj * env_factor * 280, 2)

    why_map = {}
    if hr_score > 60:
        why_map["Home Run"] = f"Elite raw power (ISO .{iso:.3f}) facing a pitcher allowing {hr9:.1f} HR/9."
    elif iso > 0.200:
        why_map["Home Run"] = f"Strong power upside (ISO .{iso:.3f}) in a decent matchup."
        
    if rbi_score > 60:
        why_map["RBI"] = f"Premium run producer (wRC+ {wrc_plus}) hitting #{order} behind an OBP-heavy top of the order."
    elif wrc_plus > 120:
        why_map["RBI"] = f"Above average run creator hitting in a prime RBI slot."
        
    if runs_score > 60:
        why_map["Runs Scored"] = f"Elite table-setter (OBP .{obp:.3f}) facing a high-traffic pitcher (WHIP {whip:.2f})."
        
    if hits_runs_score > 60:
        why_map["Hits/Runs/RBI"] = f"High-contact bat (AVG .{avg:.3f}) in a favourable environment."

    return {"Hits/Runs/RBI": hits_runs_score, "RBI": rbi_score, "Home Run": hr_score, "Runs Scored": runs_score}, why_map

# ── SIDEBAR CONFIGURATION ──
with st.sidebar:
    st.markdown("## ⚾ API Configuration")
    api_key_input = st.text_input("Tank01 API Key (RapidAPI)", value="b7f47f42-746f-4df9-9284-a07065bb285c", type="password")
    sel_date = st.date_input("Slate Date", value=date.today())
    
    st.markdown("---")
    st.markdown("### Math Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    min_obp  = st.slider("Min OBP",   0.250, 0.400, 0.280, 0.005, format="%.3f")
    max_ord  = st.slider("Max Order", 1, 9, 9)
    
    if st.button("Clear App Cache"):
        st.cache_data.clear()
        for k in ["auto_df"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

st.title("⚾ MLB Value Matrix v1.1")
st.caption("Powered by Tank01 Lineups & Official MLB Historical Maths")
st.divider()

if st.button("Load Today's Slate", type="primary"):
    if not api_key_input:
        st.warning("⚠️ Please enter your Tank01 API Key in the sidebar.")
        st.stop()
        
    # ── PROTECTION 1: Clear out any polluted browser session data before running ──
    if "auto_df" in st.session_state:
        del st.session_state["auto_df"]
        
    with st.status("Assembling metrics from hybrid data stream...", expanded=True) as status:
        sched = fetch_daily_schedule_tank(str(sel_date), api_key_input)
        if sched.empty: 
            status.update(label="No scheduled games found for this date.", state="error")
            st.error("No games found for this date.")
            st.stop()
        
        lineups_dict = fetch_lineups_tank(str(sel_date), api_key_input)
        weather_dict = fetch_weather_tank(str(sel_date), api_key_input)
        
        mlb_batters = fetch_mlb_historical_stats(sel_date.year)
        mlb_pitchers = fetch_pitcher_historical_stats(sel_date.year)

        all_rows = []

        for _, g in sched.iterrows():
            g_id = g["game_id"]
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            
            w_data = weather_dict.get(g_id, {"factor": 1.0, "symbol": "🟡 50/50", "desc": "TBD"})
            l_data = lineups_dict.get(g_id, {"away": pd.DataFrame(), "home": pd.DataFrame()})
            
            away_conf, home_conf = not l_data["away"].empty, not l_data["home"].empty
            lineup_badge = "✅ Confirmed" if (away_conf and home_conf) else "⏳ Projected/Awaiting"

            a_p_clean = str(g["away_pitcher"]).lower().replace(".", "").replace("'", "")
            h_p_clean = str(g["home_pitcher"]).lower().replace(".", "").replace("'", "")
            
            a_p_match = mlb_pitchers[mlb_pitchers["match_name"] == a_p_clean]
            h_p_match = mlb_pitchers[mlb_pitchers["match_name"] == h_p_clean]
            
            away_pitch = a_p_match.iloc[0].to_dict() if not a_p_match.empty else {"era": 4.5, "whip": 1.35, "hr9": 1.2, "k9": 8.5, "name": g["away_pitcher"]}
            home_pitch = h_p_match.iloc[0].to_dict() if not h_p_match.empty else {"era": 4.5, "whip": 1.35, "hr9": 1.2, "k9": 8.5, "name": g["home_pitcher"]}

            for side_label, roster_df, opp_pitch in [("Away", l_data["away"], home_pitch), ("Home", l_data["home"], away_pitch)]:
                if roster_df.empty: continue
                
                for _, p_row in roster_df.iterrows():
                    order = int(p_row["order"])
                    if order > max_ord: continue
                    
                    b_clean = str(p_row["name"]).lower().replace(".", "").replace("'", "")
                    b_match = mlb_batters[mlb_batters["match_name"] == b_clean]
                    if b_match.empty: continue
                    
                    base = b_match.iloc[0].to_dict()

                    if base["avg"] >= min_avg and base["obp"] >= min_obp:
                        scores, why_map = score_batter(base, opp_pitch, order, w_data["factor"])
                        best_market = max(scores, key=scores.get)
                        
                        all_rows.append({
                            "Game": g_matchup, "Time": g["game_time_bst"], "Side": side_label, "Batter": base["name"], "Order": order,
                            "AVG": base["avg"], "OBP": base["obp"], "ISO": base["iso"], "wRC+": base["wrc_plus"],
                            "Opp Pitcher": opp_pitch["name"], "Venue": g["venue"],
                            "Env Symbol": w_data["symbol"], "Weather Str": w_data["desc"], "Lineup Badge": lineup_badge,
                            "Hits/Runs/RBI": scores["Hits/Runs/RBI"], "RBI": scores["RBI"], "Home Run": scores["Home Run"], "Runs Scored": scores["Runs Scored"],
                            "Best Market": best_market, "Grade": "🟢 Premium" if scores[best_market] >= 70.0 else "🟡 Playable",
                            "Why_HR": why_map.get("Home Run", "Average matchup."),
                            "Why_RBI": why_map.get("RBI", "Average matchup."),
                            "Why_Runs": why_map.get("Runs Scored", "Average matchup."),
                            "Why_Hits": why_map.get("Hits/Runs/RBI", "Average matchup.")
                        })

        if all_rows:
            st.session_state["auto_df"] = pd.DataFrame(all_rows)
            status.update(label="Analytics matrices compiled successfully.", state="complete")
        else:
            # ── PROTECTION 2: Hard gate stop if data output is empty to block downstream slicing ──
            status.update(label="No historical datasets matched filters.", state="error")
            st.error("⚠️ No players matched your specific filtering thresholds for today's active lineups. Try widening your filters in the sidebar.")
            st.stop()

# ── UI RENDERING ──
if "auto_df" in st.session_state and not st.session_state["auto_df"].empty:
    df = st.session_state["auto_df"]

    tabs = st.tabs(["🏠 Home / Glossary", "🗂️ Daily Matchups", "🎯 Hits/Runs/RBI", "🏏 RBIs", "🏃‍♂️ Runs", "💥 Home Runs", "✅ Results Tracker"])
    
    with tabs[0]:
        st.subheader("📚 Metric & Market Glossary")
        st.markdown("""
        **Welcome to the Value Matrix.** This tool breaks down the mathematical likelihood of a batter succeeding in specific prop markets.
        
        #### The Core Stats
        * **wRC+ (Weighted Runs Created Plus):** The gold standard for overall offence. 100 is league average. 120+ is great. 140+ is elite.
        * **ISO (Isolated Power):** Measures raw extra-base hit ability. It strips away singles. .140 is average. .200+ is elite.
        * **OBP (On-Base Percentage):** How often a player avoids making an out. Vital for Runs Scored markets.
        
        #### The Betting Markets
        * **Hits/Runs/RBI:** A volume market. You want high-contact guys (High AVG) who don't strike out, batting in good weather.
        * **RBIs:** Requires a strong overall hitter (High wRC+) batting 3rd, 4th, or 5th behind guys who get on base.
        * **Runs Scored:** Requires a table-setter (High OBP) batting 1st or 2nd, facing a pitcher who allows heavy base traffic (High WHIP).
        * **Home Runs:** Requires elite slugging (High ISO) facing a pitcher who serves up fly balls (High HR/9).
        """)

    with tabs[1]:
        st.subheader("🗂️ Matchup Overview & Context")
        st.caption("Games listed in chronological order (BST).")
        sorted_games = df[["Game", "Time", "Venue", "Env Symbol", "Weather Str", "Lineup Badge"]].drop_duplicates().sort_values("Time")
        
        for _, g in sorted_games.iterrows():
            with st.expander(f"⚾ {g['Game']} | 🕒 {g['Time']} | {g['Env Symbol']}"):
                st.write(f"**Venue:** {g['Venue']}")
                st.write(f"**Conditions:** {g['Weather Str']}")
                st.write(f"**Status:** {g['Lineup Badge']}")

    market_map = {"🎯 Hits/Runs/RBI": ("Hits/Runs/RBI", "Why_Hits", "AVG"), "🏏 RBIs": ("RBI", "Why_RBI", "wRC+"), "🏃‍♂️ Runs": ("Runs Scored", "Why_Runs", "OBP"), "💥 Home Runs": ("Home Run", "Why_HR", "ISO")}
    
    for t_idx, (tab_name, data_tuple) in enumerate(market_map.items(), start=2):
        with tabs[t_idx]:
            st.subheader(f"🏆 Top Picks: {data_tuple[0]}")
            m_col, why_col, stat_col = data_tuple
            
            top_3 = df.sort_values(m_col, ascending=False).head(3)
            
            for _, row in top_3.iterrows():
                st.markdown(f"""
                <div class="value-card">
                    <div class="vc-header">
                        <span class="vc-name">{row['Batter']} ({row['Side']})</span>
                        <span class="vc-grade">{row['Grade']}</span>
                    </div>
                    <div class="vc-sub">Batting #{row['Order']} vs {row['Opp Pitcher']} | {row['Env Symbol']}</div>
                    <div class="vc-why"><b>Why:</b> {row[why_col]}</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("### 📊 Full Filterable Data")
            disp_cols = ["Game", "Time", "Batter", "Order", stat_col, m_col, "Grade"]
            st.dataframe(df.sort_values(m_col, ascending=False)[disp_cols].reset_index(drop=True), use_container_width=True)

    with tabs[6]:
        st.subheader("✅ Active Recommendations")
        tracker_df = df[df["Grade"].isin(["🟢 Premium"])].copy()
        if not tracker_df.empty:
            st.dataframe(tracker_df[["Game", "Batter", "Best Market", "Grade"]].reset_index(drop=True), use_container_width=True)
        else:
            st.info("No Premium selections currently meet value parameters.")
