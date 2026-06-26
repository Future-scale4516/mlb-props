import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Value Matrix v5.1", page_icon="⚾", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:#f7f6f2;}
.metric-card{background:#fff;border-radius:12px;padding:14px 18px;border:1px solid #dcd9d5;
  box-shadow:0 2px 8px rgba(0,0,0,.05);text-align:center;margin-bottom:10px;}
.metric-value{font-size:1.7rem;font-weight:700;color:#01696f;}
.metric-label{font-size:.72rem;color:#7a7974;text-transform:uppercase;letter-spacing:.05em;margin-top:3px;}
section[data-testid="stSidebar"]{background:#1c1b19;}
section[data-testid="stSidebar"] *{color:#cdccca !important;}
.odds-box {background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:12px; margin-top:8px; margin-bottom: 12px;}
.pick-text {color: #166534; font-weight: 800; font-size: 1.15rem;}
.ev-text {color: #15803d; font-weight: 700; background: #dcfce7; padding: 2px 6px; border-radius: 4px;}
</style>
""", unsafe_allow_html=True)

# ── BUG 4: Restored exact lat/lon coordinates for weather API ──
BALLPARKS = {
    "Oriole Park at Camden Yards": {"lat":39.2839,"lon":-76.6217,"factor":1.02,"dome":False},
    "Yankee Stadium":              {"lat":40.8296,"lon":-73.9262,"factor":1.05,"dome":False},
    "Fenway Park":                 {"lat":42.3467,"lon":-71.0972,"factor":1.08,"dome":False},
    "Wrigley Field":               {"lat":41.9484,"lon":-87.6553,"factor":1.05,"dome":False},
    "Rogers Centre":               {"lat":43.6414,"lon":-79.3894,"factor":1.05,"dome":True},
    "Coors Field":                 {"lat":39.7559,"lon":-104.9942,"factor":1.38,"dome":False},
    "loanDepot park":              {"lat":25.7781,"lon":-80.2197,"factor":0.93,"dome":True},
    "Oracle Park":                 {"lat":37.7786,"lon":-122.3893,"factor":0.93,"dome":False},
    "Petco Park":                  {"lat":32.7073,"lon":-117.1566,"factor":0.90,"dome":False},
    "Citi Field":                  {"lat":40.7571,"lon":-73.8458,"factor":0.94,"dome":False},
    "PNC Park":                    {"lat":40.4469,"lon":-80.0057,"factor":0.97,"dome":False},
    "Tropicana Field":             {"lat":27.7683,"lon":-82.6534,"factor":0.94,"dome":True},
    "Kauffman Stadium":            {"lat":39.0517,"lon":-94.4803,"factor":1.01,"dome":False},
    "Guaranteed Rate Field":       {"lat":41.8300,"lon":-87.6338,"factor":1.04,"dome":False},
    "Truist Park":                 {"lat":33.8907,"lon":-84.4677,"factor":1.01,"dome":False},
    "Angel Stadium":               {"lat":33.8003,"lon":-117.8827,"factor":1.00,"dome":False},
    "T-Mobile Park":               {"lat":47.5914,"lon":-122.3325,"factor":0.94,"dome":False},
    "Dodger Stadium":              {"lat":34.0739,"lon":-118.2400,"factor":0.97,"dome":False},
    "Busch Stadium":               {"lat":38.6226,"lon":-90.1928,"factor":0.97,"dome":False},
    "Progressive Field":           {"lat":41.4962,"lon":-81.6852,"factor":0.96,"dome":False},
    "Comerica Park":               {"lat":42.3390,"lon":-83.0485,"factor":0.95,"dome":False},
    "Globe Life Field":            {"lat":32.7473,"lon":-97.0847,"factor":1.02,"dome":True},
    "Great American Ball Park":    {"lat":39.0979,"lon":-84.5081,"factor":1.10,"dome":False},
    "American Family Field":       {"lat":43.0280,"lon":-87.9712,"factor":1.00,"dome":True},
    "Chase Field":                 {"lat":33.4453,"lon":-112.0667,"factor":1.02,"dome":True},
    "Nationals Park":              {"lat":38.8730,"lon":-77.0074,"factor":0.99,"dome":False},
    "Sutter Health Park":          {"lat":38.5802,"lon":-121.5014,"factor":1.05,"dome":False},
}

# ── BUG 2: Global safe_get restored to prevent weather crashes ──
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

# ── BUG 1: RapidAPI Host and Headers properly configured ──
def highlightly_get(endpoint, api_key, params=None):
    url = f"https://baseball-highlightly.p.rapidapi.com/{endpoint}"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "baseball-highlightly.p.rapidapi.com"
    }
    return safe_get(url, headers=headers, params=params)

# ── BUG 5: Resilient Data Parsing Applied ──
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_matches_highlightly(target_date: str, api_key: str):
    data = highlightly_get("matches", api_key, {"league": "MLB", "date": target_date})
    # Safely cascading down the JSON tree depending on RapidAPI wrapper
    matches = data.get("response", data.get("data", data.get("matches", data if isinstance(data, list) else [])))
    
    rows = []
    for g in matches:
        a_name = g.get("awayTeam", {}).get("name") if isinstance(g.get("awayTeam"), dict) else g.get("awayTeamName", "Away")
        h_name = g.get("homeTeam", {}).get("name") if isinstance(g.get("homeTeam"), dict) else g.get("homeTeamName", "Home")
        rows.append({
            "gamePk": g.get("id"), 
            "status": g.get("state", {}).get("description", "Scheduled") if isinstance(g.get("state"), dict) else "Scheduled",
            "away_team": a_name, "home_team": h_name, 
            "away_prob_name": "TBD", "home_prob_name": "TBD",
            "game_time_bst": g.get("time", "TBD"), 
            "venue": g.get("venue", {}).get("name", "") if isinstance(g.get("venue"), dict) else g.get("venue", ""), 
            "game_date_raw": g.get("date", target_date)
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_player_stats_highlightly(season: int, api_key: str):
    data = highlightly_get("players", api_key, {"league": "MLB", "season": season, "limit": 2000})
    players = data.get("response", data.get("data", data.get("players", data if isinstance(data, list) else [])))
    
    rows, lg_ops = [], 0.730
    for p in players:
        stats = p.get("statistics", {})
        slg, avg, obp, ops = float(stats.get("slg") or 0), float(stats.get("avg") or 0), float(stats.get("obp") or 0), float(stats.get("ops") or 0)
        pa, iso_val = int(stats.get("plateAppearances") or stats.get("pa") or 1), round(slg - avg, 3)
        rows.append({
            "player_id": p.get("id", 0), "name": p.get("name", ""),
            "avg": avg, "obp": obp, "slg": slg, "ops": ops, "iso": iso_val,
            "wrc_plus": int((ops / lg_ops) * 100) if lg_ops > 0 else 100,
            "barrel_pct": min(0.22, max(0.01, iso_val * 0.45)), "hard_hit_pct": min(0.60, max(0.15, (ops * 0.45) + (iso_val * 0.2))),
            "plateAppearances": pa, "k_pct": float(stats.get("strikeOuts") or stats.get("so") or 0) / max(1, pa)
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_lineups_highlightly(match_id, api_key: str):
    data = highlightly_get(f"lineups/{match_id}", api_key)
    out = {"away": pd.DataFrame(), "home": pd.DataFrame()}
    
    response_body = data.get("response", data.get("data", data))
    
    if isinstance(response_body, dict):
        for side in ["away", "home"]:
            team_data = response_body.get(f"{side}Team", {}).get("lineup", [])
            rows = [{"player_id": p.get("id"), "name": p.get("name", "Unknown"), "order": p.get("battingOrder", 9)} for p in team_data]
            if rows: out[side] = pd.DataFrame(rows).sort_values("order")
    return out

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_odds_api(api_key: str):
    if not api_key or api_key.strip() == "": return {}
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {"apiKey": api_key, "regions": "uk", "markets": "h2h,spreads,totals", "bookmakers": "williamhill,paddypower,betfair,bet365,skybet", "oddsFormat": "decimal"}
    
    data = safe_get(url, params=params)
    out = {}
    if isinstance(data, list):
        for item in data: 
            out[f"{item.get('away_team')} @ {item.get('home_team')}"] = item.get("bookmakers", [])
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue_name: str):
    meta = BALLPARKS.get(venue_name)
    if not meta: return {"temp":72,"wind":8,"factor":1.00,"dome":False,"venue":venue_name}
    if meta["dome"]: return {"temp":72,"wind":0,"factor":meta["factor"],"dome":True,"venue":venue_name}
    
    data = safe_get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": meta["lat"], "longitude": meta["lon"], 
        "current": "temperature_2m,wind_speed_10m", 
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph"
    })
    
    c = data.get("current",{})
    return {
        "temp": float(c.get("temperature_2m", 72)),
        "wind": float(c.get("wind_speed_10m", 8)),
        "factor": meta["factor"],
        "dome": False,
        "venue": venue_name
    }

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004

# ── BUG 6: Multi-line expressions in score_batter fixed ──
def score_batter(avg, obp, slg, iso, wrc_plus, hard_hit, barrel, order, era, whip, hr9, k9, env, w_era, w_whip):
    of  = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(order, 0.80)
    pv  = min(era/7.0,1.0)*w_era + min(max((whip-0.8)/1.2,0.0),1.0)*w_whip
    hrv = min(hr9/2.5,1.0)
    k_adj = 1.0 - min((k9-7.0)/14.0, 0.20)
    
    contact = avg*0.35 + obp*0.30 + (wrc_plus/200)*0.25 + (1-0.22)*0.10
    power   = iso*0.40 + hard_hit*0.35 + barrel*0.25
    on_base = obp * (wrc_plus/100)
        
    hits_runs_score = round(contact * pv * of * k_adj * env * 280, 2)
    rbi_score       = round(contact * pv * (1.0 + max(0, (5-order)*0.04)) * k_adj * env * 260, 2)
    hr_score        = round(power * hrv * env * 280, 2)
    runs_score      = round(on_base * pv * (1.0 + max(0, (4-order)*0.05)) * k_adj * env * 280, 2)

    if iso < 0.130 or barrel < 0.04 or hr9 < 0.7: hr_score = 0.0
    if order > 7 or wrc_plus < 80: rbi_score = 0.0
    if order > 5 or obp < 0.290: runs_score = 0.0

    return {"Hits/Runs": hits_runs_score, "RBI": rbi_score, "Home Run": hr_score, "Runs Scored": runs_score}

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚾ API Configuration")
    
    # ── BUG 3: API Keys are empty by default and guarded below ──
    hl_key = st.text_input("Highlightly API Key (RapidAPI)", value="", type="password")
    odds_key = st.text_input("The-Odds-API Key", value="", type="password")
    
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Model Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    min_obp  = st.slider("Min OBP",   0.250, 0.400, 0.280, 0.005, format="%.3f")
    max_ord  = st.slider("Max Order", 1, 9, 9)
    
    if st.button("Clear App Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "game_proj_dict", "odds_data"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

st.title("⚾ MLB Full-Game & Prop Value Matrix")
st.divider()

# Stop execution immediately if keys are missing
if not hl_key or not odds_key:
    st.warning("⚠️ Please enter your Highlightly API Key and The-Odds-API Key in the sidebar to run the engine.")
    st.stop()

if st.button("Load Today's Slate", type="primary"):
    with st.status("Assembling metrics from hybrid data stream...", expanded=True) as status:
        
        sched = fetch_matches_highlightly(str(sel_date), hl_key)
        if sched.empty: st.error("Highlightly returned 0 games. Verify your key and the selected date."); st.stop()
        mlb_all = fetch_player_stats_highlightly(sel_date.year, hl_key)
        
        odds_data = fetch_live_odds_api(odds_key)
        st.session_state["odds_data"] = odds_data

        all_rows, game_projections = [], {}

        for _, g in sched.iterrows():
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            
            lineups = fetch_lineups_highlightly(g["gamePk"], hl_key)
            away_conf, home_conf = not lineups.get("away",pd.DataFrame()).empty, not lineups.get("home",pd.DataFrame()).empty
            away_ids = lineups.get("away", pd.DataFrame())["player_id"].tolist() if away_conf else []
            home_ids = lineups.get("home", pd.DataFrame())["player_id"].tolist() if home_conf else []
            stats_map_away, stats_map_home = lineups.get("away", pd.DataFrame()), lineups.get("home", pd.DataFrame())
            
            # Highlightly fallback pitcher stats
            away_pitch = {"name": "TBD", "era": 4.5, "whip": 1.35, "homeRunsPer9": 1.2, "strikeoutsPer9Inn": 8.5}
            home_pitch = {"name": "TBD", "era": 4.5, "whip": 1.35, "homeRunsPer9": 1.2, "strikeoutsPer9Inn": 8.5}
            
            wx = fetch_weather(g["venue"])
            total_env = wx["factor"] * wx_modifier(wx["temp"], wx["wind"], wx["dome"])
            env_symbol = "🟢 Hitter-Friendly" if total_env >= 1.06 else "🟡 Neutral" if total_env >= 0.97 else "🔴 Pitcher-Friendly"
            weather_str = "🏟️ Dome" if wx["dome"] else f"🌡️ {int(wx['temp'])}°F | 💨 {int(wx['wind'])} mph"
            lineup_badge = "✅ Confirmed" if (away_conf and home_conf) else "⏳ Projected"

            away_wrcs, home_wrcs = [], []

            for side_label, player_ids, stats_map, opp_pitch in [("Away", away_ids, stats_map_away, home_pitch), ("Home", home_ids, stats_map_home, away_pitch)]:
                for pid in player_ids:
                    order = 9 
                    if not stats_map.empty and "player_id" in stats_map.columns:
                        p_match = stats_map[stats_map["player_id"] == int(pid)]
                        if not p_match.empty: order = int(p_match.iloc[0].get("order", 9) or 9)

                    mlb_row = mlb_all[mlb_all["player_id"] == int(pid)] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty: continue  
                    base = mlb_row.iloc[0].to_dict()

                    if side_label == "Away" and order <= max_ord: away_wrcs.append(base["wrc_plus"])
                    if side_label == "Home" and order <= max_ord: home_wrcs.append(base["wrc_plus"])

                    if base["avg"] >= min_avg and base["obp"] >= min_obp:
                        scores = score_batter(base["avg"], base["obp"], base["slg"], base["iso"], base["wrc_plus"], base["hard_hit_pct"], base["barrel_pct"], order, opp_pitch["era"], opp_pitch["whip"], opp_pitch["homeRunsPer9"], opp_pitch["strikeoutsPer9Inn"], total_env, 0.55, 0.45)
                        best_market = max(scores, key=scores.get)
                        all_rows.append({
                            "Game": g_matchup, "Side": side_label, "Batter": base["name"], "Order": order,
                            "AVG": base["avg"], "OBP": base["obp"], "ISO": base["iso"], "wRC+": base["wrc_plus"],
                            "Hits/Runs": scores["Hits/Runs"], "RBI": scores["RBI"], "Home Run": scores["Home Run"], "Runs Scored": scores["Runs Scored"],
                            "Best Market": best_market, "Best Score": scores[best_market],
                            "Grade": "🟢 Premium" if scores[best_market] >= 70.0 else "🟡 Playable" if scores[best_market] >= 48.0 else "🔴 Sub-optimal",
                            "Game Time BST": g["game_time_bst"], "Venue": g["venue"], "Game Datetime": g["game_date_raw"],
                            "Env Symbol": env_symbol, "Weather Str": weather_str, "Lineup Badge": lineup_badge
                        })

            mean_away_wrc = sum(away_wrcs)/len(away_wrcs) if away_wrcs else 100
            mean_home_wrc = sum(home_wrcs)/len(home_wrcs) if home_wrcs else 100
            proj_away_runs = round(4.1 * (mean_away_wrc/100) * (home_pitch["era"]/4.3) * wx["factor"], 2)
            proj_home_runs = round(4.1 * (mean_home_wrc/100) * (away_pitch["era"]/4.3) * wx["factor"], 2)
            away_prob = round((proj_away_runs**1.83) / ((proj_away_runs**1.83) + (proj_home_runs**1.83)), 4) if (proj_away_runs + proj_home_runs) > 0 else 0.5
            
            game_projections[g_matchup] = {
                "proj_away_runs": proj_away_runs, "proj_home_runs": proj_home_runs,
                "away_prob": away_prob, "home_prob": 1.0 - away_prob, 
                "proj_total": round(proj_away_runs + proj_home_runs, 1),
                "proj_line": round(proj_home_runs - proj_away_runs, 1)
            }

        if all_rows:
            st.session_state["auto_df"] = pd.DataFrame(all_rows)
            st.session_state["game_proj_dict"] = game_projections
            status.update(label="Analytics matrices compiled successfully.", state="complete")
        else:
            status.update(label="No historical datasets matched the active filter threshold configuration.", state="error")

# ── RENDER GRAPHICS COMPONENT ────────────────────────────────────────────────
if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data = st.session_state.get("odds_data", {})

    market_tabs = ["🎯 Hits/Runs", "🏏 RBIs", "💥 Home Runs", "🏃‍♂️ Runs Scored", "🗂️ Matchups", "💰 Moneyline", "📈 Run Line", "📊 Totals"]
    rendered_tabs = st.tabs(market_tabs)

    for idx, m_name in enumerate(["Hits/Runs", "RBI", "Home Run", "Runs Scored"]):
        with rendered_tabs[idx]:
            st.subheader(f"🏆 Top Global {m_name} Profiles")
            m_sorted = df.sort_values(m_name, ascending=False).head(10)
            st.dataframe(m_sorted[["Game", "Batter", "Order", "AVG" if m_name=="Hits/Runs" else "wRC+" if m_name=="RBI" else "ISO", m_name, "Grade"]].reset_index(drop=True), use_container_width=True)
            
            st.markdown(f"### 🗂️ Best Players Per Match ({m_name})")
            sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")
            for g_name in sorted_games["Game"].tolist():
                g_players = df[df["Game"] == g_name].sort_values(m_name, ascending=False).head(3)
                if g_players.empty: continue
                sample = g_players.iloc[0]
                with st.expander(f"🏟️ {g_name} | 🕒 {sample['Game Time BST']} (Top picks for {m_name})"):
                    st.dataframe(g_players[["Order", "Side", "Batter", "wRC+", "AVG", "ISO", m_name, "Grade"]].reset_index(drop=True), use_container_width=True)

    sorted_matchups = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")["Game"].tolist()

    # ── TAB: RAW MATCHUPS OVERVIEW ──
    with rendered_tabs[4]:
        st.subheader("🗂️ Matchup Overview & Roster Lineups")
        for game_matchup in sorted_matchups:
            game_df = df[df["Game"] == game_matchup].sort_values("Order")
            sample = game_df.iloc[0]
            away_team, home_team = game_matchup.split(" @ ")
            
            with st.expander(f"⚾ {game_matchup} | 🕒 {sample['Game Time BST']} | {sample['Venue']} ({sample['Weather Str']}) | {sample['Env Symbol']} | {sample['Lineup Badge']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"🚀 {away_team} Roster Lineup")
                    st.dataframe(game_df[game_df["Side"] == "Away"][["Order", "Batter", "wRC+", "OBP", "ISO", "Grade"]].reset_index(drop=True), use_container_width=True)
                with col2:
                    st.caption(f"🏠 {home_team} Roster Lineup")
                    st.dataframe(game_df[game_df["Side"] == "Home"][["Order", "Batter", "wRC+", "OBP", "ISO", "Grade"]].reset_index(drop=True), use_container_width=True)

    # ── TAB: MONEYLINE OVERLAY (BUG 7: Restored) ──
    with rendered_tabs[5]:
        st.subheader("💰 Live Moneyline Value")
        for game_matchup in sorted_matchups:
            proj = game_proj_dict.get(game_matchup)
            away_team, home_team = game_matchup.split(" @ ")
            match_odds_list = odds_data.get(game_matchup, [])
            
            if match_odds_list:
                best_away_ev, best_home_ev = -100, -100
                best_away_bookie, best_home_bookie = "", ""
                away_price, home_price = "", ""
                
                for b in match_odds_list:
                    h2h = next((m for m in b.get("markets", []) if m["key"] == "h2h"), None)
                    if h2h:
                        out = h2h.get("outcomes", [])
                        a_o = next((o for o in out if o["name"] == away_team), None)
                        h_o = next((o for o in out if o["name"] == home_team), None)
                        if a_o and h_o:
                            a_ev = ((proj["away_prob"] * a_o["price"]) - 1.0) * 100
                            h_ev = ((proj["home_prob"] * h_o["price"]) - 1.0) * 100
                            if a_ev > best_away_ev:
                                best_away_ev, best_away_bookie, away_price = a_ev, b["title"], decimal_to_fractional(a_o["price"])
                            if h_ev > best_home_ev:
                                best_home_ev, best_home_bookie, home_price = h_ev, b["title"], decimal_to_fractional(h_o["price"])
                
                with st.container(border=True):
                    st.markdown(f"**{game_matchup}** | Model Probabilities: {away_team} ({proj['away_prob']*100:.1f}%) vs {home_team} ({proj['home_prob']*100:.1f}%)")
                    if best_away_ev > 0:
                        st.markdown(f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: Back {away_team}</span> at {away_price} (via {best_away_bookie}) | <span class='ev-text'>+{best_away_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                    elif best_home_ev > 0:
                        st.markdown(f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: Back {home_team}</span> at {home_price} (via {best_home_bookie}) | <span class='ev-text'>+{best_home_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                    else:
                        st.write("No mathematical value edge found on current bookmaker lines.")

    # ── TAB: RUN LINE OVERLAY (BUG 7: Restored) ──
    with rendered_tabs[6]:
        st.subheader("📈 Live Run Line Value")
        for game_matchup in sorted_matchups:
            proj = game_proj_dict.get(game_matchup)
            away_team, home_team = game_matchup.split(" @ ")
            match_odds_list = odds_data.get(game_matchup, [])
            
            with st.container(border=True):
                st.markdown(f"**{game_matchup}** | Model Projected Gap: {proj['proj_line']} ({home_team} advantage)")
                found_spread = False
                if match_odds_list:
                    for b in match_odds_list:
                        spreads = next((m for m in b.get("markets", []) if m["key"] == "spreads"), None)
                        if spreads:
                            found_spread = True
                            out = spreads.get("outcomes", [])
                            a_o = next((o for o in out if o["name"] == away_team), None)
                            if a_o:
                                rec_text = ""
                                if proj['proj_line'] < (a_o['point'] * -1): 
                                    rec_text = f"<br><span class='pick-text'>🤖 Model Recommends: Back {away_team} {a_o['point']}</span>"
                                st.markdown(f"*{b['title']}:* {away_team} {a_o['point']} at {decimal_to_fractional(a_o['price'])} {rec_text}", unsafe_allow_html=True)
                            break 
                if not found_spread:
                    st.write("Awaiting live run line data.")

    # ── TAB: TOTALS OVERLAY (BUG 7: Restored) ──
    with rendered_tabs[7]:
        st.subheader("📊 Live Totals (Overs/Unders)")
        for game_matchup in sorted_matchups:
            proj = game_proj_dict.get(game_matchup)
            match_odds_list = odds_data.get(game_matchup, [])
            
            with st.container(border=True):
                st.markdown(f"**{game_matchup}** | Model Projected Total: **{proj['proj_total']} Runs**")
                found_total = False
                if match_odds_list:
                    for b in match_odds_list:
                        totals = next((m for m in b.get("markets", []) if m["key"] == "totals"), None)
                        if totals:
                            found_total = True
                            out = totals.get("outcomes", [])
                            o_o = next((o for o in out if o["name"].lower() == "over"), None)
                            u_o = next((o for o in out if o["name"].lower() == "under"), None)
                            if o_o and u_o:
                                bookie_line = o_o['point']
                                rec_text = ""
                                if proj['proj_total'] > (bookie_line + 0.5):
                                    rec_text = f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: OVER {bookie_line}</span> at {decimal_to_fractional(o_o['price'])} (via {b['title']})</div>"
                                elif proj['proj_total'] < (bookie_line - 0.5):
                                    rec_text = f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: UNDER {bookie_line}</span> at {decimal_to_fractional(u_o['price'])} (via {b['title']})</div>"
                                
                                if rec_text:
                                    st.markdown(rec_text, unsafe_allow_html=True)
                                else:
                                    st.write(f"Line set accurately at {bookie_line} by {b['title']}. No edge.")
                            break
                if not found_total:
                    st.write("Awaiting live totals data.")
