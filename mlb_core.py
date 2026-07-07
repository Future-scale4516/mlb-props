import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time
import math, statistics
try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    _UTC = ZoneInfo("UTC")
except Exception:
    _ET = None
    _UTC = None

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
def fetch_results(target_date: str):
    """Final scores for completed games on a date (for backtesting). Free MLB data."""
    data = safe_get("https://statsapi.mlb.com/api/v1/schedule", {
        "sportId": 1, "date": target_date, "hydrate": "probablePitcher,team,linescore"})
    out = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("abstractGameState", "") != "Final":
                continue
            t = g.get("teams", {})
            hs = t.get("home", {}).get("score")
            as_ = t.get("away", {}).get("score")
            if hs is None or as_ is None:
                continue
            out.append({
                "gamePk": g.get("gamePk"),
                "home_team_id": t.get("home", {}).get("team", {}).get("id"),
                "away_team_id": t.get("away", {}).get("team", {}).get("id"),
                "home_prob_id": t.get("home", {}).get("probablePitcher", {}).get("id"),
                "away_prob_id": t.get("away", {}).get("probablePitcher", {}).get("id"),
                "home_score": int(hs), "away_score": int(as_)})
    return out

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
            "runs": int(stat.get("runs") or 0),
            "hits": int(stat.get("hits") or 0),
            "games":int(stat.get("gamesPlayed") or 0),
            "strikeOuts":       so,
            "baseOnBalls":      int(stat.get("baseOnBalls") or 0),
            "plateAppearances": pa,
            "k_pct":            round(so / pa, 4) if pa > 0 else 0.22,
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_savant_stats(season: int):
    """Advanced batting metrics from Baseball Savant (Statcast) via pybaseball.
    Savant serves CSV leaderboards reliably from cloud IPs, unlike the Fangraphs
    scrape which gets blocked on Streamlit Cloud. Keyed by MLBAM player_id."""
    st.session_state["savant_error"] = ""
    st.session_state["savant_debug"] = ""
    try:
        from pybaseball import (statcast_batter_exitvelo_barrels,
                                statcast_batter_expected_stats)

        ev = statcast_batter_exitvelo_barrels(season)   # Barrel%, HardHit%
        xs = statcast_batter_expected_stats(season)     # xwOBA, xSLG, xBA

        def pick(df, *cands):
            for c in cands:
                if c in df.columns:
                    return c
            return None

        # exit velocity / barrels leaderboard
        ev_id = pick(ev, "player_id")
        brl_c = pick(ev, "brl_percent", "barrel_batted_rate", "brl_pa")
        hh_c  = pick(ev, "ev95percent", "hard_hit_percent", "ev95per")
        ev_keep = ev[[c for c in [ev_id, brl_c, hh_c] if c]].rename(
            columns={ev_id: "player_id", brl_c: "barrel_pct", hh_c: "hard_hit_pct"})

        # expected stats leaderboard
        xs_id    = pick(xs, "player_id")
        xwoba_c  = pick(xs, "est_woba", "xwoba")
        xslg_c   = pick(xs, "est_slg", "xslg")
        xba_c    = pick(xs, "est_ba", "xba")
        xs_keep = xs[[c for c in [xs_id, xwoba_c, xslg_c, xba_c] if c]].rename(
            columns={xs_id: "player_id", xwoba_c: "xwoba", xslg_c: "xslg", xba_c: "xba"})

        df = pd.merge(xs_keep, ev_keep, on="player_id", how="outer")

        # percentages -> fractions, to match score_batter()'s scale
        for pct in ["barrel_pct", "hard_hit_pct"]:
            if pct in df.columns and df[pct].dropna().max() > 1:
                df[pct] = df[pct] / 100.0

        # wRC+ proxy from xwOBA (affine fit: league wOBA ~.320 -> 100). Tune later.
        LEAGUE_WOBA = 0.320
        if "xwoba" in df.columns:
            df["wrc_plus"] = (100 + (df["xwoba"] - LEAGUE_WOBA) * 712.5).round()

        df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")

        # optional baserunning (XBR proxy) via sprint speed -- non-fatal if missing
        try:
            from pybaseball import statcast_sprint_speed
            sp = statcast_sprint_speed(season, 10)
            sp_id = pick(sp, "player_id")
            sp_c  = pick(sp, "sprint_speed")
            if sp_id and sp_c:
                sp_keep = sp[[sp_id, sp_c]].rename(
                    columns={sp_id: "player_id", sp_c: "sprint_speed"})
                sp_keep["player_id"] = pd.to_numeric(sp_keep["player_id"], errors="coerce")
                df = pd.merge(df, sp_keep, on="player_id", how="left")
        except Exception as e:
            st.session_state["savant_debug"] += f" [sprint_speed skipped: {e}]"

        missing = [c for c in ["barrel_pct", "hard_hit_pct", "xwoba"] if c not in df.columns]
        if missing:
            st.session_state["savant_error"] = (
                f"Couldn't find columns {missing}. "
                f"exitvelo cols={list(ev.columns)} | expected cols={list(xs.columns)}")
        return df
    except Exception as e:
        st.session_state["savant_error"] = f"{type(e).__name__}: {e}"
        return pd.DataFrame()

def get_secret(name: str, default: str = "") -> str:
    """Read an API key from Streamlit secrets (Settings -> Secrets on the app
    dashboard), falling back to an environment variable, then a default.
    Never hard-code keys in the source."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    import os
    return os.environ.get(name, default)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_mlb_odds(regions: str = "us", markets: str = "h2h,spreads,totals",
                   odds_format: str = "decimal"):
    """Fetch MLB game odds from The Odds API.
    Returns (data, meta) where data is a list of game dicts and meta carries
    quota info + any error. Cached 15 min to protect the free-tier quota.
    h2h = moneyline, spreads = run line, totals = over/under.
    NB: spreads/totals for MLB live on US books, so regions='us' even from the UK;
    odds_format='decimal' still returns UK-style prices."""
    key = get_secret("ODDS_API_KEY")
    if not key:
        return [], {"error": "No ODDS_API_KEY found in Streamlit secrets."}
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    try:
        r = req.get(url, params={
            "apiKey": key, "regions": regions, "markets": markets,
            "oddsFormat": odds_format, "dateFormat": "iso",
        }, timeout=15)
    except Exception as e:
        return [], {"error": f"Request failed: {e}"}
    meta = {
        "status": r.status_code,
        "remaining": r.headers.get("x-requests-remaining"),
        "used": r.headers.get("x-requests-used"),
        "error": "",
    }
    if r.status_code != 200:
        meta["error"] = f"HTTP {r.status_code}: {r.text[:300]}"
        return [], meta
    try:
        data = r.json()
    except Exception as e:
        meta["error"] = f"Bad JSON: {e}"
        return [], meta
    return data, meta


LEAGUE_RPG_DEFAULT = 4.4    # league runs/game per team (fallback)
LEAGUE_ERA_DEFAULT = 4.10   # league ERA (fallback)
LEAGUE_BULLPEN_ERA_DEFAULT = 4.20  # league bullpen ERA (fallback)
SP_WEIGHT = 0.60            # share of a game credited to the starting pitcher


# Run / HR park factors (1.00 = neutral), keyed by MLB team_id of the HOME park.
# Approximate 2026 values; relative ordering matters most and these are easy to tune.
PARK_FACTORS = {
    108: {"run": 0.99, "hr": 1.01},  # LAA  Angel Stadium
    109: {"run": 1.03, "hr": 1.02},  # ARI  Chase Field
    110: {"run": 1.01, "hr": 1.04},  # BAL  Camden Yards
    111: {"run": 1.06, "hr": 0.99},  # BOS  Fenway Park
    112: {"run": 1.01, "hr": 1.01},  # CHC  Wrigley Field
    113: {"run": 1.08, "hr": 1.12},  # CIN  Great American Ball Park
    114: {"run": 0.99, "hr": 1.01},  # CLE  Progressive Field
    115: {"run": 1.14, "hr": 1.12},  # COL  Coors Field
    116: {"run": 0.96, "hr": 0.93},  # DET  Comerica Park
    117: {"run": 1.01, "hr": 1.03},  # HOU  Daikin Park
    118: {"run": 0.99, "hr": 0.96},  # KC   Kauffman Stadium
    119: {"run": 1.01, "hr": 1.04},  # LAD  Dodger Stadium
    120: {"run": 1.00, "hr": 1.01},  # WSH  Nationals Park
    121: {"run": 0.97, "hr": 0.95},  # NYM  Citi Field
    133: {"run": 1.02, "hr": 1.08},  # ATH  Sutter Health Park (Sacramento)
    134: {"run": 0.97, "hr": 0.92},  # PIT  PNC Park
    135: {"run": 0.95, "hr": 0.96},  # SD   Petco Park
    136: {"run": 0.94, "hr": 0.93},  # SEA  T-Mobile Park
    137: {"run": 0.92, "hr": 0.89},  # SF   Oracle Park
    138: {"run": 0.98, "hr": 0.96},  # STL  Busch Stadium
    139: {"run": 0.96, "hr": 0.95},  # TB   Tropicana Field
    140: {"run": 1.01, "hr": 1.02},  # TEX  Globe Life Field
    141: {"run": 1.02, "hr": 1.03},  # TOR  Rogers Centre
    142: {"run": 1.00, "hr": 1.00},  # MIN  Target Field
    143: {"run": 1.03, "hr": 1.06},  # PHI  Citizens Bank Park
    144: {"run": 0.99, "hr": 1.01},  # ATL  Truist Park
    145: {"run": 1.01, "hr": 1.05},  # CWS  Rate Field
    146: {"run": 0.95, "hr": 0.93},  # MIA  loanDepot Park
    147: {"run": 1.02, "hr": 1.08},  # NYY  Yankee Stadium
    158: {"run": 1.02, "hr": 1.03},  # MIL  American Family Field
}

NEUTRAL_PARK = {"run": 1.0, "hr": 1.0}

TEAM_ABBR = {108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN",
             114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KC", 119: "LAD",
             120: "WSH", 121: "NYM", 133: "ATH", 134: "PIT", 135: "SD", 136: "SEA",
             137: "SF", 138: "STL", 139: "TB", 140: "TEX", 141: "TOR", 142: "MIN",
             143: "PHI", 144: "ATL", 145: "CWS", 146: "MIA", 147: "NYY", 158: "MIL"}


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_team_offense(season: int):
    """Team runs/game from the MLB Stats API. Returns (dict{team_id: rpg}, league_rpg)."""
    data = safe_get("https://statsapi.mlb.com/api/v1/teams/stats", {
        "stats": "season", "group": "hitting", "season": season, "sportIds": 1,
    })
    out = {}
    splits = data.get("stats", [{}])[0].get("splits", []) if data.get("stats") else []
    for sp in splits:
        t = sp.get("team", {}); stat = sp.get("stat", {})
        tid = int(t.get("id", 0) or 0)
        g = float(stat.get("gamesPlayed") or 0); runs = float(stat.get("runs") or 0)
        if tid and g > 0:
            out[tid] = runs / g
    league = (sum(out.values()) / len(out)) if out else LEAGUE_RPG_DEFAULT
    return out, league


def _ip_to_outs(ip_value):
    """Convert MLB's innings-pitched notation (e.g. '63.1' = 63 innings + 1 out,
    '63.2' = 63 innings + 2 outs) into a plain out count."""
    try:
        s = str(ip_value)
        if "." in s:
            whole, frac = s.split(".")
            return int(whole) * 3 + int(frac)
        return int(float(s)) * 3
    except Exception:
        return 0


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_bullpen_era(season: int):
    """Team bullpen ERA from the MLB Stats API, computed properly from aggregated
    earned runs and innings across all pitchers with zero starts that season (true
    relievers) — not an average of individual ERAs, which would be skewed by
    small-sample call-ups. Returns dict{team_id: bullpen_era}."""
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {
        "stats": "season", "group": "pitching", "season": season,
        "sportId": 1, "playerPool": "ALL", "limit": 3000,
    })
    agg = {}
    for split in data.get("stats", [{}])[0].get("splits", []):
        stat = split.get("stat", {})
        if int(stat.get("gamesStarted") or 0) > 0:
            continue  # only true relievers — anyone who started a game is excluded
        t = split.get("team", {})
        tid = int(t.get("id", 0) or 0)
        if not tid:
            continue
        er = int(stat.get("earnedRuns") or 0)
        outs = _ip_to_outs(stat.get("inningsPitched") or "0.0")
        if tid not in agg:
            agg[tid] = [0, 0]
        agg[tid][0] += er
        agg[tid][1] += outs
    out = {}
    for tid, (er, outs) in agg.items():
        if outs > 0:
            out[tid] = round(er / (outs / 3) * 9, 2)
    return out


def _pois_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _pois_vector(lam, max_runs=18):
    v = [_pois_pmf(k, lam) for k in range(max_runs + 1)]
    s = sum(v)
    return [x / s for x in v] if s else v


def expected_runs(team_rpg, opp_era, league_rpg, league_era, park=1.0,
                   opp_bullpen_era=None):
    """opp_bullpen_era replaces the flat league-average filler in the pitching
    blend with the actual opposing bullpen's quality — the starter covers ~60% of
    a game (SP_WEIGHT), the bullpen covers the rest, and previously that remaining
    40% was just assumed to be league-average pitching regardless of the real
    opponent. Falls back to league_era if bullpen data isn't available."""
    off_idx = (team_rpg / league_rpg) if league_rpg > 0 else 1.0
    fill_era = opp_bullpen_era if opp_bullpen_era is not None else league_era
    blended_era = SP_WEIGHT * opp_era + (1 - SP_WEIGHT) * fill_era
    pitch_idx = (blended_era / league_era) if league_era > 0 else 1.0
    return max(0.5, min(league_rpg * off_idx * pitch_idx * park, 12.0))


def _park_neutral_rpg(rpg, own_park_run):
    """Remove a team's own home-park effect from its season runs/game (~half of a
    team's games are at its own park), so the game's park factor can be applied once
    without double-counting the home team's park."""
    blend = (own_park_run + 1.0) / 2.0
    return rpg / blend if blend else rpg


def model_game(home_rpg, away_rpg, home_opp_era, away_opp_era,
               league_rpg, league_era, total_line, park=1.0,
               home_opp_bullpen_era=None, away_opp_bullpen_era=None):
    """home_opp_era = ERA of the pitcher the HOME team faces (the away starter).
    home_opp_bullpen_era = bullpen ERA of the team the HOME team faces (away bullpen)."""
    lam_home = expected_runs(home_rpg, home_opp_era, league_rpg, league_era, park,
                             opp_bullpen_era=home_opp_bullpen_era)
    lam_away = expected_runs(away_rpg, away_opp_era, league_rpg, league_era, park,
                             opp_bullpen_era=away_opp_bullpen_era)
    ph = _pois_vector(lam_home); pa = _pois_vector(lam_away)
    p_hw = p_aw = p_tie = p_hc = p_ac = 0.0
    for h in range(len(ph)):
        for a in range(len(pa)):
            p = ph[h] * pa[a]
            if h > a: p_hw += p
            elif a > h: p_aw += p
            else: p_tie += p
            if h - a >= 2: p_hc += p
            else: p_ac += p
    lam_tot = lam_home + lam_away
    pt = _pois_vector(lam_tot, max_runs=30)
    p_over = p_under = p_push = 0.0
    if total_line is not None:
        line = float(total_line)
        for t in range(len(pt)):
            if t > line: p_over += pt[t]
            elif t < line: p_under += pt[t]
            else: p_push += pt[t]
    return {"lam_home": lam_home, "lam_away": lam_away, "lam_total": lam_tot,
            "p_home_ml": p_hw + p_tie / 2, "p_away_ml": p_aw + p_tie / 2,
            "p_home_cover": p_hc, "p_away_cover": p_ac,
            "p_over": p_over, "p_under": p_under, "p_push": p_push}


def _median(xs):
    xs = [x for x in xs if x]
    return statistics.median(xs) if xs else None


def consolidate_odds(game, home, away):
    """Consensus (median) decimal odds + best available price per outcome."""
    ml_home, ml_away, rl_home, rl_away = [], [], [], []
    tot_by_line = {}
    for bk in game.get("bookmakers", []):
        for m in bk.get("markets", []):
            key = m.get("key")
            for o in m.get("outcomes", []):
                name, price, point = o.get("name"), o.get("price"), o.get("point")
                if key == "h2h":
                    if name == home: ml_home.append(price)
                    elif name == away: ml_away.append(price)
                elif key == "spreads":
                    if name == home: rl_home.append(price)
                    elif name == away: rl_away.append(price)
                elif key == "totals":
                    if point is None: continue
                    slot = tot_by_line.setdefault(point, {"over": [], "under": []})
                    if name and name.lower() == "over": slot["over"].append(price)
                    elif name and name.lower() == "under": slot["under"].append(price)
    best_line, best_count = None, -1
    for pt, d in tot_by_line.items():
        c = min(len(d["over"]), len(d["under"]))
        if c > best_count and c > 0:
            best_count, best_line = c, pt
    res = {"ml_home": _median(ml_home), "ml_away": _median(ml_away),
           "ml_home_best": max(ml_home) if ml_home else None,
           "ml_away_best": max(ml_away) if ml_away else None,
           "rl_home": _median(rl_home), "rl_away": _median(rl_away),
           "rl_home_best": max(rl_home) if rl_home else None,
           "rl_away_best": max(rl_away) if rl_away else None,
           "total_line": best_line, "over": None, "under": None,
           "over_best": None, "under_best": None}
    if best_line is not None:
        d = tot_by_line[best_line]
        res["over"], res["under"] = _median(d["over"]), _median(d["under"])
        res["over_best"] = max(d["over"]) if d["over"] else None
        res["under_best"] = max(d["under"]) if d["under"] else None
    return res


def devig_two(odds_a, odds_b):
    if not odds_a or not odds_b: return None, None
    ia, ib = 1 / odds_a, 1 / odds_b
    s = ia + ib
    return (ia / s, ib / s) if s > 0 else (None, None)


def edge_ev(model_p, fair_p, best_odds):
    edge = (model_p - fair_p) * 100 if (model_p is not None and fair_p is not None) else None
    ev = (model_p * best_odds - 1) * 100 if (model_p is not None and best_odds) else None
    return edge, ev


def _edge_light(edge):
    """Traffic-light banding for an edge (percentage points).
    grey <2 (no signal) · green 2-8 (value zone) · amber 8-15 (suspect) ·
    red 15+ (almost certainly a missing model input, not real value)."""
    if edge is None:
        return ""
    if edge >= 15:
        return "🔴"
    if edge >= 8:
        return "🟡"
    if edge >= 2:
        return "🟢"
    return "⚪"


def _commence_to_bst(iso):
    """Convert The Odds API commence_time (ISO UTC) to a BST HH:MM string
    (BST = UTC+1 during the MLB season)."""
    try:
        dt = datetime.strptime(iso.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        return (dt + timedelta(hours=1)).strftime("%H:%M")
    except Exception:
        return ""


def _commence_to_et_date(iso):
    """Return the game's calendar date in US Eastern (MLB's operational timezone).
    Used to filter games to the selected slate — a 10pm ET game is a 3am BST game
    the next morning, and it belongs to the US date, not the UK date."""
    if not iso or _ET is None:
        return None
    try:
        dt = datetime.strptime(iso.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=_UTC).astimezone(_ET).date()
    except Exception:
        return None


def _commence_to_et_str(iso):
    """US-Eastern display date, e.g. 'Mon Jun 30'."""
    d = _commence_to_et_date(iso)
    return d.strftime("%a %b %d") if d else ""


def _ml_rl_reason(team_rpg, opp_rpg, team_era, opp_era, opp_bullpen_era=None,
                   league_rpg=LEAGUE_RPG_DEFAULT, league_era=LEAGUE_ERA_DEFAULT,
                   league_bullpen_era=LEAGUE_BULLPEN_ERA_DEFAULT):
    """Short, honest explanation for a Moneyline/Run line pick, using the same
    inputs the model actually used: park-neutral team offense, both starters'
    ERA, and the opposing bullpen's ERA. Mirrors the style of _prop_reason."""
    bits = []
    if team_rpg - opp_rpg >= 0.5:
        bits.append(f"stronger offense ({team_rpg:.1f} vs {opp_rpg:.1f} RPG)")
    if team_era <= league_era - 0.4:
        bits.append(f"quality starter (ERA {team_era:.2f})")
    if opp_era >= league_era + 0.4:
        bits.append(f"opposing starter has struggled (ERA {opp_era:.2f})")
    if opp_bullpen_era is not None and opp_bullpen_era >= league_bullpen_era + 0.4:
        bits.append(f"opposing bullpen is shaky (ERA {opp_bullpen_era:.2f})")
    if not bits:
        return "Edge from market pricing, not a standout matchup"
    joined = "; ".join(bits[:3])
    return joined[:1].upper() + joined[1:]


def _total_reason(home_rpg, away_rpg, home_era, away_era, park, side,
                   home_bullpen_era=None, away_bullpen_era=None,
                   league_rpg=LEAGUE_RPG_DEFAULT, league_era=LEAGUE_ERA_DEFAULT,
                   league_bullpen_era=LEAGUE_BULLPEN_ERA_DEFAULT):
    """Short, honest explanation for a Totals (Over/Under) pick."""
    combined = home_rpg + away_rpg
    league_combined = league_rpg * 2
    bp_avg = None
    if home_bullpen_era is not None and away_bullpen_era is not None:
        bp_avg = (home_bullpen_era + away_bullpen_era) / 2
    bits = []
    if side == "Over":
        if combined - league_combined >= 0.8:
            bits.append(f"both offenses hot ({combined:.1f} combined RPG)")
        if home_era >= league_era + 0.4 or away_era >= league_era + 0.4:
            bits.append("a shaky starter in this game")
        if bp_avg is not None and bp_avg >= league_bullpen_era + 0.4:
            bits.append("both bullpens shaky")
        if park.get("run", 1.0) >= 1.05:
            bits.append("hitter-friendly park")
    else:
        if league_combined - combined >= 0.8:
            bits.append(f"quiet bats on both sides ({combined:.1f} combined RPG)")
        if home_era <= league_era - 0.4 and away_era <= league_era - 0.4:
            bits.append("two quality starters")
        if bp_avg is not None and bp_avg <= league_bullpen_era - 0.4:
            bits.append("both bullpens strong")
        if park.get("run", 1.0) <= 0.95:
            bits.append("pitcher-friendly park")
    if not bits:
        return "Edge from market pricing, not a standout matchup"
    joined = "; ".join(bits[:3])
    return joined[:1].upper() + joined[1:]


def build_game_edges(sel_date):
    """Match today's games to UK odds, run the model, return (df, note, meta)."""
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, "No games scheduled for this date.", {}
    team_off, league_rpg = fetch_team_offense(sel_date.year)
    bullpen_era = fetch_bullpen_era(sel_date.year)
    odds_data, meta = fetch_mlb_odds(regions="uk")
    if meta.get("error"):
        return None, meta["error"], meta
    if not odds_data:
        return None, "No UK odds returned (markets may not be up yet).", meta

    # Filter odds to the selected US-Eastern date. The Odds API returns all upcoming
    # games (including the next day's), and MLB series often have the same team pair
    # on consecutive days — so without this filter, the (home, away) index below can
    # pick up the wrong day's odds and show them on today's slate.
    if _ET is not None:
        before = len(odds_data)
        odds_data = [g for g in odds_data
                     if _commence_to_et_date(g.get("commence_time")) == sel_date]
        dropped = before - len(odds_data)
        if dropped:
            meta["dropped_wrong_day"] = dropped

    def norm(s): return (s or "").lower().strip()
    odds_index = {(norm(g.get("home_team")), norm(g.get("away_team"))): g for g in odds_data}

    rows, unmatched, game_time = [], [], {}
    for _, gm in sched.iterrows():
        home, away = gm.get("home_team"), gm.get("away_team")
        og = odds_index.get((norm(home), norm(away)))
        if not og:
            hk = norm(home).split()[-1] if norm(home).split() else ""
            ak = norm(away).split()[-1] if norm(away).split() else ""
            for (oh, oa), cand in odds_index.items():
                if hk and ak and oh.endswith(hk) and oa.endswith(ak):
                    og = cand; break
        if not og:
            unmatched.append(f"{away} @ {home}"); continue

        hid = int(gm.get("home_team_id") or 0)
        aid = int(gm.get("away_team_id") or 0)
        pf = PARK_FACTORS.get(hid, NEUTRAL_PARK)
        home_rpg = _park_neutral_rpg(team_off.get(hid, league_rpg), pf["run"])
        away_rpg = _park_neutral_rpg(team_off.get(aid, league_rpg),
                                     PARK_FACTORS.get(aid, NEUTRAL_PARK)["run"])
        away_sp = fetch_pitcher_stats(gm.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(gm.get("home_prob_id"))
        away_bp = bullpen_era.get(aid, LEAGUE_BULLPEN_ERA_DEFAULT)
        home_bp = bullpen_era.get(hid, LEAGUE_BULLPEN_ERA_DEFAULT)
        cons = consolidate_odds(og, og.get("home_team"), og.get("away_team"))
        mdl = model_game(home_rpg, away_rpg, away_sp.get("era", 4.5),
                         home_sp.get("era", 4.5), league_rpg, LEAGUE_ERA_DEFAULT,
                         cons.get("total_line"), park=pf["run"],
                         home_opp_bullpen_era=away_bp, away_opp_bullpen_era=home_bp)
        gl = f"{TEAM_ABBR.get(aid, away)} @ {TEAM_ABBR.get(hid, home)}"
        ct = og.get("commence_time") or ""
        game_time[gl] = (ct, _commence_to_bst(ct), _commence_to_et_str(ct))

        home_era = home_sp.get("era", 4.5)
        away_era = away_sp.get("era", 4.5)
        fh, fa = devig_two(cons["ml_home"], cons["ml_away"])
        if fh is not None:
            e, v = edge_ev(mdl["p_home_ml"], fh, cons["ml_home_best"])
            rows.append([gl, "Moneyline", home, mdl["p_home_ml"], fh, e, cons["ml_home_best"], v,
                         _ml_rl_reason(home_rpg, away_rpg, home_era, away_era, away_bp)])
            e, v = edge_ev(mdl["p_away_ml"], fa, cons["ml_away_best"])
            rows.append([gl, "Moneyline", away, mdl["p_away_ml"], fa, e, cons["ml_away_best"], v,
                         _ml_rl_reason(away_rpg, home_rpg, away_era, home_era, home_bp)])
        frh, fra = devig_two(cons["rl_home"], cons["rl_away"])
        if frh is not None:
            e, v = edge_ev(mdl["p_home_cover"], frh, cons["rl_home_best"])
            rows.append([gl, "Run line", f"{home} -1.5", mdl["p_home_cover"], frh, e, cons["rl_home_best"], v,
                         _ml_rl_reason(home_rpg, away_rpg, home_era, away_era, away_bp)])
            e, v = edge_ev(mdl["p_away_cover"], fra, cons["rl_away_best"])
            rows.append([gl, "Run line", f"{away} +1.5", mdl["p_away_cover"], fra, e, cons["rl_away_best"], v,
                         _ml_rl_reason(away_rpg, home_rpg, away_era, home_era, home_bp)])
        fo, fu = devig_two(cons["over"], cons["under"])
        if fo is not None and cons["total_line"] is not None:
            ln = cons["total_line"]
            e, v = edge_ev(mdl["p_over"], fo, cons["over_best"])
            rows.append([gl, "Total", f"Over {ln}", mdl["p_over"], fo, e, cons["over_best"], v,
                         _total_reason(home_rpg, away_rpg, home_era, away_era, pf, "Over",
                                       home_bp, away_bp)])
            e, v = edge_ev(mdl["p_under"], fu, cons["under_best"])
            rows.append([gl, "Total", f"Under {ln}", mdl["p_under"], fu, e, cons["under_best"], v,
                         _total_reason(home_rpg, away_rpg, home_era, away_era, pf, "Under",
                                       home_bp, away_bp)])

    if not rows:
        return None, "No matched games with usable odds.", meta
    df = pd.DataFrame(rows, columns=["Game", "Market", "Selection",
                                     "Model %", "Fair %", "Edge", "Odds", "EV %", "Reason"])
    df["Model %"] = (df["Model %"] * 100).round(1)
    df["Fair %"] = (df["Fair %"] * 100).round(1)
    df["Edge"] = df["Edge"].round(1)
    df["EV %"] = df["EV %"].round(1)
    df["_ct"] = df["Game"].map(lambda g: game_time.get(g, ("", "", ""))[0])
    df["Start"] = df["Game"].map(lambda g: game_time.get(g, ("", "", ""))[1])
    df["US Date"] = df["Game"].map(lambda g: game_time.get(g, ("", "", ""))[2])
    df = df.sort_values(["_ct", "Game"]).reset_index(drop=True)
    note = (f"Couldn't match odds for: {', '.join(unmatched)}" if unmatched else "")
    return df, note, meta


LG_HR9 = 1.15   # league avg HR allowed per 9 innings
LG_K9 = 8.5     # league avg K per 9 innings
LG_WHIP = 1.30  # league avg walks+hits per inning pitched
LG_OBP_DEFAULT = 0.320  # league avg on-base %, used for "table setters ahead" context
LG_SLG_DEFAULT = 0.400  # league avg slugging, used for "run producers behind" context


def _p_over_line(expected_count, point):
    """P(count > point) via Poisson(expected_count). point like 0.5 / 1.5 / 2.5."""
    if point is None or expected_count is None:
        return None
    need = int(math.floor(point)) + 1
    cum = sum(_pois_pmf(i, expected_count) for i in range(need))
    return max(0.0, min(1.0, 1.0 - cum))


def expected_pa(order):
    table = {1: 4.6, 2: 4.5, 3: 4.4, 4: 4.3, 5: 4.2, 6: 4.0, 7: 3.9, 8: 3.8, 9: 3.7}
    try:
        return table.get(int(order), 4.1)
    except Exception:
        return 4.1


def _lineup_context(order, slot_to_pid, stat_by_id):
    """Estimate the lineup context around a batter: the on-base ability of the
    table-setters hitting AHEAD of him (drives his RBI chances — someone has to be
    on base for him to drive in) and the power of the hitters BEHIND him (drives his
    run-scoring chances — someone has to drive him in once he's on). Uses the 3
    nearest hitters in each direction, weighted toward the closest slot, and wraps
    around the 9-spot order. Falls back to league averages when lineup data is
    missing, so this degrades gracefully rather than failing."""
    if not slot_to_pid:
        return LG_OBP_DEFAULT, LG_SLG_DEFAULT
    weights = [0.5, 0.3, 0.2]

    def slot(o):
        return ((o - 1) % 9) + 1

    ahead_vals, ahead_w = [], []
    for i, w in enumerate(weights, start=1):
        pid = slot_to_pid.get(slot(order - i))
        srow = stat_by_id.get(pid) if pid else None
        if srow:
            ahead_vals.append(srow.get("obp") or LG_OBP_DEFAULT)
            ahead_w.append(w)
    ahead_obp = (sum(v * w for v, w in zip(ahead_vals, ahead_w)) / sum(ahead_w)
                 if ahead_w else LG_OBP_DEFAULT)

    behind_vals, behind_w = [], []
    for i, w in enumerate(weights, start=1):
        pid = slot_to_pid.get(slot(order + i))
        srow = stat_by_id.get(pid) if pid else None
        if srow:
            behind_vals.append(srow.get("slg") or LG_SLG_DEFAULT)
            behind_w.append(w)
    behind_slg = (sum(v * w for v, w in zip(behind_vals, behind_w)) / sum(behind_w)
                  if behind_w else LG_SLG_DEFAULT)

    return ahead_obp, behind_slg


def _calibration_adjust(raw_p, market):
    """Apply an empirical calibration correction to raw model probabilities for
    markets where the backtest showed systematic overconfidence. Built from the
    actual backtest data: RBI consistently over-predicts by a growing margin as
    confidence rises (e.g. model says 55% → reality ~40%, model says 65% → reality ~47%).
    Runs shows a similar but milder pattern. Hits and HR are already well-calibrated
    and pass through unchanged.

    The correction uses a simple linear shrinkage toward the base rate, with the
    shrinkage fraction set per-market based on observed backtest gaps. This is
    intentionally conservative — it pulls overconfident predictions partway back
    rather than trying to perfectly remap every decile, which would overfit to a
    specific backtest window."""
    if market == "RBI":
        # RBI backtest showed ~30% overconfidence in the 40-70% bands.
        # Shrink toward the base rate (0.28) by 30%.
        base = 0.28
        shrink = 0.30
        return raw_p * (1 - shrink) + base * shrink
    elif market == "Runs":
        # Runs showed ~15-20% overconfidence in the upper bands.
        # Lighter shrinkage toward base rate (0.36).
        base = 0.36
        shrink = 0.18
        return raw_p * (1 - shrink) + base * shrink
    return raw_p


def _combo_prob(probs):
    """P(at least one of hits/runs/RBI >= 1), treating them as approximately
    independent. Returns None if any input is missing."""
    p_h = probs.get("batter_hits")
    p_r = probs.get("batter_runs_scored")
    p_rbi = probs.get("batter_rbis")
    if p_h is None or p_r is None or p_rbi is None:
        return None
    return min(1 - (1 - p_h) * (1 - p_r) * (1 - p_rbi), 0.999)


def prop_expected_counts(stat, pa, opp_hr9=LG_HR9, opp_k9=LG_K9, opp_whip=LG_WHIP,
                          ahead_obp=LG_OBP_DEFAULT, behind_slg=LG_SLG_DEFAULT,
                          park_hr=1.0, park_run=1.0):
    """Expected per-game counts (Poisson lambdas) for each batter prop market.
    Season rate carries the hitter's talent; pitcher + park + lineup are the
    adjustments. HR uses the opposing starter's HR9, Hits uses their K9. RBI uses
    the pitcher's WHIP (baserunners allowed) AND the OBP of the batters hitting
    ahead of him (real traffic on base for him to drive in — the pitcher's WHIP
    alone doesn't say whether THIS batter's teammates are the ones reaching).
    Runs uses WHIP plus the SLG of the batters hitting behind him (someone has to
    drive him in once he's on base)."""
    spa = max(stat.get("plateAppearances", 1) or 1, 1)
    hr_l = (stat.get("hr", 0) / spa) * (opp_hr9 / LG_HR9) * park_hr * pa
    hits = stat.get("hits")
    hit_rate = (hits / spa) if hits is not None else stat.get("avg", 0) * 0.88
    k_factor = 1.0 - 0.5 * min(max((opp_k9 - LG_K9) / LG_K9, -0.3), 0.3)
    hit_l = hit_rate * k_factor * (1.0 + 0.5 * (park_run - 1.0)) * pa

    whip_factor = 1.0 + 0.5 * min(max((opp_whip - LG_WHIP) / LG_WHIP, -0.3), 0.3)
    traffic_factor = 1.0 + 0.6 * min(max((ahead_obp - LG_OBP_DEFAULT) / LG_OBP_DEFAULT, -0.4), 0.4)
    rbi_l = (stat.get("rbi", 0) / spa) * (0.6 + 0.4 * park_run) * whip_factor * traffic_factor * pa

    support_factor = 1.0 + 0.5 * min(max((behind_slg - LG_SLG_DEFAULT) / LG_SLG_DEFAULT, -0.4), 0.4)
    run_l = (stat.get("runs", 0) / spa) * (0.6 + 0.4 * park_run) * whip_factor * support_factor * pa

    return {"batter_home_runs": hr_l, "batter_hits": hit_l,
            "batter_rbis": rbi_l, "batter_runs_scored": run_l}


def consolidate_prop(event, market_key):
    """Per-player consolidated odds for one prop market in one event."""
    by_player = {}
    for bk in event.get("bookmakers", []):
        for m in bk.get("markets", []):
            if m.get("key") != market_key:
                continue
            for o in m.get("outcomes", []):
                player = o.get("description"); side = (o.get("name") or "").lower()
                point = o.get("point"); price = o.get("price")
                if not player or price is None:
                    continue
                slot = by_player.setdefault(player, {}).setdefault(
                    point, {"over": [], "under": []})
                if side == "over": slot["over"].append(price)
                elif side == "under": slot["under"].append(price)
    out = {}
    for player, lines in by_player.items():
        best_pt, best_c = None, -1
        for pt, s in lines.items():
            c = min(len(s["over"]), len(s["under"]))
            if c > best_c and c > 0:
                best_c, best_pt = c, pt
        if best_pt is None:
            for pt, s in lines.items():
                if len(s["over"]) > best_c:
                    best_c, best_pt = len(s["over"]), pt
        if best_pt is None:
            continue
        s = lines[best_pt]
        out[player] = {"point": best_pt, "over": _median(s["over"]),
                       "under": _median(s["under"]) if s["under"] else None,
                       "over_best": max(s["over"]) if s["over"] else None,
                       "under_best": max(s["under"]) if s["under"] else None}
    return out


def market_prob(over_odds, under_odds):
    """Fair P(over): de-vig if both sides quoted, else raw 1/over (vig included)."""
    if over_odds and under_odds:
        fo, _ = devig_two(over_odds, under_odds)
        return fo, "de-vig"
    if over_odds:
        return min(1 / over_odds, 0.999), "raw"
    return None, None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_event_props(event_id, markets, regions="us", odds_format="decimal"):
    """Event-odds endpoint: player props for a single game (costs 1 credit per market)."""
    key = get_secret("ODDS_API_KEY")
    if not key:
        return None, {"error": "No ODDS_API_KEY in Streamlit secrets."}
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{event_id}/odds"
    try:
        r = req.get(url, params={"apiKey": key, "regions": regions, "markets": markets,
                                 "oddsFormat": odds_format, "dateFormat": "iso"}, timeout=20)
    except Exception as e:
        return None, {"error": f"Request failed: {e}"}
    meta = {"status": r.status_code, "remaining": r.headers.get("x-requests-remaining"),
            "used": r.headers.get("x-requests-used"), "last": r.headers.get("x-requests-last"),
            "error": ""}
    if r.status_code != 200:
        meta["error"] = f"HTTP {r.status_code}: {r.text[:300]}"
        return None, meta
    try:
        return r.json(), meta
    except Exception as e:
        meta["error"] = f"Bad JSON: {e}"
        return None, meta


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_event_market_keys(event_id, regions="us"):
    """Cheap (1-credit) check of which markets a game has, to confirm prop access."""
    key = get_secret("ODDS_API_KEY")
    if not key:
        return [], {"error": "No ODDS_API_KEY in Streamlit secrets."}
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{event_id}/markets"
    try:
        r = req.get(url, params={"apiKey": key, "regions": regions}, timeout=15)
    except Exception as e:
        return [], {"error": f"Request failed: {e}"}
    meta = {"remaining": r.headers.get("x-requests-remaining"),
            "used": r.headers.get("x-requests-used"), "error": ""}
    if r.status_code != 200:
        meta["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        return [], meta
    try:
        body = r.json()
    except Exception as e:
        meta["error"] = f"Bad JSON: {e}"
        return [], meta
    games = [body] if isinstance(body, dict) else body
    keys = set()
    for g in games:
        for bk in g.get("bookmakers", []):
            for m in bk.get("markets", []):
                keys.add(m.get("key"))
    return sorted(keys), meta


def _prop_reason(mkey, srow, opp_hr9, opp_k9, park, order, ahead_obp=LG_OBP_DEFAULT,
                  behind_slg=LG_SLG_DEFAULT):
    """Short, honest explanation of what is pushing a prop edge into the green/amber."""
    spa = max(srow.get("plateAppearances", 1) or 1, 1)
    bits = []
    if mkey == "batter_home_runs":
        if srow.get("hr", 0) / spa >= 0.045:
            bits.append(f"strong power ({srow.get('hr', 0)} HR)")
        if opp_hr9 >= 1.4:
            bits.append(f"HR-prone starter ({opp_hr9:.1f} HR/9)")
        if park["hr"] >= 1.05:
            bits.append("hitter-friendly park")
    elif mkey == "batter_hits":
        if srow.get("avg", 0) >= 0.285:
            bits.append(f"high contact (.{int(round(srow.get('avg', 0) * 1000)):03d} AVG)")
        if opp_k9 <= 7.5:
            bits.append(f"low-strikeout starter ({opp_k9:.1f} K/9)")
        if park["run"] >= 1.05:
            bits.append("hitter-friendly park")
    elif mkey == "batter_rbis":
        if ahead_obp >= 0.345:
            bits.append(f"good table-setters ahead (.{int(round(ahead_obp*1000)):03d} OBP)")
        if order and order <= 5:
            bits.append(f"bats #{order} (more chances)")
        rate = srow.get("rbi", 0) / spa
        if rate >= 0.13:
            bits.append("high rate for this market")
        if park["run"] >= 1.05:
            bits.append("hitter-friendly park")
    else:  # runs scored
        if behind_slg >= 0.430:
            bits.append(f"power hitters behind (.{int(round(behind_slg*1000)):03d} SLG)")
        if order and order <= 5:
            bits.append(f"bats #{order} (more chances)")
        rate = srow.get("runs", 0) / spa
        if rate >= 0.13:
            bits.append("high rate for this market")
        if park["run"] >= 1.05:
            bits.append("hitter-friendly park")
    if not bits:
        return "Edge from market pricing, not a standout matchup"
    return ("; ".join(bits[:3]))[:1].upper() + ("; ".join(bits[:3]))[1:]


def build_prop_edges(sel_date, max_games=6):
    """Full slate prop edges: per-game props adjusted for the opposing starter and
    ballpark. Returns (df, meta, note). Green+amber only (edge 2-15) is filtered in UI."""
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, {}, "No games scheduled for this date."
    odds_games, meta = fetch_mlb_odds(regions="uk")
    if not odds_games:
        if meta.get("error"):
            return None, meta, f"Odds request failed: {meta['error']}"
        return None, meta, ("No odds posted yet for today's games (this can happen "
                            "earlier in the day before US books line up — try again "
                            "closer to first pitch).")
    bat = fetch_all_mlb_batting_stats(sel_date.year)
    if bat.empty:
        return None, meta, "No batter stats available."
    name_map = {str(n).lower(): row for n, row in zip(bat["name"], bat.to_dict("records"))}
    stat_by_id = {int(r["player_id"]): r for r in bat.to_dict("records") if r.get("player_id")}

    def norm(s): return (s or "").lower().strip()
    sched_index = {(norm(gm.get("home_team")), norm(gm.get("away_team"))): gm
                   for _, gm in sched.iterrows()}

    PROP_MARKETS = "batter_home_runs,batter_hits,batter_rbis,batter_runs_scored"
    LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
             "batter_rbis": "RBI", "batter_runs_scored": "Runs"}
    cols = ["Market", "Light", "Player", "Game", "Start", "Line",
            "Model %", "Market %", "Edge", "Best over", "Reason"]
    rows, unmatched = [], []
    analysed, last_meta = 0, meta

    for ev in odds_games:
        if analysed >= max_games:
            break
        home, away = ev.get("home_team"), ev.get("away_team")
        gm = sched_index.get((norm(home), norm(away)))
        if gm is None:
            hk = norm(home).split()[-1] if norm(home).split() else ""
            ak = norm(away).split()[-1] if norm(away).split() else ""
            for (oh, oa), cand in sched_index.items():
                if hk and ak and oh.endswith(hk) and oa.endswith(ak):
                    gm = cand; break
        if gm is None:
            unmatched.append(f"{away} @ {home}"); continue

        event, em = fetch_event_props(ev.get("id"), PROP_MARKETS, regions="us")
        analysed += 1
        if em.get("remaining"):
            last_meta = em
        if em.get("error") or not event:
            continue

        home_id = int(gm.get("home_team_id") or 0)
        away_id = int(gm.get("away_team_id") or 0)
        park = PARK_FACTORS.get(home_id, NEUTRAL_PARK)
        away_sp = fetch_pitcher_stats(gm.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(gm.get("home_prob_id"))
        order_map = {}
        lineup_by_team = {home_id: {}, away_id: {}}
        try:
            lu = fetch_live_lineups(int(gm.get("gamePk")))
            for side in ("home", "away"):
                d = lu.get(side)
                if d is not None and not d.empty and "order" in d.columns:
                    tid = home_id if side == "home" else away_id
                    for _, r in d.iterrows():
                        order_map[int(r["player_id"])] = int(r["order"])
                        lineup_by_team[tid][int(r["order"])] = int(r["player_id"])
        except Exception:
            pass

        gl = f"{TEAM_ABBR.get(away_id, away)} @ {TEAM_ABBR.get(home_id, home)}"
        start = _commence_to_bst(ev.get("commence_time") or "")
        for mkey in PROP_MARKETS.split(","):
            for player, od in consolidate_prop(event, mkey).items():
                srow = name_map.get(player.lower())
                if not srow:
                    ln = player.lower().split()[-1] if player else ""
                    srow = next((v for k, v in name_map.items() if k.split()[-1] == ln), None)
                if not srow:
                    continue
                pid = int(srow.get("player_id") or 0)
                tid = int(srow.get("team_id") or 0)
                if tid == home_id:
                    opp = away_sp
                elif tid == away_id:
                    opp = home_sp
                else:
                    opp = {"homeRunsPer9": LG_HR9, "strikeoutsPer9Inn": LG_K9, "whip": LG_WHIP}
                opp_hr9 = float(opp.get("homeRunsPer9", LG_HR9) or LG_HR9)
                opp_k9 = float(opp.get("strikeoutsPer9Inn", LG_K9) or LG_K9)
                opp_whip = float(opp.get("whip", LG_WHIP) or LG_WHIP)
                order = order_map.get(pid, 5)
                ahead_obp, behind_slg = _lineup_context(
                    order, lineup_by_team.get(tid, {}), stat_by_id)
                lam = prop_expected_counts(srow, expected_pa(order), opp_hr9, opp_k9, opp_whip,
                                           ahead_obp, behind_slg, park["hr"], park["run"])
                mp = _p_over_line(lam[mkey], od["point"])
                if mp is not None:
                    mp = _calibration_adjust(mp, LABEL[mkey])
                bp, mode = market_prob(od["over"], od["under"])
                if mp is None or bp is None:
                    continue
                edge = (mp - bp) * 100
                if not (2.0 <= edge < 15.0):
                    continue
                rows.append([LABEL[mkey], _edge_light(edge), player, gl, start, f"O{od['point']}",
                             round(mp * 100, 1), round(bp * 100, 1), round(edge, 1),
                             od["over_best"], _prop_reason(mkey, srow, opp_hr9, opp_k9, park,
                                                            order, ahead_obp, behind_slg)])

    note = f"Analysed {analysed} game(s)."
    if unmatched:
        note += f" Couldn't match: {', '.join(unmatched[:4])}."
    return pd.DataFrame(rows, columns=cols), last_meta, note


def build_most_likely(sel_date, max_games=15):
    """Rank batters by the model's raw probability of recording >=1 of each prop
    market (no odds, no quota), using confirmed lineups, opposing starter and park."""
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, "No games scheduled for this date."
    bat = fetch_all_mlb_batting_stats(sel_date.year)
    if bat.empty:
        return None, "No batter stats available."
    stat_by_id = {int(r["player_id"]): r for r in bat.to_dict("records") if r.get("player_id")}
    LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
             "batter_rbis": "RBI", "batter_runs_scored": "Runs"}
    rows, n, no_lineups = [], 0, 0
    for _, gm in sched.iterrows():
        if n >= max_games:
            break
        hid = int(gm.get("home_team_id") or 0)
        aid = int(gm.get("away_team_id") or 0)
        park = PARK_FACTORS.get(hid, NEUTRAL_PARK)
        away_sp = fetch_pitcher_stats(gm.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(gm.get("home_prob_id"))
        try:
            lu = fetch_live_lineups(int(gm.get("gamePk")))
        except Exception:
            lu = {}
        gl = f"{TEAM_ABBR.get(aid, gm.get('away_team'))} @ {TEAM_ABBR.get(hid, gm.get('home_team'))}"
        start = gm.get("game_time_bst", "")
        had = False
        for side, opp_sp in (("home", away_sp), ("away", home_sp)):
            d = lu.get(side)
            if d is None or d.empty:
                continue
            had = True
            opp_hr9 = float(opp_sp.get("homeRunsPer9", LG_HR9) or LG_HR9)
            opp_k9 = float(opp_sp.get("strikeoutsPer9Inn", LG_K9) or LG_K9)
            opp_whip = float(opp_sp.get("whip", LG_WHIP) or LG_WHIP)
            slot_to_pid = {}
            if "order" in d.columns:
                for _, r in d.iterrows():
                    try:
                        slot_to_pid[int(r["order"])] = int(r["player_id"])
                    except Exception:
                        pass
            for _, pr in d.iterrows():
                srow = stat_by_id.get(int(pr["player_id"]))
                if not srow:
                    continue
                order = int(pr.get("order", 5) or 5)
                ahead_obp, behind_slg = _lineup_context(order, slot_to_pid, stat_by_id)
                lam = prop_expected_counts(srow, expected_pa(order), opp_hr9, opp_k9, opp_whip,
                                           ahead_obp, behind_slg, park["hr"], park["run"])
                probs = {}
                player_name = pr.get("name") or srow.get("name")
                for mkey, lbl in LABEL.items():
                    p = _p_over_line(lam[mkey], 0.5)
                    if p is not None:
                        p = _calibration_adjust(p, lbl)
                    probs[mkey] = p
                    rows.append([lbl, player_name, gl, start,
                                 int(order), round(p * 100, 1)])
                # combo: P(at least one of hits/runs/RBI >= 1)
                cp = _combo_prob(probs)
                if cp is not None:
                    rows.append(["Runs+Hits+RBI (1+)", player_name, gl, start,
                                 int(order), round(cp * 100, 1)])
        if not had:
            no_lineups += 1
        n += 1
    if not rows:
        return None, "No confirmed lineups posted yet for these games (try closer to first pitch)."
    df = pd.DataFrame(rows, columns=["Market", "Player", "Game", "Start", "Order", "Prob %"])
    note = f"Ranked batters across {n - no_lineups} game(s) with confirmed lineups."
    if no_lineups:
        note += f" {no_lineups} game(s) had no lineup posted yet."
    return df, note


def _calib(recs, market):
    """Calibration summary for one market: Brier, accuracy, and decile buckets."""
    rows = [(p, o) for m, p, o in recs if m == market]
    if not rows:
        return None
    n = len(rows)
    brier = sum((p - o) ** 2 for p, o in rows) / n
    acc = sum(1 for p, o in rows if (p >= 0.5) == (o == 1)) / n
    base = sum(o for p, o in rows) / n
    buckets = []
    for k in range(10):
        lo, hi = k / 10, k / 10 + 0.1
        grp = [(p, o) for p, o in rows if (lo <= p < hi) or (hi >= 1.0 and p >= 1.0)]
        if grp:
            buckets.append((f"{int(lo*100)}-{int(hi*100)}%", len(grp),
                            round(sum(p for p, o in grp) / len(grp) * 100, 1),
                            round(sum(o for p, o in grp) / len(grp) * 100, 1)))
    return {"n": n, "brier": round(brier, 4), "acc": round(acc * 100, 1),
            "base_rate": round(base * 100, 1), "buckets": buckets}


def run_backtest(sel_date, days_back=14):
    """Score the game model against real final scores from recent completed games.
    Returns (records, days_with_games) where each record is (market, pred_prob, outcome)."""
    team_off, league_rpg = fetch_team_offense(sel_date.year)
    bullpen_era = fetch_bullpen_era(sel_date.year)
    recs, days_done = [], 0
    for i in range(1, days_back + 1):
        day = sel_date - timedelta(days=i)
        results = fetch_results(str(day))
        if not results:
            continue
        days_done += 1
        for r in results:
            hid = int(r.get("home_team_id") or 0)
            aid = int(r.get("away_team_id") or 0)
            park = PARK_FACTORS.get(hid, NEUTRAL_PARK)
            home_rpg = _park_neutral_rpg(team_off.get(hid, league_rpg), park["run"])
            away_rpg = _park_neutral_rpg(team_off.get(aid, league_rpg),
                                         PARK_FACTORS.get(aid, NEUTRAL_PARK)["run"])
            away_sp = fetch_pitcher_stats(r.get("away_prob_id")) if r.get("away_prob_id") else {"era": 4.5}
            home_sp = fetch_pitcher_stats(r.get("home_prob_id")) if r.get("home_prob_id") else {"era": 4.5}
            away_bp = bullpen_era.get(aid, LEAGUE_BULLPEN_ERA_DEFAULT)
            home_bp = bullpen_era.get(hid, LEAGUE_BULLPEN_ERA_DEFAULT)
            mdl = model_game(home_rpg, away_rpg, away_sp.get("era", 4.5),
                             home_sp.get("era", 4.5), league_rpg, LEAGUE_ERA_DEFAULT,
                             8.5, park=park["run"],
                             home_opp_bullpen_era=away_bp, away_opp_bullpen_era=home_bp)
            total = r["home_score"] + r["away_score"]
            margin = r["home_score"] - r["away_score"]
            recs.append(("Moneyline (home win)", mdl["p_home_ml"], 1 if margin > 0 else 0))
            recs.append(("Total Over 8.5", mdl["p_over"], 1 if total > 8.5 else 0))
            recs.append(("Run line (home -1.5)", mdl["p_home_cover"], 1 if margin >= 2 else 0))
    return recs, days_done


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_boxscore_batters(game_pk):
    """Actual batter box-score lines (hits, HR, RBI, runs, batting order) for a
    completed game. Free MLB data, used to score the prop model in the backtest."""
    if not game_pk:
        return []
    data = safe_get(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")
    out = []
    for side in ("home", "away"):
        team = data.get("teams", {}).get(side, {})
        team_id = team.get("team", {}).get("id")
        for pid, p in team.get("players", {}).items():
            bo = p.get("battingOrder")
            bat = p.get("stats", {}).get("batting", {})
            if not bo or not bat or bat.get("plateAppearances", 0) in (0, None):
                continue
            try:
                order = int(bo) // 100
            except Exception:
                continue
            if order < 1 or order > 9:
                continue
            out.append({
                "player_id": p.get("person", {}).get("id"),
                "name": p.get("person", {}).get("fullName", ""),
                "team_id": team_id,
                "order": order,
                "hits": int(bat.get("hits") or 0),
                "hr": int(bat.get("homeRuns") or 0),
                "rbi": int(bat.get("rbi") or 0),
                "runs": int(bat.get("runs") or 0),
            })
    return out


def run_prop_backtest(sel_date, days_back=14, max_games_per_day=None):
    """Score the player-prop model against real box scores from recent completed
    games. Uses each batter's actual starting slot (so plate-appearance estimates
    match what actually happened) and the real opposing starter + park for that
    game. Adds a 'Runs+Hits+RBI (1+)' combo market alongside the four singles.
    Returns (records, days_done, games_scored)."""
    bat = fetch_all_mlb_batting_stats(sel_date.year)
    if bat.empty:
        return [], 0, 0
    stat_by_id = {int(r["player_id"]): r for r in bat.to_dict("records") if r.get("player_id")}

    LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
             "batter_rbis": "RBI", "batter_runs_scored": "Runs"}
    ACTUAL_KEY = {"batter_home_runs": "hr", "batter_hits": "hits",
                  "batter_rbis": "rbi", "batter_runs_scored": "runs"}

    recs, days_done, games_scored = [], 0, 0
    for i in range(1, days_back + 1):
        day = sel_date - timedelta(days=i)
        results = fetch_results(str(day))
        if not results:
            continue
        days_done += 1
        if max_games_per_day:
            results = results[:max_games_per_day]
        for r in results:
            gp = r.get("gamePk")
            if not gp:
                continue
            box = fetch_boxscore_batters(gp)
            if not box:
                continue
            games_scored += 1
            hid = int(r.get("home_team_id") or 0)
            aid = int(r.get("away_team_id") or 0)
            park = PARK_FACTORS.get(hid, NEUTRAL_PARK)
            away_sp = fetch_pitcher_stats(r.get("away_prob_id")) if r.get("away_prob_id") else {"era": 4.5}
            home_sp = fetch_pitcher_stats(r.get("home_prob_id")) if r.get("home_prob_id") else {"era": 4.5}
            # Real batting order for both teams, straight from the box score — more
            # accurate than a pre-game lineup guess since this is what actually happened.
            slot_by_team = {hid: {}, aid: {}}
            for b in box:
                tid_b = b.get("team_id")
                if tid_b in slot_by_team and b.get("order"):
                    slot_by_team[tid_b][int(b["order"])] = b["player_id"]
            for b in box:
                srow = stat_by_id.get(int(b["player_id"] or 0))
                if not srow:
                    continue
                opp_sp = away_sp if b["team_id"] == hid else home_sp
                opp_hr9 = float(opp_sp.get("homeRunsPer9", LG_HR9) or LG_HR9)
                opp_k9 = float(opp_sp.get("strikeoutsPer9Inn", LG_K9) or LG_K9)
                opp_whip = float(opp_sp.get("whip", LG_WHIP) or LG_WHIP)
                ahead_obp, behind_slg = _lineup_context(
                    b["order"], slot_by_team.get(b["team_id"], {}), stat_by_id)
                lam = prop_expected_counts(srow, expected_pa(b["order"]), opp_hr9, opp_k9, opp_whip,
                                           ahead_obp, behind_slg, park["hr"], park["run"])
                probs = {}
                for mkey, label in LABEL.items():
                    p = _p_over_line(lam[mkey], 0.5)
                    if p is None:
                        continue
                    outcome = 1 if b[ACTUAL_KEY[mkey]] >= 1 else 0
                    recs.append((label, p, outcome))
                    probs[mkey] = p
                if len(probs) == 4:
                    p_combo = 1 - (1 - probs["batter_hits"]) * \
                                  (1 - probs["batter_runs_scored"]) * \
                                  (1 - probs["batter_rbis"])
                    outcome_combo = 1 if (b["hits"] >= 1 or b["runs"] >= 1 or b["rbi"] >= 1) else 0
                    recs.append(("Runs+Hits+RBI (1+)", min(p_combo, 0.999), outcome_combo))
    return recs, days_done, games_scored


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
                 order, era, whip, hr9, k9, park_factor, temp, wind, dome, use_adv, w_era, w_whip,
                 park_run=1.0, park_hr=1.0):
    weather = park_factor * wx_modifier(temp, wind, dome)
    env     = weather * park_run   # structural park factor for hits / RBI / runs
    env_hr  = weather * park_hr    # structural park factor for home runs
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
    hr_score        = round(power   * hrv * env_hr * 280, 2)
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



def setup_page(title="MLB Prop Analyser"):
    """Per-page config + shared styling. Must be the first Streamlit call on a page."""
    st.set_page_config(page_title=title, page_icon="⚾", layout="wide")
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
    </style>
    """, unsafe_allow_html=True)


def sidebar_date():
    """Shared sidebar: date picker (persisted across pages) + clear cache. Returns date."""
    with st.sidebar:
        st.markdown("## ⚾ MLB Props v2")
        sel = st.date_input("Slate Date", value=date.today(), key="sel_date_picker")
        if st.button("Clear Cache", key="clear_cache_btn"):
            st.cache_data.clear()
            st.rerun()
    return sel


__all__ = [n for n in dir() if not n.startswith('__')]
