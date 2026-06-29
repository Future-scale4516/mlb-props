import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests as req
from datetime import date, datetime, timedelta
import time

st.set_page_config(page_title="MLB Prop Analyser v2", page_icon="⚾", layout="wide")

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


import math, statistics

LEAGUE_RPG_DEFAULT = 4.4    # league runs/game per team (fallback)
LEAGUE_ERA_DEFAULT = 4.10   # league ERA (fallback)
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


def _pois_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _pois_vector(lam, max_runs=18):
    v = [_pois_pmf(k, lam) for k in range(max_runs + 1)]
    s = sum(v)
    return [x / s for x in v] if s else v


def expected_runs(team_rpg, opp_era, league_rpg, league_era, park=1.0):
    off_idx = (team_rpg / league_rpg) if league_rpg > 0 else 1.0
    blended_era = SP_WEIGHT * opp_era + (1 - SP_WEIGHT) * league_era
    pitch_idx = (blended_era / league_era) if league_era > 0 else 1.0
    return max(0.5, min(league_rpg * off_idx * pitch_idx * park, 12.0))


def model_game(home_rpg, away_rpg, home_opp_era, away_opp_era,
               league_rpg, league_era, total_line, park=1.0):
    """home_opp_era = ERA of the pitcher the HOME team faces (the away starter)."""
    lam_home = expected_runs(home_rpg, home_opp_era, league_rpg, league_era, park)
    lam_away = expected_runs(away_rpg, away_opp_era, league_rpg, league_era, park)
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


def build_game_edges(sel_date):
    """Match today's games to UK odds, run the model, return (df, note, meta)."""
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, "No games scheduled for this date.", {}
    team_off, league_rpg = fetch_team_offense(sel_date.year)
    odds_data, meta = fetch_mlb_odds(regions="uk")
    if meta.get("error"):
        return None, meta["error"], meta
    if not odds_data:
        return None, "No UK odds returned (markets may not be up yet).", meta

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

        home_rpg = team_off.get(int(gm.get("home_team_id") or 0), league_rpg)
        away_rpg = team_off.get(int(gm.get("away_team_id") or 0), league_rpg)
        away_sp = fetch_pitcher_stats(gm.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(gm.get("home_prob_id"))
        cons = consolidate_odds(og, og.get("home_team"), og.get("away_team"))
        pf = PARK_FACTORS.get(int(gm.get("home_team_id") or 0), NEUTRAL_PARK)
        mdl = model_game(home_rpg, away_rpg, away_sp.get("era", 4.5),
                         home_sp.get("era", 4.5), league_rpg, LEAGUE_ERA_DEFAULT,
                         cons.get("total_line"), park=pf["run"])
        gl = f"{away} @ {home}"
        ct = og.get("commence_time") or ""
        game_time[gl] = (ct, _commence_to_bst(ct))

        fh, fa = devig_two(cons["ml_home"], cons["ml_away"])
        if fh is not None:
            e, v = edge_ev(mdl["p_home_ml"], fh, cons["ml_home_best"])
            rows.append([gl, "Moneyline", home, mdl["p_home_ml"], fh, e, cons["ml_home_best"], v])
            e, v = edge_ev(mdl["p_away_ml"], fa, cons["ml_away_best"])
            rows.append([gl, "Moneyline", away, mdl["p_away_ml"], fa, e, cons["ml_away_best"], v])
        frh, fra = devig_two(cons["rl_home"], cons["rl_away"])
        if frh is not None:
            e, v = edge_ev(mdl["p_home_cover"], frh, cons["rl_home_best"])
            rows.append([gl, "Run line", f"{home} -1.5", mdl["p_home_cover"], frh, e, cons["rl_home_best"], v])
            e, v = edge_ev(mdl["p_away_cover"], fra, cons["rl_away_best"])
            rows.append([gl, "Run line", f"{away} +1.5", mdl["p_away_cover"], fra, e, cons["rl_away_best"], v])
        fo, fu = devig_two(cons["over"], cons["under"])
        if fo is not None and cons["total_line"] is not None:
            ln = cons["total_line"]
            e, v = edge_ev(mdl["p_over"], fo, cons["over_best"])
            rows.append([gl, "Total", f"Over {ln}", mdl["p_over"], fo, e, cons["over_best"], v])
            e, v = edge_ev(mdl["p_under"], fu, cons["under_best"])
            rows.append([gl, "Total", f"Under {ln}", mdl["p_under"], fu, e, cons["under_best"], v])

    if not rows:
        return None, "No matched games with usable odds.", meta
    df = pd.DataFrame(rows, columns=["Game", "Market", "Selection",
                                     "Model %", "Fair %", "Edge", "Odds", "EV %"])
    df["Model %"] = (df["Model %"] * 100).round(1)
    df["Fair %"] = (df["Fair %"] * 100).round(1)
    df["Edge"] = df["Edge"].round(1)
    df["EV %"] = df["EV %"].round(1)
    df["_ct"] = df["Game"].map(lambda g: game_time.get(g, ("", ""))[0])
    df["Start"] = df["Game"].map(lambda g: game_time.get(g, ("", ""))[1])
    df = df.sort_values(["_ct", "Game"]).reset_index(drop=True)
    note = (f"Couldn't match odds for: {', '.join(unmatched)}" if unmatched else "")
    return df, note, meta


LG_HR9 = 1.15   # league avg HR allowed per 9 innings
LG_K9 = 8.5     # league avg K per 9 innings


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


def prop_expected_counts(stat, pa, opp_hr9=LG_HR9, opp_k9=LG_K9, park_hr=1.0, park_run=1.0):
    """Expected per-game counts (Poisson lambdas) for each batter prop market.
    Season rate carries the hitter's talent; pitcher + park are the adjustments."""
    spa = max(stat.get("plateAppearances", 1) or 1, 1)
    hr_l = (stat.get("hr", 0) / spa) * (opp_hr9 / LG_HR9) * park_hr * pa
    hits = stat.get("hits")
    hit_rate = (hits / spa) if hits is not None else stat.get("avg", 0) * 0.88
    k_factor = 1.0 - 0.5 * min(max((opp_k9 - LG_K9) / LG_K9, -0.3), 0.3)
    hit_l = hit_rate * k_factor * (1.0 + 0.5 * (park_run - 1.0)) * pa
    rbi_l = (stat.get("rbi", 0) / spa) * (0.6 + 0.4 * park_run) * pa
    run_l = (stat.get("runs", 0) / spa) * (0.6 + 0.4 * park_run) * pa
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

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚾ MLB Props v2")
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Filters")
    min_avg  = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    # NEW: OBP Slider
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
    
    # NEW: Expandable Stat Cheat Sheet
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
        for k in ["auto_df"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

allowed_markets = [m for m,s in [
    ("Hits/Runs",s_hits),("RBI",s_rbi),("Home Run",s_hr),("Runs Scored",s_runs)] if s]

st.title("⚾ MLB Prop Analyser v2")
st.caption("Auto-fetches every MLB batter, probable pitchers, confirmed lineups and live weather.")
st.divider()

col_btn, col_info = st.columns([2,3])
with col_btn:
    load_btn = st.button("Load Today's Slate")
with col_info:
    st.markdown("""
    **Auto-loads:** MLB schedule · probable pitchers · **all 500+ batters** (MLB Stats API) · Fangraphs advanced stats (if available) · confirmed lineups · live ballpark weather
    """)

with st.expander("🔌 Odds API connection test (The Odds API)"):
    st.caption("Runs one request against your quota. Use it to confirm the key works "
               "and see which markets your plan returns.")
    if st.button("Run odds API test"):
        odds_data, odds_meta = fetch_mlb_odds()
        if odds_meta.get("error"):
            st.error(odds_meta["error"])
        else:
            st.success(f"Connected — {len(odds_data)} MLB games returned.")
            st.write(f"Quota — used: {odds_meta.get('used')} | "
                     f"remaining: {odds_meta.get('remaining')}")
            present = set()
            for g in odds_data:
                for b in g.get("bookmakers", []):
                    for m in b.get("markets", []):
                        present.add(m.get("key"))
            label = {"h2h": "moneyline", "spreads": "run line", "totals": "over/under"}
            shown = ", ".join(f"{k} ({label.get(k, k)})" for k in sorted(present)) or "none"
            st.write("Markets returned:", shown)
            if odds_data:
                g = odds_data[0]
                st.write(f"Sample game: {g.get('away_team')} @ {g.get('home_team')}  "
                         f"(start {g.get('commence_time')})")
                st.json((g.get("bookmakers") or [{}])[0])

st.divider()
st.markdown("## 🎯 Game Bets — Money Line · Run Line · Totals")
st.caption("Estimates each team's runs with a Poisson model (starting pitchers + team "
           "offence), then compares to de-vigged UK odds to surface edges. Positive edge = "
           "model rates the bet better than the market price. Always confirm the live price "
           "at your book before staking — lines move.")
if st.button("Analyse game bets (UK odds)"):
    with st.spinner("Fetching schedule, team stats, pitchers and UK odds..."):
        gdf, gnote, gmeta = build_game_edges(sel_date)
    if gdf is None:
        st.warning(gnote)
    else:
        if gmeta.get("remaining"):
            st.caption(f"Odds quota — used {gmeta.get('used')}, "
                       f"remaining {gmeta.get('remaining')}")
        if gnote:
            st.info(gnote)
        green = int(((gdf["Edge"] >= 2) & (gdf["Edge"] < 8)).sum())
        amber = int(((gdf["Edge"] >= 8) & (gdf["Edge"] < 15)).sum())
        red = int((gdf["Edge"] >= 15).sum())
        st.markdown(f"### 🟢 {green} green · 🟡 {amber} amber · 🔴 {red} red")
        st.caption("🟢 2–8 pts = believable value · 🟡 8–15 = treat with caution · "
                   "🔴 15+ = almost certainly a missing model input, not a real edge · "
                   "⚪ under 2 = no signal.")
        cfg = {
            "🚦": st.column_config.TextColumn("", width="small"),
            "Start": st.column_config.TextColumn("Start (BST)", width="small"),
            "Game": st.column_config.TextColumn("Game", width="medium"),
            "Selection": st.column_config.TextColumn("Selection", width="medium"),
            "Model %": st.column_config.NumberColumn("Model %", format="%.1f"),
            "Fair %": st.column_config.NumberColumn("Fair %", format="%.1f"),
            "Edge": st.column_config.NumberColumn("Edge (pts)", format="%.1f"),
            "Odds": st.column_config.NumberColumn("Best odds", format="%.2f"),
            "EV %": st.column_config.NumberColumn("EV %", format="%.1f"),
        }

        def show_market(tab, market_name):
            with tab:
                sub = gdf[gdf["Market"] == market_name].sort_values(
                    ["_ct", "Game"]).reset_index(drop=True)
                if sub.empty:
                    st.write("No odds available for this market today.")
                    return
                sub = sub.copy()
                sub.insert(0, "🚦", sub["Edge"].apply(_edge_light))
                disp = sub[["🚦", "Start", "Game", "Selection",
                            "Model %", "Fair %", "Edge", "Odds", "EV %"]]
                st.dataframe(disp, use_container_width=True, hide_index=True,
                             column_config=cfg)

        ml_tab, rl_tab, tot_tab = st.tabs(["💰 Money Line", "📏 Run Line", "📊 Totals"])
        show_market(ml_tab, "Moneyline")
        show_market(rl_tab, "Run line")
        show_market(tot_tab, "Total")
        st.caption("Model %: our probability · Fair %: book's de-vigged probability · "
                   "Edge: model minus fair · EV %: expected return per unit stake at best "
                   "odds. Heads-up: very large edges (15+ pts) usually mean the model is "
                   "missing an input for that game (e.g. ballpark) rather than real value.")

st.divider()
st.markdown("## 🎰 Player Prop Edges — probe (stage 1)")
st.caption("Player props live on US books and are pulled one game at a time, so this first "
           "stage confirms your plan serves them and previews model-vs-market edges for a "
           "single game before we scale to the whole slate. Costs ~5 quota credits.")
PROP_MARKETS = "batter_home_runs,batter_hits,batter_rbis,batter_runs_scored"
PROP_LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
              "batter_rbis": "RBI", "batter_runs_scored": "Runs"}
if st.button("Probe player prop odds (1 game)"):
    with st.spinner("Checking prop availability and pulling one game's props..."):
        odds_games, _m = fetch_mlb_odds(regions="uk")
    if not odds_games:
        st.warning("No games available to probe right now.")
    else:
        ev = odds_games[0]
        eid = ev.get("id")
        st.write(f"Probing: **{ev.get('away_team')} @ {ev.get('home_team')}**")
        avail, am = fetch_event_market_keys(eid, regions="us")
        if am.get("error"):
            st.error(f"Availability check failed: {am['error']}")
        batter_avail = [k for k in avail if k.startswith("batter_")]
        st.write("Batter prop markets available:",
                 ", ".join(batter_avail) if batter_avail else "none found")
        if not batter_avail:
            st.warning("No batter prop markets returned for this game/plan. Player props may "
                       "not be in your tier, or may not be posted yet. Game-line edges are "
                       "unaffected.")
        else:
            event, em = fetch_event_props(eid, PROP_MARKETS, regions="us")
            if em.get("error"):
                st.error(em["error"])
            elif not event:
                st.warning("No prop odds returned.")
            else:
                if em.get("remaining"):
                    st.caption(f"Quota — last call cost {em.get('last')}, "
                               f"used {em.get('used')}, remaining {em.get('remaining')}")
                bat = fetch_all_mlb_batting_stats(sel_date.year)
                name_map = {str(n).lower(): row for n, row in
                            zip(bat["name"], bat.to_dict("records"))}
                rows = []
                for mkey in [k for k in PROP_MARKETS.split(",") if k in batter_avail]:
                    for player, od in consolidate_prop(event, mkey).items():
                        srow = name_map.get(player.lower())
                        if not srow:
                            ln = player.lower().split()[-1] if player else ""
                            srow = next((v for k, v in name_map.items()
                                         if k.split()[-1] == ln), None)
                        if not srow:
                            continue
                        lam = prop_expected_counts(srow, 4.2)   # neutral baseline (stage 1)
                        mp = _p_over_line(lam[mkey], od["point"])
                        bp, mode = market_prob(od["over"], od["under"])
                        if mp is None or bp is None:
                            continue
                        edge = (mp - bp) * 100
                        rows.append([_edge_light(edge), player, PROP_LABEL[mkey],
                                     f"O{od['point']}", round(mp * 100, 1), round(bp * 100, 1),
                                     round(edge, 1), od["over_best"], mode])
                if not rows:
                    st.warning("Got prop odds but couldn't match players to season stats.")
                else:
                    pdf = pd.DataFrame(rows, columns=["🚦", "Player", "Market", "Line",
                                       "Model %", "Market %", "Edge", "Over odds", "Price"])
                    pdf = pdf.sort_values("Edge", ascending=False).reset_index(drop=True)
                    st.dataframe(pdf, use_container_width=True, hide_index=True,
                        column_config={
                            "🚦": st.column_config.TextColumn("", width="small"),
                            "Model %": st.column_config.NumberColumn(format="%.1f"),
                            "Market %": st.column_config.NumberColumn(format="%.1f"),
                            "Edge": st.column_config.NumberColumn("Edge (pts)", format="%.1f"),
                            "Over odds": st.column_config.NumberColumn("Best over", format="%.2f"),
                        })
                    st.caption("Stage-1 probe uses a neutral pitcher/park baseline; the full "
                               "build adds the opposing starter and ballpark per player and "
                               "spans every game. Price = de-vig (both sides quoted) or raw "
                               "(one-sided market, vig still included).")

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

        st.write("Loading Baseball Savant advanced stats (xwOBA, Barrel%, HardHit%)...")
        fg_df = fetch_savant_stats(sel_date.year)
        savant_map = {}
        if fg_df.empty:
            reason = st.session_state.get("savant_error", "")
            st.warning(f"Savant unavailable — using MLB API derived metrics. {reason}")
        else:
            st.write(f"Savant loaded: {len(fg_df)} batters")
            if st.session_state.get("savant_error"):
                st.warning(st.session_state["savant_error"])
            tmp = fg_df.dropna(subset=["player_id"]).copy()
            tmp["player_id"] = tmp["player_id"].astype(int)
            savant_map = tmp.set_index("player_id").to_dict("index")

        all_rows = []
        for _, g in sched.iterrows():
            st.write(f"Processing {g['away_team']} @ {g['home_team']}...")
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
            g_pf = PARK_FACTORS.get(int(g["home_team_id"]), NEUTRAL_PARK)
            if total_env >= 1.06:
                env_symbol = "🟢 Hitter-Friendly"
            elif total_env >= 0.97:
                env_symbol = "🟡 Neutral"
            else:
                env_symbol = "🔴 Pitcher-Friendly"

            game_status_label = g["status"]

            for side_label, player_ids, stats_map, opp_pitch, conf in [
                ("Away", away_ids, away_stats_map, home_pitch, away_conf),
                ("Home", home_ids, home_stats_map, away_pitch, home_conf),
            ]:
                p_era = opp_pitch.get("era", 4.5)
                p_whip = opp_pitch.get("whip", 1.35)
                
                if p_era >= 4.5 or p_whip >= 1.35:
                    p_rating = "🟢 Target"
                elif p_era <= 3.4 and p_whip <= 1.20:
                    p_rating = "🔴 Avoid"
                else:
                    p_rating = "🟡 Neutral"

                for pid in player_ids:
                    pid = int(pid)
                    player_live_data = stats_map.get(pid, {})
                    order = int(player_live_data.get("order", 9) or 9)
                    if order > max_ord: continue

                    mlb_row = mlb_all[mlb_all["player_id"] == pid] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty: continue  
                    base = mlb_row.iloc[0].to_dict()
                    pname = base.get("name","")

                    if base.get("plateAppearances",0) < min_pa: continue
                    if float(base.get("avg",0)) < min_avg: continue
                    
                    # NEW: Implement the OBP slider logic
                    if float(base.get("obp",0)) < min_obp: continue
                    
                    if opp_pitch.get("era",4.5) > max_era: continue

                    use_adv = False
                    wrc_plus = int(max(1, float(base.get("ops",0.700) or 0.700) * 152))
                    hard_hit = min(0.65, 0.28 + float(base.get("iso",0)) * 1.2)
                    barrel   = min(0.20, float(base.get("iso",0)) * 0.35)
                    srow = savant_map.get(pid)
                    if srow:
                        wv = srow.get("wrc_plus")
                        if wv is not None and not pd.isna(wv): wrc_plus = int(wv)
                        hv = srow.get("hard_hit_pct")
                        if hv is not None and not pd.isna(hv): hard_hit = float(hv)
                        bv = srow.get("barrel_pct")
                        if bv is not None and not pd.isna(bv): barrel = float(bv)
                        use_adv = True

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
                        wx["dome"], use_adv, w_era, w_whip,
                        g_pf["run"], g_pf["hr"]
                    )
                    flt = {k:v for k,v in scores.items() if k in allowed_markets}
                    if not flt: continue
                    best_market = max(flt, key=flt.get)
                    best_score  = flt[best_market]
                    
                    if best_score >= 70.0:
                        grade_badge = "🟢 Premium"
                    elif best_score >= 48.0:
                        grade_badge = "🟡 Playable"
                    else:
                        grade_badge = "🔴 Sub-optimal"

                    if best_market == "Home Run":
                        rationale = f"Elite power (ISO {iso_v:.3f}) matching up against a pitcher allowing {opp_pitch.get('homeRunsPer9', 1.2):.1f} HR/9."
                    elif best_market == "RBI":
                        rationale = f"Strong run-producer (wRC+ {wrc_plus}) hitting #{order} in the order with men likely on base."
                    elif best_market == "Runs Scored":
                        rationale = f"High on-base threat (OBP {obp_v:.3f}) batting #{order} facing a high-WHIP ({p_whip:.2f}) pitcher."
                    else:
                        rationale = f"Excellent contact profile (AVG {avg_v:.3f}) in a favourable offensive environment."

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
                    
                    if bet_won:
                        result_status = "✅ Won"
                    elif not bet_won and is_final:
                        result_status = "❌ Lost"
                    else:
                        result_status = "⏳ Pending"

                    all_rows.append({
                        "Game":          g["away_team"] + " @ " + g["home_team"],
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

        if not all_rows:
            st.error("No batters matched filters."); status.update(label="No results", state="error")
        else:
            df = pd.DataFrame(all_rows).sort_values("Best Score", ascending=False)
            st.session_state["auto_df"] = df
            status.update(label=f"Done — {len(df)} batters scored across {len(sched)} games", state="complete")

if "auto_df" in st.session_state:
    df = st.session_state["auto_df"]
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

        all_t, game_t, tracker_t, t_hits, t_rbi, t_hr, t_runs, t_raw = st.tabs([
            "All Ranked", "🗂️ Game by Game", "✅ Slip Tracker", "Hits/Runs", "RBI", "Home Run", "Runs Scored", "Raw Data"
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

        with t_raw:
            st.dataframe(df.reset_index(drop=True), use_container_width=True, hide_index=True)

        st.download_button("Download Full CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"mlb_props_{sel_date}.csv", mime="text/csv")

st.divider()
st.caption("MLB Stats API (all batters via playerPool=ALL) · Fangraphs via pybaseball (optional enrichment) · Open-Meteo weather")
