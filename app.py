# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests as req
from datetime import date, datetime, timezone, timedelta
import time
from fractions import Fraction

st.set_page_config(
    page_title="MLB Prop Analyser",
    page_icon="âš¾",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0f1117; color: #e8e8e8; }
section[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
.game-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 0.75rem; }
.game-card-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; }
.teams { font-size: 1.1rem; font-weight: 700; color: #ffffff; }
.game-meta { font-size: 0.78rem; color: #8b949e; margin-top: 0.2rem; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em; }
.badge-hitter  { background:#1a3a2a;color:#3fb950;border:1px solid #3fb950; }
.badge-neutral { background:#2a2a1a;color:#d29922;border:1px solid #d29922; }
.badge-pitcher { background:#3a1a1a;color:#f85149;border:1px solid #f85149; }
.badge-dome    { background:#1a2a3a;color:#58a6ff;border:1px solid #58a6ff; }
.badge-confirmed  { background:#1a3a2a;color:#3fb950;border:1px solid #3fb950; }
.badge-projected  { background:#2a2a2a;color:#8b949e;border:1px solid #8b949e; }
.grade-premium    { color:#3fb950;font-weight:700; }
.grade-playable   { color:#d29922;font-weight:600; }
.grade-suboptimal { color:#8b949e; }
.reason-box { background:#0d1117;border-left:3px solid #58a6ff;border-radius:0 6px 6px 0;padding:0.5rem 0.75rem;font-size:0.8rem;color:#8b949e;margin-top:0.4rem; }
.section-title { font-size:0.7rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#8b949e;border-bottom:1px solid #30363d;padding-bottom:0.4rem;margin:1.25rem 0 0.75rem; }
.stat-pill { display:inline-block;background:#21262d;border:1px solid #30363d;border-radius:6px;padding:2px 8px;font-size:0.75rem;color:#c9d1d9;margin:2px; }
.threshold-box { background:#161b22;border:1px solid #30363d;border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.75rem;font-size:0.8rem; }
.model-explainer { background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:1rem 1.25rem;margin-bottom:1rem;font-size:0.82rem;color:#8b949e;line-height:1.7; }
@media (max-width:768px) { .teams{font-size:1rem;} .game-card{padding:0.75rem;} }
.stTabs [data-baseweb="tab-list"] { gap:4px;background:#161b22;border-radius:8px;padding:4px;flex-wrap:wrap; }
.stTabs [data-baseweb="tab"] { background:transparent;color:#8b949e;border-radius:6px;font-size:0.82rem;padding:5px 12px; }
.stTabs [aria-selected="true"] { background:#21262d !important;color:#ffffff !important; }
[data-testid="metric-container"] { background:#161b22;border:1px solid #30363d;border-radius:10px;padding:0.75rem 1rem; }
</style>
""", unsafe_allow_html=True)

# â”€â”€ CONSTANTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
RAPIDAPI_KEY = "46e23ff209mshb208e90af2f00d4p120983jsn38b0da2800d0"
TANK01_HOST  = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"
TANK01_BASE  = f"https://{TANK01_HOST}"
BST = timezone(timedelta(hours=1))
ET  = timezone(timedelta(hours=-4))

# Per-market recommended thresholds (evidence-based)
THRESHOLDS = {
    "Hits/Runs":   {"avg":0.240,"obp":0.310,"wrc":95,  "label":"Hits + Runs"},
    "RBI":         {"avg":0.255,"obp":0.315,"wrc":100, "label":"RBI"},
    "Home Run":    {"avg":0.230,"obp":0.300,"wrc":105, "label":"Home Run"},
    "Runs Scored": {"avg":0.240,"obp":0.330,"wrc":90,  "label":"Runs Scored"},
}

BALLPARKS = {
    "Oriole Park at Camden Yards":{"factor":1.02,"dome":False,"lat":39.2838,"lon":-76.6218},
    "Yankee Stadium":             {"factor":1.05,"dome":False,"lat":40.8296,"lon":-73.9262},
    "Fenway Park":                {"factor":1.08,"dome":False,"lat":42.3467,"lon":-71.0972},
    "Wrigley Field":              {"factor":1.05,"dome":False,"lat":41.9484,"lon":-87.6553},
    "Rogers Centre":              {"factor":1.05,"dome":True, "lat":43.6414,"lon":-79.3894},
    "Coors Field":                {"factor":1.38,"dome":False,"lat":39.7560,"lon":-104.9942},
    "loanDepot park":             {"factor":0.93,"dome":True, "lat":25.7781,"lon":-80.2197},
    "Oracle Park":                {"factor":0.93,"dome":False,"lat":37.7786,"lon":-122.3893},
    "Petco Park":                 {"factor":0.90,"dome":False,"lat":32.7076,"lon":-117.1570},
    "Citi Field":                 {"factor":0.94,"dome":False,"lat":40.7571,"lon":-73.8458},
    "PNC Park":                   {"factor":0.97,"dome":False,"lat":40.4469,"lon":-80.0057},
    "Tropicana Field":            {"factor":0.94,"dome":True, "lat":27.7683,"lon":-82.6534},
    "Kauffman Stadium":           {"factor":1.01,"dome":False,"lat":39.0517,"lon":-94.4803},
    "Guaranteed Rate Field":      {"factor":1.04,"dome":False,"lat":41.8300,"lon":-87.6339},
    "Truist Park":                {"factor":1.01,"dome":False,"lat":33.8908,"lon":-84.4678},
    "Angel Stadium":              {"factor":1.00,"dome":False,"lat":33.8003,"lon":-117.8827},
    "T-Mobile Park":              {"factor":0.94,"dome":False,"lat":47.5914,"lon":-122.3325},
    "Dodger Stadium":             {"factor":0.97,"dome":False,"lat":34.0739,"lon":-118.2400},
    "Busch Stadium":              {"factor":0.97,"dome":False,"lat":38.6226,"lon":-90.1928},
    "Progressive Field":          {"factor":0.96,"dome":False,"lat":41.4962,"lon":-81.6852},
    "Comerica Park":              {"factor":0.95,"dome":False,"lat":42.3390,"lon":-83.0485},
    "Globe Life Field":           {"factor":1.02,"dome":True, "lat":32.7473,"lon":-97.0825},
    "Great American Ball Park":   {"factor":1.10,"dome":False,"lat":39.0979,"lon":-84.5082},
    "American Family Field":      {"factor":1.00,"dome":True, "lat":43.0280,"lon":-87.9712},
    "Chase Field":                {"factor":1.02,"dome":True, "lat":33.4453,"lon":-112.0667},
    "Nationals Park":             {"factor":0.99,"dome":False,"lat":38.8730,"lon":-77.0074},
    "Sutter Health Park":         {"factor":1.05,"dome":False,"lat":38.5803,"lon":-121.5002},
    "Globe Life Park":            {"factor":1.02,"dome":False,"lat":32.7473,"lon":-97.0825},
}

# â”€â”€ HELPERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def to_bst(time_str, game_date):
    try:
        dt_et = datetime.strptime(f"{game_date} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        return dt_et.astimezone(BST).strftime("%H:%M BST")
    except Exception:
        try:
            epoch = float(time_str)
            dt_utc = datetime.utcfromtimestamp(epoch).replace(tzinfo=timezone.utc)
            return dt_utc.astimezone(BST).strftime("%H:%M BST")
        except Exception:
            return str(time_str)

def decimal_to_fractional(dec):
    if not dec or dec <= 1.0: return "N/A"
    if dec == 2.0: return "EVENS"
    frac = Fraction(dec - 1.0).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"

def env_badge(label):
    mapping = {
        "Hitter-Friendly": "badge-hitter",
        "Pitcher-Friendly":"badge-pitcher",
        "Dome":            "badge-dome",
    }
    cls = mapping.get(label, "badge-neutral")
    return f'<span class="badge {cls}">{label}</span>'

def lineup_badge_html(label):
    cls = "badge-confirmed" if label == "Confirmed" else "badge-projected"
    return f'<span class="badge {cls}">{label} Lineup</span>'

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp - 70) * 0.003 + wind * 0.004

def build_reason(row, market):
    name    = row["Batter"]
    avg     = row["AVG"];  obp = row["OBP"]
    iso     = row["ISO"];  wrc = row["wRC+"]
    env     = row["Env"];  venue = row["Venue"]
    pitcher = row.get("Opp Pitcher","opposing starter")
    era     = row.get("Pitcher ERA", 4.5)
    hr9     = row.get("Pitcher HR9", 1.2)
    order   = row["Order"]
    ordinal = {1:"1st",2:"2nd",3:"3rd",4:"4th",5:"5th",
               6:"6th",7:"7th",8:"8th",9:"9th"}.get(order,f"{order}th")
    if market == "Hits/Runs":
        return (f"{name} bats {ordinal} with AVG {avg:.3f} and OBP {obp:.3f}. "
                f"wRC+ of {wrc} puts them {'above' if wrc>100 else 'at or below'} league average. "
                f"{venue} is {env.lower()} â€” boosts contact/scoring potential.")
    if market == "RBI":
        return (f"Batting {ordinal} with wRC+ {wrc} and ISO {iso:.3f}. "
                f"{pitcher} carries ERA {era:.2f} â€” expect runners on base. "
                f"Slot and power profile make RBI a strong angle.")
    if market == "Home Run":
        return (f"ISO of {iso:.3f} reflects {'strong' if iso>0.18 else 'moderate'} raw power. "
                f"Opposing pitcher {pitcher} carries HR/9 of {hr9:.2f}. "
                f"{venue} park factor {'adds a further boost.' if env=='Hitter-Friendly' else 'is noted.'}")
    if market == "Runs Scored":
        return (f"OBP {obp:.3f} batting {ordinal} â€” ideal profile to score runs. "
                f"wRC+ {wrc} confirms consistent offensive output. "
                f"{'Hitter-friendly environment increases scoring probability.' if env=='Hitter-Friendly' else ''}")
    return ""

# â”€â”€ API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    if isinstance(body, dict): body = list(body.values())
    rows = []
    for g in body:
        rows.append({
            "gameID":     g.get("gameID",""),
            "away_team":  g.get("away",""),
            "home_team":  g.get("home",""),
            "away_abv":   g.get("awayTeam", g.get("away","")),
            "home_abv":   g.get("homeTeam", g.get("home","")),
            "game_time":  g.get("gameTime","TBD"),
            "venue":      g.get("ballpark", g.get("venue","")),
            "status":     g.get("gameStatus","Scheduled"),
            "away_score": g.get("awayScore",""),
            "home_score": g.get("homeScore",""),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=600, show_spinner=False)
def fetch_probable_pitchers(game_date: str):
    data = mlb_api("schedule", {"sportId":1,"date":game_date,"hydrate":"probablePitcher(note),team,linescore"})
    out = {}
    for d in data.get("dates",[]):
        for g in d.get("games",[]):
            pk   = g.get("gamePk")
            away = g.get("teams",{}).get("away",{})
            home = g.get("teams",{}).get("home",{})
            out[pk] = {
                "away_name":       away.get("team",{}).get("name",""),
                "home_name":       home.get("team",{}).get("name",""),
                "away_pitcher":    away.get("probablePitcher",{}).get("fullName","TBD"),
                "home_pitcher":    home.get("probablePitcher",{}).get("fullName","TBD"),
                "away_pitcher_id": away.get("probablePitcher",{}).get("id"),
                "home_pitcher_id": home.get("probablePitcher",{}).get("id"),
            }
    return out

@st.cache_data(ttl=600, show_spinner=False)
def fetch_pitcher_stats(pitcher_id):
    if not pitcher_id:
        return {"era":4.50,"whip":1.35,"hr9":1.20,"k9":8.5,"fip":4.50}
    data = mlb_api(f"people/{pitcher_id}/stats", {"stats":"season","group":"pitching"})
    try:
        s = data["stats"][0]["splits"][0]["stat"]
        era  = float(s.get("era")  or 4.50)
        whip = float(s.get("whip") or 1.35)
        hr9  = float(s.get("homeRunsPer9") or s.get("hrsPer9Inn") or 1.20)
        k9   = float(s.get("strikeoutsPer9Inn") or 8.5)
        bb9  = float(s.get("walksPer9Inn") or 3.2)
        # Simplified FIP proxy
        fip  = round((13*hr9 + 3*bb9 - 2*k9) / 9 + 3.20, 2)
        return {"era":era,"whip":whip,"hr9":hr9,"k9":k9,"fip":fip}
    except Exception:
        return {"era":4.50,"whip":1.35,"hr9":1.20,"k9":8.5,"fip":4.50}

@st.cache_data(ttl=600, show_spinner=False)
def fetch_mlb_lineups(game_date: str):
    data = mlb_api("schedule", {"sportId":1,"date":game_date,"hydrate":"lineups,team"})
    out = {}
    for d in data.get("dates",[]):
        for g in d.get("games",[]):
            pk      = g.get("gamePk")
            lineups = g.get("lineups",{})
            out[pk] = {
                "away":[{"id":str(p.get("id","")),"name":p.get("fullName",""),"order":i+1}
                        for i,p in enumerate(lineups.get("awayPlayers",[]))],
                "home":[{"id":str(p.get("id","")),"name":p.get("fullName",""),"order":i+1}
                        for i,p in enumerate(lineups.get("homePlayers",[]))],
            }
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_roster(team_abv: str, season: int):
    data   = tank01_get("getMLBTeamRoster", {"teamAbv":team_abv,"season":str(season),"getStats":"true"})
    body   = data.get("body",{}) or {}
    roster = body.get("roster",[])
    rows   = []
    for p in roster:
        stats   = p.get("stats",{}) or {}
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
        iso = round(max(slg - avg, 0), 3)
        ops = round(obp + slg, 3)
        wrc = int((ops / 0.730) * 100) if ops > 0 else 100
        rows.append({
            "player_id":    str(p.get("playerID","")),
            "name":         p.get("longName", p.get("shortName","Unknown")),
            "pos":          p.get("pos",""),
            "avg":avg,"obp":obp,"slg":slg,"ops":ops,"iso":iso,"wrc_plus":wrc,
            "barrel_pct":   min(0.22, max(0.01, iso * 0.45)),
            "hard_hit_pct": min(0.60, max(0.15, (ops * 0.45) + (iso * 0.2))),
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
            return {f"{i.get('away_team')} @ {i.get('home_team')}": i.get("bookmakers",[]) for i in res}
        return {}
    except Exception:
        return {}

# â”€â”€ SCORING MODEL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def score_batter(avg, obp, slg, iso, wrc, hh, barrel, order,
                 era, whip, hr9, k9, env_mod):
    """
    Returns dict of market scores 0-100.

    Components:
      contact_score  = weighted combo of AVG, OBP, wRC+ (how often batter reaches)
      pitcher_vuln   = ERA + WHIP scaled 0-1 (higher = worse pitcher = better for batter)
      order_factor   = positional multiplier (leadoff 1.0 â†’ 9-hole 0.80)
      k_adj          = strikeout rate penalty (high K9 pitchers hurt contact scores)
      park_mod       = env_mod (park factor Ã— weather modifier)
    """
    order_factor = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,
                    6:0.90,7:0.87,8:0.84,9:0.80}.get(order, 0.80)
    # Pitcher vulnerability 0-1: league avg ERA ~4.20, WHIP ~1.30
    era_vuln  = min(era  / 6.5, 1.0)  # 6.5 = very bad ERA ceiling
    whip_vuln = min(max((whip - 0.85) / 1.30, 0.0), 1.0)
    pitcher_vuln = era_vuln * 0.60 + whip_vuln * 0.40

    # Strikeout adjustment â€” K9 above 9 starts penalising contact
    k_adj = 1.0 - min(max((k9 - 9.0) / 10.0, 0.0), 0.18)

    # --- Market scores ---
    # Hits + Runs: contact + OBP Ã— pitcher vulnerability Ã— order Ã— park
    contact = avg * 0.35 + obp * 0.30 + (wrc / 200.0) * 0.25 + 0.78 * 0.10
    hs = round(contact * pitcher_vuln * order_factor * k_adj * env_mod * 290, 2)

    # RBI: power + situational hitting Ã— pitcher vuln Ã— order (3-5 hitters favoured)
    rbi_order = max(0, 1.0 - abs(order - 4) * 0.06)
    power     = iso * 0.40 + hh * 0.35 + barrel * 0.25
    rs = round(power * pitcher_vuln * (0.70 + rbi_order * 0.30) * k_adj * env_mod * 270, 2)

    # Home Run: pure power Ã— HR/9 of pitcher Ã— park
    hr9_vuln = min(hr9 / 2.5, 1.0)
    hr = round(power * hr9_vuln * env_mod * 290, 2)

    # Runs Scor
