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

# --- Platoon (handedness) ---------------------------------------------------
# League-average platoon effect, NOT per-batter splits. Individual batter splits
# exist but need a separate call per player and are thin-sample noisy for most
# hitters, so this applies the well-established league-wide effect instead:
# batters do better against opposite-handed pitching. Switch hitters ("S") get
# no adjustment since they bat from whichever side is favourable anyway.
PLATOON_ADVANTAGE = 1.06     # opposite-handed matchup (e.g. LHB vs RHP)
PLATOON_DISADVANTAGE = 0.94  # same-handed matchup (e.g. RHB vs RHP)

# --- Recent form ------------------------------------------------------------
RECENT_FORM_DAYS = 30        # window for "recent form" stats
RECENT_FORM_WEIGHT = 0.25    # how much recent form displaces the season rate.
                             # Deliberately light: short windows are noisy, so this
                             # nudges toward a hot/cold streak rather than trusting
                             # it over a full season's evidence.
MIN_PA_FOR_RECENT_FORM = 20  # below this, the recent window is too thin to use

# --- Calibration corrections ------------------------------------------------
# Per-market shrinkage toward a base rate, applied to raw model probabilities.
# These are DERIVED, not guessed: run "Fit calibration from backtest" on the
# Backtest page and paste the numbers it prints here. Starting values below are
# the earlier hand-set ones, kept so behaviour doesn't change until refitted.
# shrink=0 means "no correction, this market is already well calibrated".
CALIBRATION_FITS = {
    "RBI":  {"base": 0.280, "shrink": 0.300},
    "Runs": {"base": 0.360, "shrink": 0.180},
    # Hits, Home Run, Total Bases: no correction applied yet.
}

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
                "game_number":    g.get("gameNumber", 1),
                "double_header":  g.get("doubleHeader", "N"),  # Y/S = doubleheader, N = single
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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_day_results(target_date: str):
    """Every game on a date with team names, status and score — including games
    still in progress or not yet started. Short TTL so an in-progress score
    stays current. Free MLB data, no Odds API quota."""
    data = safe_get("https://statsapi.mlb.com/api/v1/schedule", {
        "sportId": 1, "date": target_date, "hydrate": "team,linescore,venue"})
    out = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            t = g.get("teams", {})
            status = g.get("status", {})
            ls = g.get("linescore", {})
            out.append({
                "gamePk": g.get("gamePk"),
                "game_number": g.get("gameNumber", 1),
                "double_header": g.get("doubleHeader", "N"),
                "state": status.get("abstractGameState", "Preview"),  # Preview/Live/Final
                "detail": status.get("detailedState", ""),
                "home_team": t.get("home", {}).get("team", {}).get("name", ""),
                "away_team": t.get("away", {}).get("team", {}).get("name", ""),
                "home_team_id": t.get("home", {}).get("team", {}).get("id"),
                "away_team_id": t.get("away", {}).get("team", {}).get("id"),
                "home_score": t.get("home", {}).get("score"),
                "away_score": t.get("away", {}).get("score"),
                "inning": ls.get("currentInning"),
                "inning_state": ls.get("inningState", ""),
                "venue": g.get("venue", {}).get("name", ""),
                "start_utc": g.get("gameDate", ""),
            })
    return out


_FORM_STAT_KEY = {"batter_home_runs": "homeRuns", "batter_hits": "hits",
                  "batter_rbis": "rbi", "batter_runs_scored": "runs",
                  "batter_total_bases": "totalBases"}
FORM_GAMES = 10  # 10 rather than 5: with a ~65% market like 1+ Hits, five games
                 # only gives six possible outcomes and the gap between 3/5 and
                 # 4/5 is mostly noise. Ten gives real resolution without
                 # reaching so far back it stops reflecting current form.


@st.cache_data(ttl=10800, show_spinner=False)
def fetch_player_game_log(player_id, season, games=FORM_GAMES):
    """Per-game batting lines for one player's most recent `games` appearances.
    There's no bulk endpoint for this — it's one call per player — so it's
    cached hard and should only be called for players actually being displayed."""
    if not player_id:
        return []
    data = safe_get(f"https://statsapi.mlb.com/api/v1/people/{int(player_id)}/stats", {
        "stats": "gameLog", "group": "hitting", "season": season})
    splits = []
    for s in data.get("stats", []):
        splits.extend(s.get("splits", []))
    splits = [s for s in splits if (s.get("stat") or {}).get("plateAppearances")]
    splits.sort(key=lambda s: s.get("date", ""), reverse=True)
    return [{"date": s.get("date", ""), **(s.get("stat") or {})} for s in splits[:games]]


def form_streak(player_id, season, market_key, line, games=FORM_GAMES):
    """Did this player clear `line` in this market in each of the last `games`?
    Checks the ACTUAL line (so a 2+ Total Bases pick is judged on clearing 2
    bases, not just on appearing). Returns (hits, played, symbols) — or
    (None, 0, "") when there's no usable log."""
    stat_key = _FORM_STAT_KEY.get(market_key)
    if not stat_key:
        return None, 0, ""
    log = fetch_player_game_log(player_id, season, games)
    if not log:
        return None, 0, ""
    syms, hits = [], 0
    for g in log:
        try:
            val = float(g.get(stat_key) or 0)
        except Exception:
            val = 0.0
        ok = val > float(line)
        hits += 1 if ok else 0
        syms.append("✅" if ok else "❌")
    syms.reverse()  # oldest first, so it reads left-to-right chronologically
    return hits, len(log), "".join(syms)


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


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_player_handedness(season: int):
    """Bat side (L/R/S) and pitch hand (L/R) for every player in one bulk call —
    handedness is a fixed attribute, so this is cached for a day. Returns
    (dict{player_id: bat_side}, dict{player_id: pitch_hand})."""
    data = safe_get("https://statsapi.mlb.com/api/v1/sports/1/players", {"season": season})
    bats, throws = {}, {}
    for p in data.get("people", []):
        pid = p.get("id")
        if not pid:
            continue
        bs = (p.get("batSide") or {}).get("code")
        ph = (p.get("pitchHand") or {}).get("code")
        if bs:
            bats[int(pid)] = bs
        if ph:
            throws[int(pid)] = ph
    return bats, throws


def data_confidence(pitcher_known=True, lineup_confirmed=True, batter_pa=None,
                     handedness_known=True, weather_known=True):
    """How much real data went into a pick, as distinct from how big its edge is.

    This exists because a pick built on a confirmed lineup, a named starter with
    a real stat line, and a 600-PA batter currently looks IDENTICAL to one built
    on a projected lineup, a TBD starter (where we silently substitute a
    league-average 4.50 ERA), and a 40-PA batter. Both can come out as "no
    signal" — but the first genuinely means "model and market agree", while the
    second means "the model doesn't really have an opinion here". Returns
    (level, missing_list) where level is 'high' | 'medium' | 'low'."""
    missing = []
    if not pitcher_known:
        missing.append("starter not announced (league-average ERA assumed)")
    if not lineup_confirmed:
        missing.append("lineup not confirmed (batting slot estimated)")
    if batter_pa is not None and batter_pa < 100:
        missing.append(f"small sample ({int(batter_pa)} PA this season)")
    if not handedness_known:
        missing.append("handedness unknown (no platoon adjustment)")
    if not weather_known:
        missing.append("weather unavailable")
    if not missing:
        return "high", []
    # A missing starter or unconfirmed lineup are the two that genuinely gut the
    # model's inputs; the rest just soften it.
    severe = (not pitcher_known) or (not lineup_confirmed)
    return ("low" if severe else "medium"), missing


CONFIDENCE_BADGE = {"high": "🔵 Full data", "medium": "🟠 Partial data",
                    "low": "⚫ Thin data"}


def explain_no_signal(confidence_level, missing):
    """Plain-English explanation for a ⚪ no-signal pick. Distinguishes genuine
    model/market agreement (the normal, healthy case) from a pick where the
    model simply didn't have the inputs to form a view."""
    if confidence_level == "high":
        return ("No signal — the model and the market agree here. That's the "
                "expected outcome for most bets in a liquid market, not a fault.")
    return ("No signal, but note the model is working with incomplete inputs: "
            + "; ".join(missing) + ". Treat this as 'no opinion' rather than "
            "'genuine agreement'.")


def weather_multiplier(wx):
    """Same-day weather adjustment applied ON TOP of a park's static factor, for
    the modern engine (game model + prop model). Returns 1.0 for domes.

    Deliberately asymmetric in what it trusts:
      - Temperature is the dependable part — warm air is less dense, the ball
        carries further, and the direction of the effect is unambiguous.
      - Wind is NOT — the API gives speed but not direction relative to the
        park's orientation, and wind blowing in suppresses offense as much as
        wind blowing out helps it. So wind only gets a small nudge for the
        general "windy days are livelier" effect, not the full-size adjustment
        the old scoring pipeline applied. This is a smaller, more honest
        correction than pretending we know which way it's blowing."""
    if not wx or wx.get("dome"):
        return 1.0
    temp = float(wx.get("temp", 72) or 72)
    wind = float(wx.get("wind", 8) or 8)
    mult = 1.0 + (temp - 70) * 0.0030 + max(wind - 8, 0) * 0.0015
    return max(0.90, min(mult, 1.12))


def apply_weather_to_park(park, wx):
    """Combine a park's static run/HR factors with today's weather."""
    m = weather_multiplier(wx)
    return {"run": park.get("run", 1.0) * m, "hr": park.get("hr", 1.0) * m}


def _safe_int(v):
    """int() that returns None instead of raising for NaN, None or junk.

    Needed because a TBD probable pitcher comes back from pandas as NaN — and
    NaN is TRUTHY in Python, so a plain `if pid:` guard sails straight past it
    and int(nan) then throws ValueError."""
    if v is None:
        return None
    try:
        if v != v:  # NaN is the only value that isn't equal to itself
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def platoon_factor(bat_side, pitch_hand):
    """League-average platoon multiplier for a batter/pitcher handedness matchup.
    Returns 1.0 (neutral) when either side is unknown or the batter is a switch
    hitter — never guesses when the data isn't there."""
    if not bat_side or not pitch_hand or bat_side == "S":
        return 1.0
    return PLATOON_DISADVANTAGE if bat_side == pitch_hand else PLATOON_ADVANTAGE


@st.cache_data(ttl=10800, show_spinner=False)
def fetch_recent_form(season: int, end_date_str: str, days: int = RECENT_FORM_DAYS):
    """Per-batter rates over the last `days` before end_date_str, in one bulk
    call. Used to nudge season rates toward current form. Returns
    dict{player_id: {pa, avg, obp, slg, hr_rate, hits_rate, rbi_rate, runs_rate}}."""
    try:
        end_d = datetime.strptime(str(end_date_str), "%Y-%m-%d").date()
    except Exception:
        return {}
    start_d = end_d - timedelta(days=days)
    data = safe_get("https://statsapi.mlb.com/api/v1/stats", {
        "stats": "byDateRange", "group": "hitting", "season": season,
        "sportId": 1, "playerPool": "ALL", "limit": 2000,
        "startDate": start_d.strftime("%m/%d/%Y"), "endDate": end_d.strftime("%m/%d/%Y"),
    })
    out = {}
    for split in data.get("stats", [{}])[
