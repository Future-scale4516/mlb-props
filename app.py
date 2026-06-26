import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Prop & Game Analyser v5", page_icon="âš¾", layout="wide")

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

BALLPARKS = {
    "Oriole Park at Camden Yards": {"factor":1.02,"dome":False}, "Yankee Stadium": {"factor":1.05,"dome":False},
    "Fenway Park": {"factor":1.08,"dome":False}, "Wrigley Field": {"factor":1.05,"dome":False},
    "Rogers Centre": {"factor":1.05,"dome":True}, "Coors Field": {"factor":1.38,"dome":False},
    "loanDepot park": {"factor":0.93,"dome":True}, "Oracle Park": {"factor":0.93,"dome":False},
    "Petco Park": {"factor":0.90,"dome":False}, "Citi Field": {"factor":0.94,"dome":False},
    "PNC Park": {"factor":0.97,"dome":False}, "Tropicana Field": {"factor":0.94,"dome":True},
    "Kauffman Stadium": {"factor":1.01,"dome":False}, "Guaranteed Rate Field": {"factor":1.04,"dome":False},
    "Truist Park": {"factor":1.01,"dome":False}, "Angel Stadium": {"factor":1.00,"dome":False},
    "T-Mobile Park": {"factor":0.94,"dome":False}, "Dodger Stadium": {"factor":0.97,"dome":False},
    "Busch Stadium": {"factor":0.97,"dome":False}, "Progressive Field": {"factor":0.96,"dome":False},
    "Comerica Park": {"factor":0.95,"dome":False}, "Globe Life Field": {"factor":1.02,"dome":True},
    "Great American Ball Park": {"factor":1.10,"dome":False}, "American Family Field": {"factor":1.00,"dome":True},
    "Chase Field": {"factor":1.02,"dome":True}, "Nationals Park": {"factor":0.99,"dome":False},
    "Sutter Health Park": {"factor":1.05,"dome":False},
}

def decimal_to_fractional(dec):
    if not dec or dec <= 1.0: return "N/A"
    if dec == 2.0: return "EVENS"
    frac = Fraction(dec - 1.0).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"

# â”€â”€ API PATHWAY 1: HIGHLIGHTLY (METADATA, STATS & LINEUPS) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def highlightly_get(endpoint, api_key, params=None):
    """Hits the correct dedicated Highlightly MLB endpoint."""
    url = f"https://baseball.highlightly.net/{endpoint}"
    headers = {"x-rapidapi-key": api_key}
    for attempt in range(3):
        try:
            r = req.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except:
            if attempt == 2: return {}
            time.sleep(1)
    return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_matches_highlightly(target_date: str, api_key: str):
    data = highlightly_get("matches", api_key, {"leagueName": "MLB", "date": target_date, "limit": 100})
    rows = []
    matches = data.get("data", []) if isinstance(data, dict) else data
    for g in matches:
        rows.append({
            "gamePk": g.get("id"),
            "status": g.get("state", {}).get("current", "Scheduled") if isinstance(g.get("state"), dict) else g.get("state", "Scheduled"),
            "away_team": g.get("awayTeamName", "Away"),
            "home_team": g.get("homeTeamName", "Home"),
            "game_time_bst": g.get("time", "TBD"),
            "venue": g.get("venue", ""),
            "game_date_raw": g.get("date", target_date)
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_player_stats_highlightly(season: int, api_key: str):
    data = highlightly_get("players", api_key, {"leagueName": "MLB", "season": season, "limit": 2000})
    rows = []
    players = data.get("data", []) if isinstance(data, dict) else data
    lg_ops = 0.730 
    
    for p in players:
        stats = p.get("statistics", {})
        slg, avg, obp = float(stats.get("slg") or 0), float(stats.get("avg") or 0), float(stats.get("obp") or 0)
        ops = float(stats.get("ops") or 0)
        iso_val = round(slg - avg, 3)
        wrc_plus_proxy = int((ops / lg_ops) * 100) if lg_ops > 0 else 100
        
        rows.append({
            "player_id": p.get("id", 0),
            "name": p.get("name", ""),
            "avg": avg, "obp": obp, "slg": slg, "ops": ops,
            "iso": iso_val, "wrc_plus": wrc_plus_proxy,
            "barrel_pct": min(0.22, max(0.01, iso_val * 0.45)),
            "hard_hit_pct": min(0.60, max(0.15, (ops * 0.45) + (iso_val * 0.2))),
            "plateAppearances": int(stats.get("plateAppearances") or 1),
            "k_pct": float(stats.get("strikeOuts") or 0) / max(1, float(stats.get("plateAppearances") or 1))
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_lineups_highlightly(match_id, api_key: str):
    data = highlightly_get(f"lineups/{match_id}", api_key)
    out = {"away": pd.DataFrame(), "home": pd.DataFrame()}
    if isinstance(data, dict):
        for side in ["away", "home"]:
            rows = []
            team_data = data.get(f"{side}Team", {}).get("lineup", [])
            for p in team_data:
                rows.append({"player_id": p.get("id"), "name": p.get("name"), "order": p.get("battingOrder", 9)})
            if rows:
                out[side] = pd.DataFrame(rows).sort_values("order")
    return out

# â”€â”€ API PATHWAY 2: THE-ODDS-API (UK MARKET DATA OVERLAY) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_odds_api(api_key: str):
    if not api_key or api_key.strip() == "": return {}
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": api_key, "regions": "uk", "markets": "h2h,spreads,totals",
        "bookmakers": "williamhill,paddypower,betfair,bet365,skybet", "oddsFormat": "decimal"
    }
    for attempt in range(3):
        try:
            r = req.get(url, params=params, timeout=15)
            r.raise_for_status()
            res = r.json()
            out = {}
            if isinstance(res, list):
                for item in res:
                    out[f"{item.get('away_team')} @ {item.get('home_team')}"] = item.get("bookmakers", [])
            return out
        except:
            if attempt == 2: return {}
            time.sleep(1)
    return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue_name: str):
    meta = BALLPARKS.get(venue_name)
    if not meta: return {"temp":72,"wind":8,"factor":1.00,"dome":False,"venue":venue_name}
    if meta["dome"]: return {"temp":72,"wind":0,"factor":meta["factor"],"dome":True,"venue":venue_name}
    try:
        data = safe_get("https://api.open-meteo.com/v1/forecast", {
            "latitude":meta.get("lat", 39.0), "longitude":meta.get("lon", -95.0),
            "current":"temperature_2m,wind_speed_10m",
            "temperature_unit":"fahrenheit","wind_speed_unit":"mph"
        })
        c = data.get("current",{})
        return {"temp":float(c.get("temperature_2m") or 72),"wind":float(c.get("wind_speed_10m") or 8),
                "factor":meta["factor"],"dome":False,"venue":venue_name}
    except:
        return {"temp":72, "wind":8, "factor":meta["factor"], "dome":False, "venue":venue_name}

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004

def score_batter(avg, obp, slg, iso, wrc_plus, hard_hit, barrel, order, era, whip, hr9, k9, env, w_era, w_whip):
    of  = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(order, 0.80)
    pv  = min(era/7.0,1.0)*w_era + min(max((whip-0.8)/1.2,0.0),1.0)*w_whip
    hrv = min(hr9/2.5,1.0)
    k_adj = 1.0 - min((k9-7.0)/14.0, 0.20)
    
    contact = avg*0.35 + obp*0.30 + (wrc_plus/200)*0.25 + (1-0.22)*0.10
    power   = iso*0.40 + hard_hit*0.35 + barrel*0.25
    on_base = obp * (wrc_plus/100)
        
    hits_runs_score = round(contact * pv * of * k_adj * env * 280, 2)
    rbi_score       = round(contact * pv * (1.0 + max(0,(5-order)*0.04)) * k_adj * env * 260, 2)
    hr_score        = round(power   * hrv * env * 280, 2)
    runs_score      = round(on_base * pv * (1.0 + max(0,(4-order)*0.05)) * k_adj * env * 280, 2)

    if iso < 0.130 or barrel < 0.04 or hr9 < 0.7: hr_score = 0.0
    if order > 7 or wrc_plus < 80: rbi_score = 0.0
    if order > 5 or obp < 0.290: runs_score = 0.0

    return {"Hits/Runs": hits_runs_score, "RBI": rbi_score, "Home Run": hr_score, "Runs Scored": runs_score}

# â”€â”€ SIDEBAR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
with st.sidebar:
    st.markdown("## âš¾ Hybrid Analytics Control")
    
    hl_key = st.text_input("Highlightly API Key", value="b7f47f42-746f-4df9-9284-a07065bb285c", type="password")
    odds_key = st.text_input("The-Odds-API Key", value="4b959d673d4ef9c7128271557c038dfe", type="password")
    
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Model Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    min_obp  = st.slider("Min OBP",   0.250, 0.400, 0.280, 0.005, format="%.3f")
    max_ord  = st.slider("Max Order", 1, 9, 9)
    
    st.markdown("---")
    if st.button("Clear App Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "game_proj_dict", "odds_data"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

st.title("âš¾ MLB Full-Game & Prop Value Matrix")
st.caption("Hybrid Framework: Roster Data via Highlightly | Real-Time Market Overlay via The-Odds-API")
st.divider()

if st.button("Load Today's Slate", type="primary"):
    with st.status("Assembling metrics from hybrid data stream...", expanded=True) as status:
        sched = fetch_matches_highlightly(str(sel_date), hl_key)
        if sched.empty: st.error("No games matched the criteria configuration. Check API keys or date."); st.stop()

        mlb_all = fetch_player_stats_highlightly(sel_date.year, hl_key)
        
        odds_data = fetch_live_odds_api(odds_key)
        st.session_state["odds_data"] = odds_data

        all_rows, game_projections = [], {}

        for _, g in sched.iterrows():
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            lineups = fetch_lineups_highlightly(g["gamePk"], hl_key)
            away_conf, home_conf = not lineups.get("away",pd.DataFrame()).empty, not lineups.get("home",pd.DataFrame()).empty
            
            wx = fetch_weather(g["venue"])
            total_env = wx["factor"] * wx_modifier(wx["temp"], wx["wind"], wx["dome"])
            env_symbol = "ðŸŸ¢ Hitter-Friendly" if total_env >= 1.06 else "ðŸŸ¡ Neutral" if total_env >= 0.97 else "ðŸ”´ Pitcher-Friendly"
            weather_str = "ðŸŸï¸ Dome" if wx["dome"] else f"ðŸŒ¡ï¸ {int(wx['temp'])}Â°F | ðŸ’¨ {int(wx['wind'])} mph"
            lineup_badge = "âœ… Confirmed" if (away_conf and home_conf) else "â³ Projected"

            opp_pitch = {"era": 4.5, "whip": 1.35, "homeRunsPer9": 1.2, "strikeoutsPer9Inn": 8.5}
            away_wrcs, home_wrcs = [], []

            for side_label, roster_df in [("Away", lineups.get("away", pd.DataFrame())), ("Home", lineups.get("home", pd.DataFrame()))]:
                if roster_df.empty: continue
                
                for _, p_row in roster_df.iterrows():
                    order = int(p_row.get("order", 9))
                    pid = p_row.get("player_id")
                    pname = p_row.get("name")

                    mlb_row = mlb_all[mlb_all["player_id"] == pid] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty: continue  
                    base = mlb_row.iloc[0].to_dict()

                    if side_label == "Away" and order <= max_ord: away_wrcs.append(base["wrc_plus"])
                    if side_label == "Home" and order <= max_ord: home_wrcs.append(base["wrc_plus"])

                    if base["avg"] >= min_avg and base["obp"] >= min_obp:
                        scores = score_batter(base["avg"], base["obp"], base["slg"], base["iso"], base["wrc_plus"], base["hard_hit_pct"], base["barrel_pct"], order, opp_pitch["era"], opp_pitch["whip"], opp_pitch["homeRunsPer9"], opp_pitch["strikeoutsPer9Inn"], total_env, 0.55, 0.45)
                        best_market = max(scores, key=scores.get)
                        all_rows.append({
                            "Game": g_matchup, "Side": side_label, "Batter": pname, "Order": order,
                            "AVG": base["avg"], "OBP": base["obp"], "ISO": base["iso"], "wRC+": base["wrc_plus"],
                            "Hits/Runs": scores["Hits/Runs"], "RBI": scores["RBI"], "Home Run": scores["Home Run"], "Runs Scored": scores["Runs Scored"],
                            "Best Market": best_market, "Best Score": scores[best_market],
                            "Grade": "ðŸŸ¢ Premium" if scores[best_market] >= 70.0 else "ðŸŸ¡ Playable" if scores[best_market] >= 48.0 else "ðŸ”´ Sub-optimal",
                            "Game Time BST": g["game_time_bst"], "Venue": g["venue"], "Game Datetime": g["game_date_raw"],
                            "Env Symbol": env_symbol, "Weather Str": weather_str, "Lineup Badge": lineup_badge
                        })

            mean_away_wrc = sum(away_wrcs)/len(away_wrcs) if away_wrcs else 100
            mean_home_wrc = sum(home_wrcs)/len(home_wrcs) if home_wrcs else 100
            proj_away_runs = round(4.1 * (mean_away_wrc/100) * (opp_pitch["era"]/4.3) * wx["factor"], 2)
            proj_home_runs = round(4.1 * (mean_home_wrc/100) * (opp_pitch["era"]/4.3) * wx["factor"], 2)
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

# â”€â”€ RENDER GRAPHICS COMPONENT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data = st.session_state.get("odds_data", {})

    market_tabs = ["ðŸŽ¯ Hits/Runs", "ðŸ RBIs", "ðŸ’¥ Home Runs", "ðŸƒâ€â™‚ï¸ Runs Scored", "ðŸ—‚ï¸ Matchups", "ðŸ’° Moneyline", "ðŸ“ˆ Run Line", "ðŸ“Š Totals"]
    rendered_tabs = st.tabs(market_tabs)

    for idx, m_name in enumerate(["Hits/Runs", "RBI", "Home Run", "Runs Scored"]):
        with rendered_tabs[idx]:
            st.subheader(f"ðŸ† Top Global {m_name} Profiles")
            m_sorted = df.sort_values(m_name, ascending=False).head(10)
            st.dataframe(m_sorted[["Game", "Batter", "Order", "AVG" if m_name=="Hits/Runs" else "wRC+" if m_name=="RBI" else "ISO", m_name, "Grade"]].reset_index(drop=True), use_container_width=True)
            
            st.markdown(f"### ðŸ—‚ï¸ Best Players Per Match ({m_name})")
            sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")
            for g_name in sorted_games["Game"].tolist():
                g_players = df[df["Game"] == g_name].sort_values(m_name, ascending=False).head(3)
                if g_players.empty: continue
                sample = g_players.iloc[0]
                with st.expander(f"ðŸŸï¸ {g_name} | ðŸ•’ {sample['Game Time BST']} (Top picks for {m_name})"):
                    st.dataframe(g_players[["Order", "Side", "Batter", "wRC+", "AVG", "ISO", m_name, "Grade"]].reset_index(drop=True), use_container_width=True)

    sorted_matchups = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")["Game"].tolist()

    # â”€â”€ TAB: RAW MATCHUPS OVERVIEW â”€â”€
    with rendered_tabs[4]:
        st.subheader("ðŸ—‚ï¸ Matchup Overview & Roster Lineups")
        for game_matchup in sorted_matchups:
            game_df = df[df["Game"] == game_matchup].sort_values("Order")
            sample = game_df.iloc[0]
            away_team, home_team = game_matchup.split(" @ ")
            
            with st.expander(f"âš¾ {game_matchup} ðŸ•’ {sample['Game Time BST']} | {sample['Venue']} ({sample['Weather Str']}) | {sample['Env Symbol']} | {sample['Lineup Badge']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"ðŸš€ {away_team} Roster Lineup")
                    st.dataframe(game_df[game_df["Side"] == "Away"][["Order", "Batter", "wRC+", "OBP", "ISO", "Grade"]].reset_index(drop=True), use_container_width=True)
                with col2:
                    st.caption(f"ðŸ  {home_team} Roster Lineup")
                    st.dataframe(game_df[game_df["Side"] == "Home"][["Order", "Batter", "wRC+", "OBP", "ISO", "Grade"]].reset_index(drop=True), use_container_width=True)

    # â”€â”€ TAB: MONEYLINE OVERLAY â”€â”€
    with rendered_tabs[5]:
        st.subheader("ðŸ’° Live Moneyline Value")
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
                        st.markdown(f"<div class='odds-box'><span class='pick-text'>ðŸ¤– Model Recommends: Back {away_team}</span> at {away_price} (via {best_away_bookie}) | <span class='ev-text'>+{best_away_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                    elif best_home_ev > 0:
                        st.markdown(f"<div class='odds-box'><span class='pick-text'>ðŸ¤– Model Recommends: Back {home_team}</span> at {home_price} (via {best_home_bookie}) | <span class='ev-text'>+{best_home_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                    else:
                        st.write("No mathematical value edge found on current bookmaker lines.")

    # â”€â”€ TAB: RUN LINE OVERLAY â”€â”€
    with rendered_tabs[6]:
        st.subheader("ðŸ“ˆ Live Run Line Value")
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
                                    rec_text = f"<br><span class='pick-text'>ðŸ¤– Model Recommends: Back {away_team} {a_o['point']}</span>"
                                st.markdown(f"*{b['title']}:* {away_team} {a_o['point']} at {decimal_to_fractional(a_o['price'])} {rec_text}", unsafe_allow_html=True)
                            break 
                if not found_spread:
                    st.write("Awaiting live run line data.")

    # â”€â”€ TAB: TOTALS OVERLAY â”€â”€
    with rendered_tabs[7]:
        st.subheader("ðŸ“Š Live Totals (Overs/Unders)")
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
                                    rec_text = f"<div class='odds-box'><span class='pick-text'>ðŸ¤– Model Recommends: OVER {bookie_line}</span> at {decimal_to_fractional(o_o['price'])} (via {b['title']})</div>"
                                elif proj['proj_total'] < (bookie_line - 0.5):
                                    rec_text = f"<div class='odds-box'><span class='pick-text'>ðŸ¤– Model Recommends: UNDER {bookie_line}</span> at {decimal_to_fractional(u_o['price'])} (via {b['title']})</div>"
                                
                                if rec_text:
                                    st.markdown(rec_text, unsafe_allow_html=True)
                                else:
                                    st.write(f"Line set accurately at {bookie_line} by {b['title']}. No edge.")
                            break
                if not found_total:
                    st.write("Awaiting live totals data.")