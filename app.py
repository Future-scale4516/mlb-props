import streamlit as st
import pandas as pd
import requests as req
from datetime import date
import time
from fractions import Fraction

st.set_page_config(page_title="MLB Prop & Game Analyser v5", page_icon="baseball", layout="wide")

RAPIDAPI_KEY = "46e23ff209mshb208e90af2f00d4p120983jsn38b0da2800d0"

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

def safe_get(url, params=None, headers=None):
    try:
        r = req.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def highlightly_get(endpoint, params=None):
    url = f"https://baseball-highlightly.p.rapidapi.com/{endpoint}"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "baseball-highlightly.p.rapidapi.com"
    }
    for attempt in range(3):
        try:
            r = req.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 2:
                st.warning(f"Highlightly API error on /{endpoint}: {e}")
                return {}
            time.sleep(1)
    return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_matches_highlightly(target_date: str):
    data = highlightly_get("matches", {"leagueName": "MLB", "date": target_date, "limit": 100})
    rows = []
    if isinstance(data, dict):
        matches = data.get("data", data.get("matches", data.get("response", [])))
    elif isinstance(data, list):
        matches = data
    else:
        matches = []
    for g in matches:
        state = g.get("state", {})
        status = state.get("current", "Scheduled") if isinstance(state, dict) else str(state)
        rows.append({
            "gamePk":        g.get("id"),
            "status":        status,
            "away_team":     g.get("awayTeamName", g.get("awayTeam", {}).get("name", "Away")),
            "home_team":     g.get("homeTeamName", g.get("homeTeam", {}).get("name", "Home")),
            "game_time_bst": g.get("time", g.get("startTime", "TBD")),
            "venue":         g.get("venue", g.get("venueName", "")),
            "game_date_raw": g.get("date", target_date),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_player_stats_highlightly(season: int):
    data = highlightly_get("players", {"leagueName": "MLB", "season": season, "limit": 2000})
    rows = []
    if isinstance(data, dict):
        players = data.get("data", data.get("players", data.get("response", [])))
    elif isinstance(data, list):
        players = data
    else:
        players = []
    lg_ops = 0.730
    for p in players:
        stats = p.get("statistics", p.get("stats", {}))
        if isinstance(stats, list) and len(stats) > 0:
            stats = stats[0]
        slg = float(stats.get("slg") or 0)
        avg = float(stats.get("avg") or stats.get("battingAverage") or 0)
        obp = float(stats.get("obp") or stats.get("onBasePercentage") or 0)
        ops = float(stats.get("ops") or (obp + slg))
        iso_val = round(slg - avg, 3)
        wrc_plus_proxy = int((ops / lg_ops) * 100) if lg_ops > 0 else 100
        rows.append({
            "player_id":        p.get("id", 0),
            "name":             p.get("name", p.get("fullName", "")),
            "avg":              avg,
            "obp":              obp,
            "slg":              slg,
            "ops":              ops,
            "iso":              iso_val,
            "wrc_plus":         wrc_plus_proxy,
            "barrel_pct":       min(0.22, max(0.01, iso_val * 0.45)),
            "hard_hit_pct":     min(0.60, max(0.15, (ops * 0.45) + (iso_val * 0.2))),
            "plateAppearances": int(stats.get("plateAppearances") or stats.get("atBats") or 1),
            "k_pct":            float(stats.get("strikeOuts") or stats.get("strikeouts") or 0) /
                                max(1, float(stats.get("plateAppearances") or stats.get("atBats") or 1))
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_lineups_highlightly(match_id):
    data = highlightly_get(f"lineups/{match_id}")
    out = {"away": pd.DataFrame(), "home": pd.DataFrame()}
    if not isinstance(data, dict):
        return out
    payload = data.get("data", data.get("lineup", data))
    for side in ["away", "home"]:
        rows = []
        team_data = (
            payload.get(f"{side}Team", {}).get("lineup", []) or
            payload.get(f"{side}Lineup", []) or
            data.get(f"{side}Team", {}).get("lineup", []) or
            []
        )
        for p in team_data:
            rows.append({
                "player_id": p.get("id"),
                "name":      p.get("name", p.get("fullName", "Unknown")),
                "order":     int(p.get("battingOrder", p.get("order", 9)) or 9),
            })
        if rows:
            out[side] = pd.DataFrame(rows).sort_values("order")
    return out

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_odds_api(api_key: str):
    if not api_key or api_key.strip() == "":
        return {}
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": api_key,
        "regions": "uk",
        "markets": "h2h,spreads,totals",
        "bookmakers": "williamhill,paddypower,betfair,bet365,skybet",
        "oddsFormat": "decimal"
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
        except Exception:
            if attempt == 2:
                return {}
            time.sleep(1)
    return {}

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather(venue_name: str):
    meta = BALLPARKS.get(venue_name)
    if not meta:
        return {"temp":72,"wind":8,"factor":1.00,"dome":False,"venue":venue_name}
    if meta["dome"]:
        return {"temp":72,"wind":0,"factor":meta["factor"],"dome":True,"venue":venue_name}
    try:
        data = safe_get("https://api.open-meteo.com/v1/forecast", {
            "latitude":  meta.get("lat", 39.0),
            "longitude": meta.get("lon", -95.0),
            "current":   "temperature_2m,wind_speed_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit":  "mph"
        })
        c = data.get("current", {})
        return {
            "temp":   float(c.get("temperature_2m") or 72),
            "wind":   float(c.get("wind_speed_10m") or 8),
            "factor": meta["factor"], "dome": False, "venue": venue_name
        }
    except Exception:
        return {"temp":72,"wind":8,"factor":meta["factor"],"dome":False,"venue":venue_name}

def wx_modifier(temp, wind, dome):
    return 1.0 if dome else 1.0 + (temp - 70) * 0.003 + wind * 0.004

def score_batter(avg, obp, slg, iso, wrc_plus, hard_hit, barrel,
                 order, era, whip, hr9, k9, env, w_era, w_whip):
    of = {1:1.00,2:0.97,3:0.97,4:0.95,5:0.93,6:0.90,7:0.87,8:0.84,9:0.80}.get(order, 0.80)
    pv = min(era / 7.0, 1.0) * w_era + min(max((whip - 0.8) / 1.2, 0.0), 1.0) * w_whip
    hrv   = min(hr9 / 2.5, 1.0)
    k_adj = 1.0 - min((k9 - 7.0) / 14.0, 0.20)
    contact  = avg * 0.35 + obp * 0.30 + (wrc_plus / 200) * 0.25 + (1 - 0.22) * 0.10
    power    = iso * 0.40 + hard_hit * 0.35 + barrel * 0.25
    on_base  = obp * (wrc_plus / 100)
    hits_runs_score = round(contact * pv * of * k_adj * env * 280, 2)
    rbi_score       = round(contact * pv * (1.0 + max(0, (5 - order) * 0.04)) * k_adj * env * 260, 2)
    hr_score        = round(power * hrv * env * 280, 2)
    runs_score      = round(on_base * pv * (1.0 + max(0, (4 - order) * 0.05)) * k_adj * env * 280, 2)
    if iso < 0.130 or barrel < 0.04 or hr9 < 0.7:
        hr_score = 0.0
    if order > 7 or wrc_plus < 80:
        rbi_score = 0.0
    if order > 5 or obp < 0.290:
        runs_score = 0.0
    return {"Hits/Runs": hits_runs_score, "RBI": rbi_score,
            "Home Run": hr_score, "Runs Scored": runs_score}

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## MLB Analytics Control")
    odds_key = st.text_input("The-Odds-API Key (optional)", value="", type="password",
                              help="Get from the-odds-api.com for UK bookmaker odds")
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Model Filters")
    min_avg = st.slider("Min AVG",   0.100, 0.350, 0.180, 0.005, format="%.3f")
    min_obp = st.slider("Min OBP",   0.250, 0.400, 0.280, 0.005, format="%.3f")
    max_ord = st.slider("Max Order", 1, 9, 9)
    st.markdown("---")
    if st.button("Clear App Cache"):
        st.cache_data.clear()
        for k in ["auto_df", "game_proj_dict", "odds_data"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

st.title("MLB Full-Game & Prop Value Matrix")
st.caption("Roster Data via Highlightly (RapidAPI) | Market Overlay via The-Odds-API")
st.divider()

# ── LOAD SLATE ────────────────────────────────────────────────────────────────
if st.button("Load Today's Slate", type="primary"):
    with st.status("Fetching data...", expanded=True) as status:
        sched = fetch_matches_highlightly(str(sel_date))

        if sched.empty:
            st.error(
                f"No games returned for {sel_date}. "
                "Check that your RapidAPI account is active and subscribed to Highlightly Baseball, "
                "or try a different date."
            )
            st.stop()

        mlb_all   = fetch_player_stats_highlightly(sel_date.year)
        odds_data = fetch_live_odds_api(odds_key)
        st.session_state["odds_data"] = odds_data

        all_rows, game_projections = [], {}

        for _, g in sched.iterrows():
            g_matchup = f"{g['away_team']} @ {g['home_team']}"
            lineups   = fetch_lineups_highlightly(g["gamePk"])
            away_conf = not lineups.get("away", pd.DataFrame()).empty
            home_conf = not lineups.get("home", pd.DataFrame()).empty

            wx        = fetch_weather(g["venue"])
            total_env = wx["factor"] * wx_modifier(wx["temp"], wx["wind"], wx["dome"])
            env_symbol   = "Hitter-Friendly" if total_env >= 1.06 else "Neutral" if total_env >= 0.97 else "Pitcher-Friendly"
            weather_str  = "Dome" if wx["dome"] else f"{int(wx['temp'])}F | {int(wx['wind'])} mph wind"
            lineup_badge = "Confirmed" if (away_conf and home_conf) else "Projected"

            opp_pitch = {"era": 4.5, "whip": 1.35, "homeRunsPer9": 1.2, "strikeoutsPer9Inn": 8.5}
            away_wrcs, home_wrcs = [], []

            for side_label, roster_df in [("Away", lineups.get("away", pd.DataFrame())),
                                           ("Home", lineups.get("home", pd.DataFrame()))]:
                if roster_df.empty:
                    continue
                for _, p_row in roster_df.iterrows():
                    order = int(p_row.get("order", 9))
                    pid   = p_row.get("player_id")
                    pname = p_row.get("name")
                    mlb_row = mlb_all[mlb_all["player_id"] == pid] if not mlb_all.empty else pd.DataFrame()
                    if mlb_row.empty:
                        continue
                    base = mlb_row.iloc[0].to_dict()
                    if side_label == "Away" and order <= max_ord:
                        away_wrcs.append(base["wrc_plus"])
                    if side_label == "Home" and order <= max_ord:
                        home_wrcs.append(base["wrc_plus"])
                    if base["avg"] >= min_avg and base["obp"] >= min_obp:
                        scores = score_batter(
                            base["avg"], base["obp"], base["slg"], base["iso"],
                            base["wrc_plus"], base["hard_hit_pct"], base["barrel_pct"],
                            order,
                            opp_pitch["era"], opp_pitch["whip"],
                            opp_pitch["homeRunsPer9"], opp_pitch["strikeoutsPer9Inn"],
                            total_env, 0.55, 0.45
                        )
                        best_market = max(scores, key=scores.get)
                        all_rows.append({
                            "Game":          g_matchup,
                            "Side":          side_label,
                            "Batter":        pname,
                            "Order":         order,
                            "AVG":           base["avg"],
                            "OBP":           base["obp"],
                            "ISO":           base["iso"],
                            "wRC+":          base["wrc_plus"],
                            "Hits/Runs":     scores["Hits/Runs"],
                            "RBI":           scores["RBI"],
                            "Home Run":      scores["Home Run"],
                            "Runs Scored":   scores["Runs Scored"],
                            "Best Market":   best_market,
                            "Best Score":    scores[best_market],
                            "Grade":         "Premium" if scores[best_market] >= 70.0
                                             else "Playable" if scores[best_market] >= 48.0
                                             else "Sub-optimal",
                            "Game Time BST": g["game_time_bst"],
                            "Venue":         g["venue"],
                            "Game Datetime": g["game_date_raw"],
                            "Env":           env_symbol,
                            "Weather":       weather_str,
                            "Lineup":        lineup_badge,
                        })

            mean_away_wrc  = sum(away_wrcs) / len(away_wrcs) if away_wrcs else 100
            mean_home_wrc  = sum(home_wrcs) / len(home_wrcs) if home_wrcs else 100
            proj_away_runs = round(4.1 * (mean_away_wrc / 100) * (opp_pitch["era"] / 4.3) * wx["factor"], 2)
            proj_home_runs = round(4.1 * (mean_home_wrc / 100) * (opp_pitch["era"] / 4.3) * wx["factor"], 2)
            denom = (proj_away_runs ** 1.83) + (proj_home_runs ** 1.83)
            away_prob = round((proj_away_runs ** 1.83) / denom, 4) if denom > 0 else 0.5
            game_projections[g_matchup] = {
                "proj_away_runs": proj_away_runs,
                "proj_home_runs": proj_home_runs,
                "away_prob":      away_prob,
                "home_prob":      1.0 - away_prob,
                "proj_total":     round(proj_away_runs + proj_home_runs, 1),
                "proj_line":      round(proj_home_runs - proj_away_runs, 1),
            }

        if all_rows:
            st.session_state["auto_df"]        = pd.DataFrame(all_rows)
            st.session_state["game_proj_dict"] = game_projections
            status.update(label="Done! Data loaded successfully.", state="complete")
        else:
            status.update(label="No players matched filters. Try lowering Min AVG / Min OBP.", state="error")

# ── RENDER ────────────────────────────────────────────────────────────────────
if "auto_df" in st.session_state:
    df             = st.session_state["auto_df"]
    game_proj_dict = st.session_state.get("game_proj_dict", {})
    odds_data      = st.session_state.get("odds_data", {})

    rendered_tabs = st.tabs(["Hits/Runs","RBIs","Home Runs","Runs Scored","Matchups","Moneyline","Run Line","Totals"])

    for idx, m_name in enumerate(["Hits/Runs","RBI","Home Run","Runs Scored"]):
        with rendered_tabs[idx]:
            st.subheader(f"Top {m_name} Picks")
            col_key  = "AVG" if m_name == "Hits/Runs" else "wRC+" if m_name == "RBI" else "ISO"
            m_sorted = df.sort_values(m_name, ascending=False).head(10)
            st.dataframe(m_sorted[["Game","Batter","Order",col_key,m_name,"Grade"]].reset_index(drop=True),
                         use_container_width=True)
            st.markdown(f"### By Game")
            sorted_games = df[["Game","Game Datetime"]].drop_duplicates().sort_values("Game Datetime")
            for g_name in sorted_games["Game"].tolist():
                g_players = df[df["Game"] == g_name].sort_values(m_name, ascending=False).head(3)
                if g_players.empty:
                    continue
                sample = g_players.iloc[0]
                with st.expander(f"{g_name} | {sample['Game Time BST']} BST"):
                    st.dataframe(g_players[["Order","Side","Batter","wRC+","AVG","ISO",m_name,"Grade"]].reset_index(drop=True),
                                 use_container_width=True)

    sorted_matchups = df[["Game","Game Datetime"]].drop_duplicates().sort_values("Game Datetime")["Game"].tolist()

    with rendered_tabs[4]:
        st.subheader("Matchup Overview")
        for game_matchup in sorted_matchups:
            game_df = df[df["Game"] == game_matchup].sort_values("Order")
            sample  = game_df.iloc[0]
            parts   = game_matchup.split(" @ ")
            away_team = parts[0]
            home_team = parts[1] if len(parts) > 1 else "Home"
            with st.expander(f"{game_matchup} | {sample['Game Time BST']} BST | {sample['Venue']} | {sample['Weather']} | {sample['Env']} | {sample['Lineup']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"Away: {away_team}")
                    st.dataframe(game_df[game_df["Side"]=="Away"][["Order","Batter","wRC+","OBP","ISO","Grade"]].reset_index(drop=True), use_container_width=True)
                with col2:
                    st.caption(f"Home: {home_team}")
                    st.dataframe(game_df[game_df["Side"]=="Home"][["Order","Batter","wRC+","OBP","ISO","Grade"]].reset_index(drop=True), use_container_width=True)

    with rendered_tabs[5]:
        st.subheader("Moneyline Value")
        if not odds_data:
            st.info("Enter your The-Odds-API key in the sidebar to see UK bookmaker odds.")
        for game_matchup in sorted_matchups:
            proj = game_proj_dict.get(game_matchup)
            if not proj:
                continue
            parts     = game_matchup.split(" @ ")
            away_team = parts[0]
            home_team = parts[1] if len(parts) > 1 else "Home"
            match_odds_list = odds_data.get(game_matchup, [])
            with st.container(border=True):
                st.markdown(f"**{game_matchup}** | {away_team} {proj['away_prob']*100:.1f}% vs {home_team} {proj['home_prob']*100:.1f}%")
                if match_odds_list:
                    best_away_ev, best_home_ev = -100, -100
                    best_away_bookie, best_home_bookie = "", ""
                    away_price, home_price = "", ""
                    for b in match_odds_list:
                        h2h = next((m for m in b.get("markets",[]) if m["key"]=="h2h"), None)
                        if h2h:
                            outcomes = h2h.get("outcomes",[])
                            a_o = next((o for o in outcomes if o["name"]==away_team), None)
                            h_o = next((o for o in outcomes if o["name"]==home_team), None)
                            if a_o and h_o:
                                a_ev = ((proj["away_prob"] * a_o["price"]) - 1.0) * 100
                                h_ev = ((proj["home_prob"] * h_o["price"]) - 1.0) * 100
                                if a_ev > best_away_ev:
                                    best_away_ev, best_away_bookie, away_price = a_ev, b["title"], decimal_to_fractional(a_o["price"])
                                if h_ev > best_home_ev:
                                    best_home_ev, best_home_bookie, home_price = h_ev, b["title"], decimal_to_fractional(h_o["price"])
                    if best_away_ev > 0:
                        st.success(f"VALUE: {away_team} @ {away_price} ({best_away_bookie}) | EV: +{best_away_ev:.1f}")
                    if best_home_ev > 0:
                        st.success(f"VALUE: {home_team} @ {home_price} ({best_home_bookie}) | EV: +{best_home_ev:.1f}")
                    if best_away_ev <= 0 and best_home_ev <= 0:
                        st.warning("No value edge detected.")
                else:
                    st.caption("No bookmaker odds available.")

    with rendered_tabs[6]:
        st.subheader("Run Line Projections")
        for game_matchup in sorted_matchups:
            proj = game_proj_dict.get(game_matchup)
            if not proj:
                continue
            with st.container(border=True):
                st.markdown(f"**{game_matchup}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("Proj Away Runs", proj["proj_away_runs"])
                c2.metric("Proj Home Runs", proj["proj_home_runs"])
                c3.metric("Run Line",       f"{proj['proj_line']:+.1f}")

    with rendered_tabs[7]:
        st.subheader("Over/Under Projections")
        totals_rows = []
        for game_matchup in sorted_matchups:
            proj = game_proj_dict.get(game_matchup)
            if proj:
                totals_rows.append({
                    "Game":       game_matchup,
                    "Proj Total": proj["proj_total"],
                    "Away Runs":  proj["proj_away_runs"],
                    "Home Runs":  proj["proj_home_runs"],
                    "Away Win%":  f"{proj['away_prob']*100:.1f}%",
                    "Home Win%":  f"{proj['home_prob']*100:.1f}%",
                })
        if totals_rows:
            st.dataframe(pd.DataFrame(totals_rows), use_container_width=True)
        else:
            st.info("Load the slate to see totals projections.")