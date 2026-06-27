import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Prop Analyser v2.1", page_icon="⚾", layout="wide")

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
    "Rate Field":                  {"lat":41.8300,"lon":-87.6338,"factor":1.04,"dome":False},
    "Truist Park":                 {"lat":33.8907,"lon":-84.4677,"factor":1.01,"dome":False},
    "Angel Stadium":               {"lat":33.8003,"lon":-117.8827,"factor":1.00,"dome":False},
    "T-Mobile Park":               {"lat":47.5914,"lon":-122.3325,"factor":0.94,"dome":False},
    "Dodger Stadium":              {"lat":34.0739,"lon":-118.2400,"factor":0.97,"dome":False},
    "Busch Stadium":               {"lat":38.6226,"lon":-90.1928,"factor":0.97,"dome":False},
    "Progressive Field":           {"lat":41.4962,"lon":-81.6852,"factor":0.96,"dome":False},
    "Comerica Park":               {"lat":42.3390,"lon":-83.0485,"factor":0.95,"dome":False},
    "Globe Life Field":            {"lat":32.7473,"lon":-97.0847,"factor":1.02,"dome":True},
    "Great American Ball Park":    {"lat":39.0979,"lon":-84.5081,"factor":1.10,"dome":False},
    "American Family Field":       {"lat":43.0280,"lon":-87.9712,"factor":1.00,"dome":False},
    "Chase Field":                 {"lat":33.4453,"lon":-112.0667,"factor":1.02,"dome":True},
    "Nationals Park":              {"lat":38.8730,"lon":-77.0074,"factor":0.99,"dome":False},
    "Las Vegas Ballpark":          {"lat":36.1318,"lon":-115.1439,"factor":1.12,"dome":False},
    "Sutter Health Park":          {"lat":38.5802,"lon":-121.5014,"factor":1.05,"dome":False},
}

MARKET_COLORS = {"Hits/Runs":"#01696f","RBI":"#d19900","Home Run":"#a12c7b","Runs Scored":"#006494"}

def safe_get(url, params=None):
    for attempt in range(3):
        try:
            r = req.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                return {}
            time.sleep(1)
    return {}

def decimal_to_fractional(dec):
    if not dec or dec <= 1.0: return "N/A"
    if dec == 2.0: return "EVENS"
    frac = Fraction(dec - 1.0).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"

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
def fetch_schedule(target_date: str):
    data = safe_get("https://statsapi.mlb.com/api/v1/schedule", {
        "sportId":1, "date":target_date,
        "hydrate":"probablePitcher,team,venue,linescore"
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
                except:
                    pass

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
        "sportId":1, "playerPool":"ALL", "limit":2000,
    })
    rows = []
    for split in data.get("stats",[{}])[0].get("splits",[]):
        p   = split.get("player",{})
        t   = split.get("team",{})
        stat = split.get("stat",{})
        slg = float(stat.get("slg") or 0)
        avg = float(stat.get("avg") or 0)
        obp = float(stat.get("obp") or 0)
        so  = int(stat.get("strikeOuts") or 0)
        pa  = int(stat.get("plateAppearances") or 1)
        rows.append({
            "player_id":  int(p.get("id",0)),
            "name":       p.get("fullName",""),
            "team_id":    int(t.get("id",0)),
            "avg":  avg, "obp":  obp, "slg":  slg,
            "ops":  float(stat.get("ops") or 0),
            "iso":  round(slg - avg, 3),
            "hr":   int(stat.get("homeRuns") or 0),
            "rbi":  int(stat.get("rbi") or 0),
            "games":int(stat.get("gamesPlayed") or 0),
            "strikeOuts":       so,
            "baseOnBalls":      int(stat.get("baseOnBalls") or 0),
            "plateAppearances": pa,
            "k_pct":            round(so / pa, 4) if pa > 0 else 0.22,
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_fangraphs_stats(season: int):
    try:
        from pybaseball import batting_stats
        df = batting_stats(season, qual=50)
        col_map = {"Name":"name","AVG":"avg","OBP":"obp","SLG":"slg","ISO":"iso",
                   "wRC+":"wrc_plus","K%":"k_pct","BB%":"bb_pct",
                   "HardHit%":"hard_hit_pct","Barrel%":"barrel_pct","HR":"hr","G":"games"}
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        for pct in ["k_pct","bb_pct","hard_hit_pct","barrel_pct"]:
            if pct in df.columns and df[pct].max() > 1:
                df[pct] = df[pct] / 100
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pitcher_stats(pitcher_id):
    if not pitcher_id or pd.isna(pitcher_id):
        return {"era":4.50,"whip":1.35,"homeRunsPer9":1.20,"strikeoutsPer9Inn":8.5,"name":"TBD"}
    data = safe_get(f"https://statsapi.mlb.com/api/v1/people/{int(pitcher_id)}", {
        "hydrate": f"stats(group=[pitching],type=[season],season={date.today().year})"
    })
    person = data.get("people",[{}])[0]
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
        rows.append({"player_id":p.get("id"),"name":p.get("fullName"),
                     "pos_type":pos.get("type"),"pos_abbr":pos.get("abbreviation")})
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
                    live_stats = p.get("stats", {}).get("batting", {})
                    rows.append({
                        "player_id": pid,
                        "name": p.get("person",{}).get("fullName",""),
                        "order": slot,
                        "live_hits": live_stats.get("hits", 0),
                        "live_runs": live_stats.get("runs", 0),
                        "live_rbi": live_stats.get("rbi", 0),
                        "live_hr": live_stats.get("homeRuns", 0)
                    })
                except: continue
        
        if rows:
            out[side] = pd.DataFrame(rows).sort_values("order")
        else:
            out[side] = pd.DataFrame() 
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue_name: str):
    meta = BALLPARKS.get(venue_name)
    if not meta:
        return {"temp":72,"wind":8,"factor":1.00,"dome":False,"venue":venue_name}
    if meta["dome"]:
        return {"temp":72,"wind":0,"factor":meta["factor"],"dome":True,"venue":venue_name}
    data = safe_get("https://api.open-meteo.com/v1/forecast", {
        "latitude":meta["lat"],"longitude":meta["lon"],
        "current":"temperature_2m,wind_speed_10m",
        "temperature_unit":"fahrenheit","wind_speed_unit":"mph"
    })
    c = data.get("current",{})
    return {"temp":float(c.get("temperature_2m") or 72),"wind":float(c.get("wind_speed_10m") or 8),
            "factor":meta["factor"],"dome":False,"venue":venue_name}

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004

def order_factor(order):
    return {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(int(order or 9),0.80)

def score_batter(avg, obp, slg, iso, ops, k_pct, hard_hit, barrel, wrc_plus,
                 order, era, whip, hr9, k9, park_factor, temp, wind, dome, use_adv, w_era, w_whip):
    env = park_factor * wx_modifier(temp, wind, dome)
    of  = order_factor(order)
    pv  = min(era/7.0,1.0)*w_era + min(max((whip-0.8)/1.2,0.0),1.0)*w_whip
    hrv = min(hr9/2.5,1.0)
    k_adj = 1.0 - min((k9-7.0)/14.0, 0.20)
    rbi_of  = 1.0 + max(0,(5-order)*0.04)
    run_of  = 1.0 + max(0,(4-order)*0.05)
    
    if use_adv:
        contact = avg*0.35 + obp*0.30 + (wrc_plus/200)*0.25 + (1-k_pct)*0.10
        power   = iso*0.40 + hard_hit*0.35 + barrel*0.25
        on_base = obp * (wrc_plus/100)
    else:
        contact = avg*0.65 + obp*0.35
        power   = max(0.05, slg - avg)
        on_base = obp
        
    hits_runs_score = round(contact * pv * of * k_adj * env * 280, 2)
    rbi_score       = round(contact * pv * rbi_of * k_adj * env * 260, 2)
    hr_score        = round(power   * hrv * env * 280, 2)
    runs_score      = round(on_base * pv * run_of * k_adj * env * 280, 2)

    if iso < 0.130 or barrel < 0.04 or hr9 < 0.7:
        hr_score = 0.0
    if order > 7 or wrc_plus < 80:
        rbi_score = 0.0
    if order > 5 or obp < 0.290:
        runs_score = 0.0

    return {
        "Hits/Runs":   hits_runs_score,
        "RBI":         rbi_score,
        "Home Run":    hr_score,
        "Runs Scored": runs_score,
    }

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚾ MLB Props v2.1")
    odds_key = st.text_input("The-Odds-API Key (Optional)", type="password", help="Input key to overlay live UK bookmaker odds on team markets.")
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    min_obp  = st.slider("Min OBP",   0.250, 0.400, 0.280, 0.005, format="%.3f")
    min_pa   = st.slider("Min PA",    0, 200, 30, 10)
    max_era  = st.slider("Max opp ERA", 1.5, 10.0, 10.0, 0.1)
    max_ord  = st.slider("Max Order", 1, 9, 9)
    st.markdown("### Markets")
    s_hits = st.checkbox("Hits/Runs",   True)
    s_rbi  = st.checkbox("RBI",         True)
    s_hr   = st.checkbox("Home Run",    True)
    s_runs = st.checkbox("Runs Scored", True)
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
        * 100 = League Average
        * 120+ = Great
        * 140+ = Elite
        
        **ISO (Raw Power - HR Targets)**
        * .140 = Average
        * .200 = Great 
        * .250+ = Elite Slugger
        
        **OBP (On-Base - Run Targets)**
        * .320 = Average
        * .350 = Great 
        * .380+ = Elite Table-Setter
        
        **Pitcher Vulnerability**
        * **HR/9:** > 1.30 is highly vulnerable
        * **WHIP:** > 1.35 means heavy base traffic
        * **K/9:** < 7.50 ensures balls put in play
        """)

    st.markdown("---")
    if st.button("Clear Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "game_proj_dict", "odds_data"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

allowed_markets = [m for m,s in [
    ("Hits/Runs",s_hits),("RBI",s_rbi),("Home Run",s_hr),("Runs Scored",s_runs)] if s]

st.title("⚾ MLB Prop & Game Analyser v2.1")
st.caption("Auto-fetches every MLB batter, probable pitchers, confirmed lineups, live weather, and game projections.")
st.divider()

col_btn, col_info = st.columns([2,3])
with col_btn:
    load_btn = st.button("Load Today's Slate")
with col_info:
    st.markdown("""
    **Auto-loads:** MLB schedule · probable pitchers · **all 500+ batters** (MLB Stats API) · Fangraphs advanced stats (if available) · confirmed lineups · live ballpark weather · **game projections**
    """)

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

        st.write("Trying Fangraphs advanced stats (wRC+, Hard Hit%, Barrel%)...")
        fg_df = fetch_fangraphs_stats(sel_date.year)
        if fg_df.empty:
            st.write("Fangraphs unavailable — using MLB API stats with derived metrics")
        else:
            st.write(f"Fangraphs loaded: {len(fg_df)} batters")

        st.session_state["odds_data"] = fetch_live_odds_api(odds_key) if odds_key else {}

        all_rows = []
        game_projections = {}

        for _, g in sched.iterrows():
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            st.write(f"Processing {g_matchup}...")
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
            if total_env >= 1.06: env_symbol = "🟢 Hitter-Friendly"
            elif total_env >= 0.97: env_symbol = "🟡 Neutral"
            else: env_symbol = "🔴 Pitcher-Friendly"

            game_status_label = g["status"]

            away_wrcs = []
            home_wrcs = []

            for side_label, player_ids, stats_map, opp_pitch, conf in [
                ("Away", away_ids, away_stats_map, home_pitch, away_conf),
                ("Home", home_ids, home_stats_map, away_pitch, home_conf),
            ]:
                p_era = opp_pitch.get("era", 4.5)
                p_whip = opp_pitch.get("whip", 1.35)
                
                if p_era >= 4.5 or p_whip >= 1.35: p_rating = "🟢 Target"
                elif p_era <= 3.4 and p_whip <= 1.20: p_rating = "🔴 Avoid"
                else: p_rating = "🟡 Neutral"

                for pid in player_ids:
                    pid = int(pid)
                    player_live_data = stats_map.get(pid, {})
                    order = int(player_live_data.get("order", 9) or 9)
                    
                    mlb_row = mlb_all[mlb_all["player_id"] == pid] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty: continue  
                    base = mlb_row.iloc[0].to_dict()
                    pname = base.get("name","")

                    use_adv = False
                    wrc_plus = int(max(1, float(base.get("ops",0.700) or 0.700) * 152))
                    hard_hit = min(0.65, 0.28 + float(base.get("iso",0)) * 1.2)
                    barrel   = min(0.20, float(base.get("iso",0)) * 0.35)
                    
                    if not fg_df.empty and "name" in fg_df.columns:
                        fg_match = fg_df[fg_df["name"].str.lower() == pname.lower()]
                        if fg_match.empty:
                            last = pname.split()[-1].lower() if pname else ""
                            fg_match = fg_df[fg_df["name"].str.lower().str.endswith(last, na=False)]
                        if not fg_match.empty:
                            fg = fg_match.iloc[0]
                            wrc_plus = int(fg.get("wrc_plus",wrc_plus) or wrc_plus)
                            hard_hit = float(fg.get("hard_hit_pct",hard_hit) or hard_hit)
                            barrel   = float(fg.get("barrel_pct",barrel) or barrel)
                            use_adv  = True

                    if side_label == "Away" and order <= 9: away_wrcs.append(wrc_plus)
                    if side_label == "Home" and order <= 9: home_wrcs.append(wrc_plus)

                    if order > max_ord: continue
                    if base.get("plateAppearances",0) < min_pa: continue
                    if float(base.get("avg",0)) < min_avg: continue
                    if float(base.get("obp",0)) < min_obp: continue
                    if opp_pitch.get("era",4.5) > max_era: continue

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
                        wx["dome"], use_adv, w_era, w_whip
                    )
                    flt = {k:v for k,v in scores.items() if k in allowed_markets}
                    if not flt: continue
                    best_market = max(flt, key=flt.get)
                    best_score  = flt[best_market]
                    
                    if best_score >= 70.0: grade_badge = "🟢 Premium"
                    elif best_score >= 48.0: grade_badge = "🟡 Playable"
                    else: grade_badge = "🔴 Sub-optimal"

                    if best_market == "Home Run": rationale = f"Elite power (ISO {iso_v:.3f}) matching up against a pitcher allowing {opp_pitch.get('homeRunsPer9', 1.2):.1f} HR/9."
                    elif best_market == "RBI": rationale = f"Strong run-producer (wRC+ {wrc_plus}) hitting #{order} in the order with men likely on base."
                    elif best_market == "Runs Scored": rationale = f"High on-base threat (OBP {obp_v:.3f}) batting #{order} facing a high-WHIP ({p_whip:.2f}) pitcher."
                    else: rationale = f"Excellent contact profile (AVG {avg_v:.3f}) in a favourable offensive environment."

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
                    
                    if bet_won: result_status = "✅ Won"
                    elif not bet_won and is_final: result_status = "❌ Lost"
                    else: result_status = "⏳ Pending"

                    all_rows.append({
                        "Game":          g_matchup,
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
                        "Stats Source":  "Fangraphs" if use_adv else "MLB API",
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

            # Calculate Team Projections
            mean_away_wrc = sum(away_wrcs)/len(away_wrcs) if away_wrcs else 100
            mean_home_wrc = sum(home_wrcs)/len(home_wrcs) if home_wrcs else 100
            proj_away_runs = round(4.1 * (mean_away_wrc/100) * (home_pitch.get("era", 4.3)/4.3) * wx["factor"], 2)
            proj_home_runs = round(4.1 * (mean_home_wrc/100) * (away_pitch.get("era", 4.3)/4.3) * wx["factor"], 2)
            away_prob = round((proj_away_runs**1.83) / ((proj_away_runs**1.83) + (proj_home_runs**1.83)), 4) if (proj_away_runs + proj_home_runs) > 0 else 0.5
            
            game_projections[g_matchup] = {
                "proj_away_runs": proj_away_runs, "proj_home_runs": proj_home_runs,
                "away_prob": away_prob, "home_prob": 1.0 - away_prob, 
                "proj_total": round(proj_away_runs + proj_home_runs, 1),
                "proj_line": round(proj_home_runs - proj_away_runs, 1)
            }

        if not all_rows:
            st.error("No batters matched filters."); status.update(label="No results", state="error")
        else:
            df = pd.DataFrame(all_rows).sort_values("Best Score", ascending=False)
            st.session_state["auto_df"] = df
            st.session_state["game_proj_dict"] = game_projections
            status.update(label=f"Done — {len(df)} batters scored across {len(sched)} games", state="complete")

if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data = st.session_state.get("odds_data", {})
    
    if df.empty:
        st.info("No results. Adjust filters and reload.")
    else:
        top = df.iloc[0]
        fg_c  = len(df[df["Stats Source"]=="Fangraphs"])
        mlb_c = len(df[df["Stats Source"]=="MLB API"])
        conf_c= len(df[df["Lineup Status"]=="Confirmed"])

        k1,k2,k3,k4 = st.columns(4)
        for col,val,lbl in [(k1,str(len(df)),"Batters Scored"),(k2,top["Batter"],"Top Batter"),
                            (k3,top["Best Market"],"Best Market"),(k4,f"{top['Best Score']:.2f}","Top Score")]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-value">{val}</div>'
                            f'<div class="metric-label">{lbl}</div></div>', unsafe_allow_html=True)

        st.info(f"Fangraphs: {fg_c} batters  |  MLB API: {mlb_c} batters  |  Confirmed lineups: {conf_c} batters")

        SHOW = ["Game","Game Time BST","Batter","Order","AVG","OBP","ISO","wRC+","Env Rating", "Pitcher Rating", "Grade"]

        all_t, game_t, tracker_t, t_hits, t_rbi, t_hr, t_runs, t_ml, t_rl, t_tot, t_raw = st.tabs([
            "All Ranked", "🗂️ Game by Game", "✅ Slip Tracker", "Hits/Runs", "RBI", "Home Run", "Runs Scored", "💰 Moneyline", "📈 Run Line", "📊 Totals", "Raw Data"
        ])

        with all_t:
            st.markdown("### 📋 Ranked Prop Targets")
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                sel_markets = st.multiselect("🎯 Filter by Market", options=df["Best Market"].unique(), default=df["Best Market"].unique())
            with f_col2:
                sel_grades = st.multiselect("📊 Filter by Grade", options=df["Grade"].unique(), default=df["Grade"].unique())
            with f_col3:
                sel_status = st.multiselect("⏳ Lineup Status", options=df["Lineup Status"].unique(), default=df["Lineup Status"].unique())
            
            filtered_df = df[
                (df["Best Market"].isin(sel_markets)) & 
                (df["Grade"].isin(sel_grades)) &
                (df["Lineup Status"].isin(sel_status))
            ]
            
            max_score = float(filtered_df["Best Score"].max()) if not filtered_df.empty else 100.0
            
            disp = [c for c in SHOW + ["Best Market", "Best Score", "Lineup Status"] if c in filtered_df.columns]
            st.dataframe(filtered_df[disp].reset_index(drop=True), use_container_width=True, hide_index=True,
                column_config={
                    "Best Score": st.column_config.ProgressColumn("Best Score", min_value=0, max_value=max_score, format="%.1f", color="#a12c7b"),
                    "AVG": st.column_config.NumberColumn("BA", format="%.3f"),
                    "OBP": st.column_config.NumberColumn(format="%.3f"),
                    "ISO": st.column_config.NumberColumn(format="%.3f"),
                })

        with game_t:
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

        with tracker_t:
            st.subheader("✅ Live Slip Tracker")
            st.caption("Tracks your top recommended bets in real-time. Hit the 'Load Today's Slate' button to fetch the latest pitch-by-pitch updates.")
            
            tracker_df = df[df["Grade"].isin(["🟢 Premium", "🟡 Playable"])].copy()
            
            if tracker_df.empty:
                st.info("No Playable or Premium bets available to track right now.")
            else:
                tracker_df["Target"] = tracker_df["Best Market"].apply(lambda x: "2+ (Hits+Runs)" if x == "Hits/Runs" else "1+ " + x)
                tracker_df["Live Stats"] = "H:" + tracker_df["Live Hits"].astype(str) + " R:" + tracker_df["Live Runs"].astype(str) + " RBI:" + tracker_df["Live RBI"].astype(str) + " HR:" + tracker_df["Live HR"].astype(str)
                
                display_cols = ["Game Time BST", "Batter", "Game Status", "Best Market", "Target", "Live Stats", "Slip Result"]
                
                st.dataframe(
                    tracker_df[display_cols].reset_index(drop=True), 
                    use_container_width=True, 
                    hide_index=True
                )

        for tab, market in [(t_hits,"Hits/Runs"),(t_rbi,"RBI"),(t_hr,"Home Run"),(t_runs,"Runs Scored")]:
            with tab:
                sub = df[df["Best Market"]==market]
                if sub.empty:
                    st.info("No picks available for " + market); continue
                c_chart, c_cards = st.columns([3,2])
                with c_chart:
                    fig = go.Figure(go.Bar(
                        y=sub.head(12)["Batter"]+" | "+sub.head(12)["Game"],
                        x=sub.head(12)["Best Score"], orientation="h",
                        marker_color=MARKET_COLORS[market],
                        text=["ERA "+str(e) for e in sub.head(12)["Pitcher ERA"]],
                        textposition="inside", insidetextanchor="start",
                        textfont=dict(color="white",size=11),
                    ))
                    fig.update_layout(title="Top "+market+" Picks",
                        yaxis=dict(autorange="reversed"), height=460,
                        plot_bgcolor="#f9f8f5", paper_bgcolor="#f7f6f2",
                        margin=dict(l=10,r=10,t=40,b=20), font=dict(family="Inter"))
                    st.plotly_chart(fig, use_container_width=True)
                
                with c_cards:
                    st.markdown("### 🎯 Best Value Slips")
                    for _, row in sub.head(6).iterrows():
                        with st.container(border=True):
                            card_left, card_right = st.columns([3, 1])
                            with card_left:
                                st.markdown(f"**{row['Batter']}**")
                                st.caption(f"Slot: #{int(row['Order'])} | {row['Game']} 🕒 {row['Game Time BST']}")
                            with card_right:
                                st.metric(label="Score", value=f"{row['Best Score']:.1f}")
                                st.markdown(f"**{row['Grade']}**")
                            
                            st.markdown(f"🔬 `wRC+: {row['wRC+']}` | `OBP: {row['OBP']:.3f}` | `ISO: {row['ISO']:.3f}`")
                            st.markdown(f"🔥 `vs: {row['Opp Pitcher']} (ERA {row['Pitcher ERA']})` | {row['Pitcher Rating']}")
                            st.markdown(f"🏟️ `{row['Venue']}` | Conditions: `{row['Env Rating']}`")
                            st.divider()
                            st.caption(f"💡 **Why back him:** {row['Rationale']}")

        # ── MONEYLINE OVERLAY ──
        with t_ml:
            st.subheader("💰 Live Moneyline Value")
            sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")["Game"].tolist()
            if not odds_data: st.info("No Odds API key detected. Model probabilities are displayed without bookmaker comparisons.")
            
            for game_matchup in sorted_games:
                proj = game_proj_dict.get(game_matchup)
                if not proj: continue
                away_team, home_team = game_matchup.split(" @ ")
                match_odds_list = odds_data.get(game_matchup, [])
                
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
                                if a_ev > best_away_ev:
                                    best_away_ev, best_away_bookie, away_price = a_ev, b["title"], decimal_to_fractional(a_o["price"])
                                if h_ev > best_home_ev:
                                    best_home_ev, best_home_bookie, home_price = h_ev, b["title"], decimal_to_fractional(h_o["price"])
                
                with st.container(border=True):
                    st.markdown(f"**{game_matchup}** | Model Probabilities: {away_team} ({proj['away_prob']*100:.1f}%) vs {home_team} ({proj['home_prob']*100:.1f}%)")
                    if not match_odds_list:
                        pass # Only display probabilities if no odds are fetched
                    elif best_away_ev > 0:
                        st.markdown(f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: Back {away_team}</span> at {away_price} (via {best_away_bookie}) | <span class='ev-text'>+{best_away_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                    elif best_home_ev > 0:
                        st.markdown(f"<div class='odds-box'><span class='pick-text'>🤖 Model Recommends: Back {home_team}</span> at {home_price} (via {best_home_bookie}) | <span class='ev-text'>+{best_home_ev:.1f}% EV</span></div>", unsafe_allow_html=True)
                    else:
                        st.write("No mathematical value edge found on current bookmaker lines.")

        # ── RUN LINE OVERLAY ──
        with t_rl:
            st.subheader("📈 Live Run Line Value")
            sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")["Game"].tolist()
            if not odds_data: st.info("No Odds API key detected. Model projected lines are displayed without bookmaker comparisons.")
            
            for game_matchup in sorted_games:
                proj = game_proj_dict.get(game_matchup)
                if not proj: continue
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
                    if match_odds_list and not found_spread:
                        st.write("Awaiting live run line data.")

        # ── TOTALS OVERLAY ──
        with t_tot:
            st.subheader("📊 Live Totals (Overs/Unders)")
            sorted_games = df[["Game", "Game Datetime"]].drop_duplicates().sort_values("Game Datetime")["Game"].tolist()
            if not odds_data: st.info("No Odds API key detected. Model projected totals are displayed without bookmaker comparisons.")
            
            for game_matchup in sorted_games:
                proj = game_proj_dict.get(game_matchup)
                if not proj: continue
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
                    if match_odds_list and not found_total:
                        st.write("Awaiting live totals data.")

        with t_raw:
            st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)

        st.download_button("Download Full CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"mlb_props_{sel_date}.csv", mime="text/csv")

st.divider()
st.caption("MLB Stats API (all batters via playerPool=ALL) · Fangraphs via pybaseball (optional enrichment) · Open-Meteo weather")
