import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Prop & Game Analyser v3", page_icon="⚾", layout="wide")

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
.odds-box {background:#fff; border:1px solid #dcd9d5; border-radius:8px; padding:10px; margin-top:5px;}
</style>
""", unsafe_allow_html=True)

BALLPARKS = {
    "Oriole Park at Camden Yards": {"factor":1.02,"dome":False},
    "Yankee Stadium":              {"factor":1.05,"dome":False},
    "Fenway Park":                 {"factor":1.08,"dome":False},
    "Wrigley Field":               {"factor":1.05,"dome":False},
    "Rogers Centre":               {"factor":1.05,"dome":True},
    "Coors Field":                 {"factor":1.38,"dome":False},
    "loanDepot park":              {"factor":0.93,"dome":True},
    "Oracle Park":                 {"factor":0.93,"dome":False},
    "Petco Park":                  {"factor":0.90,"dome":False},
    "Citi Field":                  {"factor":0.94,"dome":False},
    "PNC Park":                    {"factor":0.97,"dome":False},
    "Tropicana Field":             {"factor":0.94,"dome":True},
    "Kauffman Stadium":            {"factor":1.01,"dome":False},
    "Guaranteed Rate Field":       {"factor":1.04,"dome":False},
    "Truist Park":                 {"factor":1.01,"dome":False},
    "Angel Stadium":               {"factor":1.00,"dome":False},
    "T-Mobile Park":               {"factor":0.94,"dome":False},
    "Dodger Stadium":              {"factor":0.97,"dome":False},
    "Busch Stadium":               {"factor":0.97,"dome":False},
    "Progressive Field":           {"factor":0.96,"dome":False},
    "Comerica Park":               {"factor":0.95,"dome":False},
    "Globe Life Field":            {"factor":1.02,"dome":True},
    "Great American Ball Park":    {"factor":1.10,"dome":False},
    "American Family Field":       {"factor":1.00,"dome":True},
    "Chase Field":                 {"factor":1.02,"dome":True},
    "Nationals Park":              {"factor":0.99,"dome":False},
    "Sutter Health Park":          {"factor":1.05,"dome":False},
}

def safe_get(url, params=None):
    for attempt in range(3):
        try:
            r = req.get(url, params=params, timeout=15)
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

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_schedule(target_date: str):
    data = safe_get("https://statsapi.mlb.com/api/v1/schedule", {
        "sportId":1, "date":target_date, "hydrate":"probablePitcher,team,venue,linescore"
    })
    rows = []
    for d in data.get("dates",[]):
        for g in d.get("games",[]):
            t = g.get("teams",{})
            raw_date = g.get("gameDate", "")
            bst_time_str = "TBD"
            if raw_date:
                try:
                    utc_dt = datetime.strptime(raw_date, "%Y-%m-%dT%H:%M:%SZ")
                    bst_dt = utc_dt + timedelta(hours=1)
                    bst_time_str = bst_dt.strftime("%H:%M BST")
                except: pass

            rows.append({
                "gamePk":         g.get("gamePk"),
                "status":         g.get("status",{}).get("detailedState", "Scheduled"),
                "away_team":      t.get("away",{}).get("team",{}).get("name"),
                "home_team":      t.get("home",{}).get("team",{}).get("name"),
                "away_team_id":   t.get("away",{}).get("team",{}).get("id"),
                "home_team_id":   t.get("home",{}).get("team",{}).get("id"),
                "away_prob_id":   t.get("away",{}).get("probablePitcher",{}).get("id"),
                "away_prob_name": t.get("away",{}).get("probablePitcher",{}).get("fullName","TBD"),
                "home_prob_id":   t.get("home",{}).get("probablePitcher",{}).get("id"),
                "home_prob_name": t.get("home",{}).get("probablePitcher",{}).get("fullName","TBD"),
                "venue":          g.get("venue",{}).get("name",""),
                "game_time_bst":  bst_time_str,
                "game_date_raw":  raw_date,
            })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_all_mlb_batting_stats(season: int):
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {
        "stats":"season", "group":"hitting", "season":season,
        "sportId":1, "playerPool":"ALL", "limit":1500,
    })
    rows = []
    splits = data.get("stats",[{}])[0].get("splits",[])
    
    total_ops, count = 0.0, 0
    for s in splits:
        ops_val = float(s.get("stat",{}).get("ops") or 0.0)
        if ops_val > 0.400:
            total_ops += ops_val; count += 1
    lg_ops = (total_ops / count) if count > 0 else 0.730

    for split in splits:
        p    = split.get("player",{})
        t    = split.get("team",{})
        stat = split.get("stat",{})
        slg  = float(stat.get("slg") or 0)
        avg  = float(stat.get("avg") or 0)
        obp  = float(stat.get("obp") or 0)
        ops  = float(stat.get("ops") or 0)
        so   = int(stat.get("strikeOuts") or 0)
        pa   = int(stat.get("plateAppearances") or 1)
        
        wrc_plus_proxy = int((ops / lg_ops) * 100) if lg_ops > 0 else 100
        iso_val = round(slg - avg, 3)
        barrel_proxy = min(0.22, max(0.01, iso_val * 0.45))
        hard_hit_proxy = min(0.60, max(0.15, (ops * 0.45) + (iso_val * 0.2)))

        rows.append({
            "player_id":  int(p.get("id",0)),
            "name":       p.get("fullName",""),
            "team_id":    int(t.get("id",0)),
            "avg": avg, "obp": obp, "slg": slg, "ops": ops,
            "iso": iso_val, "wrc_plus": wrc_plus_proxy,
            "barrel_pct": barrel_proxy, "hard_hit_pct": hard_hit_proxy,
            "plateAppearances": pa, "k_pct": round(so / pa, 4) if pa > 0 else 0.22,
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_fangraphs_stats(season: int):
    url = "https://www.fangraphs.com/api/leaders/major-league/data"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    params = {
        "age": "", "pos": "all", "stats": "bat", "lg": "all", 
        "qual": "0", "season": season, "season1": season, 
        "startdate": "", "enddate": "", "month": "0", "hand": "", 
        "team": "0", "pageitems": "2000", "pagenum": "1", 
        "ind": "0", "rost": "0", "players": "", "type": "8", 
        "postseason": "", "sortdir": "default", "sortstat": "WAR"
    }
    
    try:
        session = req.Session()
        r = session.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
        
        if not data: return pd.DataFrame()
            
        df = pd.DataFrame(data)
        col_map = {
            "PlayerName": "name", "wRC+": "wrc_plus", 
            "K%": "k_pct", "BB%": "bb_pct", 
            "HardHit%": "hard_hit_pct", "Barrel%": "barrel_pct"
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        
        for pct in ["k_pct", "bb_pct", "hard_hit_pct", "barrel_pct"]:
            if pct in df.columns and df[pct].max() > 1:
                df[pct] = df[pct] / 100
                
        return df
        
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pitcher_stats(pitcher_id):
    if not pitcher_id or pd.isna(pitcher_id):
        return {"era":4.50,"whip":1.35,"homeRunsPer9":1.20,"strikeoutsPer9Inn":8.5,"name":"TBD"}
    data = safe_get(f"https://statsapi.mlb.com/api/v1/people/{int(pitcher_id)}", {
        "hydrate": f"stats(group=[pitching],type=[season],season={date.today().year})"
    })
    people = data.get("people",[])
    if not people: return {"era":4.50,"whip":1.35,"homeRunsPer9":1.20,"strikeoutsPer9Inn":8.5,"name":"TBD"}
    person = people[0]
    splits = person.get("stats",[{}])[0].get("splits",[{}]) if person.get("stats") else [{}]
    stat = splits[0].get("stat",{}) if splits else {}
    return {
        "name":              person.get("fullName","TBD"),
        "era":               float(stat.get("era") or 4.50),
        "whip":              float(stat.get("whip") or 1.35),
        "homeRunsPer9":      float(stat.get("homeRunsPer9") or 1.20),
        "strikeoutsPer9Inn": float(stat.get("strikeoutsPer9Inn") or 8.50),
    }

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_active_roster(team_id: int):
    data = safe_get(f"https://statsapi.mlb.com/api/v1/teams/{int(team_id)}/roster", {"rosterType":"active"})
    rows = []
    for r in data.get("roster",[]):
        p = r.get("person",{}); pos = r.get("position",{})
        rows.append({"player_id":p.get("id"),"name":p.get("fullName"),"pos_type":pos.get("type")})
    return pd.DataFrame(rows)

@st.cache_data(ttl=120, show_spinner=False)
def fetch_live_lineups(game_pk: int):
    data = safe_get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    teams = data.get("liveData",{}).get("boxscore",{}).get("teams",{})
    out = {}
    for side in ["away","home"]:
        team  = teams.get(side,{})
        pmap  = team.get("players",{})
        rows = []
        for pid in (team.get("batters",[]) or []):
            p = pmap.get(f"ID{pid}",{})
            raw = p.get("battingOrder")
            if raw:
                try: 
                    slot = int(raw) // 100
                    rows.append({"player_id": pid, "name": p.get("person",{}).get("fullName",""), "order": slot})
                except: continue
        out[side] = pd.DataFrame(rows).sort_values("order") if rows else pd.DataFrame() 
    return out

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_odds_api(api_key: str):
    if not api_key or api_key.strip() == "": return {}
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": api_key, "regions": "uk", "markets": "h2h,spreads,totals",
        "bookmakers": "williamhill,paddypower,betfair,bet365,skybet", "oddsFormat": "decimal"
    }
    res = safe_get(url, params)
    out = {}
    if isinstance(res, list):
        for item in res:
            out[f"{item.get('away_team')} @ {item.get('home_team')}"] = item.get("bookmakers", [])
    return out

def score_batter(avg, obp, slg, iso, wrc_plus, hard_hit, barrel, order, era, whip, hr9, k9, venue_name, w_era, w_whip):
    meta = BALLPARKS.get(venue_name, {"factor":1.00,"dome":False})
    env = meta["factor"]
    
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

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚾ MLB Props & Game Analyser")
    
    # Pre-populated with your verified API key
    api_key_input = st.text_input(
        "The-Odds-API Key (UK Markets)", 
        value="4b959d673d4ef9c7128271557c038dfe",
        type="password", 
        help="Your live API key is pre-loaded. You can change it here if needed."
    )
    
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    min_obp  = st.slider("Min OBP",   0.250, 0.400, 0.280, 0.005, format="%.3f")
    min_pa   = st.slider("Min PA",    0, 200, 30, 10)
    max_era  = st.slider("Max opp ERA", 1.5, 10.0, 10.0, 0.1)
    max_ord  = st.slider("Max Order", 1, 9, 9)
    st.markdown("### Markets")
    s_hits, s_rbi, s_hr, s_runs = st.checkbox("Hits/Runs", True), st.checkbox("RBI", True), st.checkbox("Home Run", True), st.checkbox("Runs Scored", True)
    st.markdown("### Model Weights")
    w_era  = st.slider("ERA Weight",  0.1, 0.9, 0.55, 0.05)
    w_whip = st.slider("WHIP Weight", 0.1, 0.9, 0.45, 0.05)
    
    st.markdown("---")
    st.markdown("### 📊 Score Key")
    st.markdown("🟢 **70+** : Premium Value\n🟡 **48-69** : Playable\n🔴 **<48** : Sub-optimal")
    
    st.markdown("---")
    st.markdown("### 📖 Stat Cheat Sheet")
    with st.expander("View Elite Thresholds"):
        st.markdown("""
        **wRC+ (Overall Offence)**
        * 100 = Average | 120+ = Great | 140+ = Elite
        **ISO (Raw Power - HR Targets)**
        * .140 = Average | .200 = Great | .250+ = Elite
        **OBP (On-Base - Run Targets)**
        * .320 = Average | .350 = Great | .380+ = Elite
        """)

    if st.button("Clear Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "game_proj_dict", "odds_data"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

allowed_markets = [m for m,s in [("Hits/Runs",s_hits),("RBI",s_rbi),("Home Run",s_hr),("Runs Scored",s_runs)] if s]

st.title("⚾ MLB Prop & Full-Game Analyser")
st.caption("Combines structural prop scoring with predictive full-game modelling and live UK bookmaker lines.")
st.divider()

if st.button("Load Today's Slate", type="primary"):
    with st.status("Assembling slate parameters...", expanded=True) as status:
        st.write("Fetching MLB schedule...")
        sched = fetch_schedule(str(sel_date))
        if sched.empty: st.error("No matches found."); st.stop()

        st.write("Loading player database information...")
        mlb_all = fetch_all_mlb_batting_stats(sel_date.year)
        
        st.write("Fetching advanced FanGraphs metrics...")
        fg_df = fetch_fangraphs_stats(sel_date.year)
        if fg_df.empty:
            st.write("⚠️ FanGraphs backend connection blocked. Relying on mathematical proxy engine.")

        odds_data = {}
        if api_key_input.strip():
            st.write("Connecting to The-Odds-API (UK Region)...")
            odds_data = fetch_live_odds_api(api_key_input)
            st.session_state["odds_data"] = odds_data

        all_rows = []
        game_projections = {}

        for _, g in sched.iterrows():
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            
            lineups = fetch_live_lineups(int(g["gamePk"]))
            away_conf, home_conf = not lineups.get("away",pd.DataFrame()).empty, not lineups.get("home",pd.DataFrame()).empty

            away_roster = fetch_active_roster(int(g["away_team_id"]))
            home_roster = fetch_active_roster(int(g["home_team_id"]))
            
            away_ids = lineups["away"]["player_id"].tolist() if away_conf else away_roster[away_roster["pos_type"] != "Pitcher"]["player_id"].tolist()
            home_ids = lineups["home"]["player_id"].tolist() if home_conf else home_roster[home_roster["pos_type"] != "Pitcher"]["player_id"].tolist()

            away_pitch = fetch_pitcher_stats(g["away_prob_id"])
            home_pitch = fetch_pitcher_stats(g["home_prob_id"])
            away_pitch["name"], home_pitch["name"] = g["away_prob_name"], g["home_prob_name"]

            away_wrcs, home_wrcs = [], []
            park_factor = BALLPARKS.get(g["venue"], {"factor":1.00})["factor"]

            for side_label, player_ids, stats_map, opp_pitch in [
                ("Away", away_ids, lineups.get("away", {}), home_pitch),
                ("Home", home_ids, lineups.get("home", {}), away_pitch),
            ]:
                for pid in player_ids:
                    order = 9
                    if not stats_map.empty and "player_id" in stats_map.columns:
                        p_match = stats_map[stats_map["player_id"] == int(pid)]
                        if not p_match.empty: order = int(p_match.iloc[0].get("order", 9) or 9)

                    mlb_row = mlb_all[mlb_all["player_id"] == int(pid)] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty: continue  
                    base = mlb_row.iloc[0].to_dict()

                    if not fg_df.empty and "name" in fg_df.columns:
                        fg_match = fg_df[fg_df["name"].str.lower() == base["name"].lower()]
                        if not fg_match.empty:
                            fg = fg_match.iloc[0]
                            base["wrc_plus"] = int(fg.get("wrc_plus", base["wrc_plus"]) or base["wrc_plus"])
                            base["hard_hit_pct"] = float(fg.get("hard_hit_pct", base["hard_hit_pct"]) or base["hard_hit_pct"])
                            base["barrel_pct"] = float(fg.get("barrel_pct", base["barrel_pct"]) or base["barrel_pct"])

                    if side_label == "Away" and order <= 9: away_wrcs.append(base["wrc_plus"])
                    if side_label == "Home" and order <= 9: home_wrcs.append(base["wrc_plus"])

                    scores = score_batter(base["avg"], base["obp"], base["slg"], base["iso"], base["wrc_plus"], base["hard_hit_pct"], base["barrel_pct"], order, opp_pitch["era"], opp_pitch["whip"], opp_pitch["homeRunsPer9"], opp_pitch["strikeoutsPer9Inn"], g["venue"], 0.55, 0.45)
                    
                    best_market = max(scores, key=scores.get)
                    all_rows.append({
                        "Game": g_matchup, "Side": side_label, "Batter": base["name"], "Order": order,
                        "AVG": base["avg"], "OBP": base["obp"], "ISO": base["iso"], "wRC+": base["wrc_plus"],
                        "Opp Pitcher": opp_pitch["name"], "Hits/Runs": scores["Hits/Runs"], "RBI": scores["RBI"],
                        "Home Run": scores["Home Run"], "Runs Scored": scores["Runs Scored"], "Best Market": best_market, "Best Score": scores[best_market],
                        "Grade": "🟢 Premium" if scores[best_market] >= 70.0 else "🟡 Playable" if scores[best_market] >= 48.0 else "🔴 Sub-optimal",
                        "Game Time BST": g["game_time_bst"], "Venue": g["venue"], "Game Datetime": g["game_date_raw"]
                    })

            mean_away_wrc = sum(away_wrcs)/len(away_wrcs) if away_wrcs else 100
            mean_home_wrc = sum(home_wrcs)/len(home_wrcs) if home_wrcs else 100
            proj_away_runs = round(4.1 * (mean_away_wrc/100) * (home_pitch["era"]/4.3) * park_factor, 2)
            proj_home_runs = round(4.1 * (mean_home_wrc/100) * (away_pitch["era"]/4.3) * park_factor, 2)
            away_prob = round((proj_away_runs**1.83) / ((proj_away_runs**1.83) + (proj_home_runs**1.83)), 4) if (proj_away_runs + proj_home_runs) > 0 else 0.5
            
            game_projections[g_matchup] = {
                "proj_away_runs": proj_away_runs, "proj_home_runs": proj_home_runs,
                "away_prob": away_prob, "home_prob": 1.0 - away_prob, "proj_total": round(proj_away_runs + proj_home_runs, 1)
            }

        if all_rows:
            st.session_state["auto_df"] = pd.DataFrame(all_rows)
            st.session_state["game_proj_dict"] = game_projections
            status.update(label="Analysis matrix compiled completely.", state="complete")
        else:
            status.update(label="No players qualified configuration boundaries.", state="error")

# ── OUTPUT RENDER INTERFACE ──────────────────────────────────────────────────
if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data = st.session_state.get("odds_data", {})

    market_tabs = ["🎯 Hits/Runs", "🏏 RBIs", "💥 Home Runs", "🏃‍♂️ Runs Scored", "🗂️ Matchups & Live Odds", "✅ Slip Tracker"]
    rendered_tabs = st.tabs(market_tabs)

    for idx, m_name in enumerate(["Hits/Runs", "RBI", "Home Run", "Runs Scored"]):
        with rendered_tabs[idx]:
            st.subheader(f"🏆 Top 10 Global {m_name} Profiles")
            m_sorted = df.sort_values(m_name, ascending=False).head(10)
            
            st.dataframe(m_sorted[["Game", "Batter", "Order", "AVG" if m_name=="Hits/Runs" else "wRC+" if m_name=="RBI" else "ISO", "Opp Pitcher", m_name, "Grade"]].reset_index(drop=True), use_container_width=True)
            
            st.markdown(f"### 🗂️ Best 2-3 Players Per Match ({m_name})")
            
            sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")
            for g_name in sorted_games["Game"].tolist():
                g_players = df[df["Game"] == g_name].sort_values(m_name, ascending=False).head(3)
                if g_players.empty: continue
                sample = g_players.iloc[0]
                
                with st.expander(f"🏟️ {g_name} | 🕒 {sample['Game Time BST']} (Top picks for {m_name})"):
                    st.dataframe(g_players[["Order", "Side", "Batter", "wRC+", "AVG", "ISO", m_name, "Grade"]].reset_index(drop=True), use_container_width=True)

    with rendered_tabs[4]:
        st.subheader("🗂️ Live Matchup Lines & Bookmaker Edge Profiles")
        sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")
        for game_matchup in sorted_games["Game"].tolist():
            game_df = df[df["Game"] == game_matchup].sort_values("Order")
            proj = game_proj_dict.get(game_matchup, {"proj_away_runs":4.0,"proj_home_runs":4.0,"away_prob":0.5,"home_prob":0.5,"proj_total":8.0})
            away_team, home_team = game_matchup.split(" @ ")
            
            with st.expander(f"⚾ {game_matchup} | Model Projection: {away_team} {proj['proj_away_runs']} - {proj['proj_home_runs']} {home_team}"):
                match_odds_list = odds_data.get(game_matchup, [])
                if not match_odds_list:
                    st.caption("No live odds returned. Input API Key in sidebar to parse live value edges.")
                else:
                    for b in match_odds_list:
                        st.markdown(f"**🔹 {b['title']} Markets**")
                        c_m, c_r, c_t = st.columns(3)
                        h2h = next((m for m in b.get("markets", []) if m["key"] == "h2h"), None)
                        if h2h:
                            out = h2h.get("outcomes", [])
                            a_o = next((o for o in out if o["name"] == away_team), None)
                            h_o = next((o for o in out if o["name"] == home_team), None)
                            if a_o and h_o:
                                a_ev = (proj["away_prob"] * a_o["price"]) - 1.0
                                h_ev = (proj["home_prob"] * h_o["price"]) - 1.0
                                with c_m:
                                    st.write(f"**Moneyline:**")
                                    st.write(f"{away_team}: {decimal_to_fractional(a_o['price'])} " + (f"🟢 **+{a_ev*100:.1f}% EV**" if a_ev > 0 else ""))
                                    st.write(f"{home_team}: {decimal_to_fractional(h_o['price'])} " + (f"🟢 **+{h_ev*100:.1f}% EV**" if h_ev > 0 else ""))
                        st.markdown("---")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"🚀 {away_team} Roster Context")
                    st.dataframe(game_df[game_df["Side"] == "Away"][["Order", "Batter", "wRC+", "OBP", "ISO", "Best Market", "Best Score"]].reset_index(drop=True), use_container_width=True)
                with col2:
                    st.caption(f"🏠 {home_team} Roster Context")
                    st.dataframe(game_df[game_df["Side"] == "Home"][["Order", "Batter", "wRC+", "OBP", "ISO", "Best Market", "Best Score"]].reset_index(drop=True), use_container_width=True)

    with rendered_tabs[5]:
        st.subheader("✅ Active Mathematical Selections")
        tracker_df = df[df["Grade"].isin(["🟢 Premium", "🟡 Playable"])].copy()
        if not tracker_df.empty:
            st.dataframe(tracker_df[["Game", "Game Time BST", "Batter", "Order", "Best Market", "Best Score", "Grade"]].reset_index(drop=True), use_container_width=True)
        else:
            st.info("No selections currently meet value parameters.")
