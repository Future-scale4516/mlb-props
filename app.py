# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests as req
from datetime import date, datetime
import time
from fractions import Fraction
import pytz

st.set_page_config(
    page_title="MLB Prop Analyser",
    page_icon="baseball",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0f1117; color: #e8e8e8; }
section[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
.game-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
.game-card-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; }
.teams { font-size: 1.15rem; font-weight: 700; color: #ffffff; }
.game-meta { font-size: 0.8rem; color: #8b949e; margin-top: 0.25rem; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.03em; }
.badge-hitter  { background: #1a3a2a; color: #3fb950; border: 1px solid #3fb950; }
.badge-neutral { background: #2a2a1a; color: #d29922; border: 1px solid #d29922; }
.badge-pitcher { background: #3a1a1a; color: #f85149; border: 1px solid #f85149; }
.badge-dome    { background: #1a2a3a; color: #58a6ff; border: 1px solid #58a6ff; }
.badge-confirmed { background: #1a3a2a; color: #3fb950; border: 1px solid #3fb950; }
.badge-projected { background: #2a2a2a; color: #8b949e; border: 1px solid #8b949e; }
.grade-premium    { color: #3fb950; font-weight: 700; }
.grade-playable   { color: #d29922; font-weight: 600; }
.grade-suboptimal { color: #8b949e; }
.reason-box { background: #0d1117; border-left: 3px solid #58a6ff; border-radius: 0 6px 6px 0; padding: 0.5rem 0.75rem; font-size: 0.8rem; color: #8b949e; margin-top: 0.4rem; }
.section-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #8b949e; border-bottom: 1px solid #30363d; padding-bottom: 0.4rem; margin: 1.25rem 0 0.75rem; }
.stat-pill { display: inline-block; background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; color: #c9d1d9; margin: 2px; }
.glossary-item { margin-bottom: 0.6rem; }
.glossary-term { font-weight: 700; color: #58a6ff; }
.glossary-def  { color: #8b949e; font-size: 0.85rem; }
@media (max-width: 768px) { .teams { font-size: 1rem; } .game-card { padding: 0.75rem; } .game-card-header { flex-direction: column; } }
.stTabs [data-baseweb="tab-list"] { gap: 4px; background: #161b22; border-radius: 8px; padding: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent; color: #8b949e; border-radius: 6px; font-size: 0.85rem; padding: 6px 14px; }
.stTabs [aria-selected="true"] { background: #21262d !important; color: #ffffff !important; }
[data-testid="metric-container"] { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 0.75rem 1rem; }
</style>
""", unsafe_allow_html=True)

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
RAPIDAPI_KEY = "46e23ff209mshb208e90af2f00d4p120983jsn38b0da2800d0"
TANK01_HOST  = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"
TANK01_BASE  = f"https://{TANK01_HOST}"
BST          = pytz.timezone("Europe/London")
ET           = pytz.timezone("America/New_York")

BALLPARKS = {
    "Oriole Park at Camden Yards": {"factor":1.02,"dome":False,"lat":39.2838,"lon":-76.6218},
    "Yankee Stadium":              {"factor":1.05,"dome":False,"lat":40.8296,"lon":-73.9262},
    "Fenway Park":                 {"factor":1.08,"dome":False,"lat":42.3467,"lon":-71.0972},
    "Wrigley Field":               {"factor":1.05,"dome":False,"lat":41.9484,"lon":-87.6553},
    "Rogers Centre":               {"factor":1.05,"dome":True, "lat":43.6414,"lon":-79.3894},
    "Coors Field":                 {"factor":1.38,"dome":False,"lat":39.7560,"lon":-104.9942},
    "loanDepot park":              {"factor":0.93,"dome":True, "lat":25.7781,"lon":-80.2197},
    "Oracle Park":                 {"factor":0.93,"dome":False,"lat":37.7786,"lon":-122.3893},
    "Petco Park":                  {"factor":0.90,"dome":False,"lat":32.7076,"lon":-117.1570},
    "Citi Field":                  {"factor":0.94,"dome":False,"lat":40.7571,"lon":-73.8458},
    "PNC Park":                    {"factor":0.97,"dome":False,"lat":40.4469,"lon":-80.0057},
    "Tropicana Field":             {"factor":0.94,"dome":True, "lat":27.7683,"lon":-82.6534},
    "Kauffman Stadium":            {"factor":1.01,"dome":False,"lat":39.0517,"lon":-94.4803},
    "Guaranteed Rate Field":       {"factor":1.04,"dome":False,"lat":41.8300,"lon":-87.6339},
    "Truist Park":                 {"factor":1.01,"dome":False,"lat":33.8908,"lon":-84.4678},
    "Angel Stadium":               {"factor":1.00,"dome":False,"lat":33.8003,"lon":-117.8827},
    "T-Mobile Park":               {"factor":0.94,"dome":False,"lat":47.5914,"lon":-122.3325},
    "Dodger Stadium":              {"factor":0.97,"dome":False,"lat":34.0739,"lon":-118.2400},
    "Busch Stadium":               {"factor":0.97,"dome":False,"lat":38.6226,"lon":-90.1928},
    "Progressive Field":           {"factor":0.96,"dome":False,"lat":41.4962,"lon":-81.6852},
    "Comerica Park":               {"factor":0.95,"dome":False,"lat":42.3390,"lon":-83.0485},
    "Globe Life Field":            {"factor":1.02,"dome":True, "lat":32.7473,"lon":-97.0825},
    "Great American Ball Park":    {"factor":1.10,"dome":False,"lat":39.0979,"lon":-84.5082},
    "American Family Field":       {"factor":1.00,"dome":True, "lat":43.0280,"lon":-87.9712},
    "Chase Field":                 {"factor":1.02,"dome":True, "lat":33.4453,"lon":-112.0667},
    "Nationals Park":              {"factor":0.99,"dome":False,"lat":38.8730,"lon":-77.0074},
    "Sutter Health Park":          {"factor":1.05,"dome":False,"lat":38.5803,"lon":-121.5002},
}

MARKET_DISPLAY = {
    "Hits/Runs":   "Hits + Runs",
    "RBI":         "RBI",
    "Home Run":    "Home Run",
    "Runs Scored": "Runs Scored",
}

GLOSSARY = {
    "AVG (Batting Average)":    "Hits divided by at-bats. Baseline measure of how often a batter gets a hit. League average ~.250.",
    "OBP (On-Base Percentage)": "How often a batter reaches base (hits, walks, HBP). More predictive than AVG. League avg ~.320.",
    "SLG (Slugging Percentage)":"Total bases per at-bat. Doubles/triples/HRs weighted higher. League avg ~.410.",
    "ISO (Isolated Power)":     "SLG minus AVG. Pure power metric. Above .200 is elite.",
    "wRC+ (Weighted Runs Created+)": "Overall offensive value vs league average. 100 = league avg. 130+ is excellent.",
    "Barrel %":                 "Rate of ideal contact (98mph+ exit velo, 26-30 degree launch angle). Strongly predicts HRs.",
    "Hard Hit %":               "Balls hit 95mph+. Higher = more consistent damage.",
    "Park Factor":              "How much a ballpark affects scoring vs average (1.00). Coors Field = 1.38 (38% more runs).",
    "Hits + Runs prop":         "Batter records at least 1 hit OR scores at least 1 run. Highest frequency market — best for top of order.",
    "RBI prop":                 "Batter drives in at least 1 run. Best for 3-5 hitters with runners on base.",
    "Home Run prop":            "Batter hits a HR. Higher risk/reward. Best for power hitters vs pitchers with high HR/9.",
    "Runs Scored prop":         "Batter scores a run. Best for 1-2 hitters with high OBP who get on base regularly.",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def to_bst(time_str, game_date):
    try:
        dt_et = ET.localize(datetime.strptime(f"{game_date} {time_str}", "%Y-%m-%d %H:%M"))
        return dt_et.astimezone(BST).strftime("%H:%M BST")
    except Exception:
        try:
            epoch = float(time_str)
            dt_utc = datetime.utcfromtimestamp(epoch).replace(tzinfo=pytz.utc)
            return dt_utc.astimezone(BST).strftime("%H:%M BST")
        except Exception:
            return str(time_str)

def decimal_to_fractional(dec):
    if not dec or dec <= 1.0: return "N/A"
    if dec == 2.0: return "EVENS"
    frac = Fraction(dec - 1.0).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"

def env_badge(label):
    if label == "Hitter-Friendly":  return '<span class="badge badge-hitter">Hitter Friendly</span>'
    if label == "Pitcher-Friendly": return '<span class="badge badge-pitcher">Pitcher Friendly</span>'
    if label == "Dome":             return '<span class="badge badge-dome">Dome</span>'
    return '<span class="badge badge-neutral">Neutral</span>'

def lineup_badge_html(label):
    cls = "badge-confirmed" if label == "Confirmed" else "badge-projected"
    return f'<span class="badge {cls}">{label} Lineup</span>'

def build_reason(row, market):
    name    = row["Batter"]
    avg     = row["AVG"]
    obp     = row["OBP"]
    iso     = row["ISO"]
    wrc     = row["wRC+"]
    env     = row["Env"]
    venue   = row["Venue"]
    pitcher = row.get("Opp Pitcher", "opposing starter")
    era     = row.get("Pitcher ERA", 4.5)
    hr9     = row.get("Pitcher HR9", 1.2)
    order   = row["Order"]
    ordinal = {1:"1st",2:"2nd",3:"3rd",4:"4th",5:"5th",
               6:"6th",7:"7th",8:"8th",9:"9th"}.get(order, f"{order}th")
    if market == "Hits/Runs":
        return (f"{name} bats {ordinal} with AVG {avg:.3f} and OBP {obp:.3f}. "
                f"wRC+ of {wrc} puts them {'above' if wrc>100 else 'at'} league average. "
                f"{venue} is {env.lower()} — boosts contact scoring potential.")
    if market == "RBI":
        return (f"Batting {ordinal} with wRC+ {wrc} and ISO {iso:.3f}. "
                f"{pitcher} carries ERA {era:.2f} — more baserunners expected. "
                f"Slot and power profile make RBI a strong angle.")
    if market == "Home Run":
        return (f"ISO of {iso:.3f} reflects strong raw power. "
                f"Opposing pitcher {pitcher} carries HR/9 of {hr9:.2f}. "
                f"{venue} park factor {'adds a further boost.' if env=='Hitter-Friendly' else 'noted.'}")
    if market == "Runs Scored":
        return (f"OBP {obp:.3f} batting {ordinal} — ideal profile to score runs. "
                f"wRC+ {wrc} confirms consistent offensive output. "
                f"{'Hitter-friendly environment increases scoring probability.' if env=='Hitter-Friendly' else ''}")
    return ""

# ── API ───────────────────────────────────────────────────────────────────────
def tank01_get(endpoint, params=None):
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": TANK01_HOST}
    for attempt in range(3):
        try:
            r = req.get(f"{TANK01_BASE}/{endpoint}", headers=headers, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 2: return {}
            time.sleep(1.5)
    return {}

def mlb_api(endpoint, params=None):
    try:
        r = req.get(f"https://statsapi.mlb.com/api/v1/{endpoint}", params=params, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def safe_get(url, params=None):
    try:
        r = req.get(url, params=params, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_games(game_date: str):
    data = tank01_get("getMLBGamesForDate", {"gameDate": game_date})
    body = data.get("body", [])
    if isinstance(body, dict):
        body = list(body.values())
    rows = []
    for g in body:
        rows.append({
            "gameID":     g.get("gameID", ""),
            "away_team":  g.get("away", ""),
            "home_team":  g.get("home", ""),
            "away_abv":   g.get("awayTeam", g.get("away", "")),
            "home_abv":   g.get("homeTeam", g.get("home", "")),
            "game_time":  g.get("gameTime", "TBD"),
            "venue":      g.get("ballpark", g.get("venue", "")),
            "status":     g.get("gameStatus", "Scheduled"),
            "away_score": g.get("awayScore", ""),
            "home_score": g.get("homeScore", ""),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=600, show_spinner=False)
def fetch_probable_pitchers(game_date: str):
    data = mlb_api("schedule", {
        "sportId": 1, "date": game_date,
        "hydrate": "probablePitcher(note),team,linescore"
    })
    out = {}
    for d in data.get("dates", []):
        for g in d.get("games", []):
            pk   = g.get("gamePk")
            away = g.get("teams", {}).get("away", {})
            home = g.get("teams", {}).get("home", {})
            out[pk] = {
                "away_name":       away.get("team", {}).get("name", ""),
                "home_name":       home.get("team", {}).get("name", ""),
                "away_pitcher":    away.get("probablePitcher", {}).get("fullName", "TBD"),
                "home_pitcher":    home.get("probablePitcher", {}).get("fullName", "TBD"),
                "away_pitcher_id": away.get("probablePitcher", {}).get("id"),
                "home_pitcher_id": home.get("probablePitcher", {}).get("id"),
            }
    return out

@st.cache_data(ttl=600, show_spinner=False)
def fetch_pitcher_stats(pitcher_id):
    if not pitcher_id:
        return {"era":4.50,"whip":1.35,"hr9":1.20,"k9":8.5}
    data = mlb_api(f"people/{pitcher_id}/stats", {"stats":"season","group":"pitching"})
    try:
        s = data["stats"][0]["splits"][0]["stat"]
        return {
            "era":  float(s.get("era")  or 4.50),
            "whip": float(s.get("whip") or 1.35),
            "hr9":  float(s.get("homeRunsPer9") or s.get("hrsPer9Inn") or 1.20),
            "k9":   float(s.get("strikeoutsPer9Inn") or 8.5),
        }
    except Exception:
        return {"era":4.50,"whip":1.35,"hr9":1.20,"k9":8.5}

@st.cache_data(ttl=600, show_spinner=False)
def fetch_mlb_lineups(game_date: str):
    data = mlb_api("schedule", {"sportId":1,"date":game_date,"hydrate":"lineups,team"})
    out = {}
    for d in data.get("dates", []):
        for g in d.get("games", []):
            pk      = g.get("gamePk")
            lineups = g.get("lineups", {})
            out[pk] = {
                "away": [{"id":str(p.get("id","")),"name":p.get("fullName",""),"order":i+1}
                         for i,p in enumerate(lineups.get("awayPlayers",[]))],
                "home": [{"id":str(p.get("id","")),"name":p.get("fullName",""),"order":i+1}
                         for i,p in enumerate(lineups.get("homePlayers",[]))],
            }
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_roster(team_abv: str, season: int):
    data = tank01_get("getMLBTeamRoster", {"teamAbv":team_abv,"season":str(season),"getStats":"true"})
    body   = data.get("body", {}) or {}
    roster = body.get("roster", [])
    rows   = []
    for p in roster:
        stats   = p.get("stats", {}) or {}
        ab      = float(stats.get("AB") or p.get("AB") or 1)
        hits    = float(stats.get("H")  or p.get("H")  or 0)
        bb      = float(stats.get("BB") or p.get("BB") or 0)
        hbp     = float(stats.get("HBP") or 0)
        sf      = float(stats.get("SF")  or 0)
        hr      = float(stats.get("HR")  or p.get("HR") or 0)
        doubles = float(stats.get("2B")  or p.get("2B") or 0)
        triples = float(stats.get("3B")  or p.get("3B") or 0)
        pa      = ab + bb + hbp + sf
        avg_d   = stats.get("avg") or stats.get("battingAvg") or p.get("avg")
        obp_d   = stats.get("obp") or stats.get("onBasePct")  or p.get("obp")
        slg_d   = stats.get("slg") or stats.get("slugPct")    or p.get("slg")
        avg = float(avg_d) if avg_d else (round(hits/ab,3) if ab>1 else 0.0)
        obp = float(obp_d) if obp_d else (round((hits+bb+hbp)/pa,3) if pa>1 else 0.0)
        tb  = hits + doubles + (2*triples) + (3*hr)
        slg = float(slg_d) if slg_d else (round(tb/ab,3) if ab>1 else 0.0)
        iso = round(max(slg-avg,0),3)
        ops = round(obp+slg,3)
        wrc = int((ops/0.730)*100) if ops>0 else 100
        rows.append({
            "player_id":    str(p.get("playerID","")),
            "name":         p.get("longName",p.get("shortName","Unknown")),
            "pos":          p.get("pos",""),
            "avg":avg,"obp":obp,"slg":slg,"ops":ops,"iso":iso,"wrc_plus":wrc,
            "barrel_pct":   min(0.22, max(0.01, iso*0.45)),
            "hard_hit_pct": min(0.60, max(0.15, (ops*0.45)+(iso*0.2))),
            "ab":int(ab),"hr":int(hr),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue: str):
    meta = BALLPARKS.get(venue)
    if not meta:
        return {"temp":72,"wind":8,"wind_dir":"","factor":1.00,"dome":False}
    if meta["dome"]:
        return {"temp":72,"wind":0,"wind_dir":"","factor":meta["factor"],"dome":True}
    try:
        d = safe_get("https://api.open-meteo.com/v1/forecast", {
            "latitude":meta["lat"],"longitude":meta["lon"],
            "current":"temperature_2m,wind_speed_10m,wind_direction_10m",
            "temperature_unit":"fahrenheit","wind_speed_unit":"mph"
        })
        c = d.get("current",{})
        deg = float(c.get("wind_direction_10m") or 0)
        dirs = ["N","NE","E","SE","S","SW","W","NW"]
        wind_dir = dirs[int((deg+22.5)//45)%8]
        return {"temp":float(c.get("temperature_2m") or 72),
                "wind":float(c.get("wind_speed_10m") or 8),
                "wind_dir":wind_dir,"factor":meta["factor"],"dome":False}
    except Exception:
        return {"temp":72,"wind":8,"wind_dir":"","factor":meta["factor"],"dome":False}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_odds(api_key: str):
    if not api_key or not api_key.strip(): return {}
    try:
        r = req.get("https://api.the-odds-api.com/v4/sports/baseball_mlb/odds", params={
            "apiKey":api_key,"regions":"uk","markets":"h2h,spreads,totals",
            "bookmakers":"williamhill,paddypower,betfair,bet365,skybet","oddsFormat":"decimal"
        }, timeout=15)
        r.raise_for_status()
        res = r.json()
        if isinstance(res, list):
            return {f"{i.get('away_team')} @ {i.get('home_team')}":i.get("bookmakers",[]) for i in res}
        return {}
    except Exception:
        return {}

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp-70)*0.003 + wind*0.004

def score_batter(avg,obp,slg,iso,wrc,hh,barrel,order,era,whip,hr9,k9,env):
    of    = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(order,0.80)
    pv    = min(era/7.0,1.0)*0.55 + min(max((whip-0.8)/1.2,0.0),1.0)*0.45
    hrv   = min(hr9/2.5,1.0)
    k_adj = 1.0 - min((k9-7.0)/14.0,0.20)
    contact = avg*0.35 + obp*0.30 + (wrc/200)*0.25 + 0.78*0.10
    power   = iso*0.40 + hh*0.35  + barrel*0.25
    on_base = obp*(wrc/100)
    hs = round(contact*pv*of*k_adj*env*280,2)
    rs = round(contact*pv*(1.0+max(0,(5-order)*0.04))*k_adj*env*260,2)
    hr = round(power*hrv*env*280,2)
    sc = round(on_base*pv*(1.0+max(0,(4-order)*0.05))*k_adj*env*280,2)
    if iso<0.130 or barrel<0.04 or hr9<0.7: hr = 0.0
    if order>7 or wrc<80:                   rs = 0.0
    if order>5 or obp<0.290:               sc = 0.0
    return {"Hits/Runs":hs,"RBI":rs,"Home Run":hr,"Runs Scored":sc}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### MLB Prop Analyser")
    sel_date = st.date_input("Slate Date", value=date.today())
    odds_key = st.text_input("The-Odds-API Key (optional)", value="", type="password",
                              help="the-odds-api.com — for UK bookmaker odds")
    st.markdown("---")
    st.markdown("**Model Filters**")
    min_avg = st.slider("Min AVG",   0.000, 0.350, 0.000, 0.005, format="%.3f")
    min_obp = st.slider("Min OBP",   0.000, 0.400, 0.000, 0.005, format="%.3f")
    min_wrc = st.slider("Min wRC+",  0,     180,   0,     5)
    max_ord = st.slider("Max Batting Order", 1, 9, 9)
    st.markdown("---")
    show_glossary = st.checkbox("Show Stats Glossary", value=False)
    debug_mode    = st.checkbox("Debug Mode", value=False)
    if st.button("Clear Cache & Reload"):
        st.cache_data.clear()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("<h1 style='color:#ffffff;margin-bottom:0'>MLB Prop Analyser</h1>", unsafe_allow_html=True)
st.markdown(
    f"<p style='color:#8b949e;margin-top:4px'>Slate: "
    f"<b style='color:#58a6ff'>{sel_date.strftime('%A %d %B %Y')}</b>"
    f" &nbsp;|&nbsp; Data: Tank01 + MLB Stats API &nbsp;|&nbsp; Times in BST</p>",
    unsafe_allow_html=True
)
st.divider()

# ── GLOSSARY ──────────────────────────────────────────────────────────────────
if show_glossary:
    st.markdown("<div class='section-title'>Stats and Markets Glossary</div>", unsafe_allow_html=True)
    cols = st.columns(2)
    for i,(term,defn) in enumerate(GLOSSARY.items()):
        with cols[i%2]:
            st.markdown(
                f"<div class='glossary-item'>"
                f"<span class='glossary-term'>{term}</span><br>"
                f"<span class='glossary-def'>{defn}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
    st.divider()

# ── LOAD ──────────────────────────────────────────────────────────────────────
load_col, _ = st.columns([2,6])
with load_col:
    load_btn = st.button("Load Slate", type="primary", use_container_width=True)

if load_btn:
    tank01_date = sel_date.strftime("%Y%m%d")
    mlb_date    = sel_date.strftime("%Y-%m-%d")

    with st.status("Loading slate data...", expanded=True) as status:
        games_df = fetch_games(tank01_date)
        if games_df.empty:
            st.error("No games found. Check your RapidAPI subscription or try a different date.")
            st.stop()
        st.write(f"Found {len(games_df)} games")

        pitchers     = fetch_probable_pitchers(mlb_date)
        mlb_lineups  = fetch_mlb_lineups(mlb_date)
        odds_data    = fetch_odds(odds_key)
        st.write("Fetching rosters and weather...")

        all_rows, game_meta, game_proj = [], {}, {}

        for _, g in games_df.iterrows():
            g_match  = f"{g['away_team']} @ {g['home_team']}"
            away_abv = g["away_abv"]
            home_abv = g["home_abv"]

            wx      = fetch_weather(g["venue"])
            env_mod = wx["factor"] * wx_modifier(wx["temp"],wx["wind"],wx["dome"])
            if wx["dome"]:          env_label = "Dome"
            elif env_mod >= 1.06:   env_label = "Hitter-Friendly"
            elif env_mod >= 0.97:   env_label = "Neutral"
            else:                   env_label = "Pitcher-Friendly"
            wx_str = ("Dome (controlled)" if wx["dome"]
                      else f"{int(wx['temp'])}F | {int(wx['wind'])} mph {wx['wind_dir']}")

            bst_time = to_bst(str(g["game_time"]), str(sel_date))

            away_pitcher = {"era":4.5,"whip":1.35,"hr9":1.2,"k9":8.5,"name":"TBD"}
            home_pitcher = {"era":4.5,"whip":1.35,"hr9":1.2,"k9":8.5,"name":"TBD"}
            for pk, pdata in pitchers.items():
                if (g["away_team"] in pdata.get("away_name","") or
                    g["home_team"] in pdata.get("home_name","")):
                    ap = fetch_pitcher_stats(pdata.get("away_pitcher_id"))
                    ap["name"] = pdata.get("away_pitcher","TBD")
                    hp = fetch_pitcher_stats(pdata.get("home_pitcher_id"))
                    hp["name"] = pdata.get("home_pitcher","TBD")
                    away_pitcher, home_pitcher = ap, hp
                    break

            confirmed = {"away":[],"home":[]}
            for pk,ldata in mlb_lineups.items():
                if ldata.get("away") or ldata.get("home"):
                    confirmed = ldata
                    break
            lineup_confirmed = bool(confirmed["away"] and confirmed["home"])

            away_roster = fetch_roster(away_abv, sel_date.year)
            home_roster = fetch_roster(home_abv, sel_date.year)

            def build_df(roster, lineup_list):
                if lineup_list and not roster.empty:
                    order_map = {p["id"]:p["order"] for p in lineup_list}
                    r = roster.copy()
                    r["order"] = r["player_id"].map(order_map)
                    r = r.dropna(subset=["order"])
                    r["order"] = r["order"].astype(int)
                    return r.sort_values("order")
                if not roster.empty:
                    return roster.assign(order=range(1,len(roster)+1))
                return pd.DataFrame()

            away_df = build_df(away_roster, confirmed["away"])
            home_df = build_df(home_roster, confirmed["home"])

            away_wrcs, home_wrcs = [], []

            for side, df_side, opp_p in [
                ("Away", away_df, home_pitcher),
                ("Home", home_df, away_pitcher),
            ]:
                if df_side is None or df_side.empty:
                    continue
                for _, p in df_side.iterrows():
                    order = int(p.get("order",9) or 9)
                    if order > max_ord: continue
                    avg  = float(p.get("avg") or 0)
                    obp  = float(p.get("obp") or 0)
                    slg  = float(p.get("slg") or 0)
                    iso  = float(p.get("iso") or 0)
                    wrc  = int(p.get("wrc_plus") or 100)
                    hh   = float(p.get("hard_hit_pct") or 0.35)
                    bar  = float(p.get("barrel_pct") or 0.06)
                    name = str(p.get("name","Unknown"))

                    if side=="Away": away_wrcs.append(wrc)
                    else:            home_wrcs.append(wrc)

                    if avg<min_avg or obp<min_obp or wrc<min_wrc:
                        continue

                    scores = score_batter(avg,obp,slg,iso,wrc,hh,bar,order,
                                         opp_p["era"],opp_p["whip"],opp_p["hr9"],opp_p["k9"],env_mod)
                    best_m = max(scores, key=scores.get)
                    best_s = scores[best_m]
                    grade  = "Premium" if best_s>=70 else "Playable" if best_s>=48 else "Sub-optimal"

                    all_rows.append({
                        "Game":        g_match,
                        "Side":        side,
                        "Batter":      name,
                        "Order":       order,
                        "AVG":         avg,
                        "OBP":         obp,
                        "SLG":         slg,
                        "ISO":         iso,
                        "wRC+":        wrc,
                        "Hits/Runs":   scores["Hits/Runs"],
                        "RBI":         scores["RBI"],
                        "Home Run":    scores["Home Run"],
                        "Runs Scored": scores["Runs Scored"],
                        "Best Market": best_m,
                        "Best Score":  best_s,
                        "Grade":       grade,
                        "BST Time":    bst_time,
                        "Venue":       g["venue"],
                        "Env":         env_label,
                        "Weather":     wx_str,
                        "Lineup":      "Confirmed" if lineup_confirmed else "Projected",
                        "Opp Pitcher": opp_p["name"],
                        "Pitcher ERA": opp_p["era"],
                        "Pitcher HR9": opp_p["hr9"],
                        "Park Factor": wx["factor"],
                    })

            maw = sum(away_wrcs)/len(away_wrcs) if away_wrcs else 100
            mhw = sum(home_wrcs)/len(home_wrcs) if home_wrcs else 100
            par = round(4.1*(maw/100)*(home_pitcher["era"]/4.3)*wx["factor"],2)
            phr = round(4.1*(mhw/100)*(away_pitcher["era"]/4.3)*wx["factor"],2)
            den = (par**1.83)+(phr**1.83)
            awp = round((par**1.83)/den,4) if den>0 else 0.5

            game_meta[g_match] = {
                "bst_time":     bst_time,
                "venue":        g["venue"],
                "env":          env_label,
                "wx":           wx_str,
                "lineup":       "Confirmed" if lineup_confirmed else "Projected",
                "away_team":    g["away_team"],
                "home_team":    g["home_team"],
                "away_pitcher": away_pitcher["name"],
                "home_pitcher": home_pitcher["name"],
                "away_era":     away_pitcher["era"],
                "home_era":     home_pitcher["era"],
                "park_factor":  wx["factor"],
                "status":       g["status"],
                "away_score":   g.get("away_score",""),
                "home_score":   g.get("home_score",""),
            }
            game_proj[g_match] = {
                "proj_away":  par,
                "proj_home":  phr,
                "away_prob":  awp,
                "home_prob":  1-awp,
                "proj_total": round(par+phr,1),
                "run_line":   round(phr-par,1),
            }

        st.session_state["all_rows"]  = all_rows
        st.session_state["game_meta"] = game_meta
        st.session_state["game_proj"] = game_proj
        st.session_state["odds_data"] = odds_data

        if all_rows:
            status.update(label=f"Done — {len(all_rows)} player profiles across {len(game_meta)} games.", state="complete")
        else:
            status.update(label="Games loaded but no player stats returned. Enable Debug Mode in sidebar.", state="error")

# ── NOTHING LOADED ────────────────────────────────────────────────────────────
if "all_rows" not in st.session_state:
    st.markdown("""
    <div style='text-align:center;padding:3rem;color:#8b949e'>
        <div style='font-size:3rem'>baseball</div>
        <p style='font-size:1.1rem;margin-top:1rem'>
            Select a date and click <b style='color:#58a6ff'>Load Slate</b> to begin
        </p>
        <p style='font-size:0.85rem'>
            Tick <b>Show Stats Glossary</b> in the sidebar for a breakdown of all metrics and markets
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

df_all       = pd.DataFrame(st.session_state["all_rows"])
game_meta    = st.session_state["game_meta"]
game_proj    = st.session_state["game_proj"]
odds_data    = st.session_state.get("odds_data",{})
sorted_games = sorted(game_meta.keys(), key=lambda g: game_meta[g]["bst_time"])

# ── GAME OVERVIEW CARDS ───────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Today's Games</div>", unsafe_allow_html=True)

hitter_games  = [g for g in sorted_games if game_meta[g]["env"]=="Hitter-Friendly"]
neutral_games = [g for g in sorted_games if game_meta[g]["env"] in ("Neutral","Dome")]
pitcher_games = [g for g in sorted_games if game_meta[g]["env"]=="Pitcher-Friendly"]

def render_game_card(g):
    m   = game_meta[g]
    score_str = ""
    if m.get("away_score") and m.get("home_score"):
        score_str = f"&nbsp; <b style='color:#3fb950'>{m['away_score']} - {m['home_score']}</b>"
    st.markdown(f"""
    <div class='game-card'>
      <div class='game-card-header'>
        <div>
          <div class='teams'>{m['away_team']} <span style='color:#8b949e'>@</span> {m['home_team']}{score_str}</div>
          <div class='game-meta'>
            {m['bst_time']} &nbsp;|&nbsp; {m['venue']} &nbsp;|&nbsp; {m['wx']}
          </div>
          <div class='game-meta' style='margin-top:4px'>
            {m['away_team']} SP: <b>{m['away_pitcher']}</b> (ERA {m['away_era']:.2f})
            &nbsp;|&nbsp;
            {m['home_team']} SP: <b>{m['home_pitcher']}</b> (ERA {m['home_era']:.2f})
          </div>
        </div>
        <div style='text-align:right'>
          {env_badge(m['env'])} &nbsp; {lineup_badge_html(m['lineup'])}
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

if hitter_games:
    st.markdown("<div class='section-title'>Hitter Friendly</div>", unsafe_allow_html=True)
    for g in hitter_games: render_game_card(g)

if neutral_games:
    st.markdown("<div class='section-title'>Neutral / Dome</div>", unsafe_allow_html=True)
    for g in neutral_games: render_game_card(g)

if pitcher_games:
    st.markdown("<div class='section-title'>Pitcher Friendly</div>", unsafe_allow_html=True)
    for g in pitcher_games: render_game_card(g)

st.divider()

# ── TABS ──────────────────────────────────────────────────────────────────────
tabs = st.tabs(["Hits + Runs","RBI","Runs Scored","Home Runs","Moneyline","Over/Under","Run Line","Results"])

# ── PROP TABS ─────────────────────────────────────────────────────────────────
prop_markets = ["Hits/Runs","RBI","Runs Scored","Home Run"]

for tab_idx, market in enumerate(prop_markets):
    with tabs[tab_idx]:
        if df_all.empty:
            st.info("No data loaded.")
            continue

        m_df = df_all[df_all[market] > 0].copy()

        fc1,fc2,fc3,fc4 = st.columns(4)
        with fc1:
            env_f   = st.selectbox("Environment",["All","Hitter-Friendly","Neutral","Dome","Pitcher-Friendly"],key=f"env_{tab_idx}")
        with fc2:
            side_f  = st.selectbox("Side",["All","Away","Home"],key=f"side_{tab_idx}")
        with fc3:
            grade_f = st.selectbox("Grade",["All","Premium","Playable"],key=f"grade_{tab_idx}")
        with fc4:
            game_f  = st.selectbox("Game",["All"]+sorted_games,key=f"game_{tab_idx}")

        if env_f   != "All": m_df = m_df[m_df["Env"]   == env_f]
        if side_f  != "All": m_df = m_df[m_df["Side"]  == side_f]
        if grade_f != "All": m_df = m_df[m_df["Grade"] == grade_f]
        if game_f  != "All": m_df = m_df[m_df["Game"]  == game_f]

        m_df = m_df.sort_values(market, ascending=False)
        score_col = MARKET_DISPLAY[market] + " Score"
        st.markdown(f"**{len(m_df)} picks** matching filters")

        display_cols = ["Game","Batter","Order","Side","AVG","OBP","ISO","wRC+",market,"Grade","BST Time","Opp Pitcher"]
        st.dataframe(
            m_df[display_cols].rename(columns={market: score_col}).reset_index(drop=True),
            use_container_width=True,
            column_config={
                score_col: st.column_config.ProgressColumn(score_col, min_value=0, max_value=100, format="%.1f"),
                "AVG": st.column_config.NumberColumn("AVG", format="%.3f"),
                "OBP": st.column_config.NumberColumn("OBP", format="%.3f"),
                "ISO": st.column_config.NumberColumn("ISO", format="%.3f"),
            }
        )

        st.markdown("---")
        st.markdown("**Best picks per game with model reasoning**")
        for g in sorted_games:
            g_picks = m_df[m_df["Game"]==g].head(3)
            if g_picks.empty: continue
            m_data  = game_meta[g]
            with st.expander(f"{g}  |  {m_data['bst_time']}  |  {m_data['venue']}"):
                for _, row in g_picks.iterrows():
                    reason = build_reason(row, market)
                    sc     = row[market]
                    grade  = row["Grade"]
                    g_cls  = ("grade-premium" if grade=="Premium"
                              else "grade-playable" if grade=="Playable"
                              else "grade-suboptimal")
                    st.markdown(f"""
                    <div style='margin-bottom:0.75rem'>
                      <span style='font-weight:700;color:#c9d1d9'>{row['Batter']}</span>
                      &nbsp;<span class='stat-pill'>#{row['Order']}</span>
                      &nbsp;<span class='stat-pill'>{row['Side']}</span>
                      &nbsp;<span class='stat-pill'>AVG {row['AVG']:.3f}</span>
                      &nbsp;<span class='stat-pill'>OBP {row['OBP']:.3f}</span>
                      &nbsp;<span class='stat-pill'>ISO {row['ISO']:.3f}</span>
                      &nbsp;<span class='stat-pill'>wRC+ {row['wRC+']}</span>
                      &nbsp;<span class='{g_cls}'> Score: {sc:.1f}</span>
                      <div class='reason-box'>{reason}</div>
                    </div>
                    """, unsafe_allow_html=True)

# ── MONEYLINE TAB ─────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Moneyline — Model Probabilities")
    if not odds_data:
        st.info("Enter your The-Odds-API key in the sidebar for live UK bookmaker odds.")
    for g in sorted_games:
        prj = game_proj.get(g)
        m   = game_meta[g]
        if not prj: continue
        at,ht = m["away_team"],m["home_team"]
        with st.container(border=True):
            c1,c2,c3 = st.columns([3,1,1])
            with c1:
                st.markdown(f"**{g}** &nbsp; {m['bst_time']}")
                st.markdown(f"<span style='color:#8b949e;font-size:0.8rem'>{m['venue']} | {m['wx']}</span>",unsafe_allow_html=True)
            with c2:
                st.metric(f"{at} Win%", f"{prj['away_prob']*100:.1f}%")
            with c3:
                st.metric(f"{ht} Win%", f"{prj['home_prob']*100:.1f}%")
            bk_list = odds_data.get(g,[])
            if bk_list:
                bae,bhe,bab,bhb,ap,hp = -100,-100,"","","",""
                for b in bk_list:
                    h2h = next((mk for mk in b.get("markets",[]) if mk["key"]=="h2h"),None)
                    if h2h:
                        oc = h2h.get("outcomes",[])
                        ao = next((o for o in oc if o["name"]==at),None)
                        ho = next((o for o in oc if o["name"]==ht),None)
                        if ao and ho:
                            aev = ((prj["away_prob"]*ao["price"])-1.0)*100
                            hev = ((prj["home_prob"]*ho["price"])-1.0)*100
                            if aev>bae: bae,bab,ap = aev,b["title"],decimal_to_fractional(ao["price"])
                            if hev>bhe: bhe,bhb,hp = hev,b["title"],decimal_to_fractional(ho["price"])
                if bae>0: st.success(f"VALUE: {at} @ {ap} ({bab}) | EV: +{bae:.1f}")
                if bhe>0: st.success(f"VALUE: {ht} @ {hp} ({bhb}) | EV: +{bhe:.1f}")
                if bae<=0 and bhe<=0: st.warning("No moneyline value edge detected.")

# ── OVER/UNDER TAB ────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Over/Under — Model Projections")
    ou_rows = []
    for g in sorted_games:
        prj = game_proj.get(g)
        m   = game_meta[g]
        if not prj: continue
        ou_rows.append({
            "Game":             g,
            "Time (BST)":       m["bst_time"],
            "Venue":            m["venue"],
            "Environment":      m["env"],
            "Park Factor":      m["park_factor"],
            "Away SP (ERA)":    f"{m['away_pitcher']} ({m['away_era']:.2f})",
            "Home SP (ERA)":    f"{m['home_pitcher']} ({m['home_era']:.2f})",
            "Proj Away Runs":   prj["proj_away"],
            "Proj Home Runs":   prj["proj_home"],
            "Proj Total":       prj["proj_total"],
        })
    if ou_rows:
        st.dataframe(pd.DataFrame(ou_rows), use_container_width=True,
                     column_config={"Proj Total": st.column_config.ProgressColumn(
                         "Proj Total", min_value=4, max_value=14, format="%.1f")})
        st.caption("Proj Total above 9.0 suggests OVER lean. Below 7.5 suggests UNDER lean.")

# ── RUN LINE TAB ──────────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("Run Line — Model Projections")
    rl_rows = []
    for g in sorted_games:
        prj = game_proj.get(g)
        m   = game_meta[g]
        if not prj: continue
        spread = prj["run_line"]
        lean   = (f"{m['home_team']} -{abs(spread):.1f}" if spread<-0.5
                  else f"{m['away_team']} -{abs(spread):.1f}" if spread>0.5
                  else "Pick'em")
        rl_rows.append({
            "Game":           g,
            "Time (BST)":     m["bst_time"],
            "Proj Away Runs": prj["proj_away"],
            "Proj Home Runs": prj["proj_home"],
            "Proj Run Line":  f"{prj['run_line']:+.1f} (Home)",
            "Model Lean":     lean,
            "Away Win%":      f"{prj['away_prob']*100:.1f}%",
            "Home Win%":      f"{prj['home_prob']*100:.1f}%",
        })
    if rl_rows:
        st.dataframe(pd.DataFrame(rl_rows), use_container_width=True)
        st.caption("Proj Run Line = projected home margin. Positive = home favoured by model.")

# ── RESULTS TAB ───────────────────────────────────────────────────────────────
with tabs[7]:
    st.subheader("Results — Auto-Fetched Final Scores")
    st.caption("Scores pulled live from Tank01. Only completed games show a winner.")
    results_rows = []
    for g in sorted_games:
        m   = game_meta[g]
        prj = game_proj.get(g,{})
        as_ = str(m.get("away_score",""))
        hs_ = str(m.get("home_score",""))
        if as_=="" or hs_=="" or not as_.isdigit() or not hs_.isdigit():
            status_str,winner = "Scheduled / In Progress","—"
        else:
            ai,hi = int(as_),int(hs_)
            winner     = m["away_team"] if ai>hi else m["home_team"]
            status_str = f"Final: {ai} - {hi}"
        model_pick = m["away_team"] if prj.get("away_prob",0.5)>=0.5 else m["home_team"]
        correct    = "correct" if winner==model_pick else ("—" if winner=="—" else "wrong")
        results_rows.append({
            "Game":          g,
            "Time (BST)":    m["bst_time"],
            "Score":         status_str,
            "Winner":        winner,
            "Model Pick":    model_pick,
            "Result":        correct,
            "Proj Total":    prj.get("proj_total",""),
            "Actual Total":  (int(as_)+int(hs_)) if (as_.isdigit() and hs_.isdigit()) else "—",
        })
    if results_rows:
        res_df = pd.DataFrame(results_rows)
        st.dataframe(res_df, use_container_width=True)
        completed = res_df[res_df["Winner"]!="—"]
        if not completed.empty:
            n_correct = (completed["Result"]=="correct").sum()
            st.metric("Model Accuracy (today)",
                      f"{n_correct}/{len(completed)} ({n_correct/len(completed)*100:.0f}%)")
    else:
        st.info("No results yet. Check back after games complete.")

# ── DEBUG ─────────────────────────────────────────────────────────────────────
if debug_mode and "all_rows" in st.session_state:
    st.divider()
    st.markdown("**Debug — Raw Data (first 20 rows)**")
    st.dataframe(pd.DataFrame(st.session_state["all_rows"]).head(20), use_container_width=True)
    st.markdown("**Game Meta (first game)**")
    if game_meta:
        st.json(dict(list(game_meta.items())[0:1]))
