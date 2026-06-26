# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests as req
from datetime import date
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Prop & Game Analyser - Tank01", page_icon="baseball", layout="wide")

RAPIDAPI_KEY  = "46e23ff209mshb208e90af2f00d4p120983jsn38b0da2800d0"
TANK01_HOST   = "tank01-mlb-live-in-game-real-time-statistics.p.rapidapi.com"
TANK01_BASE   = f"https://{TANK01_HOST}"

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

def decimal_to_fractional(dec):
    if not dec or dec <= 1.0:
        return "N/A"
    if dec == 2.0:
        return "EVENS"
    frac = Fraction(dec - 1.0).limit_denominator(20)
    return f"{frac.numerator}/{frac.denominator}"

def tank01_get(endpoint, params=None):
    url = f"{TANK01_BASE}/{endpoint}"
    headers = {
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": TANK01_HOST,
    }
    for attempt in range(3):
        try:
            r = req.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                st.warning(f"Tank01 API error on /{endpoint}: {e}")
                return {}
            time.sleep(1.5)
    return {}

def safe_get(url, params=None):
    try:
        r = req.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_games_for_date(game_date: str):
    data = tank01_get("getMLBGamesForDate", {"gameDate": game_date})
    body = data.get("body", [])
    if isinstance(body, dict):
        body = list(body.values())
    rows = []
    for g in body:
        rows.append({
            "gameID":    g.get("gameID", ""),
            "away_team": g.get("away", ""),
            "home_team": g.get("home", ""),
            "game_time": g.get("gameTime", "TBD"),
            "venue":     g.get("ballpark", g.get("venue", "")),
            "status":    g.get("gameStatus", "Scheduled"),
            "away_abv":  g.get("awayTeam", g.get("away", "")),
            "home_abv":  g.get("homeTeam", g.get("home", "")),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_box_score(game_id: str):
    data = tank01_get("getMLBBoxScore", {"gameID": game_id})
    return data.get("body", {})

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_team_roster_raw(team_abv: str, season: int):
    """Returns raw API response for debugging."""
    return tank01_get("getMLBTeamRoster", {"teamAbv": team_abv, "season": str(season), "getStats": "true"})

def parse_roster(raw_data):
    body   = raw_data.get("body", {})
    roster = body.get("roster", [])
    rows   = []
    for p in roster:
        # Tank01 stats can be nested under "stats" or directly on the player object
        stats = p.get("stats", {}) or {}
        if not isinstance(stats, dict):
            stats = {}

        # Try both short and long stat key names
        ab      = float(stats.get("AB") or stats.get("atBats") or p.get("AB") or 1)
        hits    = float(stats.get("H")  or stats.get("hits")   or p.get("H")  or 0)
        bb      = float(stats.get("BB") or stats.get("walks")  or p.get("BB") or 0)
        hbp     = float(stats.get("HBP") or p.get("HBP") or 0)
        sf      = float(stats.get("SF")  or p.get("SF")  or 0)
        hr      = float(stats.get("HR")  or stats.get("homeRuns") or p.get("HR") or 0)
        doubles = float(stats.get("2B")  or stats.get("doubles")  or p.get("2B") or 0)
        triples = float(stats.get("3B")  or stats.get("triples")  or p.get("3B") or 0)

        # Try pre-computed avg/obp/slg directly from API first
        avg_direct = stats.get("avg") or stats.get("battingAvg") or p.get("avg") or p.get("battingAvg")
        obp_direct = stats.get("obp") or stats.get("onBasePct")  or p.get("obp") or p.get("onBasePct")
        slg_direct = stats.get("slg") or stats.get("slugPct")    or p.get("slg") or p.get("slugPct")

        pa  = ab + bb + hbp + sf
        avg = float(avg_direct) if avg_direct else (round(hits / ab, 3) if ab > 1 else 0.0)
        obp = float(obp_direct) if obp_direct else (round((hits + bb + hbp) / pa, 3) if pa > 1 else 0.0)
        tb  = hits + doubles + (2 * triples) + (3 * hr)
        slg = float(slg_direct) if slg_direct else (round(tb / ab, 3) if ab > 1 else 0.0)
        iso = round(slg - avg, 3)
        ops = round(obp + slg, 3)
        wrc_plus = int((ops / 0.730) * 100) if ops > 0 else 100

        rows.append({
            "player_id":    p.get("playerID", ""),
            "name":         p.get("longName", p.get("shortName", "Unknown")),
            "pos":          p.get("pos", ""),
            "avg":          avg,
            "obp":          obp,
            "slg":          slg,
            "ops":          ops,
            "iso":          iso,
            "wrc_plus":     wrc_plus,
            "barrel_pct":   min(0.22, max(0.01, iso * 0.45)),
            "hard_hit_pct": min(0.60, max(0.15, (ops * 0.45) + (iso * 0.2))),
            "ab":           int(ab),
            "hr":           int(hr),
        })
    return pd.DataFrame(rows)

def parse_lineup_from_boxscore(box, side="away"):
    rows = []
    batting_key = None
    for k in box.keys():
        if side.lower() in k.lower() and "batter" 
