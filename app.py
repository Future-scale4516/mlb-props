import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Value Matrix v2.2", page_icon="⚾", layout="wide")

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
.odds-box {background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px; margin-top:8px; margin-bottom: 12px;}
.pick-text {color: #166534; font-weight: 800; font-size: 1.15rem;}
.ev-text {color: #15803d; font-weight: 700; background: #dcfce7; padding: 2px 6px; border-radius: 4px;}
</style>
""", unsafe_allow_html=True)

# ── FALLBACK TEAM IDs FOR UNCONFIRMED LINEUPS ──
TEAM_IDS = {
    "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CHW": 145,
    "CIN": 113, "CLE": 114, "COL": 115, "DET": 116, "HOU": 117, "KC": 118,
    "LAA": 108, "LAD": 119, "MIA": 146, "MIL": 158, "MIN": 142, "NYM": 121,
    "NYY": 147, "OAK": 133, "PHI": 143, "PIT": 134, "SD": 135, "SF": 137,
    "SEA": 136, "STL": 138, "TB": 139, "TEX": 140, "TOR": 141, "WSH": 120
}

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

def decimal_to_fractional(dec):
    if not dec or dec <= 1.0: return "N/A"
    if dec == 2.0: return "EVENS"
    frac = Fraction(dec - 1.0).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"

# ── TANK01 API PIPELINE (SCHEDULE & LINEUPS) ──
def tank01_get(endpoint, api_key, params=None):
    url = f"https://tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com/{endpoint}"
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"}
    return safe_get(url, headers=headers, params=params)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_daily_schedule_tank(target_date: str, api_key: str):
    data = tank01_get("getMLBGamesForDate", api_key, {"gameDate": target_date.replace("-", "")})
    columns_blueprint = ["game_id", "status", "away_team", "home_team", "away_pitcher", "home_pitcher", "venue", "game_time_bst", "epoch"]
    if not data or "body" not in data: return pd.DataFrame(columns=columns_blueprint)
    games = data.get("body", [])
    if not isinstance(games, list) or len(games) == 0: return pd.DataFrame(columns=columns_blueprint)
    
    rows = []
    for g in games:
        bst_time_str = "TBD"
        epoch = g.get("gameTimeEpoch")
        if epoch:
            try: bst_time_str = (datetime.fromtimestamp(float(epoch)) + timedelta(hours=1)).strftime("%H:%M")
            except: pass
        rows.append({
            "game_id": g.get("gameID"), "status": g.get("gameStatus", "Scheduled"),
            "away_team": g.get("away", ""), "home_team": g.get("home", ""),
            "away_pitcher": g.get("probableStartingPitchers", {}).get("away", "TBD"),
            "home_pitcher": g.get("probableStartingPitchers", {}).get("home", "TBD"),
            "venue": g.get("gameLocation", "TBD"), "game_time_bst": bst_time_str, "epoch": float(epoch) if epoch else 9999999999
        })
    return pd.DataFrame(rows).sort_values("epoch") if rows else pd.DataFrame(columns=columns_blueprint)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_lineups_tank(target_date: str, api_key: str):
    data = tank01_get("getMLBLineups", api_key, {"gameDate": target_date.replace("-", "")})
    lineups = data.get("body", {}) if isinstance(data, dict) else {}
    out = {}
    for game_id, details in (lineups.items() if isinstance(lineups, dict) else []):
        if not isinstance(details, dict): continue
        game_roster = {"away": pd.DataFrame(), "home": pd.DataFrame()}
        for side in ["away", "home"]:
            side_data = details.get(f"{side}Lineup", {})
            rows = []
            for order_str, player_info in (side_data.items() if isinstance(side_data, dict) else []):
                if order_str == "pitcher": continue
                try: 
                    order = int(order_str)
                    rows.append({"name": player_info.get("longName", ""), "order": order})
                except: continue
            if rows: game_roster[side] = pd.DataFrame(rows).sort_values("order")
        out[game_id] = game_roster
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather_tank(target_date: str, api_key: str):
    data = tank01_get("getMLBWeather", api_key, {"gameDate": target_date.replace("-", "")})
    weather_dict = data.get("body", {}) if isinstance(data, dict) else {}
    out = {}
    for game_id, details in (weather_dict.items() if isinstance(weather_dict, dict) else []):
        w = details.get("weather", {}) if isinstance(details, dict) else {}
        try: temp = float(w.get("temp", 72))
        except: temp = 72.0
        try: wind = float(w.get("wind", 8))
        except: wind = 8.0
        dome = str(w.get("dome", "false")).lower() == "true"
        env_factor = 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004
        env_symbol = "🟢 Batter Friendly" if env_factor >= 1.05 else "🟡 50/50" if env_factor >= 0.98 else "🔴 Pitcher Friendly"
        out[game_id] = {"factor": env_factor, "symbol": env_symbol, "desc": "🏟️ Dome" if dome else f"🌡️ {int(temp)}°F | 💨 {int(wind)} mph"}
    return out

# ── MLB API PIPELINE (HISTORICAL MATHS & ROSTER FALLBACKS) ──
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_mlb_historical_stats(season: int):
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {"stats":"season", "group":"hitting", "season":season, "sportId":1, "playerPool":"ALL", "limit":1500})
    splits, rows, total_ops, count = data.get("stats",[{}])[0].get("splits",[]), [], 0.0, 0
    for s in splits:
        ops_val = float(s.get("stat",{}).get("ops") or 0.0)
        if ops_val > 0.400: total_ops += ops_val; count += 1
    lg_ops = (total_ops / count) if count > 0 else 0.730
    for split in splits:
        p, stat = split.get("player",{}), split.get("stat",{})
        slg, avg, obp, ops = float(stat.get("slg") or 0), float(stat.get("avg") or 0), float(stat.get("obp") or 0), float(stat.get("ops") or 0)
        pa, iso_val = int(stat.get("plateAppearances") or 1), round(slg - avg, 3)
        rows.append({
            "name": p.get("fullName",""), "avg": avg, "obp": obp, "iso": iso_val, "wrc_plus": int((ops / lg_ops) * 100) if lg_ops > 0 else 100,
            "plateAppearances": pa, "k_pct": float(stat.get("strikeOuts") or 0) / max(1, pa),
            "match_name": p.get("fullName","").lower().replace(".", "").replace("'", "")
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pitcher_historical_stats(season: int):
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {"stats":"season", "group":"pitching", "season":season, "sportId":1, "playerPool":"ALL", "limit":1000})
    rows = []
    for split in data.get("stats",[{}])[0].get("splits",[]):
        p, stat = split.get("player",{}), split.get("stat",{})
        rows.append({
            "name": p.get("fullName",""), "era": float(stat.get("era") or 4.50), "whip": float(stat.get("whip") or 1.35),
            "hr9": float(stat.get("homeRunsPer9") or 1.20), "k9": float(stat.get("strikeoutsPer9Inn") or 8.50),
            "match_name": p.get("fullName","").lower().replace(".", "").replace("'", "")
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_active_roster_mlb(team_id: int):
    if not team_id: return pd.DataFrame()
    data = safe_get(f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster", {"rosterType":"active"})
    rows = []
    for r in data.get("roster",[]):
        if r.get("position",{}).get("type") != "Pitcher":
            rows.append({"name": r.get("person",{}).get("fullName"), "order": 4})
    return pd.DataFrame(rows)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_odds_api(api_key: str):
    if not api_key or api_key.strip() == "": return {}
    url, params = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds", {"apiKey": api_key, "regions": "uk", "markets": "h2h,spreads,totals", "bookmakers": "williamhill,paddypower,betfair,bet365,skybet", "oddsFormat": "decimal"}
    data = safe_get(url, params=params)
    out = {}
    if isinstance(data, list):
        for item in data: out[f"{item.get('away_team')} @ {item.get('home_team')}"] = item.get("bookmakers", [])
    return out

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
    if hr_score > 60: why_map["Home Run"] = f"Elite raw power (ISO .{iso:.3f}) vs pitcher allowing {hr9:.1f} HR/9."
    elif iso > 0.200: why_map["Home Run"] = f"Strong power upside (ISO .{iso:.3f}) in decent matchup."
    if rbi_score > 60: why_map["RBI"] = f"Premium run producer (wRC+ {wrc_plus}) hitting #{order} behind OBP-heavy batters."
    elif wrc_plus > 120: why_map["RBI"] = f"Above average run creator hitting in prime RBI slot."
    if runs_score > 60: why_map["Runs Scored"] = f"Elite table-setter (OBP .{obp:.3f}) vs high-traffic pitcher (WHIP {whip:.2f})."
    if hits_runs_score > 60: why_map["Hits/Runs/RBI"] = f"High-contact bat (AVG .{avg:.3f}) in favourable environment."

    return {"Hits/Runs/RBI": hits_runs_score, "RBI": rbi_score, "Home Run": hr_score, "Runs Scored": runs_score}, why_map

# ── SIDEBAR CONFIGURATION ──
with st.sidebar:
    st.markdown("## ⚾ API Keys")
    # BOTH KEYS ARE NOW HARDCODED HERE FOR YOU
    api_key_input = st.text_input("Tank01 API Key (RapidAPI)", value="46e23ff209mshb208e90af2f00d4p120983jsn38b0da2800d0", type="password")
    odds_key = st.text_input("The-Odds-API Key", value="4b959d673d4ef9c7128271557c038dfe", type="password")
    sel_date = st.date_input("Slate Date", value=date.today())
    
    st.markdown("---")
    st.markdown("### Player Prop Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.240, 0.005, format="%.3f")
    min_obp  = st.slider("Min OBP",   0.250, 0.400, 0.315, 0.005, format="%.3f")
    min_pa   = st.slider("Min PA",    0, 300, 100, 10)
    max_ord  = st.slider("Max Order", 1, 9, 6, help="Ignored for Projected lineups so elite batters aren't hidden early.")
    min_opp_era = st.slider("Min Opp Pitcher ERA", 0.0, 7.0, 0.0, 0.1, help="Set higher to target vulnerable pitchers.")
    
    if st.button("Clear App Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "sched_df", "game_proj_dict", "odds_data"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

st.title("⚾ MLB Value Matrix v2.2")
st.caption("Decoupled Architecture: Game odds run independently of strict player prop filters.")
st.divider()

if st.button("Load Today's Slate", type="primary"):
    with st.status("Fetching decoupled data streams...", expanded=True) as status:
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
        game_projections = {}

        for _, g in sched.iterrows():
            g_id = g["game_id"]
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            w_data = weather_dict.get(g_id, {"factor": 1.0, "symbol": "🟡 50/50", "desc": "TBD"})
            l_data = lineups_dict.get(g_id, {"away": pd.DataFrame(), "home": pd.DataFrame()})
            
            # EARLY MORNING ROSTER FALLBACK
            if l_data["away"].empty:
                l_data["away"] = fetch_active_roster_mlb(TEAM_IDS.get(g["away_team"]))
                away_conf = False
            else: away_conf = True
                
            if l_data["home"].empty:
                l_data["home"] = fetch_active_roster_mlb(TEAM_IDS.get(g["home_team"]))
                home_conf = False
            else: home_conf = True
            
            lineup_badge = "✅ Confirmed" if (away_conf and home_conf) else "⏳ Projected"

            a_p_clean = str(g["away_pitcher"]).lower().replace(".", "").replace("'", "")
            h_p_clean = str(g["home_pitcher"]).lower().replace(".", "").replace("'", "")
            
            a_p_match = mlb_pitchers[mlb_pitchers["match_name"] == a_p_clean]
            h_p_match = mlb_pitchers[mlb_pitchers["match_name"] == h_p_clean]
            
            away_pitch = a_p_match.iloc[0].to_dict() if not a_p_match.empty else {"era": 4.5, "whip": 1.35, "hr9": 1.2, "k9": 8.5, "name": g["away_pitcher"]}
            home_pitch = h_p_match.iloc[0].to_dict() if not h_p_match.empty else {"era": 4.5, "whip": 1.35, "hr9": 1.2, "k9": 8.5, "name": g["home_pitcher"]}

            away_wrcs, home_wrcs = [], []

            for side_label, roster_df, opp_pitch, conf in [("Away", l_data["away"], home_pitch, away_conf), ("Home", l_data["home"], away_pitch, home_conf)]:
                if roster_df.empty: continue
                
                for _, p_row in roster_df.iterrows():
                    order = int(p_row["order"])
                    b_clean = str(p_row["name"]).lower().replace(".", "").replace("'", "")
                    b_match = mlb_batters[mlb_batters["match_name"] == b_clean]
                    if b_match.empty: continue
                    base = b_match.iloc[0].to_dict()
                    
                    if side_label == "Away" and order <= 6: away_wrcs.append(base["wrc_plus"])
                    if side_label == "Home" and order <= 6: home_wrcs.append(base["wrc_plus"])

                    if conf and order > max_ord: continue 
                    if base["plateAppearances"] < min_pa: continue
                    if base["avg"] < min_avg: continue
                    if base["obp"] < min_obp: continue
                    if opp_pitch.get("era", 4.5) < min_opp_era: continue 

                    scores, why_map = score_batter(base, opp_pitch, order, w_data["factor"])
                    best_market = max(scores, key=scores.get)
                    
                    all_rows.append({
                        "Game": g_matchup, "Time": g["game_time_bst"], "Side": side_label, "Batter": base["name"], "Order": order,
                        "AVG": base["avg"], "OBP": base["obp"], "ISO": base["iso"], "wRC+": base["wrc_plus"],
                        "Opp Pitcher": opp_pitch["name"], "Venue": g["venue"],
                        "Hits/Runs/RBI": scores["Hits/Runs/RBI"], "RBI": scores["RBI"], "Home Run": scores["Home Run"], "Runs Scored": scores["Runs Scored"],
                        "Best Market": best_market, "Grade": "🟢 Premium" if scores[best_market] >= 70.0 else "🟡 Playable",
                        "Why_HR": why_map.get("Home Run", ""), "Why_RBI": why_map.get("RBI", ""),
                        "Why_Runs": why_map.get("Runs Scored", ""), "Why_Hits": why_map.get("Hits/Runs/RBI", "")
                    })

            # Calculate Team Projections for Game Tabs regardless of batter filters
            mean_away_wrc = sum(away_wrcs)/len(away_wrcs) if away_wrcs else 100
            mean_home_wrc = sum(home_wrcs)/len(home_wrcs) if home_wrcs else 100
            proj_away_runs = round(4.1 * (mean_away_wrc/100) * (home_pitch.get("era", 4.3)/4.3) * w_data["factor"], 2)
            proj_home_runs = round(4.1 * (mean_home_wrc/100) * (away_pitch.get("era", 4.3)/4.3) * w_data["factor"], 2)
            away_prob = round((proj_away_runs**1.83) / ((proj_away_runs**1.83) + (proj_home_runs**1.83)), 4) if (proj_away_runs + proj_home_runs) > 0 else 0.5
            
            game_projections[g_matchup] = {
                "proj_away_runs": proj_away_runs, "proj_home_runs": proj_home_runs,
                "away_prob": away_prob, "home_prob": 1.0 - away_prob, 
                "proj_total": round(proj_away_runs + proj_home_runs, 1),
                "proj_line": round(proj_home_runs - proj_away_runs, 1),
                "env_symbol": w_data["symbol"], "weather_str": w_data["desc"], 
                "venue": g["venue"], "bst_time": g["game_time_bst"], "lineup_badge": lineup_badge
            }

        st.session_state["auto_df"] = pd.DataFrame(all_rows)
        st.session_state["game_proj_dict"] = game_projections
        st.session_state["sched_df"] = sched
        st.session_state["odds_data"] = fetch_live_odds_api(odds_key) if odds_key else {}
        status.update(label="Analytics matrices compiled successfully.", state="complete")

# ── DECOUPLED UI RENDERING ──
if "sched_df" in st.session_state and not st.session_state["sched_df"].empty:
    df = st.session_state.get("auto_df", pd.DataFrame())
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data = st.session_state.get("odds_data", {})
    
    tabs = st.tabs(["🏠 Glossary", "🗂️ Matchups", "💰 Moneyline", "📈 Run Line", "📊 Totals", "🎯 Hits/Runs/RBI", "🏏 RBIs", "💥 Home Runs", "🏃‍♂️ Runs Scored"])
    
    with tabs[0]:
        st.subheader("📚 Metric & Market Glossary")
        st.markdown("""
        **wRC+:** 100 is average. 120+ is great. 140+ is elite. | **ISO:** .140 is average. .200+ is elite. | **OBP:** Vital for Runs Scored markets.
        """)

    with tabs[1]:
        st.subheader("🗂️ Matchup Overview")
        for g_matchup, proj in game_proj_dict.items():
            with st.expander(f"⚾ {g_matchup} | 🕒 {proj['bst_time']} | {proj['env_symbol']}"):
                st.write(f"**Venue:** {proj['venue']}")
                st.write(f"**Conditions:** {proj['weather_str']}")
                st.write(f"**Status:** {proj['lineup_badge']}")

    # ── GAME ODDS TABS (RENDER INDEPENDENTLY OF BATTER FILTERS) ──
    with tabs[2]:
        st.subheader("💰 Live Moneyline Value")
        for g_matchup, proj in game_proj_dict.items():
            away_team, home_team = g_matchup.split(" @ ")
            match_odds_list = odds_data.get(g_matchup, [])
            best_away_ev, best_home_ev = -100, -100
            best_away_bookie, best_home_bookie, away_price, home_price = "", "", "", ""
            
            if match_odds_list:
                for b in match_odds_list:
                    h2h = next((m for m in b.get("markets", []) if m["key"] == "h2h"), None)
                    if h2h:
                        out = h2h.get("outcomes", [])
                        a_o = next((o for o in out if o["name"] == away_team), None)
                        h_o = next((o for o in out if o["name"] == home_team), None)
                        if a_o and h_o:
                            a_ev = ((proj["away_prob"] * a_o["price"]) - 1.0) * 100
                            h_ev = ((proj["home_prob"] * h_o["price"]) - 1.0) * 100
                            if a_ev > best_away_ev: best_away_ev, best_away_bookie, away_price = a_ev, b["title"], decimal_to_fractional(a_o["price"])
                            if h_ev > best_home_ev: best_home_ev, best_home_bookie, home_price = h_ev, b["title"], decimal_to_fractional(h_o["price"])
            
            with st.container(border=True):
                st.markdown(f"**{g_matchup}** | Model Probabilities: {away_team} ({proj['away_prob']*100:.1f}%) vs {home_team} ({proj['home_prob']*100:.1f}%)")
                if best_away_ev > 0: st.markdown(f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: Back {away_team}</span> at {away_price} (via {best_away_bookie}) | <span class='ev-text'>+{best_away_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                elif best_home_ev > 0: st.markdown(f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: Back {home_team}</span> at {home_price} (via {best_home_bookie}) | <span class='ev-text'>+{best_home_ev:.1f}% EV</span></div>", unsafe_allow_html=True)

    with tabs[3]:
        st.subheader("📈 Live Run Line Value")
        for g_matchup, proj in game_proj_dict.items():
            away_team, home_team = g_matchup.split(" @ ")
            match_odds_list = odds_data.get(g_matchup, [])
            with st.container(border=True):
                st.markdown(f"**{g_matchup}** | Model Projected Gap: {proj['proj_line']} ({home_team} advantage)")
                if match_odds_list:
                    for b in match_odds_list:
                        spreads = next((m for m in b.get("markets", []) if m["key"] == "spreads"), None)
                        if spreads:
                            a_o = next((o for o in spreads.get("outcomes", []) if o["name"] == away_team), None)
                            if a_o:
                                rec_text = f"<br><span class='pick-text'>🤖 Model Recommends: Back {away_team} {a_o['point']}</span>" if proj['proj_line'] < (a_o['point'] * -1) else ""
                                st.markdown(f"*{b['title']}:* {away_team} {a_o['point']} at {decimal_to_fractional(a_o['price'])} {rec_text}", unsafe_allow_html=True)
                            break 

    with tabs[4]:
        st.subheader("📊 Live Totals (Overs/Unders)")
        for g_matchup, proj in game_proj_dict.items():
            match_odds_list = odds_data.get(g_matchup, [])
            with st.container(border=True):
                st.markdown(f"**{g_matchup}** | Model Projected Total: **{proj['proj_total']} Runs**")
                if match_odds_list:
                    for b in match_odds_list:
                        totals = next((m for m in b.get("markets", []) if m["key"] == "totals"), None)
                        if totals:
                            o_o = next((o for o in totals.get("outcomes", []) if o["name"].lower() == "over"), None)
                            u_o = next((o for o in totals.get("outcomes", []) if o["name"].lower() == "under"), None)
                            if o_o and u_o:
                                bookie_line = o_o['point']
                                rec_text = f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: OVER {bookie_line}</span> at {decimal_to_fractional(o_o['price'])} (via {b['title']})</div>" if proj['proj_total'] > (bookie_line + 0.5) else f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: UNDER {bookie_line}</span> at {decimal_to_fractional(u_o['price'])} (via {b['title']})</div>" if proj['proj_total'] < (bookie_line - 0.5) else ""
                                if rec_text: st.markdown(rec_text, unsafe_allow_html=True)
                            break

    # ── PLAYER PROP TABS (FILTER DEPENDENT) ──
    market_map = {"🎯 Hits/Runs/RBI": ("Hits/Runs/RBI", "Why_Hits"), "🏏 RBIs": ("RBI", "Why_RBI"), "💥 Home Runs": ("Home Run", "Why_HR"), "🏃‍♂️ Runs Scored": ("Runs Scored", "Why_Runs")}
    
    for t_idx, (tab_name, data_tuple) in enumerate(market_map.items(), start=5):
        with tabs[t_idx]:
            if df.empty:
                st.info("⚠️ No batters passed the strict Math Filters in the sidebar for today's slate. Try widening the filters.")
            else:
                m_col, why_col = data_tuple
                st.subheader(f"🏆 Top Picks: {m_col}")
                sub = df[df[m_col] > 0.0].sort_values(by=m_col, ascending=False)
                
                if sub.empty:
                    st.info("No batters met the mathematical criteria for " + m_col)
                else:
                    for _, row in sub.head(3).iterrows():
                        st.markdown(f"""
                        <div class="value-card">
                            <div class="vc-header">
                                <span class="vc-name">{row['Batter']} ({row['Side']})</span>
                                <span class="vc-grade">{row['Grade']}</span>
                            </div>
                            <div class="vc-sub">Batting #{row['Order']} vs {row['Opp Pitcher']}</div>
                            <div class="vc-why"><b>Why:</b> {row[why_col]}</div>
                        </div>
                        """, unsafe_allow_html=True)
