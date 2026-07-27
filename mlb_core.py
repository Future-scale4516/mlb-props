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
    # Fitted using fit_calibration()'s own method (weighted decile-bucket
    # regression, shrink capped at 0.60) on 2 slates: 2026-07-22 and 2026-07-26,
    # ~2,570 graded Most-Likely picks. adjusted = raw*(1-shrink) + base*shrink.
    #
    # IMPORTANT: an earlier version of these numbers was fit by hand-solving
    # for "shrink that makes the mean match", which bypasses fit_calibration's
    # 0.60 safety cap and crushes variance along with bias — it made RBI (and
    # to a lesser extent Runs/Total Bases) barely respond to the raw model %
    # at all, which is why recommendations nearly disappeared. These values
    # are back on the proper method. Always regenerate via "Fit calibration
    # from backtest" on the Backtest page rather than solving by hand — two
    # slates is enough to see direction, not to lock these in for good.
    "Runs":        {"base": 0.28, "shrink": 0.42},  # slope 0.58 — real overconfidence, moderate correction
    "RBI":         {"base": 0.19, "shrink": 0.52},  # slope 0.48 — the least reliable market bar HR; corrected but not flattened
    "Total Bases": {"base": 0.24, "shrink": 0.56},  # ALSO gets a distribution fix (see p_total_bases_over)
    # Hits: fitted slope was 1.07 (i.e. raw_shrink went slightly negative,
    # capped at 0) — it was already well-calibrated, so no shrink is applied.
    # Home Run: only 94 picks across 2 nights produced just 1 usable decile
    # bucket — not enough to fit reliably (fit_calibration itself would refuse,
    # needing 3+ bands). Left uncorrected until more nights accumulate; treat
    # every HR pick as lower-confidence than its % suggests in the meantime.
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
    """Combine a park's static run/HR factors with today's weather.

    Keeps the raw weather/venue details (venue, temp, wind, dome) on the
    returned dict alongside the numeric "run"/"hr" multipliers, instead of
    discarding them once the multiplier is computed. Every existing caller
    that only reads park["hr"]/park["run"] is unaffected — this purely adds
    keys. The extra keys let build_prop_edges/build_most_likely surface the
    actual conditions (e.g. "82°F, wind 9mph out, Coors Field") instead of
    only ever showing their numeric effect on the model."""
    m = weather_multiplier(wx)
    return {
        "run": park.get("run", 1.0) * m,
        "hr": park.get("hr", 1.0) * m,
        "venue": wx.get("venue", ""),
        "temp": wx.get("temp"),
        "wind": wx.get("wind"),
        "dome": wx.get("dome", False),
    }


def _conditions_str(park):
    """Turn the enriched park dict (see apply_weather_to_park) into a short
    human-readable conditions string for display on a pick card, e.g.
    '82°F · wind 9mph · Coors Field' or '🏟️ Dome · Yankee Stadium'."""
    venue = park.get("venue") or ""
    if park.get("dome"):
        bits = ["🏟️ Dome"]
    else:
        bits = []
        if park.get("temp") is not None:
            bits.append(f"{int(round(park['temp']))}°F")
        if park.get("wind") is not None:
            bits.append(f"wind {int(round(park['wind']))}mph")
    if venue:
        bits.append(venue)
    return " · ".join(bits) if bits else ""


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
    for split in data.get("stats", [{}])[0].get("splits", []):
        p = split.get("player", {}); stat = split.get("stat", {})
        pid = int(p.get("id", 0) or 0)
        pa = int(stat.get("plateAppearances") or 0)
        if not pid or pa < MIN_PA_FOR_RECENT_FORM:
            continue
        out[pid] = {
            "pa": pa,
            "avg": float(stat.get("avg") or 0), "obp": float(stat.get("obp") or 0),
            "slg": float(stat.get("slg") or 0),
            "hr_rate": (int(stat.get("homeRuns") or 0)) / pa,
            "hits_rate": (int(stat.get("hits") or 0)) / pa,
            "rbi_rate": (int(stat.get("rbi") or 0)) / pa,
            "runs_rate": (int(stat.get("runs") or 0)) / pa,
        }
    return out


def blend_recent_form(srow, recent):
    """Return a copy of a batter's season stat row with rates nudged toward
    recent form. Weighted lightly (RECENT_FORM_WEIGHT) because short windows are
    noisy — this catches a genuine hot/cold streak without letting a good
    fortnight override a full season. Returns the row unchanged if there's no
    usable recent data."""
    if not recent:
        return srow
    spa = max(srow.get("plateAppearances", 1) or 1, 1)
    w = RECENT_FORM_WEIGHT
    out = dict(srow)
    for season_key, rate_key in (("hr", "hr_rate"), ("hits", "hits_rate"),
                                 ("rbi", "rbi_rate"), ("runs", "runs_rate")):
        season_rate = (srow.get(season_key, 0) or 0) / spa
        blended = season_rate * (1 - w) + recent[rate_key] * w
        out[season_key] = blended * spa  # keep it as a count; /spa downstream recovers the rate
    for k in ("avg", "obp", "slg"):
        if recent.get(k):
            out[k] = (srow.get(k, 0) or 0) * (1 - w) + recent[k] * w
    return out

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
def _snapshot_iso_for_start(start_iso, lead_minutes=60):
    """Timestamp to request for a game starting at start_iso — `lead_minutes`
    before first pitch, floored to a 5-minute boundary since that's the interval
    historical snapshots are stored at. Returns None if the start is unusable."""
    dt = _parse_iso_utc(start_iso)
    if dt is None:
        return None
    snap = dt - timedelta(minutes=lead_minutes)
    snap = snap.replace(minute=(snap.minute // 5) * 5, second=0, microsecond=0)
    return snap.strftime("%Y-%m-%dT%H:%M:%SZ")


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_historical_mlb_odds(snapshot_iso, regions="uk",
                               markets="h2h,spreads,totals", odds_format="decimal"):
    """Game odds as they stood at a past moment.

    COST WARNING: the historical endpoint bills 10 credits per region per market,
    so this call is 30 credits for three markets on one region — roughly ten
    times a live odds pull. Cached for a day since past odds never change."""
    key = get_secret("ODDS_API_KEY")
    if not key:
        return [], {"error": "No ODDS_API_KEY found in Streamlit secrets."}
    url = "https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/odds"
    try:
        r = req.get(url, params={
            "apiKey": key, "regions": regions, "markets": markets,
            "oddsFormat": odds_format, "dateFormat": "iso", "date": snapshot_iso,
        }, timeout=20)
    except Exception as e:
        return [], {"error": f"Request failed: {e}"}
    meta = {"status": r.status_code, "remaining": r.headers.get("x-requests-remaining"),
            "used": r.headers.get("x-requests-used"), "error": "",
            "snapshot_requested": snapshot_iso}
    if r.status_code != 200:
        meta["error"] = f"HTTP {r.status_code}: {r.text[:300]}"
        return [], meta
    try:
        payload = r.json()
    except Exception as e:
        meta["error"] = f"Bad JSON: {e}"
        return [], meta
    # Historical responses wrap the game list, unlike the live endpoint
    meta["snapshot_actual"] = payload.get("timestamp")
    return payload.get("data", []), meta


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_historical_event_props(event_id, markets, snapshot_iso,
                                  regions="us", odds_format="decimal"):
    """Player props for one game as they stood at a past moment. Costs about the
    same as the live event-odds call (markets x regions), not the 10x rate the
    featured historical endpoint charges."""
    key = get_secret("ODDS_API_KEY")
    if not key:
        return None, {"error": "No ODDS_API_KEY in Streamlit secrets."}
    url = ("https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/"
           f"events/{event_id}/odds")
    try:
        r = req.get(url, params={"apiKey": key, "regions": regions, "markets": markets,
                                 "oddsFormat": odds_format, "dateFormat": "iso",
                                 "date": snapshot_iso}, timeout=25)
    except Exception as e:
        return None, {"error": f"Request failed: {e}"}
    meta = {"status": r.status_code, "remaining": r.headers.get("x-requests-remaining"),
            "used": r.headers.get("x-requests-used"), "last": r.headers.get("x-requests-last"),
            "error": "", "snapshot_requested": snapshot_iso}
    if r.status_code != 200:
        meta["error"] = f"HTTP {r.status_code}: {r.text[:300]}"
        return None, meta
    try:
        payload = r.json()
    except Exception as e:
        meta["error"] = f"Bad JSON: {e}"
        return None, meta
    meta["snapshot_actual"] = payload.get("timestamp")
    data = payload.get("data", payload)  # unwrap if wrapped
    return data, meta


def historical_slate_odds(sched, regions="uk", lead_minutes=60):
    """Assemble game odds for a whole past slate, each game priced at its OWN
    snapshot (lead_minutes before that game's first pitch).

    Games starting close together share a snapshot, so this makes one call per
    DISTINCT snapshot time rather than one per game — on a typical slate that's
    a handful of calls instead of fifteen. Returns (odds_list, meta, snapshots)."""
    groups = {}
    for _, gm in sched.iterrows():
        snap = _snapshot_iso_for_start(gm.get("game_date_raw"), lead_minutes)
        if snap:
            groups.setdefault(snap, []).append(gm)
    merged, metas, used_snapshots = [], [], []
    seen_ids = set()
    for snap in sorted(groups):
        want_pairs = {((g.get("home_team") or "").lower().strip(),
                       (g.get("away_team") or "").lower().strip()) for g in groups[snap]}
        data, meta = fetch_historical_mlb_odds(snap, regions=regions)
        metas.append(meta)
        used_snapshots.append({"requested": snap, "actual": meta.get("snapshot_actual"),
                               "games": len(groups[snap]), "error": meta.get("error", "")})
        for ev in data:
            pair = ((ev.get("home_team") or "").lower().strip(),
                    (ev.get("away_team") or "").lower().strip())
            # only take games this snapshot was actually fetched for, so a game
            # isn't priced off some other game's snapshot time
            if pair in want_pairs and ev.get("id") not in seen_ids:
                merged.append(ev)
                seen_ids.add(ev.get("id"))
    combined = {"used": metas[-1].get("used") if metas else None,
                "remaining": metas[-1].get("remaining") if metas else None,
                "error": next((m.get("error") for m in metas if m.get("error")), ""),
                "calls": len(groups),
                "credits_estimate": len(groups) * 30}
    return merged, combined, used_snapshots


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
    """Consensus (median) decimal odds + best available price per outcome.
    Run line (spreads) is bucketed by point value, same as totals — a book
    occasionally posts an alternate run line (e.g. ±0.5 or ±2.5 alongside the
    standard ±1.5), and without bucketing, prices from different lines get
    silently averaged together into a number that doesn't price any single
    real market, which is why a paired-side implied-probability sum could come
    out far from a sane ~100-110% instead of reflecting one coherent line."""
    ml_home, ml_away = [], []
    rl_by_line = {}
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
                    if point is None: continue
                    abs_pt = abs(point)
                    slot = rl_by_line.setdefault(abs_pt, {"home": [], "away": []})
                    if name == home: slot["home"].append(price)
                    elif name == away: slot["away"].append(price)
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
    best_rl_line, best_rl_count = None, -1
    for pt, d in rl_by_line.items():
        c = min(len(d["home"]), len(d["away"]))
        if c > best_rl_count and c > 0:
            best_rl_count, best_rl_line = c, pt
    res = {"ml_home": _median(ml_home), "ml_away": _median(ml_away),
           "ml_home_best": max(ml_home) if ml_home else None,
           "ml_away_best": max(ml_away) if ml_away else None,
           "rl_home": None, "rl_away": None,
           "rl_home_best": None, "rl_away_best": None, "rl_line": best_rl_line,
           "total_line": best_line, "over": None, "under": None,
           "over_best": None, "under_best": None}
    if best_rl_line is not None:
        d = rl_by_line[best_rl_line]
        res["rl_home"], res["rl_away"] = _median(d["home"]), _median(d["away"])
        res["rl_home_best"] = max(d["home"]) if d["home"] else None
        res["rl_away_best"] = max(d["away"]) if d["away"] else None
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


MARKET_EDGE_BANDS = {
    # (no_signal_ceiling, green_ceiling, amber_ceiling): edge below the first
    # number is grey (no signal), between 1st-2nd is green, 2nd-3rd is amber,
    # at/above the 3rd is red. Markets with a long, clean backtest track record
    # (Moneyline, Run line, Total, Hits) keep the original baseline bands.
    # Home Run keeps baseline: its trust issue isn't edge size, it's inherent
    # rarity, which is handled separately as a flagged lottery pick rather than
    # by tightening these bands.
    #
    # RBI and Total Bases both sit at baseline (2, 8, 15) now. Both were
    # previously widened (RBI to (4,12,20), TB to (3,10,18)) to compensate for
    # overconfidence — but CALIBRATION_FITS now corrects that overconfidence
    # directly (fit properly via fit_calibration's bucketed regression, capped
    # at 0.60 shrink). Keeping the wide band ON TOP of a working calibration
    # double-corrected and suppressed nearly every pick in both markets. If a
    # market is already honest, it doesn't also need a bigger goalpost.
    #
    # Runs keeps a modest widening: even after proper calibration its fit slope
    # (0.58) was the second-weakest after RBI, so a slightly bigger edge is
    # asked for before trusting it. Revisit alongside RBI once more nights of
    # results come in — this whole set of bands is a rough placeholder, not a
    # tuned system.
    "Moneyline": (2, 8, 15), "Run line": (2, 8, 15), "Total": (2, 8, 15),
    "Hits": (2, 8, 15), "Home Run": (2, 8, 15), "Total Bases": (2, 8, 15),
    "RBI": (2, 8, 15),
    "Runs": (3, 10, 18),
}

MARKET_PROB_CEILING = {
    # A raw model probability above this ceiling is treated as implausible for
    # that market regardless of edge size — the same underlying problem as a
    # huge edge (a missing/broken input), just caught via the number itself
    # rather than the gap to market. E.g. a Moneyline pick at 95% could still
    # show a small, "green"-looking edge if the market also prices it high —
    # but 95% is barely ever a sane single-game probability in MLB, and the
    # small edge wouldn't catch that on its own.
    "Moneyline": 90, "Run line": 88, "Total": 85, "Hits": 88,
    "Runs": 65, "RBI": 60, "Total Bases": 80, "Home Run": 20,
}


def _edge_light(edge, market=None):
    """Traffic-light banding for an edge (percentage points). Uses market-
    specific bands when a market is given; falls back to the original baseline
    bands otherwise (kept for any caller that doesn't pass one)."""
    if edge is None:
        return ""
    lo, mid, hi = MARKET_EDGE_BANDS.get(market, (2, 8, 15))
    if edge >= hi:
        return "🔴"
    if edge >= mid:
        return "🟡"
    if edge >= lo:
        return "🟢"
    return "⚪"


def classify_pick(edge, model_pct, market=None):
    """Full traffic-light classification: checks the raw model probability for
    plausibility FIRST — a suspiciously high probability is a red flag on its
    own, even paired with a small edge — then falls back to the market-specific
    edge bands. This is the function every page/build should use; _edge_light
    alone only ever sees the edge, never the raw probability."""
    ceiling = MARKET_PROB_CEILING.get(market, 95)
    if model_pct is not None and model_pct > ceiling:
        return "🔴"
    return _edge_light(edge, market)


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


def _parse_iso_utc(iso):
    """Parse an ISO UTC timestamp (either API's format) into a naive datetime for
    time-distance comparisons. Returns None on failure."""
    if not iso:
        return None
    try:
        return datetime.strptime(str(iso).replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _index_by_teams(items, home_key, away_key):
    """Build a {(home,away): [items]} index that keeps ALL matches per team pair,
    not just the last one. Doubleheaders mean the same two teams can appear twice
    in one day's odds or schedule — a plain dict comprehension silently drops one
    of them; this keeps both so they can be disambiguated by kickoff time."""
    idx = {}
    for it in items:
        home = (it.get(home_key) or "").lower().strip()
        away = (it.get(away_key) or "").lower().strip()
        idx.setdefault((home, away), []).append(it)
    return idx


def _pick_closest_time(candidates, target_dt, time_getter):
    """From a list of candidate dicts, return the one whose parsed time is closest
    to target_dt. Falls back to the first candidate if timestamps are unusable —
    this only matters when there are 2+ candidates (a doubleheader); with exactly
    one candidate it's a no-op."""
    if not candidates:
        return None
    if len(candidates) == 1 or target_dt is None:
        return candidates[0]
    best, best_diff = candidates[0], None
    for c in candidates:
        c_dt = _parse_iso_utc(time_getter(c))
        if c_dt is None:
            continue
        diff = abs((c_dt - target_dt).total_seconds())
        if best_diff is None or diff < best_diff:
            best, best_diff = c, diff
    return best


def _dh_suffix(gm):
    """(1)/(2) suffix for a schedule row that's part of a doubleheader, else ''."""
    try:
        gn = int(gm.get("game_number", 1) or 1)
    except Exception:
        gn = 1
    dh = str(gm.get("double_header", "N") or "N")
    return f" ({gn})" if dh in ("Y", "S") and gn else ""


def render_pick_card(light, title, subtitle, metrics, reason=None, conditions=None):
    """Render one betting pick as a compact, mobile-friendly card instead of a
    wide table row — a light+title header, one dense line of metrics, and
    optional reason/conditions captions underneath. `metrics` is a list of
    (label, value) tuples joined into a single small-text line — deliberately
    NOT one st.metric widget per value, since those are large KPI-style
    displays by design and were the main driver of how much vertical space
    each card took. Everything stacks vertically, avoiding the horizontal-
    scroll problem st.dataframe has on narrow phone screens.

    `conditions` is a short string like "82°F · wind 9mph · Coors Field" —
    kept as its own line rather than folded into `reason`, so the matchup
    rationale and the live conditions behind it stay visually distinct."""
    with st.container(border=True):
        header = f"{light} **{title}**" if light else f"**{title}**"
        st.markdown(header)
        if subtitle:
            st.caption(subtitle)
        st.caption("  ·  ".join(f"{label}: {value}" for label, value in metrics))
        if reason:
            st.caption(reason)
        if conditions:
            st.caption(f"📍 {conditions}")


def sort_picker(df, sort_options, key):
    """Show a small selectbox letting the user choose how a card list is
    sorted, then return the dataframe sorted accordingly. sort_options is a
    list of (label, column, ascending) tuples; the first one is the default —
    this replaces the click-a-column-header sorting st.dataframe gave for free,
    which cards don't have since they're not a grid."""
    labels = [lbl for lbl, _, _ in sort_options]
    choice = st.selectbox("Sort by", labels, key=key)
    _, col, asc = next(o for o in sort_options if o[0] == choice)
    return df.sort_values(col, ascending=asc).reset_index(drop=True)


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


def build_game_edges(sel_date, odds_override=None, meta_override=None):
    """Match today's games to UK odds, run the model, return (df, note, meta)."""
    refresh_league_averages(sel_date.year)  # current league baselines, not stale constants
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, "No games scheduled for this date.", {}
    team_off, league_rpg = fetch_team_offense(sel_date.year)
    bullpen_era = fetch_bullpen_era(sel_date.year)
    if odds_override is not None:
        # Reconstructing a past slate from historical snapshots — see
        # historical_slate_odds. Skips the live fetch entirely.
        odds_data, meta = odds_override, (meta_override or {})
    else:
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
    odds_index = _index_by_teams(odds_data, "home_team", "away_team")

    rows, unmatched, game_time, game_conf = [], [], {}, {}
    for _, gm in sched.iterrows():
        home, away = gm.get("home_team"), gm.get("away_team")
        candidates = odds_index.get((norm(home), norm(away)), [])
        if not candidates:
            hk = norm(home).split()[-1] if norm(home).split() else ""
            ak = norm(away).split()[-1] if norm(away).split() else ""
            for (oh, oa), cands in odds_index.items():
                if hk and ak and oh.endswith(hk) and oa.endswith(ak):
                    candidates = cands; break
        # Doubleheaders put two odds events under the same team-name key — pick
        # whichever one's kickoff time is actually closest to THIS schedule row's
        # real start time, rather than silently taking whichever came first/last.
        og = _pick_closest_time(candidates, _parse_iso_utc(gm.get("game_date_raw")),
                                 lambda c: c.get("commence_time"))
        if not og:
            unmatched.append(f"{away} @ {home}"); continue

        hid = int(gm.get("home_team_id") or 0)
        aid = int(gm.get("away_team_id") or 0)
        pf = PARK_FACTORS.get(hid, NEUTRAL_PARK)
        # Same-day weather on top of the park's static factor (see weather_multiplier)
        _wx = fetch_weather(gm.get("venue", ""))
        pf = apply_weather_to_park(pf, _wx)
        _wx_known = bool(gm.get("venue")) and gm.get("venue") in BALLPARKS
        home_rpg = _park_neutral_rpg(team_off.get(hid, league_rpg), pf["run"])
        away_rpg = _park_neutral_rpg(team_off.get(aid, league_rpg),
                                     PARK_FACTORS.get(aid, NEUTRAL_PARK)["run"])
        away_sp = fetch_pitcher_stats(gm.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(gm.get("home_prob_id"))
        away_bp = bullpen_era.get(aid, LEAGUE_BULLPEN_ERA_DEFAULT)
        home_bp = bullpen_era.get(hid, LEAGUE_BULLPEN_ERA_DEFAULT)
        _pitchers_known = (away_sp.get("name", "TBD") != "TBD"
                           and home_sp.get("name", "TBD") != "TBD")
        _conf_level, _conf_missing = data_confidence(
            pitcher_known=_pitchers_known, lineup_confirmed=True,
            batter_pa=None, handedness_known=True, weather_known=_wx_known)
        cons = consolidate_odds(og, og.get("home_team"), og.get("away_team"))
        mdl = model_game(home_rpg, away_rpg, away_sp.get("era", 4.5),
                         home_sp.get("era", 4.5), league_rpg, LEAGUE_ERA_DEFAULT,
                         cons.get("total_line"), park=pf["run"],
                         home_opp_bullpen_era=away_bp, away_opp_bullpen_era=home_bp)
        gl = f"{TEAM_ABBR.get(aid, away)} @ {TEAM_ABBR.get(hid, home)}{_dh_suffix(gm)}"
        ct = og.get("commence_time") or ""
        game_time[gl] = (ct, _commence_to_bst(ct), _commence_to_et_str(ct))
        game_conf[gl] = (_conf_level, _conf_missing)

        home_era = home_sp.get("era", 4.5)
        away_era = away_sp.get("era", 4.5)
        gpk = gm.get("gamePk")
        fh, fa = devig_two(cons["ml_home"], cons["ml_away"])
        if fh is not None:
            e, v = edge_ev(mdl["p_home_ml"], fh, cons["ml_home_best"])
            rows.append([gl, "Moneyline", home, mdl["p_home_ml"], fh, e, cons["ml_home_best"], v,
                         _ml_rl_reason(home_rpg, away_rpg, home_era, away_era, away_bp),
                         gpk, "home", None, None])
            e, v = edge_ev(mdl["p_away_ml"], fa, cons["ml_away_best"])
            rows.append([gl, "Moneyline", away, mdl["p_away_ml"], fa, e, cons["ml_away_best"], v,
                         _ml_rl_reason(away_rpg, home_rpg, away_era, home_era, home_bp),
                         gpk, "away", None, None])
        frh, fra = devig_two(cons["rl_home"], cons["rl_away"])
        # The model only ever computes "win by 2+ runs" (a 1.5-run margin) — only
        # show Run Line when that's genuinely the line being priced, so a "-1.5"/
        # "+1.5" label is never paired with a probability computed for a different
        # margin (this is what the bucket-by-point fix above makes possible to check).
        rl_is_standard = cons.get("rl_line") is not None and abs(cons["rl_line"] - 1.5) < 0.01
        if frh is not None and rl_is_standard:
            e, v = edge_ev(mdl["p_home_cover"], frh, cons["rl_home_best"])
            rows.append([gl, "Run line", f"{home} -1.5", mdl["p_home_cover"], frh, e, cons["rl_home_best"], v,
                         _ml_rl_reason(home_rpg, away_rpg, home_era, away_era, away_bp),
                         gpk, "home", 1.5, None])
            e, v = edge_ev(mdl["p_away_cover"], fra, cons["rl_away_best"])
            rows.append([gl, "Run line", f"{away} +1.5", mdl["p_away_cover"], fra, e, cons["rl_away_best"], v,
                         _ml_rl_reason(away_rpg, home_rpg, away_era, home_era, home_bp),
                         gpk, "away", 1.5, None])
        fo, fu = devig_two(cons["over"], cons["under"])
        if fo is not None and cons["total_line"] is not None:
            ln = cons["total_line"]
            e, v = edge_ev(mdl["p_over"], fo, cons["over_best"])
            rows.append([gl, "Total", f"Over {ln}", mdl["p_over"], fo, e, cons["over_best"], v,
                         _total_reason(home_rpg, away_rpg, home_era, away_era, pf, "Over",
                                       home_bp, away_bp),
                         gpk, None, ln, "Over"])
            e, v = edge_ev(mdl["p_under"], fu, cons["under_best"])
            rows.append([gl, "Total", f"Under {ln}", mdl["p_under"], fu, e, cons["under_best"], v,
                         _total_reason(home_rpg, away_rpg, home_era, away_era, pf, "Under",
                                       home_bp, away_bp),
                         gpk, None, ln, "Under"])

    if not rows:
        return None, "No matched games with usable odds.", meta
    df = pd.DataFrame(rows, columns=["Game", "Market", "Selection",
                                     "Model %", "Fair %", "Edge", "Odds", "EV %", "Reason",
                                     "GamePk", "Side", "Threshold", "Direction"])
    df["Model %"] = (df["Model %"] * 100).round(1)
    df["Fair %"] = (df["Fair %"] * 100).round(1)
    df["Edge"] = df["Edge"].round(1)
    df["EV %"] = df["EV %"].round(1)
    df["_ct"] = df["Game"].map(lambda g: game_time.get(g, ("", "", ""))[0])
    df["Start"] = df["Game"].map(lambda g: game_time.get(g, ("", "", ""))[1])
    df["US Date"] = df["Game"].map(lambda g: game_time.get(g, ("", "", ""))[2])
    df["Confidence"] = df["Game"].map(lambda g: game_conf.get(g, ("high", []))[0])
    df["DataNotes"] = df["Game"].map(lambda g: "; ".join(game_conf.get(g, ("high", []))[1]))
    df = df.sort_values(["_ct", "Game"]).reset_index(drop=True)
    note = (f"Couldn't match odds for: {', '.join(unmatched)}" if unmatched else "")
    return df, note, meta


LG_HR9 = 1.15   # league avg HR allowed per 9 innings
LG_K9 = 8.5     # league avg K per 9 innings
LG_WHIP = 1.30  # league avg walks+hits per inning pitched
LG_OBP_DEFAULT = 0.320  # league avg on-base %, used for "table setters ahead" context
MIN_PA_FOR_RANKING = 30  # batters below this get excluded from prop rankings/edges —
                          # below this, season SLG/AVG/OBP are mostly noise from a
                          # handful of at-bats (e.g. a 2-game callup with one lucky
                          # double looks like an elite slugger with zero real evidence)
LG_SLG_DEFAULT = 0.400  # league avg slugging, used for "run producers behind" context


def _p_over_line(expected_count, point):
    """P(count > point) via Poisson(expected_count). point like 0.5 / 1.5 / 2.5.

    Correct for genuine COUNT markets — HR, hits, RBI, runs — where each event is
    a discrete +1 that arrives roughly independently across a game. Do NOT use it
    for Total Bases: bases don't arrive as independent +1 events (one home run is
    +4 at once) and are capped by the batter's ~4 at-bats, so a Poisson badly
    over-weights the tail. Use p_total_bases_over() for that market instead.
    """
    if point is None or expected_count is None:
        return None
    need = int(math.floor(point)) + 1
    cum = sum(_pois_pmf(i, expected_count) for i in range(need))
    return max(0.0, min(1.0, 1.0 - cum))


# Share of a batter's hits that are singles / doubles / triples / home runs,
# league-wide. Used to turn "expected total bases" into a real per-at-bat base
# distribution rather than pretending bases trickle in one Poisson event at a
# time. Roughly the long-run MLB hit-type split; refined by fit if needed.
LG_HIT_TYPE_SPLIT = {1: 0.62, 2: 0.20, 3: 0.02, 4: 0.16}  # 1B, 2B, 3B, HR shares
LG_TB_PER_HIT = sum(bases * share for bases, share in LG_HIT_TYPE_SPLIT.items())  # ~1.72


def p_total_bases_over(exp_tb, point, ab=4.0):
    """P(total bases > point) for one batter in one game, modelled properly.

    The old approach fed `exp_tb` (a continuous expectation like 1.4 bases) into a
    Poisson P(>=2), which assumes bases arrive as many independent +1 events. They
    don't: a single swing yields 0/1/2/3/4 bases at once, and the whole total is
    capped by ~4 at-bats. That mis-shape put far too much probability in the 2+
    tail and was the single biggest source of Total-Bases overconfidence in the
    tracked results.

    Instead: split `exp_tb` across `ab` at-bats. Each at-bat independently either
    produces no bases (an out) or a hit worth 1/2/3/4 bases in the league hit-type
    proportions. We derive the per-at-bat hit probability `h` from
    exp_tb = ab * h * TB_per_hit, then enumerate the exact P(0 total) and
    P(1 total) and return 1 - those for the standard 1.5 (i.e. "2+") line. For
    other points we fall back to a short convolution over at-bat outcomes.
    """
    if point is None or exp_tb is None or exp_tb <= 0:
        return None
    ab_int = max(1, int(round(ab)))
    h = exp_tb / (ab_int * LG_TB_PER_HIT)
    h = min(max(h, 0.0), 0.95)  # per-AB probability of getting a hit at all

    # Per-at-bat base-count distribution: P(0 bases)=1-h, then h split by hit type.
    per_ab = {0: 1.0 - h}
    for bases, share in LG_HIT_TYPE_SPLIT.items():
        per_ab[bases] = h * share

    # Convolve `ab_int` independent at-bats into a total-bases distribution.
    dist = {0: 1.0}
    for _ in range(ab_int):
        nxt = {}
        for tot, ptot in dist.items():
            for bases, pb in per_ab.items():
                nxt[tot + bases] = nxt.get(tot + bases, 0.0) + ptot * pb
        dist = nxt

    need = int(math.floor(point)) + 1
    p_at_least = sum(p for tot, p in dist.items() if tot >= need)
    return max(0.0, min(1.0, p_at_least))


@st.cache_data(ttl=86400, show_spinner=False)
def _league_averages_cached(season):
    """Cached wrapper so the league-average API call happens at most once a day."""
    return compute_league_pitching_averages(season)


def refresh_league_averages(season):
    """Update the module-level LG_* pitching constants from the season's real data.
    Call once at the start of any build so every downstream model uses current
    league baselines instead of the hardcoded fallbacks. Safe to call repeatedly —
    the underlying fetch is cached for a day, and any stat that can't be computed
    keeps its existing value. Returns the dict actually applied, for display."""
    global LG_HR9, LG_K9, LG_WHIP, LEAGUE_ERA_DEFAULT
    avgs = _league_averages_cached(season)
    # Only overwrite with sane, positive numbers — never let a bad fetch zero these.
    if avgs.get("hr9", 0) > 0:
        LG_HR9 = avgs["hr9"]
    if avgs.get("k9", 0) > 0:
        LG_K9 = avgs["k9"]
    if avgs.get("whip", 0) > 0:
        LG_WHIP = avgs["whip"]
    if avgs.get("era", 0) > 0:
        LEAGUE_ERA_DEFAULT = avgs["era"]
    return avgs


def _prop_prob(market_key, lam_dict, point):
    """Single entry point for turning a batter's expected-count vector into a
    P(over the line) for a given prop market. Total Bases uses the compound
    per-at-bat model (bases arrive in clumps, capped by at-bats); every other
    market is a genuine count and uses the Poisson. Callers should use this
    rather than calling _p_over_line directly, so the TB special-case can never
    be forgotten at one of the several call sites."""
    if market_key == "batter_total_bases":
        return p_total_bases_over(lam_dict["batter_total_bases"], point)
    return _p_over_line(lam_dict.get(market_key), point)


def compute_league_pitching_averages(season):
    """Compute league-wide HR/9, K/9, WHIP and ERA from the season's actual
    pitching data, instead of relying on the hardcoded LG_* constants. Returns a
    dict; any stat that can't be computed falls back to its hardcoded default so
    this can never make things worse than the frozen constants did.

    Why this exists: the MLB Stats API gives per-player and per-team stats, but
    NOT league baselines — those were hand-typed constants (LG_HR9=1.15 etc.) that
    never updated as the season moved. Every prop's pitcher adjustment is measured
    relative to these baselines, so a stale baseline biases every pick. Computing
    them from the same data we already pull keeps them honest and current.
    """
    fallback = {"hr9": LG_HR9, "k9": LG_K9, "whip": LG_WHIP, "era": LEAGUE_ERA_DEFAULT}
    try:
        data = safe_get("https://statsapi.mlb.com/api/v1/stats", {
            "stats": "season", "group": "pitching", "season": season,
            "sportId": 1, "playerPool": "ALL", "limit": 3000,
        })
        splits = data.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return fallback
        tot_hr = tot_so = tot_bb = tot_h = tot_er = tot_outs = 0.0
        for s in splits:
            stt = s.get("stat", {})
            tot_hr += float(stt.get("homeRuns") or 0)
            tot_so += float(stt.get("strikeOuts") or 0)
            tot_bb += float(stt.get("baseOnBalls") or 0)
            tot_h += float(stt.get("hits") or 0)
            tot_er += float(stt.get("earnedRuns") or 0)
            tot_outs += _ip_to_outs(stt.get("inningsPitched"))
        ip = tot_outs / 3.0
        if ip <= 0:
            return fallback
        return {
            "hr9": round(tot_hr * 9 / ip, 3),
            "k9": round(tot_so * 9 / ip, 3),
            "whip": round((tot_bb + tot_h) / ip, 3),
            "era": round(tot_er * 9 / ip, 3),
        }
    except Exception:
        return fallback


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

    The correction is a simple linear shrinkage toward a base rate. The numbers
    live in CALIBRATION_FITS below — update them by running "Fit calibration
    from backtest" on the Backtest page, which derives them from the actual
    reliability curve rather than by eye."""
    fit = CALIBRATION_FITS.get(market)
    if not fit or not fit.get("shrink"):
        return raw_p
    return raw_p * (1 - fit["shrink"]) + fit["base"] * fit["shrink"]


def fit_calibration(recs, market, min_samples=200):
    """Derive a calibration correction for one market from real backtest records
    instead of setting it by eye.

    Method: the correction we apply is `adjusted = p*(1-s) + b*s`, which
    rearranges to `adjusted = p*(1-s) + (b*s)`. That's just a straight line in
    p — so fitting it is a weighted least-squares regression of what ACTUALLY
    happened against what the model PREDICTED, across the decile buckets, with
    each bucket weighted by how many samples it holds (so sparse bands like the
    thin upper HR buckets can't drag the fit around).

    slope = 1 - shrink, intercept = base * shrink.

    Returns (fit_dict_or_None, message)."""
    rows = [(p, o) for mk, p, o in recs if mk == market]
    if len(rows) < min_samples:
        return None, f"{market}: only {len(rows)} samples, need {min_samples}+ to fit reliably."

    buckets = {}
    for p, o in rows:
        b = min(int(p * 10), 9)
        buckets.setdefault(b, []).append((p, o))
    pts = []
    for b, vals in buckets.items():
        n = len(vals)
        if n < 20:
            continue  # too thin to trust this band at all
        mean_p = sum(v[0] for v in vals) / n
        actual = sum(v[1] for v in vals) / n
        pts.append((mean_p, actual, n))
    if len(pts) < 3:
        return None, f"{market}: only {len(pts)} usable probability bands, need 3+."

    tot_w = sum(n for _, _, n in pts)
    mean_x = sum(x * n for x, _, n in pts) / tot_w
    mean_y = sum(y * n for _, y, n in pts) / tot_w
    num = sum(n * (x - mean_x) * (y - mean_y) for x, y, n in pts)
    den = sum(n * (x - mean_x) ** 2 for x, _, n in pts)
    if den <= 0:
        return None, f"{market}: predictions show no spread, can't fit."
    slope = num / den
    intercept = mean_y - slope * mean_x

    shrink = 1.0 - slope
    if shrink <= 0.01:
        return ({"base": 0.0, "shrink": 0.0},
                f"{market}: already well calibrated (slope {slope:.2f}) — no correction needed.")
    shrink = min(shrink, 0.60)  # never shrink more than 60% toward base
    base = intercept / shrink
    base = max(0.0, min(base, 1.0))
    return ({"base": round(base, 3), "shrink": round(shrink, 3)},
            f"{market}: fitted from {len(rows)} samples across {len(pts)} bands "
            f"(slope {slope:.3f}).")


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
                          park_hr=1.0, park_run=1.0, platoon=1.0):
    """Expected per-game counts (Poisson lambdas) for each batter prop market.
    Season rate carries the hitter's talent; pitcher + park + lineup are the
    adjustments. HR uses the opposing starter's HR9, Hits uses their K9. RBI uses
    the pitcher's WHIP (baserunners allowed) AND the OBP of the batters hitting
    ahead of him (real traffic on base for him to drive in — the pitcher's WHIP
    alone doesn't say whether THIS batter's teammates are the ones reaching).
    Runs uses WHIP plus the SLG of the batters hitting behind him (someone has to
    drive him in once he's on base). Total Bases is built from the batter's own
    SLG (bases per at-bat) — a good pitcher's low HR9 suppresses power, a high K9
    suppresses contact overall, and park blends both HR- and hit-friendliness
    since extra-base hits benefit from both."""
    # `platoon` is the handedness multiplier (see platoon_factor). It's applied to
    # the markets that depend on the batter actually squaring the ball up — HR,
    # Hits, Total Bases — at full strength. RBI and Runs get a damped version,
    # since those depend heavily on teammates (traffic ahead, power behind) as
    # well as the batter's own contact, so the platoon edge is diluted.
    platoon_damped = 1.0 + (platoon - 1.0) * 0.5

    spa = max(stat.get("plateAppearances", 1) or 1, 1)
    hr_l = (stat.get("hr", 0) / spa) * (opp_hr9 / LG_HR9) * park_hr * platoon * pa
    hits = stat.get("hits")
    hit_rate = (hits / spa) if hits is not None else stat.get("avg", 0) * 0.88
    k_factor = 1.0 - 0.5 * min(max((opp_k9 - LG_K9) / LG_K9, -0.3), 0.3)
    hit_l = hit_rate * k_factor * (1.0 + 0.5 * (park_run - 1.0)) * platoon * pa

    whip_factor = 1.0 + 0.5 * min(max((opp_whip - LG_WHIP) / LG_WHIP, -0.3), 0.3)
    traffic_factor = 1.0 + 0.6 * min(max((ahead_obp - LG_OBP_DEFAULT) / LG_OBP_DEFAULT, -0.4), 0.4)
    rbi_l = (stat.get("rbi", 0) / spa) * (0.6 + 0.4 * park_run) * whip_factor * traffic_factor * platoon_damped * pa

    support_factor = 1.0 + 0.5 * min(max((behind_slg - LG_SLG_DEFAULT) / LG_SLG_DEFAULT, -0.4), 0.4)
    run_l = (stat.get("runs", 0) / spa) * (0.6 + 0.4 * park_run) * whip_factor * support_factor * platoon_damped * pa

    ab_est = pa * 0.89  # rough PA->AB conversion; ~11% of PA are walks/HBP/sac
    power_factor = 1.0 + 0.5 * min(max((opp_hr9 - LG_HR9) / LG_HR9, -0.3), 0.3)
    tb_park = 0.6 * park_hr + 0.4 * park_run
    tb_l = stat.get("slg", LG_SLG_DEFAULT) * ab_est * k_factor * power_factor * tb_park * platoon

    return {"batter_home_runs": hr_l, "batter_hits": hit_l,
            "batter_rbis": rbi_l, "batter_runs_scored": run_l,
            "batter_total_bases": tb_l}


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


# Typical bookmaker overround (vig) on a single-sided player prop line, when
# we only have one side quoted and can't de-vig properly against its
# opposite. This is an approximation, not a measured constant — but using it
# is a lot closer to true fair value than using the raw vig-included price
# outright, which is what was happening before.
TYPICAL_PROP_OVERROUND = 0.06


def market_prob(over_odds, under_odds):
    """Fair P(over): de-vig if both sides quoted, else back out an approximate
    fair price from the single side using TYPICAL_PROP_OVERROUND, rather than
    using the raw vig-included implied probability directly.

    Why this matters: 1/odds on a single side includes the book's margin, so
    it's a few points HIGHER than true fair value (typically 2-5 pts at normal
    prop overrounds). Edge = model% - fair%, so treating that inflated number
    as "fair" silently shrinks every genuine edge computed this way — exactly
    the kind of gap that pushes a real signal into the "no signal" band. This
    haircut is an approximation (we don't know the book's actual margin
    without both sides), but it's much closer than not correcting at all.
    """
    if over_odds and under_odds:
        fo, _ = devig_two(over_odds, under_odds)
        return fo, "de-vig"
    if over_odds:
        raw = min(1 / over_odds, 0.999)
        approx_fair = raw / (1 + TYPICAL_PROP_OVERROUND)
        return max(0.001, min(approx_fair, 0.999)), "raw (overround-adjusted)"
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
    elif mkey == "batter_runs_scored":
        if behind_slg >= 0.430:
            bits.append(f"power hitters behind (.{int(round(behind_slg*1000)):03d} SLG)")
        if order and order <= 5:
            bits.append(f"bats #{order} (more chances)")
        rate = srow.get("runs", 0) / spa
        if rate >= 0.13:
            bits.append("high rate for this market")
        if park["run"] >= 1.05:
            bits.append("hitter-friendly park")
    else:  # batter_total_bases
        if srow.get("slg", 0) >= 0.460:
            bits.append(f"strong slugger (.{int(round(srow.get('slg', 0) * 1000)):03d} SLG)")
        if opp_hr9 >= 1.4:
            bits.append(f"HR-prone starter ({opp_hr9:.1f} HR/9)")
        if opp_k9 <= 7.5:
            bits.append(f"low-strikeout starter ({opp_k9:.1f} K/9)")
        if park["hr"] >= 1.05:
            bits.append("hitter-friendly park")
    if not bits:
        return "Edge from market pricing, not a standout matchup"
    return ("; ".join(bits[:3]))[:1].upper() + ("; ".join(bits[:3]))[1:]


def build_prop_edges(sel_date, max_games=6, snapshot_by_event=None,
                     odds_override=None, meta_override=None):
    """Full slate prop edges: per-game props adjusted for the opposing starter and
    ballpark. Returns (df, meta, note). Green+amber only (edge 2-15) is filtered in UI."""
    refresh_league_averages(sel_date.year)  # current league baselines, not stale constants
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, {}, "No games scheduled for this date."
    if odds_override is not None:
        odds_games, meta = odds_override, (meta_override or {})
    else:
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
    bats_map, throws_map = fetch_player_handedness(sel_date.year)
    recent_map = fetch_recent_form(sel_date.year, str(sel_date))

    def norm(s): return (s or "").lower().strip()
    sched_index = _index_by_teams([gm for _, gm in sched.iterrows()], "home_team", "away_team")

    PROP_MARKETS = "batter_home_runs,batter_hits,batter_rbis,batter_runs_scored,batter_total_bases"
    LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
             "batter_rbis": "RBI", "batter_runs_scored": "Runs",
             "batter_total_bases": "Total Bases"}
    cols = ["Market", "Light", "Player", "Game", "Start", "Line",
            "Model %", "Market %", "Edge", "Best over", "Reason", "Conditions",
            "GamePk", "PlayerID", "MarketKey", "Point"]
    rows, unmatched = [], []
    analysed, last_meta = 0, meta

    for ev in odds_games:
        if analysed >= max_games:
            break
        home, away = ev.get("home_team"), ev.get("away_team")
        candidates = sched_index.get((norm(home), norm(away)), [])
        if not candidates:
            hk = norm(home).split()[-1] if norm(home).split() else ""
            ak = norm(away).split()[-1] if norm(away).split() else ""
            for (oh, oa), cands in sched_index.items():
                if hk and ak and oh.endswith(hk) and oa.endswith(ak):
                    candidates = cands; break
        # Same doubleheader disambiguation as build_game_edges: pick the schedule
        # row whose real kickoff is closest to this specific odds event's time.
        gm = _pick_closest_time(candidates, _parse_iso_utc(ev.get("commence_time")),
                                 lambda c: c.get("game_date_raw"))
        if gm is None:
            unmatched.append(f"{away} @ {home}"); continue

        _snap = (snapshot_by_event or {}).get(ev.get("id"))
        if _snap:
            event, em = fetch_historical_event_props(ev.get("id"), PROP_MARKETS,
                                                      _snap, regions="us")
        else:
            event, em = fetch_event_props(ev.get("id"), PROP_MARKETS, regions="us")
        analysed += 1
        if em.get("remaining"):
            last_meta = em
        if em.get("error") or not event:
            continue

        home_id = int(gm.get("home_team_id") or 0)
        away_id = int(gm.get("away_team_id") or 0)
        park = apply_weather_to_park(PARK_FACTORS.get(home_id, NEUTRAL_PARK),
                                      fetch_weather(gm.get("venue", "")))
        away_pid_p, home_pid_p = gm.get("away_prob_id"), gm.get("home_prob_id")
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

        gl = f"{TEAM_ABBR.get(away_id, away)} @ {TEAM_ABBR.get(home_id, home)}{_dh_suffix(gm)}"
        start = _commence_to_bst(ev.get("commence_time") or "")
        for mkey in PROP_MARKETS.split(","):
            for player, od in consolidate_prop(event, mkey).items():
                srow = name_map.get(player.lower())
                if not srow:
                    ln = player.lower().split()[-1] if player else ""
                    srow = next((v for k, v in name_map.items() if k.split()[-1] == ln), None)
                if not srow:
                    continue
                if (srow.get("plateAppearances") or 0) < MIN_PA_FOR_RANKING:
                    continue  # too small a sample — season rates would be mostly noise
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
                lineup_confirmed = pid in order_map
                ahead_obp, behind_slg = _lineup_context(
                    order, lineup_by_team.get(tid, {}), stat_by_id)
                opp_pid = away_pid_p if tid == home_id else (home_pid_p if tid == away_id else None)
                _opp_pid_i = _safe_int(opp_pid)
                pf_platoon = platoon_factor(bats_map.get(pid),
                                            throws_map.get(_opp_pid_i) if _opp_pid_i else None)
                srow_eff = blend_recent_form(srow, recent_map.get(pid))
                lam = prop_expected_counts(srow_eff, expected_pa(order), opp_hr9, opp_k9, opp_whip,
                                           ahead_obp, behind_slg, park["hr"], park["run"],
                                           platoon=pf_platoon)
                mp = _prop_prob(mkey, lam, od["point"])
                if mp is not None:
                    mp = _calibration_adjust(mp, LABEL[mkey])
                bp, mode = market_prob(od["over"], od["under"])
                if mp is None or bp is None:
                    continue
                edge = (mp - bp) * 100
                mkt_label = LABEL[mkey]
                _lo, _mid, _hi = MARKET_EDGE_BANDS.get(mkt_label, (2, 8, 15))
                if not (_lo <= edge < _hi):
                    continue
                _cond = _conditions_str(park)
                if not lineup_confirmed:
                    _cond += " · ⏳ lineup not yet confirmed (assumed order)"
                rows.append([mkt_label, classify_pick(edge, mp * 100, mkt_label),
                             player, gl, start, f"O{od['point']}",
                             round(mp * 100, 1), round(bp * 100, 1), round(edge, 1),
                             od["over_best"], _prop_reason(mkey, srow, opp_hr9, opp_k9, park,
                                                            order, ahead_obp, behind_slg),
                             _cond,
                             gm.get("gamePk"), pid, mkey, od["point"]])

    note = f"Analysed {analysed} game(s)."
    if unmatched:
        note += f" Couldn't match: {', '.join(unmatched[:4])}."
    return pd.DataFrame(rows, columns=cols), last_meta, note


MARKET_TRUST_TIER = {
    # Relative weights for stake allocation. Updated from a mix of backtest history
    # AND real tracked results: Moneyline stays top-tier (consistently the steadiest
    # market across real slips). Total Bases promoted after two strong real nights
    # in a row, including harder "2+" threshold picks landing cleanly. Run Line
    # holds steady. Runs and RBI demoted — both have shown genuine "hit and miss"
    # nights in real tracking (RBI's historically weaker calibration, Runs' first
    # clean 0-for-3 miss), so they get a smaller slice while that's the pattern.
    # Totals unchanged, no strong signal either way yet. Home Run is NOT part of
    # this proportional split — see suggest_stakes, it's a flat small lottery slice.
    "Moneyline": 3.0, "Total Bases": 2.5, "Run Line": 2.0,
    "Totals": 1.5, "Runs": 1.5, "RBI": 0.75,
}


def _normalize_game_row(row):
    return {"label": row["Selection"], "game": row["Game"], "odds": float(row["Odds"]),
            "model_pct": float(row["Model %"]), "reason": row.get("Reason", ""),
            "kind": "game", "market": row["Market"], "game_pk": row.get("GamePk"),
            "side": row.get("Side"), "threshold": row.get("Threshold"),
            "direction": row.get("Direction")}


def _normalize_prop_row(row):
    return {"label": f"{row['Player']} {row['Line']}", "game": row["Game"],
            "odds": float(row["Best over"]), "model_pct": float(row["Model %"]),
            "reason": row.get("Reason", ""),
            "kind": "prop", "market": row["Market"], "game_pk": row.get("GamePk"),
            "player_id": row.get("PlayerID"), "market_key": row.get("MarketKey"),
            "point": row.get("Point")}


def _best_combo(candidates, n_legs, normalize_fn):
    """Greedily pick the n_legs highest-Model% rows from DIFFERENT games (ranked by
    raw model probability, not edge size — a bigger amber edge isn't automatically
    riskier if the underlying probability is still sane). Returns None if fewer than
    n_legs distinct-game candidates are available."""
    if candidates is None or candidates.empty:
        return None
    sorted_df = candidates.sort_values("Model %", ascending=False)
    chosen, used_games = [], set()
    for _, row in sorted_df.iterrows():
        norm = normalize_fn(row)
        if norm["game"] in used_games:
            continue
        chosen.append(norm)
        used_games.add(norm["game"])
        if len(chosen) == n_legs:
            break
    if len(chosen) < n_legs:
        return None
    combined_odds = 1.0
    combined_prob = 1.0
    for leg in chosen:
        combined_odds *= leg["odds"]
        combined_prob *= leg["model_pct"] / 100.0
    return {"legs": chosen, "combined_odds": combined_odds, "combined_prob": combined_prob}


def build_suggested_bets(sel_date, prop_max_games=6):
    """Auto-build green/amber (edge 2-15) doubles and trebles across Moneyline, Run
    Line, Totals, Runs, RBI, Total Bases, and Home Run (Hits excluded — use the
    dedicated Player Props page for that). Ranked by raw Model %, no two legs from
    the same game. Returns (results dict keyed by market, quota metadata dict)."""
    results = {}
    quota_meta = {}

    gdf, gnote, gmeta = build_game_edges(sel_date)
    quota_meta["game"] = gmeta
    for label in ["Moneyline", "Run line", "Total"]:
        out_key = {"Moneyline": "Moneyline", "Run line": "Run Line", "Total": "Totals"}[label]
        if gdf is not None and not gdf.empty:
            _lo, _mid, _hi = MARKET_EDGE_BANDS.get(label, (2, 8, 15))
            sub = gdf[(gdf["Market"] == label) & (gdf["Edge"] >= _lo) & (gdf["Edge"] < _hi)]
            results[out_key] = {
                "double": _best_combo(sub, 2, _normalize_game_row),
                "treble": _best_combo(sub, 3, _normalize_game_row),
                "note": "" if not sub.empty else "No green/amber picks in this market today.",
            }
        else:
            results[out_key] = {"double": None, "treble": None, "note": gnote or "No game odds available."}

    pdf, pmeta, pnote = build_prop_edges(sel_date, prop_max_games)
    quota_meta["props"] = pmeta
    for market in ["Runs", "RBI", "Total Bases", "Home Run"]:
        if pdf is not None and not pdf.empty:
            sub = pdf[pdf["Market"] == market]
            results[market] = {
                "double": _best_combo(sub, 2, _normalize_prop_row),
                "treble": _best_combo(sub, 3, _normalize_prop_row),
                "note": "" if not sub.empty else "No green/amber picks in this market today.",
            }
        else:
            results[market] = {"double": None, "treble": None, "note": pnote or "No prop odds available."}

    return results, quota_meta


def suggest_stakes(bankroll, markets_with_bets):
    """Allocate a bankroll across markets by trust tier. Home Run always gets a
    flat £1 'lottery ticket' stake — deliberately NOT scaled to bankroll, since
    it's a for-fun long shot regardless of how much you're staking overall, not
    a market that should get proportionally more just because the bankroll is
    bigger."""
    stakes = {}
    has_hr = "Home Run" in markets_with_bets
    hr_flat = min(1.0, bankroll) if has_hr else 0.0
    remaining = bankroll - hr_flat
    other_markets = [m for m in markets_with_bets if m != "Home Run"]
    total_weight = sum(MARKET_TRUST_TIER.get(m, 1.0) for m in other_markets)
    if has_hr:
        stakes["Home Run"] = hr_flat
    for m in other_markets:
        w = MARKET_TRUST_TIER.get(m, 1.0)
        stakes[m] = round(remaining * w / total_weight, 2) if total_weight > 0 else 0.0
    return stakes



def build_most_likely(sel_date, max_games=15):
    """Rank batters by the model's raw probability of recording >=1 of each prop
    market (no odds, no quota), using confirmed lineups, opposing starter and park."""
    refresh_league_averages(sel_date.year)  # current league baselines, not stale constants
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, "No games scheduled for this date."
    bat = fetch_all_mlb_batting_stats(sel_date.year)
    if bat.empty:
        return None, "No batter stats available."
    stat_by_id = {int(r["player_id"]): r for r in bat.to_dict("records") if r.get("player_id")}
    bats_map, throws_map = fetch_player_handedness(sel_date.year)
    recent_map = fetch_recent_form(sel_date.year, str(sel_date))
    LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
             "batter_rbis": "RBI", "batter_runs_scored": "Runs"}
    rows, n, no_lineups = [], 0, 0
    for _, gm in sched.iterrows():
        if n >= max_games:
            break
        hid = int(gm.get("home_team_id") or 0)
        aid = int(gm.get("away_team_id") or 0)
        park = apply_weather_to_park(PARK_FACTORS.get(hid, NEUTRAL_PARK),
                                      fetch_weather(gm.get("venue", "")))
        away_sp = fetch_pitcher_stats(gm.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(gm.get("home_prob_id"))
        try:
            lu = fetch_live_lineups(int(gm.get("gamePk")))
        except Exception:
            lu = {}
        gl = f"{TEAM_ABBR.get(aid, gm.get('away_team'))} @ {TEAM_ABBR.get(hid, gm.get('home_team'))}{_dh_suffix(gm)}"
        start = gm.get("game_time_bst", "")
        had = False
        for side, opp_sp, opp_pid_ml in (("home", away_sp, gm.get("away_prob_id")),
                                          ("away", home_sp, gm.get("home_prob_id"))):
            d = lu.get(side)
            if d is None or d.empty:
                continue
            had = True
            _opp_pid_ml_i = _safe_int(opp_pid_ml)
            opp_hand = throws_map.get(_opp_pid_ml_i) if _opp_pid_ml_i else None
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
                if (srow.get("plateAppearances") or 0) < MIN_PA_FOR_RANKING:
                    continue  # too small a sample — season rates would be mostly noise
                order = int(pr.get("order", 5) or 5)
                _bpid = int(pr["player_id"])
                ahead_obp, behind_slg = _lineup_context(order, slot_to_pid, stat_by_id)
                pf_platoon = platoon_factor(bats_map.get(_bpid), opp_hand)
                srow_eff = blend_recent_form(srow, recent_map.get(_bpid))
                lam = prop_expected_counts(srow_eff, expected_pa(order), opp_hr9, opp_k9, opp_whip,
                                           ahead_obp, behind_slg, park["hr"], park["run"],
                                           platoon=pf_platoon)
                probs = {}
                player_name = pr.get("name") or srow.get("name")
                for mkey, lbl in LABEL.items():
                    p = _p_over_line(lam[mkey], 0.5)
                    if p is not None:
                        p = _calibration_adjust(p, lbl)
                    probs[mkey] = p
                    rows.append([lbl, player_name, gl, start,
                                 int(order), round(p * 100, 1), _conditions_str(park)])
                # combo: P(at least one of hits/runs/RBI >= 1)
                cp = _combo_prob(probs)
                if cp is not None:
                    rows.append(["Runs+Hits+RBI (1+)", player_name, gl, start,
                                 int(order), round(cp * 100, 1), _conditions_str(park)])
                # Total Bases: expected value, not a "1+" probability (any hit is
                # already >=1 TB, so a threshold framing would just duplicate Hits)
                rows.append(["Total Bases (expected)", player_name, gl, start,
                             int(order), round(lam["batter_total_bases"], 2), _conditions_str(park)])
        if not had:
            no_lineups += 1
        n += 1
    if not rows:
        return None, "No confirmed lineups posted yet for these games (try closer to first pitch)."
    df = pd.DataFrame(rows, columns=["Market", "Player", "Game", "Start", "Order", "Value", "Conditions"])
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
    refresh_league_averages(sel_date.year)  # match the baselines live builds use
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


def _parse_boxscore_batters(data):
    """Shared parsing logic for boxscore batter data — used by both the long-TTL
    backtest version (finished games only) and the short-TTL live-check version
    (a game still in progress, where stats change inning to inning)."""
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
                "total_bases": int(bat.get("totalBases") or 0),
            })
    return out


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_boxscore_batters(game_pk):
    """Actual batter box-score lines (hits, HR, RBI, runs, batting order) for a
    completed game. Free MLB data, used to score the prop model in the backtest.
    Long TTL is fine here since backtests only ever look at already-finished games."""
    if not game_pk:
        return []
    data = safe_get(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")
    return _parse_boxscore_batters(data)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_boxscore_batters_live(game_pk):
    """Same data as fetch_boxscore_batters but with a short TTL, for checking a
    batter's CURRENT stat line during a game still in progress — the long-TTL
    version would otherwise serve a stale snapshot for the rest of the game."""
    if not game_pk:
        return []
    data = safe_get(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")
    return _parse_boxscore_batters(data)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_game_state(game_pk):
    """Current score/state for a single game — works whether it hasn't started,
    is in progress, or has finished. Short TTL so re-checking mid-game is fresh."""
    if not game_pk:
        return {"status": "Unknown", "home_runs": None, "away_runs": None}
    data = safe_get(f"https://statsapi.mlb.com/api/v1.1/game/{int(game_pk)}/feed/live")
    game_state = data.get("gameData", {}).get("status", {}).get("abstractGameState", "Preview")
    linescore = data.get("liveData", {}).get("linescore", {})
    teams = linescore.get("teams", {})
    return {
        "status": game_state,  # "Preview" | "Live" | "Final"
        "home_runs": teams.get("home", {}).get("runs"),
        "away_runs": teams.get("away", {}).get("runs"),
        "inning": linescore.get("currentInning"),
        "inning_state": linescore.get("inningState", ""),
    }


_PROP_STAT_KEY = {"batter_home_runs": "hr", "batter_hits": "hits", "batter_rbis": "rbi",
                  "batter_runs_scored": "runs", "batter_total_bases": "total_bases"}


def evaluate_leg_status(leg):
    """Check a single suggested-bet leg against live/final MLB data. Returns
    (status, detail) where status is one of: 'pending' (game not started),
    'winning'/'losing' (live, currently on/off track), 'won'/'lost' (final),
    or 'unknown' (couldn't determine — e.g. a push, or data unavailable)."""
    gpk = leg.get("game_pk")
    if not gpk:
        return "unknown", "No game data available for this leg."
    state = fetch_live_game_state(gpk)
    game_status = state.get("status", "Preview")
    if game_status == "Preview":
        return "pending", "Game hasn't started yet."

    if leg["kind"] == "game":
        hr, ar = state.get("home_runs"), state.get("away_runs")
        if hr is None or ar is None:
            return "unknown", "Live score unavailable."
        market = leg["market"]
        if market == "Moneyline":
            side = leg["side"]
            team_r = hr if side == "home" else ar
            opp_r = ar if side == "home" else hr
            tied = team_r == opp_r
            ahead = team_r > opp_r
        elif market == "Run Line":
            side = leg["side"]
            margin = leg.get("threshold") or 1.5
            team_r = hr if side == "home" else ar
            opp_r = ar if side == "home" else hr
            diff = team_r - opp_r
            ahead = diff >= margin if side == "home" else diff > -margin
            tied = False
        elif market == "Totals":
            total = hr + ar
            line = leg.get("threshold")
            direction = leg.get("direction")
            ahead = total > line if direction == "Over" else total < line
            tied = total == line
        else:
            return "unknown", "Unrecognized market for live checking."

        if game_status == "Final":
            if tied:
                return "unknown", f"Final {ar}-{hr} — push or unusual result, check manually."
            return ("won" if ahead else "lost"), f"Final score: {ar} away, {hr} home."
        return ("winning" if ahead else "losing"), \
               f"Live: {ar} away, {hr} home (inning {state.get('inning')})."

    # prop leg
    pid = leg.get("player_id")
    mkey = leg.get("market_key")
    point = leg.get("point")
    if not pid or not mkey or point is None:
        return "unknown", "Missing player/market data for this leg."
    box = fetch_boxscore_batters_live(int(gpk)) if game_status != "Final" \
        else fetch_boxscore_batters(int(gpk))
    player_row = next((b for b in box if b.get("player_id") == pid), None)
    if player_row is None:
        return "pending", "Not in the box score yet — hasn't batted, or not starting."
    actual = player_row.get(_PROP_STAT_KEY.get(mkey), 0)
    ahead = actual > point
    if game_status == "Final":
        return ("won" if ahead else "lost"), f"Final: {actual} (needed more than {point})."
    return ("winning" if ahead else "losing"), f"So far: {actual} (needed more than {point})."


def evaluate_combo_status(combo):
    """Overall verdict for a combo: one lost leg kills the whole thing regardless
    of the others; all legs won means the combo won; otherwise it's still alive
    (a mix of pending/winning/won legs), unless something couldn't be determined."""
    leg_results = [evaluate_leg_status(leg) for leg in combo["legs"]]
    statuses = [s for s, _ in leg_results]
    if "lost" in statuses:
        overall = "lost"
    elif all(s == "won" for s in statuses):
        overall = "won"
    elif "unknown" in statuses:
        overall = "unknown"
    else:
        overall = "alive"
    return overall, leg_results





def build_priced_results(sel_date, max_games=8, lead_minutes=60):
    """Reconstruct the value picks the app WOULD have shown for a past date —
    using real bookmaker odds from a snapshot `lead_minutes` before each game's
    first pitch — then score them against the actual box scores.

    Unlike build_prop_results (model reads only), this includes the real edge,
    traffic-light colour and price, because historical odds are available on a
    paid plan. It costs real credits: roughly 30 per distinct snapshot time for
    game lines, plus ~5 per game for props.

    Returns (df, note, cost_info)."""
    sched = fetch_schedule(str(sel_date))
    if sched.empty:
        return None, "No games scheduled for that date.", {}

    odds, ometa, snaps = historical_slate_odds(sched, regions="uk",
                                               lead_minutes=lead_minutes)
    if not odds:
        err = ometa.get("error") or ""
        return None, (f"No historical odds returned for that date. {err}").strip(), \
               {"snapshots": snaps, "credits_estimate": ometa.get("credits_estimate", 0)}

    snap_by_event = {}
    for ev in odds:
        s = _snapshot_iso_for_start(ev.get("commence_time"), lead_minutes)
        if s:
            snap_by_event[ev.get("id")] = s

    pdf, pmeta, pnote = build_prop_edges(sel_date, max_games,
                                         snapshot_by_event=snap_by_event,
                                         odds_override=odds, meta_override=ometa)

    # ALSO reconstruct + grade game-line picks (Moneyline / Run line / Total)
    # from the SAME historical odds fetch. Reusing the odds we already paid for
    # means this adds zero Odds API cost — just the free MLB final-score lookup.
    gdf, gnote, _ = build_game_edges(sel_date,
                                     odds_override=odds, meta_override=ometa)
    finals = fetch_results(str(sel_date))
    final_by_gpk = {f["gamePk"]: f for f in finals}
    game_rows = []
    if isinstance(gdf, pd.DataFrame) and not gdf.empty:
        for _, r in gdf.iterrows():
            gp = r.get("GamePk")
            fin = final_by_gpk.get(int(gp)) if gp else None
            if not fin:
                continue  # game not completed yet
            hs, as_ = int(fin["home_score"]), int(fin["away_score"])
            mkt = r["Market"]
            side = r.get("Side")
            hit = None
            if mkt == "Moneyline":
                hit = (hs > as_) if side == "home" else (as_ > hs)
            elif mkt == "Run line":
                hit = ((hs - as_) >= 2) if side == "home" else ((as_ - hs) >= 2)
            elif mkt == "Total":
                tot, ln = hs + as_, float(r.get("Threshold") or 0)
                direction = r.get("Direction")
                if direction == "Over":
                    hit = tot > ln
                elif direction == "Under":
                    hit = tot < ln
            if hit is None:
                continue
            odds_dec = float(r.get("Odds") or 0)
            pl = (odds_dec - 1.0) if hit else -1.0
            game_rows.append({
                "Market": mkt, "Light": classify_pick(r["Edge"], r["Model %"], mkt),
                "Player": r["Selection"], "Game": r["Game"], "Line": r.get("Threshold") or "",
                "Model %": r["Model %"], "Market %": r["Fair %"], "Edge": r["Edge"],
                "Odds": odds_dec, "Actual": f"{as_}-{hs}", "Hit": bool(hit),
                "P/L (1u)": round(pl, 2), "Reason": r.get("Reason", ""),
            })

    cost = {"snapshots": snaps,
            "game_line_credits": ometa.get("credits_estimate", 0),
            "prop_games": min(max_games, len(odds)),
            "remaining": pmeta.get("remaining") if pmeta else ometa.get("remaining"),
            "game_picks_graded": len(game_rows)}
    if (pdf is None or pdf.empty) and not game_rows:
        return None, (pnote or gnote or "No qualifying value picks found for that date."), cost

    ACTUAL_KEY = {"batter_home_runs": "hr", "batter_hits": "hits",
                  "batter_rbis": "rbi", "batter_runs_scored": "runs",
                  "batter_total_bases": "total_bases"}
    box_by_game = {}
    for gp in pdf["GamePk"].dropna().unique():
        box_by_game[int(gp)] = {int(b["player_id"]): b
                                for b in fetch_boxscore_batters(int(gp))
                                if b.get("player_id")}

    rows = []
    for _, r in pdf.iterrows():
        gp = r.get("GamePk")
        pid = r.get("PlayerID")
        mkey = r.get("MarketKey")
        point = r.get("Point")
        if gp is None or pid is None or mkey not in ACTUAL_KEY or point is None:
            continue
        b = box_by_game.get(int(gp), {}).get(int(pid))
        if not b:
            continue  # didn't appear in the box score (scratched, or DNP)
        actual = b.get(ACTUAL_KEY[mkey], 0)
        hit = bool(actual > float(point))
        odds_dec = float(r.get("Best over") or 0)
        # Profit on a 1-unit stake at the price that was actually available
        pl = (odds_dec - 1.0) if hit else -1.0
        rows.append({
            "Market": r["Market"], "Light": r["Light"], "Player": r["Player"],
            "Game": r["Game"], "Line": r["Line"],
            "Model %": r["Model %"], "Market %": r["Market %"], "Edge": r["Edge"],
            "Odds": odds_dec, "Actual": actual, "Hit": hit,
            "P/L (1u)": round(pl, 2), "Reason": r.get("Reason", ""),
        })

    all_rows = rows + game_rows
    if not all_rows:
        return None, ("Picks were reconstructed, but no matching results were "
                      "found — the games may not have completed yet."), cost
    summary = f"Reconstructed and scored {len(rows)} prop picks and {len(game_rows)} game-line picks."
    return pd.DataFrame(all_rows), summary, cost


def build_game_results(sel_date):
    """Score the model's game-line predictions for ONE date against real final scores.
    Returns (df, note).

    Same idea and same limitation as build_prop_results: The Odds API doesn't
    serve historical prices, so this reconstructs the MODEL's own read (Moneyline
    home/away win prob, Run Line -1.5/+1.5 cover prob, Total over/under prob)
    from the real starters, real bullpens and real park, then checks it against
    the real final score. It answers \"was the model's game-level read right?\",
    not \"what odds were available at the time?\" — for that use build_priced_results
    which now also grades game bets when historical odds are on the plan.

    Output columns mirror build_prop_results so the same downstream export/CSV
    logic works: Result, Market, Selection, Line, Model %, Actual, Game, Score.
    Selection covers both sides (e.g. two Moneyline rows per game, one per team),
    so the tracked hit rate reflects every prediction the model made, not just
    the favored side."""
    refresh_league_averages(sel_date.year)
    results = fetch_results(str(sel_date))
    if not results:
        return None, ("No completed games on this date yet — game-line results "
                      "appear once games finish.")
    team_off, league_rpg = fetch_team_offense(sel_date.year)
    bullpen_era = fetch_bullpen_era(sel_date.year)

    rows = []
    for r in results:
        hid = int(r.get("home_team_id") or 0)
        aid = int(r.get("away_team_id") or 0)
        if not hid or not aid:
            continue
        hs, as_ = int(r.get("home_score") or 0), int(r.get("away_score") or 0)

        pf = PARK_FACTORS.get(hid, NEUTRAL_PARK)
        home_rpg = _park_neutral_rpg(team_off.get(hid, league_rpg), pf["run"])
        away_rpg = _park_neutral_rpg(team_off.get(aid, league_rpg),
                                     PARK_FACTORS.get(aid, NEUTRAL_PARK)["run"])
        away_sp = fetch_pitcher_stats(r.get("away_prob_id"))
        home_sp = fetch_pitcher_stats(r.get("home_prob_id"))
        away_bp = bullpen_era.get(aid, LEAGUE_BULLPEN_ERA_DEFAULT)
        home_bp = bullpen_era.get(hid, LEAGUE_BULLPEN_ERA_DEFAULT)

        # No historical total line available from The Odds API, so use the
        # league-neutral 8.5 for a totals reconstruction. It's a rough anchor
        # rather than the real closing line, but it's consistent across dates.
        mdl = model_game(home_rpg, away_rpg,
                         away_sp.get("era", 4.5), home_sp.get("era", 4.5),
                         league_rpg, LEAGUE_ERA_DEFAULT, total_line=8.5,
                         park=pf["run"],
                         home_opp_bullpen_era=away_bp, away_opp_bullpen_era=home_bp)

        home_ab = TEAM_ABBR.get(hid, r.get("home_team", "HOME"))
        away_ab = TEAM_ABBR.get(aid, r.get("away_team", "AWAY"))
        gl = f"{away_ab} @ {home_ab}"
        score_txt = f"{as_}-{hs}"

        # Shape matches build_prop_results so one Streamlit page can render both:
        # Hit (bool), Player (the pick label), Market/Line/Model %/Actual/Game/Score.
        def add(mkt, sel, line, model_p, hit):
            rows.append({
                "Market": mkt, "Player": sel, "Line": line,
                "Model %": round(model_p * 100, 1),
                "Actual": score_txt,          # game outcome is the score itself
                "Hit": bool(hit),
                "Game": gl, "Score": score_txt,
            })

        # Moneyline — both sides. Exactly one wins.
        add("Moneyline", home_ab, "ML", mdl["p_home_ml"], hs > as_)
        add("Moneyline", away_ab, "ML", mdl["p_away_ml"], as_ > hs)

        # Run line — home -1.5 / away +1.5. Exactly one covers by 2+.
        add("Run line", f"{home_ab} -1.5", "-1.5", mdl["p_home_cover"], (hs - as_) >= 2)
        add("Run line", f"{away_ab} +1.5", "+1.5", mdl["p_away_cover"], (as_ - hs) >= 2)

        # Total — over/under 8.5 (the anchor line the model was run at). No
        # historical odds means we can't match each game's actual closing total,
        # so we anchor at league-neutral 8.5 and grade against it — model % is
        # meaningful in absolute terms, but "edge vs the book" isn't recoverable.
        tot = hs + as_
        add("Total", "Over 8.5", "O8.5", mdl["p_over"], tot > 8.5)
        add("Total", "Under 8.5", "U8.5", mdl["p_under"], tot < 8.5)

    if not rows:
        return None, "No game results could be reconstructed."
    df = pd.DataFrame(rows)
    return df, f"Scored {len(df)} game-line predictions across {len(results)} completed games."


def build_prop_results(sel_date, max_games=None):
    """Score the model's own prop predictions for ONE date against what actually
    happened in the box scores. Returns (df, note).

    Important limitation, stated plainly: The Odds API only serves current and
    upcoming odds, not historical ones. So for a date that's already played,
    the bookmaker prices — and therefore the edge, the green/amber colour, and
    which specific combos Suggested Bets built — genuinely cannot be
    reconstructed. What CAN be rebuilt is the model's own probability for every
    batter, using the real lineup and starter from that game, and checked
    against the real result. That's what this does: it answers "were the
    model's reads right?", not "what price was showing at the time?"."""
    results = fetch_day_results(str(sel_date))
    finals = [r for r in results if r.get("state") == "Final"]
    if not finals:
        return None, ("No completed games on this date yet — results appear once "
                      "games finish.")
    if max_games:
        finals = finals[:max_games]

    bat = fetch_all_mlb_batting_stats(sel_date.year)
    if bat.empty:
        return None, "No batter stats available."
    stat_by_id = {int(r["player_id"]): r for r in bat.to_dict("records") if r.get("player_id")}
    bats_map, throws_map = fetch_player_handedness(sel_date.year)

    LABEL = {"batter_home_runs": "Home Run", "batter_hits": "Hits",
             "batter_rbis": "RBI", "batter_runs_scored": "Runs"}
    ACTUAL_KEY = {"batter_home_runs": "hr", "batter_hits": "hits",
                  "batter_rbis": "rbi", "batter_runs_scored": "runs",
                  "batter_total_bases": "total_bases"}

    rows, games_scored = [], 0
    for r in finals:
        gp = r.get("gamePk")
        if not gp:
            continue
        box = fetch_boxscore_batters(gp)
        if not box:
            continue
        games_scored += 1
        hid = int(r.get("home_team_id") or 0)
        aid = int(r.get("away_team_id") or 0)
        park = apply_weather_to_park(PARK_FACTORS.get(hid, NEUTRAL_PARK),
                                     fetch_weather(r.get("venue", "")))
        sched_rows = fetch_schedule(str(sel_date))
        gm_row = None
        if not sched_rows.empty:
            match = sched_rows[sched_rows["gamePk"] == gp]
            if not match.empty:
                gm_row = match.iloc[0]
        away_pid = gm_row.get("away_prob_id") if gm_row is not None else None
        home_pid = gm_row.get("home_prob_id") if gm_row is not None else None
        away_sp = fetch_pitcher_stats(away_pid)
        home_sp = fetch_pitcher_stats(home_pid)

        slot_by_team = {hid: {}, aid: {}}
        for b in box:
            tid_b = b.get("team_id")
            if tid_b in slot_by_team and b.get("order"):
                slot_by_team[tid_b][int(b["order"])] = b["player_id"]

        gl = f"{TEAM_ABBR.get(aid, r.get('away_team',''))} @ {TEAM_ABBR.get(hid, r.get('home_team',''))}"
        score_txt = f"{r.get('away_score')}-{r.get('home_score')}"

        for b in box:
            pid = int(b.get("player_id") or 0)
            srow = stat_by_id.get(pid)
            if not srow:
                continue
            if (srow.get("plateAppearances") or 0) < MIN_PA_FOR_RANKING:
                continue
            is_home = b.get("team_id") == hid
            opp_sp = away_sp if is_home else home_sp
            opp_pid = away_pid if is_home else home_pid
            opp_hr9 = float(opp_sp.get("homeRunsPer9", LG_HR9) or LG_HR9)
            opp_k9 = float(opp_sp.get("strikeoutsPer9Inn", LG_K9) or LG_K9)
            opp_whip = float(opp_sp.get("whip", LG_WHIP) or LG_WHIP)
            ahead_obp, behind_slg = _lineup_context(
                b["order"], slot_by_team.get(b["team_id"], {}), stat_by_id)
            _opp_pid_i = _safe_int(opp_pid)
            pf_platoon = platoon_factor(bats_map.get(pid),
                                        throws_map.get(_opp_pid_i) if _opp_pid_i else None)
            lam = prop_expected_counts(srow, expected_pa(b["order"]), opp_hr9, opp_k9,
                                       opp_whip, ahead_obp, behind_slg,
                                       park["hr"], park["run"], platoon=pf_platoon)

            for mkey, label in LABEL.items():
                p = _p_over_line(lam[mkey], 0.5)
                if p is None:
                    continue
                p = _calibration_adjust(p, label)
                actual = b.get(ACTUAL_KEY[mkey], 0)
                rows.append({
                    "Market": label, "Player": b.get("name", ""), "Game": gl,
                    "Score": score_txt, "Slot": b["order"],
                    "Model %": round(p * 100, 1), "Line": "1+",
                    "Actual": actual, "Hit": bool(actual >= 1),
                })
            # Total Bases is judged at 2+ (a single already gives 1 TB, so a
            # 1+ line would just duplicate the Hits market). Uses the compound
            # per-at-bat model, not Poisson — see p_total_bases_over.
            p_tb = _prop_prob("batter_total_bases", lam, 1.5)
            if p_tb is not None:
                actual_tb = b.get("total_bases", 0)
                rows.append({
                    "Market": "Total Bases", "Player": b.get("name", ""), "Game": gl,
                    "Score": score_txt, "Slot": b["order"],
                    "Model %": round(p_tb * 100, 1), "Line": "2+",
                    "Actual": actual_tb, "Hit": bool(actual_tb > 1.5),
                })

    if not rows:
        return None, "No box-score data available for this date's games yet."
    df = pd.DataFrame(rows)
    return df, f"Scored {games_scored} completed game(s) on {sel_date}."



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
                # Total Bases tested at a 1.5 line (i.e. 2+ bases) rather than 0.5 —
                # any single already counts as 1 TB, so a 0.5 threshold would just
                # duplicate the Hits market and tell us nothing new. Uses the
                # compound per-at-bat model, not Poisson — see p_total_bases_over.
                p_tb = _prop_prob("batter_total_bases", lam, 1.5)
                if p_tb is not None:
                    outcome_tb = 1 if b["total_bases"] > 1.5 else 0
                    recs.append(("Total Bases (2+)", p_tb, outcome_tb))
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
