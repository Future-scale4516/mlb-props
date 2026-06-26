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
        if side.lower() in k.lower() and "batter" in k.lower():
            batting_key = k
            break
    if not batting_key:
        return pd.DataFrame()
    batters = box.get(batting_key, [])
    if isinstance(batters, dict):
        batters = list(batters.values())
    for i, p in enumerate(batters):
        rows.append({
            "player_id": p.get("playerID", ""),
            "name":      p.get("longName", p.get("name", "Unknown")),
            "order":     int(p.get("battingOrder", i + 1) or i + 1),
        })
    return pd.DataFrame(rows).sort_values("order") if rows else pd.DataFrame()

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_odds_api(api_key: str):
    if not api_key or not api_key.strip():
        return {}
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": api_key, "regions": "uk",
        "markets": "h2h,spreads,totals",
        "bookmakers": "williamhill,paddypower,betfair,bet365,skybet",
        "oddsFormat": "decimal"
    }
    try:
        r = req.get(url, params=params, timeout=15)
        r.raise_for_status()
        res = r.json()
        out = {}
        if isinstance(res, list):
            for item in res:
                key = f"{item.get('away_team')} @ {item.get('home_team')}"
                out[key] = item.get("bookmakers", [])
        return out
    except Exception:
        return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue_name: str):
    meta = BALLPARKS.get(venue_name)
    if not meta:
        return {"temp": 72, "wind": 8, "factor": 1.00, "dome": False}
    if meta["dome"]:
        return {"temp": 72, "wind": 0, "factor": meta["factor"], "dome": True}
    try:
        data = safe_get("https://api.open-meteo.com/v1/forecast", {
            "latitude": meta["lat"], "longitude": meta["lon"],
            "current": "temperature_2m,wind_speed_10m",
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph"
        })
        c = data.get("current", {})
        return {"temp": float(c.get("temperature_2m") or 72),
                "wind": float(c.get("wind_speed_10m") or 8),
                "factor": meta["factor"], "dome": False}
    except Exception:
        return {"temp": 72, "wind": 8, "factor": meta["factor"], "dome": False}

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp - 70) * 0.003 + wind * 0.004

def score_batter(avg, obp, slg, iso, wrc_plus, hard_hit, barrel,
                 order, era, whip, hr9, k9, env):
    of_map = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}
    of    = of_map.get(order, 0.80)
    pv    = min(era / 7.0, 1.0) * 0.55 + min(max((whip - 0.8) / 1.2, 0.0), 1.0) * 0.45
    hrv   = min(hr9 / 2.5, 1.0)
    k_adj = 1.0 - min((k9 - 7.0) / 14.0, 0.20)
    contact  = avg * 0.35 + obp * 0.30 + (wrc_plus / 200) * 0.25 + 0.78 * 0.10
    power    = iso * 0.40 + hard_hit * 0.35 + barrel * 0.25
    on_base  = obp * (wrc_plus / 100)
    hits_score = round(contact * pv * of * k_adj * env * 280, 2)
    rbi_score  = round(contact * pv * (1.0 + max(0, (5 - order) * 0.04)) * k_adj * env * 260, 2)
    hr_score   = round(power * hrv * env * 280, 2)
    runs_score = round(on_base * pv * (1.0 + max(0, (4 - order) * 0.05)) * k_adj * env * 280, 2)
    if iso < 0.130 or barrel < 0.04 or hr9 < 0.7:
        hr_score = 0.0
    if order > 7 or wrc_plus < 80:
        rbi_score = 0.0
    if order > 5 or obp < 0.290:
        runs_score = 0.0
    return {"Hits/Runs": hits_score, "RBI": rbi_score,
            "Home Run": hr_score, "Runs Scored": runs_score}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## MLB Analytics Control")
    odds_key = st.text_input("The-Odds-API Key (optional)", value="", type="password")
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Model Filters")
    # Defaults lowered so stats always show regardless of data quality
    min_avg = st.slider("Min AVG",   0.000, 0.350, 0.000, 0.005, format="%.3f")
    min_obp = st.slider("Min OBP",   0.000, 0.400, 0.000, 0.005, format="%.3f")
    max_ord = st.slider("Max Batting Order", 1, 9, 9)
    debug   = st.checkbox("Show raw API data (debug)", value=False)
    st.markdown("---")
    if st.button("Clear Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "game_proj_dict", "odds_data", "debug_rosters"]:
            st.session_state.pop(k, None)
        st.rerun()

st.title("MLB Full-Game & Prop Value Matrix")
st.caption("Powered by Tank01 MLB API (RapidAPI) | Weather via Open-Meteo | Odds via The-Odds-API")
st.divider()

# ── LOAD SLATE ────────────────────────────────────────────────────────────────
if st.button("Load Today's Slate", type="primary"):
    tank01_date = sel_date.strftime("%Y%m%d")

    with st.status("Fetching games from Tank01...", expanded=True) as status:
        sched = fetch_games_for_date(tank01_date)
        if sched.empty:
            st.error(f"No games found for {sel_date}. Check your RapidAPI subscription or try a different date.")
            st.stop()

        st.write(f"Found {len(sched)} games. Fetching rosters...")
        odds_data = fetch_live_odds_api(odds_key)
        st.session_state["odds_data"] = odds_data

        all_rows, game_projections, debug_rosters = [], {}, {}

        for _, g in sched.iterrows():
            away_abv  = g["away_abv"]
            home_abv  = g["home_abv"]
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            game_id   = g["gameID"]

            wx        = fetch_weather(g["venue"])
            total_env = wx["factor"] * wx_modifier(wx["temp"], wx["wind"], wx["dome"])
            env_label = "Hitter-Friendly" if total_env >= 1.06 else "Neutral" if total_env >= 0.97 else "Pitcher-Friendly"
            wx_str    = "Dome" if wx["dome"] else f"{int(wx['temp'])}F | {int(wx['wind'])} mph wind"

            box          = fetch_box_score(game_id)
            away_lineup  = parse_lineup_from_boxscore(box, "away")
            home_lineup  = parse_lineup_from_boxscore(box, "home")
            lineup_badge = "Confirmed" if (not away_lineup.empty and not home_lineup.empty) else "Projected"

            away_raw    = fetch_team_roster_raw(away_abv, sel_date.year)
            home_raw    = fetch_team_roster_raw(home_abv, sel_date.year)
            away_roster = parse_roster(away_raw)
            home_roster = parse_roster(home_raw)

            # Store first game's raw data for debug view
            if not debug_rosters:
                debug_rosters["game"]       = g_matchup
                debug_rosters["away_raw"]   = away_raw
                debug_rosters["away_parsed"]= away_roster

            def merge_lineup(lineup_df, roster_df):
                if not lineup_df.empty and not roster_df.empty:
                    merged = lineup_df.merge(roster_df, on="player_id", how="left", suffixes=("", "_r"))
                    merged["name"] = merged["name"].fillna(merged.get("name_r", merged["name"]))
                    return merged
                if not roster_df.empty:
                    return roster_df.copy().assign(order=range(1, len(roster_df) + 1))
                return pd.DataFrame()

            away_df = merge_lineup(away_lineup, away_roster)
            home_df = merge_lineup(home_lineup, home_roster)

            opp_pitch = {"era": 4.5, "whip": 1.35, "homeRunsPer9": 1.2, "strikeoutsPer9Inn": 8.5}
            away_wrcs, home_wrcs = [], []

            for side_label, roster_df in [("Away", away_df), ("Home", home_df)]:
                if roster_df is None or roster_df.empty:
                    continue
                for _, p in roster_df.iterrows():
                    order = int(p.get("order", 9) or 9)
                    if order > max_ord:
                        continue
                    avg   = float(p.get("avg") or 0)
                    obp   = float(p.get("obp") or 0)
                    slg   = float(p.get("slg") or 0)
                    iso   = float(p.get("iso") or 0)
                    wrc   = int(p.get("wrc_plus") or 100)
                    hh    = float(p.get("hard_hit_pct") or 0.35)
                    bar   = float(p.get("barrel_pct") or 0.06)
                    pname = str(p.get("name", "Unknown"))

                    if side_label == "Away":
                        away_wrcs.append(wrc)
                    else:
                        home_wrcs.append(wrc)

                    if avg < min_avg or obp < min_obp:
                        continue

                    scores = score_batter(avg, obp, slg, iso, wrc, hh, bar, order,
                                         opp_pitch["era"], opp_pitch["whip"],
                                         opp_pitch["homeRunsPer9"],
                                         opp_pitch["strikeoutsPer9Inn"], total_env)
                    best_m = max(scores, key=scores.get)
                    best_s = scores[best_m]
                    all_rows.append({
                        "Game":        g_matchup,
                        "Side":        side_label,
                        "Batter":      pname,
                        "Order":       order,
                        "AVG":         avg,
                        "OBP":         obp,
                        "ISO":         iso,
                        "wRC+":        wrc,
                        "Hits/Runs":   scores["Hits/Runs"],
                        "RBI":         scores["RBI"],
                        "Home Run":    scores["Home Run"],
                        "Runs Scored": scores["Runs Scored"],
                        "Best Market": best_m,
                        "Best Score":  best_s,
                        "Grade":       "Premium"  if best_s >= 70 else
                                       "Playable" if best_s >= 48 else "Sub-optimal",
                        "Game Time":   g["game_time"],
                        "Venue":       g["venue"],
                        "Env":         env_label,
                        "Weather":     wx_str,
                        "Lineup":      lineup_badge,
                    })

            maw = sum(away_wrcs) / len(away_wrcs) if away_wrcs else 100
            mhw = sum(home_wrcs) / len(home_wrcs) if home_wrcs else 100
            par = round(4.1 * (maw / 100) * (opp_pitch["era"] / 4.3) * wx["factor"], 2)
            phr = round(4.1 * (mhw / 100) * (opp_pitch["era"] / 4.3) * wx["factor"], 2)
            den = (par ** 1.83) + (phr ** 1.83)
            awp = round((par ** 1.83) / den, 4) if den > 0 else 0.5
            game_projections[g_matchup] = {
                "proj_away_runs": par, "proj_home_runs": phr,
                "away_prob": awp,     "home_prob": 1 - awp,
                "proj_total": round(par + phr, 1),
                "proj_line":  round(phr - par, 1),
            }

        st.session_state["debug_rosters"] = debug_rosters

        if all_rows:
            st.session_state["auto_df"]        = pd.DataFrame(all_rows)
            st.session_state["game_proj_dict"] = game_projections
            status.update(label=f"Done! {len(all_rows)} player profiles generated.", state="complete")
        else:
            status.update(label="No players matched filters. Filters set to 0 — check raw API data via the debug checkbox in the sidebar.", state="error")

# ── DEBUG VIEW ────────────────────────────────────────────────────────────────
if debug and "debug_rosters" in st.session_state:
    dr = st.session_state["debug_rosters"]
    st.subheader(f"Raw API Debug — {dr.get('game','')}")
    with st.expander("Raw Tank01 roster response (first game away team)"):
        st.json(dr.get("away_raw", {}))
    with st.expander("Parsed roster dataframe"):
        st.dataframe(dr.get("away_parsed", pd.DataFrame()), use_container_width=True)

# ── RENDER TABS ───────────────────────────────────────────────────────────────
if "auto_df" in st.session_state:
    df             = st.session_state["auto_df"]
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data      = st.session_state.get("odds_data", {})

    tabs = st.tabs(["Hits/Runs", "RBIs", "Home Runs", "Runs Scored", "Matchups", "Moneyline", "Run Line", "Totals"])

    for idx, m_name in enumerate(["Hits/Runs", "RBI", "Home Run", "Runs Scored"]):
        with tabs[idx]:
            st.subheader(f"Top {m_name} Picks")
            key_col = "AVG" if m_name == "Hits/Runs" else "wRC+" if m_name == "RBI" else "ISO"
            top10   = df.sort_values(m_name, ascending=False).head(10)
            st.dataframe(top10[["Game","Batter","Order",key_col,m_name,"Grade"]].reset_index(drop=True),
                         use_container_width=True)
            st.markdown("### By Game")
            for g_name in df["Game"].unique():
                sub = df[df["Game"] == g_name].sort_values(m_name, ascending=False).head(3)
                if sub.empty:
                    continue
                s = sub.iloc[0]
                with st.expander(f"{g_name} | {s['Game Time']}"):
                    st.dataframe(sub[["Order","Side","Batter","wRC+","AVG","ISO",m_name,"Grade"]].reset_index(drop=True),
                                 use_container_width=True)

    sorted_games = df["Game"].unique().tolist()

    with tabs[4]:
        st.subheader("Matchup Overview")
        for gm in sorted_games:
            gdf   = df[df["Game"] == gm].sort_values("Order")
            s     = gdf.iloc[0]
            parts = gm.split(" @ ")
            away_t = parts[0]
            home_t = parts[1] if len(parts) > 1 else "Home"
            with st.expander(f"{gm} | {s['Game Time']} | {s['Venue']} | {s['Weather']} | {s['Env']} | {s['Lineup']}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.caption(f"Away: {away_t}")
                    st.dataframe(gdf[gdf["Side"]=="Away"][["Order","Batter","wRC+","OBP","ISO","Grade"]].reset_index(drop=True),
                                 use_container_width=True)
                with c2:
                    st.caption(f"Home: {home_t}")
                    st.dataframe(gdf[gdf["Side"]=="Home"][["Order","Batter","wRC+","OBP","ISO","Grade"]].reset_index(drop=True),
                                 use_container_width=True)

    with tabs[5]:
        st.subheader("Moneyline Value")
        if not odds_data:
            st.info("Enter your The-Odds-API key in the sidebar to see UK bookmaker odds.")
        for gm in sorted_games:
            proj = game_proj_dict.get(gm)
            if not proj:
                continue
            parts   = gm.split(" @ ")
            at      = parts[0]
            ht      = parts[1] if len(parts) > 1 else "Home"
            bk_list = odds_data.get(gm, [])
            with st.container(border=True):
                st.markdown(f"**{gm}** | {at} {proj['away_prob']*100:.1f}% vs {ht} {proj['home_prob']*100:.1f}%")
                if bk_list:
                    bae, bhe, bab, bhb, ap, hp = -100, -100, "", "", "", ""
                    for b in bk_list:
                        h2h = next((m for m in b.get("markets", []) if m["key"] == "h2h"), None)
                        if h2h:
                            oc = h2h.get("outcomes", [])
                            ao = next((o for o in oc if o["name"] == at), None)
                            ho = next((o for o in oc if o["name"] == ht), None)
                            if ao and ho:
                                aev = ((proj["away_prob"] * ao["price"]) - 1.0) * 100
                                hev = ((proj["home_prob"] * ho["price"]) - 1.0) * 100
                                if aev > bae: bae, bab, ap = aev, b["title"], decimal_to_fractional(ao["price"])
                                if hev > bhe: bhe, bhb, hp = hev, b["title"], decimal_to_fractional(ho["price"])
                    if bae > 0: st.success(f"VALUE: {at} @ {ap} ({bab}) | EV: +{bae:.1f}")
                    if bhe > 0: st.success(f"VALUE: {ht} @ {hp} ({bhb}) | EV: +{bhe:.1f}")
                    if bae <= 0 and bhe <= 0: st.warning("No value edge detected.")
                else:
                    st.caption("No bookmaker odds available for this game.")

    with tabs[6]:
        st.subheader("Run Line Projections")
        for gm in sorted_games:
            proj = game_proj_dict.get(gm)
            if not proj:
                continue
            with st.container(border=True):
                st.markdown(f"**{gm}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Proj Away Runs", proj["proj_away_runs"])
                c2.metric("Proj Home Runs", proj["proj_home_runs"])
                c3.metric("Run Line",       f"{proj['proj_line']:+.1f}")

    with tabs[7]:
        st.subheader("Over/Under Projections")
        rows = [
            {"Game": gm, "Proj Total": p["proj_total"], "Away Runs": p["proj_away_runs"],
             "Home Runs": p["proj_home_runs"], "Away Win%": f"{p['away_prob']*100:.1f}%",
             "Home Win%": f"{p['home_prob']*100:.1f}%"}
            for gm, p in game_proj_dict.items()
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("Load the slate to see totals projections.")
