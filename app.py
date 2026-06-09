
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import date, datetime
import time

st.set_page_config(
    page_title="MLB Prop Analyser v2",
    page_icon="baseball",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:#f7f6f2;}
.metric-card{background:#fff;border-radius:12px;padding:14px 18px;border:1px solid #dcd9d5;
  box-shadow:0 2px 8px rgba(0,0,0,.05);text-align:center;margin-bottom:10px;}
.metric-value{font-size:1.7rem;font-weight:700;color:#01696f;}
.metric-label{font-size:.72rem;color:#7a7974;text-transform:uppercase;letter-spacing:.05em;margin-top:3px;}
.batter-card{background:#fff;border-radius:10px;padding:12px;margin-bottom:8px;border:1px solid #dcd9d5;}
.batter-name{font-weight:600;color:#28251d;}
.batter-meta{color:#7a7974;font-size:.8rem;margin-top:2px;}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.7rem;font-weight:600;}
.badge-hits{background:#cedcd8;color:#01696f;}
.badge-rbi{background:#e9e0c6;color:#8a5b00;}
.badge-hr{background:#e0ced7;color:#7d1e5e;}
.badge-runs{background:#c6d8e4;color:#0b3751;}
.stButton>button{background:#01696f;color:white;border-radius:8px;padding:10px 24px;
  font-weight:600;border:none;width:100%;font-size:1rem;}
.stButton>button:hover{background:#0c4e54;color:white;}
section[data-testid="stSidebar"]{background:#1c1b19;}
section[data-testid="stSidebar"] *{color:#cdccca !important;}
</style>
""", unsafe_allow_html=True)

# ── BALLPARK METADATA ───────────────────────────────────────────────────────
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
}

MARKET_COLORS = {
    "Hits/Runs":"#01696f","RBI":"#d19900",
    "Home Run":"#a12c7b","Runs Scored":"#006494",
}
MARKET_BADGES = {
    "Hits/Runs":"badge-hits","RBI":"badge-rbi",
    "Home Run":"badge-hr","Runs Scored":"badge-runs",
}

# ── API HELPERS ─────────────────────────────────────────────────────────────
def safe_get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                st.warning(f"API call failed: {url} — {e}")
                return {}
            time.sleep(2)
    return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_schedule(target_date: str):
    data = safe_get("https://statsapi.mlb.com/api/v1/schedule", {
        "sportId": 1, "date": target_date,
        "hydrate": "probablePitcher,team,venue,linescore"
    })
    rows = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            t = g.get("teams", {})
            rows.append({
                "gamePk":            g.get("gamePk"),
                "status":            g.get("status", {}).get("detailedState"),
                "away_team":         t.get("away",{}).get("team",{}).get("name"),
                "home_team":         t.get("home",{}).get("team",{}).get("name"),
                "away_team_id":      t.get("away",{}).get("team",{}).get("id"),
                "home_team_id":      t.get("home",{}).get("team",{}).get("id"),
                "away_prob_id":      t.get("away",{}).get("probablePitcher",{}).get("id"),
                "away_prob_name":    t.get("away",{}).get("probablePitcher",{}).get("fullName","TBD"),
                "home_prob_id":      t.get("home",{}).get("probablePitcher",{}).get("id"),
                "home_prob_name":    t.get("home",{}).get("probablePitcher",{}).get("fullName","TBD"),
                "venue":             g.get("venue",{}).get("name",""),
            })
    return pd.DataFrame(rows)

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
        "inningsPitched":    float(stat.get("inningsPitched") or 0),
    }

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_active_roster(team_id: int):
    data = safe_get(f"https://statsapi.mlb.com/api/v1/teams/{int(team_id)}/roster",
                    {"rosterType":"active"})
    rows = []
    for r in data.get("roster",[]):
        p = r.get("person",{})
        pos = r.get("position",{})
        rows.append({
            "player_id": p.get("id"),
            "name":      p.get("fullName"),
            "pos_type":  pos.get("type"),
            "pos_abbr":  pos.get("abbreviation"),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)  # cache 24hrs — respects Fangraphs rate limits
def fetch_fangraphs_stats(season: int):
    """
    Pull season batting stats from Fangraphs via pybaseball.
    Returns DataFrame with name, AVG, OBP, SLG, ISO, wRC+, K%, BB%.
    Falls back gracefully if pybaseball unavailable.
    """
    try:
        from pybaseball import batting_stats
        df = batting_stats(season, qual=50)
        # Normalise column names
        col_map = {
            "Name":"name","AVG":"avg","OBP":"obp","SLG":"slg",
            "ISO":"iso","wRC+":"wrc_plus","K%":"k_pct","BB%":"bb_pct",
            "HardHit%":"hard_hit_pct","Barrel%":"barrel_pct",
            "HR":"hr","RBI":"rbi","G":"games",
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        # normalise percentages
        for pct in ["k_pct","bb_pct","hard_hit_pct","barrel_pct"]:
            if pct in df.columns and df[pct].max() > 1:
                df[pct] = df[pct] / 100
        return df
    except Exception as e:
        return pd.DataFrame()  # silent fallback to MLB API stats

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mlb_batting_stats(player_ids: list, season: int):
    if not player_ids:
        return pd.DataFrame()
    rows = []
    for pid in player_ids:
        data = safe_get(f"https://statsapi.mlb.com/api/v1/people/{pid}", {
            "hydrate": f"stats(group=[hitting],type=[season],season={season})"
        })
        person = data.get("people",[{}])[0]
        splits = person.get("stats",[{}])[0].get("splits",[{}]) if person.get("stats") else [{}]
        stat = splits[0].get("stat",{}) if splits else {}
        rows.append({
            "player_id": pid,
            "name":      person.get("fullName",""),
            "avg":  float(stat.get("avg") or 0),
            "obp":  float(stat.get("obp") or 0),
            "slg":  float(stat.get("slg") or 0),
            "ops":  float(stat.get("ops") or 0),
            "hr":   int(stat.get("homeRuns") or 0),
            "rbi":  int(stat.get("rbi") or 0),
            "games":int(stat.get("gamesPlayed") or 0),
        })
        time.sleep(0.05)
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_live_lineups(game_pk: int):
    data = safe_get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    teams = data.get("liveData",{}).get("boxscore",{}).get("teams",{})
    out = {}
    for side in ["away","home"]:
        team  = teams.get(side,{})
        pmap  = team.get("players",{})
        order_list = team.get("batters",[]) or []
        rows = []
        for pid in order_list:
            p = pmap.get(f"ID{pid}",{})
            raw_order = p.get("battingOrder")
            if raw_order:
                try: lineup_slot = int(raw_order) // 100
                except: lineup_slot = None
                rows.append({
                    "player_id": pid,
                    "name": p.get("person",{}).get("fullName",""),
                    "order": lineup_slot,
                })
        out[side] = pd.DataFrame(rows).sort_values("order") if rows else pd.DataFrame()
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue_name: str):
    meta = BALLPARKS.get(venue_name)
    if not meta:
        return {"temp":72,"wind":8,"factor":1.00,"dome":False,"venue":venue_name}
    if meta["dome"]:
        return {"temp":72,"wind":0,"factor":meta["factor"],"dome":True,"venue":venue_name}
    data = safe_get("https://api.open-meteo.com/v1/forecast", {
        "latitude": meta["lat"], "longitude": meta["lon"],
        "current": "temperature_2m,wind_speed_10m",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    })
    c = data.get("current",{})
    return {
        "temp":   float(c.get("temperature_2m") or 72),
        "wind":   float(c.get("wind_speed_10m") or 8),
        "factor": meta["factor"],
        "dome":   False,
        "venue":  venue_name,
    }

# ── SCORING MODEL ────────────────────────────────────────────────────────────
def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004

def order_factor(order):
    return {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(int(order or 9), 0.80)

def pitcher_vuln(era, whip, w_era=0.55, w_whip=0.45):
    return min((era or 4.5)/7.0,1.0)*w_era + min(((whip or 1.35)-0.8)/1.2,1.0)*w_whip

def hr_vuln(hr9):
    return min((hr9 or 1.2)/2.5, 1.0)

def score_batter(row, opp, wx, w_era, w_whip, use_adv):
    avg      = row.get("avg",0) or 0
    obp      = row.get("obp",0) or 0
    slg      = row.get("slg",0) or 0
    iso      = row.get("iso", slg - avg) or 0
    wrc_plus = row.get("wrc_plus", 100) or 100
    k_pct    = row.get("k_pct", 0.22) or 0.22
    hard_hit = row.get("hard_hit_pct", 0.38) or 0.38
    barrel   = row.get("barrel_pct", 0.08) or 0.08
    order    = int(row.get("order", 9) or 9)

    if use_adv:
        contact_score = (avg*0.35 + obp*0.30 + (wrc_plus/200)*0.25 + (1-k_pct)*0.10)
        power_score   = (iso*0.40 + hard_hit*0.35 + barrel*0.25)
        on_base_score = obp * (wrc_plus/100)
    else:
        contact_score = avg*0.65 + obp*0.35
        power_score   = max(0.05, slg - avg)
        on_base_score = obp

    pv  = pitcher_vuln(opp["era"], opp["whip"], w_era, w_whip)
    hrv = hr_vuln(opp["homeRunsPer9"])
    k9  = opp.get("strikeoutsPer9Inn", 8.5)
    k_adj = 1.0 - min((k9 - 7.0) / 14.0, 0.2)

    of  = order_factor(order)
    env = wx["factor"] * wx_modifier(wx["temp"], wx["wind"], wx["dome"])
    rbi_of  = 1.0 + max(0, (5 - order) * 0.04)
    run_of  = 1.0 + max(0, (4 - order) * 0.05)

    scores = {
        "Hits/Runs":   round(contact_score * pv * of * k_adj * env * 110, 2),
        "RBI":         round(contact_score * pv * rbi_of * k_adj * env * 100, 2),
        "Home Run":    round(power_score   * hrv * env * 95, 2),
        "Runs Scored": round(on_base_score * pv * run_of * k_adj * env * 105, 2),
    }
    best = max(scores, key=scores.get)
    return scores, best, scores[best]

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## MLB Props v2")
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    max_era  = st.slider("Max ERA",   1.5,   10.0,  10.0,  0.1)
    max_ord  = st.slider("Max Order", 1, 9, 9)
    st.markdown("### Markets")
    s_hits = st.checkbox("Hits/Runs",   True)
    s_rbi  = st.checkbox("RBI",         True)
    s_hr   = st.checkbox("Home Run",    True)
    s_runs = st.checkbox("Runs Scored", True)
    st.markdown("### Weights")
    w_era  = st.slider("ERA Weight",  0.1, 0.9, 0.55, 0.05)
    w_whip = st.slider("WHIP Weight", 0.1, 0.9, 0.45, 0.05)
    st.markdown("---")
    if st.button("Clear All"):
        for k in ["auto_df","sched_df","fg_df","load_log"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()
    st.caption("MLB Prop Analyser v2")

allowed_markets = [m for m,s in [
    ("Hits/Runs",s_hits),("RBI",s_rbi),
    ("Home Run",s_hr),("Runs Scored",s_runs)
] if s]

# ── HEADER ───────────────────────────────────────────────────────────────────
st.markdown("# MLB Prop Analyser v2")
st.caption("Auto-fetches schedule, probable pitchers, lineups (when confirmed), Fangraphs advanced stats, and live weather.")
st.divider()

# ── LOAD BUTTON ──────────────────────────────────────────────────────────────
col_btn, col_info = st.columns([2,3])
with col_btn:
    load_btn = st.button("Load Today's Slate")
with col_info:
    st.markdown("""
    **What gets auto-loaded:**
    - MLB schedule + probable pitchers (MLB Stats API)
    - Advanced batting stats: AVG, OBP, ISO, wRC+, K%, Hard Hit% (Fangraphs via pybaseball — cached 24hrs)
    - Live weather per ballpark (Open-Meteo)
    - Confirmed lineups when posted (MLB live feed)
    """)

if load_btn:
    log = []
    with st.status("Loading today's slate...", expanded=True) as status:

        st.write("Fetching MLB schedule and probable pitchers...")
        sched = fetch_schedule(str(sel_date))
        if sched.empty:
            st.error("No games found for " + str(sel_date))
            st.stop()
        log.append(f"{len(sched)} games found")
        st.write(f"Found {len(sched)} games")

        st.write("Loading Fangraphs advanced stats (cached 24hrs)...")
        fg_df = fetch_fangraphs_stats(sel_date.year)
        if fg_df.empty:
            log.append("Fangraphs unavailable — using MLB API basic stats")
            st.write("Fangraphs unavailable — falling back to MLB API batting stats")
        else:
            log.append(f"Fangraphs loaded: {len(fg_df)} batters")
            st.write(f"Fangraphs: {len(fg_df)} batters loaded")
        st.session_state["fg_df"] = fg_df

        all_rows = []
        for _, g in sched.iterrows():

            st.write(f"Processing {g['away_team']} @ {g['home_team']}...")

            wx = fetch_weather(g["venue"])
            lineups = fetch_live_lineups(int(g["gamePk"]))

            away_roster = fetch_active_roster(int(g["away_team_id"]))
            home_roster = fetch_active_roster(int(g["home_team_id"]))
            away_batters = away_roster[away_roster["pos_type"] != "Pitcher"]
            home_batters = home_roster[home_roster["pos_type"] != "Pitcher"]

            away_lineup_confirmed = not lineups["away"].empty if "away" in lineups else False
            home_lineup_confirmed = not lineups["home"].empty if "home" in lineups else False

            away_ids = lineups["away"]["player_id"].tolist() if away_lineup_confirmed else away_batters["player_id"].tolist()[:9]
            home_ids = lineups["home"]["player_id"].tolist() if home_lineup_confirmed else home_batters["player_id"].tolist()[:9]

            away_order_map = dict(zip(lineups["away"]["player_id"], lineups["away"]["order"])) if away_lineup_confirmed else {pid:i+1 for i,pid in enumerate(away_ids)}
            home_order_map = dict(zip(lineups["home"]["player_id"], lineups["home"]["order"])) if home_lineup_confirmed else {pid:i+1 for i,pid in enumerate(home_ids)}

            # Get pitcher stats
            away_pitch = fetch_pitcher_stats(g["away_prob_id"])
            home_pitch = fetch_pitcher_stats(g["home_prob_id"])
            away_pitch["name"] = g["away_prob_name"]
            home_pitch["name"] = g["home_prob_name"]

            # Get batting stats — prefer Fangraphs, fallback to MLB API
            def get_batter_stats(pid, fg):
                pid = int(pid)
                if not fg.empty and "name" in fg.columns:
                    pass  # Fangraphs data merged by name below
                return {}

            away_mlb_stats = fetch_mlb_batting_stats(away_ids, sel_date.year) if fg_df.empty else pd.DataFrame()
            home_mlb_stats = fetch_mlb_batting_stats(home_ids, sel_date.year) if fg_df.empty else pd.DataFrame()

            def get_name_from_roster(pid, roster):
                row = roster[roster["player_id"] == pid]
                return row.iloc[0]["name"] if not row.empty else str(pid)

            for side_label, player_ids, order_map, opp_pitch, conf, roster, mlb_stats in [
                ("Away", away_ids, away_order_map, home_pitch, away_lineup_confirmed, away_roster, away_mlb_stats),
                ("Home", home_ids, home_order_map, away_pitch, home_lineup_confirmed, home_roster, home_mlb_stats),
            ]:
                for pid in player_ids:
                    pid = int(pid)
                    pname = get_name_from_roster(pid, roster)
                    order = order_map.get(pid, 9)

                    if not fg_df.empty:
                        fg_match = fg_df[fg_df["name"].str.lower() == pname.lower()] if "name" in fg_df.columns else pd.DataFrame()
                        if fg_match.empty:
                            fg_match = fg_df[fg_df["name"].str.lower().str.contains(pname.split()[-1].lower(), na=False)] if pname else pd.DataFrame()
                        row = fg_match.iloc[0].to_dict() if not fg_match.empty else {}
                        row["order"] = order
                        use_adv = not fg_match.empty
                    else:
                        mlb_row = mlb_stats[mlb_stats["player_id"] == pid] if not mlb_stats.empty else pd.DataFrame()
                        row = mlb_row.iloc[0].to_dict() if not mlb_row.empty else {}
                        row["order"] = order
                        use_adv = False

                    row["name"] = pname

                    if (row.get("avg") or 0) < min_avg: continue
                    if opp_pitch.get("era",4.5) > max_era: continue
                    if order > max_ord: continue

                    scores, best_market, best_score = score_batter(row, opp_pitch, wx, w_era, w_whip, use_adv)
                    flt = {k:v for k,v in scores.items() if k in allowed_markets}
                    if not flt: continue
                    best_market = max(flt, key=flt.get)
                    best_score  = flt[best_market]

                    all_rows.append({
                        "Game":           g["away_team"] + " @ " + g["home_team"],
                        "Side":           side_label,
                        "Batter":         pname,
                        "Order":          order,
                        "AVG":            round(row.get("avg",0) or 0, 3),
                        "OBP":            round(row.get("obp",0) or 0, 3),
                        "ISO":            round(row.get("iso",0) or 0, 3),
                        "wRC+":           int(row.get("wrc_plus",100) or 100),
                        "K%":             round((row.get("k_pct",0) or 0)*100, 1),
                        "HardHit%":       round((row.get("hard_hit_pct",0) or 0)*100, 1),
                        "Barrel%":        round((row.get("barrel_pct",0) or 0)*100, 1),
                        "Stats Source":   "Fangraphs" if use_adv else "MLB API",
                        "Opp Pitcher":    opp_pitch.get("name","TBD"),
                        "Pitcher ERA":    opp_pitch.get("era",4.5),
                        "Pitcher WHIP":   opp_pitch.get("whip",1.35),
                        "Pitcher HR/9":   opp_pitch.get("homeRunsPer9",1.2),
                        "Pitcher K/9":    opp_pitch.get("strikeoutsPer9Inn",8.5),
                        "Venue":          wx["venue"],
                        "Park Factor":    wx["factor"],
                        "Temp":           wx["temp"],
                        "Wind":           wx["wind"],
                        "Dome":           wx["dome"],
                        **scores,
                        "Best Market":    best_market,
                        "Best Score":     best_score,
                        "Lineup Status":  "Confirmed" if conf else "Projected",
                    })

        if not all_rows:
            st.error("No batters matched your current filters.")
            status.update(label="Done — no results matched filters", state="error")
        else:
            df = pd.DataFrame(all_rows).sort_values("Best Score", ascending=False)
            st.session_state["auto_df"] = df
            st.session_state["load_log"] = log
            status.update(label="Slate loaded — " + str(len(df)) + " batters scored", state="complete")

# ── RESULTS ──────────────────────────────────────────────────────────────────
if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
    if df.empty:
        st.info("No results. Try adjusting filters.")
    else:
        top = df.iloc[0]
        fg_count = len(df[df["Stats Source"] == "Fangraphs"])
        mlb_count= len(df[df["Stats Source"] == "MLB API"])
        conf_count= len(df[df["Lineup Status"] == "Confirmed"])

        k1,k2,k3,k4 = st.columns(4)
        for col,val,lbl in [
            (k1, str(len(df)),       "Batters Scored"),
            (k2, str(top["Batter"]), "Top Batter"),
            (k3, top["Best Market"], "Best Market"),
            (k4, str(top["Best Score"]), "Top Score"),
        ]:
            with col:
                st.markdown(
                    '<div class="metric-card"><div class="metric-value">' + str(val) + '</div>'
                    '<div class="metric-label">' + lbl + '</div></div>',
                    unsafe_allow_html=True
                )

        col_a, col_b, col_c = st.columns(3)
        col_a.info("Fangraphs stats: " + str(fg_count) + " batters")
        col_b.info("MLB API stats: " + str(mlb_count) + " batters")
        col_c.info("Confirmed lineups: " + str(conf_count) + " batters")

        st.markdown("<br>", unsafe_allow_html=True)
        all_t, t_hits, t_rbi, t_hr, t_runs, t_raw = st.tabs([
            "All Ranked","Hits/Runs","RBI","Home Run","Runs Scored","Raw Data"
        ])

        SHOW_COLS = ["Game","Batter","Order","AVG","OBP","ISO","wRC+","K%","HardHit%",
                     "Opp Pitcher","Pitcher ERA","Pitcher WHIP","Pitcher HR/9",
                     "Venue","Temp","Wind","Best Market","Best Score","Lineup Status","Stats Source"]

        with all_t:
            disp = [c for c in SHOW_COLS if c in df.columns]
            st.dataframe(df[disp].reset_index(drop=True), use_container_width=True, hide_index=True,
                column_config={
                    "Best Score": st.column_config.ProgressColumn("Best Score", min_value=0, max_value=float(df["Best Score"].max())),
                    "AVG":        st.column_config.NumberColumn(format="%.3f"),
                    "OBP":        st.column_config.NumberColumn(format="%.3f"),
                    "ISO":        st.column_config.NumberColumn(format="%.3f"),
                })

        for tab, market in [(t_hits,"Hits/Runs"),(t_rbi,"RBI"),(t_hr,"Home Run"),(t_runs,"Runs Scored")]:
            with tab:
                sub = df[df["Best Market"]==market]
                if sub.empty:
                    st.info("No top picks for " + market + " with current filters.")
                    continue
                c_chart, c_cards = st.columns([3,2])
                with c_chart:
                    fig = go.Figure(go.Bar(
                        y=sub.head(12)["Batter"] + " | " + sub.head(12)["Game"],
                        x=sub.head(12)["Best Score"],
                        orientation="h",
                        marker_color=MARKET_COLORS[market],
                        text=["ERA " + str(e) for e in sub.head(12)["Pitcher ERA"]],
                        textposition="inside", insidetextanchor="start",
                        textfont=dict(color="white",size=11),
                    ))
                    fig.update_layout(
                        title="Top " + market + " Picks",
                        yaxis=dict(autorange="reversed"), height=460,
                        plot_bgcolor="#f9f8f5", paper_bgcolor="#f7f6f2",
                        margin=dict(l=10,r=10,t=40,b=20), font=dict(family="Inter"),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with c_cards:
                    for _, row in sub.head(8).iterrows():
                        avg_str = ".{:03d}".format(int(round(float(row["AVG"]),3)*1000))
                        wrc_str = " | wRC+ " + str(int(row.get("wRC+",100))) if row.get("Stats Source")=="Fangraphs" else ""
                        k_str   = " | K% " + str(row.get("K%",""))+"%" if row.get("Stats Source")=="Fangraphs" else ""
                        card = (
                            '<div class="batter-card">'
                            '<div class="batter-name">' + str(row["Batter"]) + '</div>'
                            '<div class="batter-meta">' + str(row["Game"]) + ' | #' + str(int(row["Order"])) + ' | ' + avg_str + wrc_str + k_str + '</div>'
                            '<div class="batter-meta">vs ' + str(row["Opp Pitcher"]) + ' ERA ' + str(row["Pitcher ERA"]) + ' WHIP ' + str(row["Pitcher WHIP"]) + '</div>'
                            '<div class="batter-meta">' + str(row["Venue"]) + ' | ' + str(int(row["Temp"])) + 'F | ' + str(int(row["Wind"])) + 'mph wind | Park ' + str(row["Park Factor"]) + 'x</div>'
                            '<div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;">'
                            '<span class="badge ' + MARKET_BADGES[market] + '">' + market + '</span>'
                            '<span style="font-weight:700;color:' + MARKET_COLORS[market] + '">Score: ' + str(row["Best Score"]) + '</span>'
                            '</div></div>'
                        )
                        st.markdown(card, unsafe_allow_html=True)

        with t_raw:
            st.caption("Full raw data table with all model inputs")
            st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)

        st.divider()
        st.download_button(
            "Download Full CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="mlb_props_v2_" + str(date.today()) + ".csv",
            mime="text/csv",
        )

st.markdown("---")
st.caption("Sources: MLB Stats API (schedule, pitchers, lineups) | Fangraphs via pybaseball (advanced batting stats, cached 24hrs) | Open-Meteo (weather, no API key required)")
