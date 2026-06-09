import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

st.set_page_config(page_title="MLB Prop Analyser", page_icon="baseball", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f7f6f2; }
.metric-card { background:#fff; border-radius:12px; padding:16px 20px; border:1px solid #dcd9d5;
  box-shadow:0 2px 8px rgba(0,0,0,0.06); text-align:center; margin-bottom:12px; }
.metric-value { font-size:1.8rem; font-weight:700; color:#01696f; }
.metric-label { font-size:0.75rem; color:#7a7974; font-weight:500; letter-spacing:0.05em;
  text-transform:uppercase; margin-top:4px; }
.batter-card { background:#fff; border-radius:10px; padding:12px 14px; margin-bottom:8px; border:1px solid #dcd9d5; }
.batter-name { font-weight:600; color:#28251d; font-size:0.95rem; }
.batter-meta { color:#7a7974; font-size:0.8rem; margin-top:2px; }
.badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:0.72rem; font-weight:600; }
.badge-hits { background:#cedcd8; color:#01696f; }
.badge-rbi  { background:#e9e0c6; color:#8a5b00; }
.badge-hr   { background:#e0ced7; color:#7d1e5e; }
.badge-runs { background:#c6d8e4; color:#0b3751; }
.stButton > button { background:#01696f; color:white; border-radius:8px; padding:10px 24px;
  font-weight:600; border:none; width:100%; font-size:1rem; }
.stButton > button:hover { background:#0c4e54; color:white; }
section[data-testid="stSidebar"] { background:#1c1b19; }
section[data-testid="stSidebar"] * { color:#cdccca !important; }
</style>
""", unsafe_allow_html=True)

PARK_FACTORS = {
    "Coors Field":1.38,"Las Vegas Ballpark":1.12,"Fenway Park":1.08,
    "Great American Ball Park":1.10,"Wrigley Field":1.05,"Rogers Centre":1.05,
    "Yankee Stadium":1.05,"Rate Field":1.04,"Oriole Park":1.02,"Chase Field":1.02,
    "Globe Life Field":1.02,"Truist Park":1.01,"Kauffman Stadium":1.01,
    "Angel Stadium":1.00,"American Family Field":1.00,"PNC Park":0.97,
    "Dodger Stadium":0.97,"Busch Stadium":0.97,"Progressive Field":0.96,
    "Comerica Park":0.95,"T-Mobile Park":0.94,"Tropicana Field":0.94,
    "Citi Field":0.94,"Oracle Park":0.93,"loanDepot park":0.93,"Petco Park":0.90,
    "Other / Unknown":1.00,
}
MARKET_COLORS = {"Hits/Runs":"#01696f","RBI":"#d19900","Home Run":"#a12c7b","Runs Scored":"#006494"}
MARKET_BADGES = {"Hits/Runs":"badge-hits","RBI":"badge-rbi","Home Run":"badge-hr","Runs Scored":"badge-runs"}
MARKET_ICONS  = {"Hits/Runs":"H","RBI":"R","Home Run":"HR","Runs Scored":"RS"}

def p_vuln(era, whip, we, ww):
    return min(era/7,1)*we + min((whip-.8)/1.2,1)*ww

def hr_vuln(hr9):
    return min(hr9/2.5, 1)

def wx_mod(temp, wind, dome):
    return 1.0 if dome else 1 + (temp-70)*.003 + wind*.004

def o_factor(o):
    return {1:1.00,2:.97,3:.97,4:.95,5:.93,6:.90,7:.87,8:.84,9:.80}.get(o,.80)

def score_batter(avg, order, era, whip, hr9, pf, wx, we, ww):
    pv  = p_vuln(era, whip, we, ww)
    hrv = hr_vuln(hr9)
    of  = o_factor(order)
    env = pf * wx
    return {
        "Hits/Runs":   round(avg*pv*of*env*100, 2),
        "RBI":         round(avg*pv*(1+max(0,(5-order)*.04))*env*90, 2),
        "Home Run":    round(avg*hrv*pf*wx*60, 2),
        "Runs Scored": round(avg*pv*(1+max(0,(4-order)*.05))*env*85, 2),
    }

if "games"   not in st.session_state: st.session_state.games   = []
if "batters" not in st.session_state: st.session_state.batters = {}

# SIDEBAR
with st.sidebar:
    st.markdown("## MLB Props")
    sel_date = st.date_input("Slate Date", value=date.today())
    st.markdown("---")
    st.markdown("### Filters")
    min_avg = st.slider("Min Batting AVG", 0.150, 0.350, 0.200, 0.005, format="%.3f")
    max_era = st.slider("Max Opp ERA", 1.5, 9.0, 9.0, 0.1)
    max_ord = st.slider("Max Batting Order", 1, 9, 9)
    st.markdown("### Markets")
    s_hits = st.checkbox("Hits / Runs",   True)
    s_rbi  = st.checkbox("RBI",           True)
    s_hr   = st.checkbox("Home Run",      True)
    s_runs = st.checkbox("Runs Scored",   True)
    st.markdown("### Weights")
    w_era  = st.slider("ERA Weight",  0.1, 0.9, 0.55, 0.05)
    w_whip = st.slider("WHIP Weight", 0.1, 0.9, 0.45, 0.05)
    st.markdown("---")
    if st.button("Clear All Data"):
        st.session_state.games   = []
        st.session_state.batters = {}
        if "results_df" in st.session_state:
            del st.session_state["results_df"]
        st.rerun()
    st.caption("MLB Prop Analyser v1.0")

allowed = [m for m,s in [("Hits/Runs",s_hits),("RBI",s_rbi),("Home Run",s_hr),("Runs Scored",s_runs)] if s]

st.markdown("# MLB Prop Analyser")
st.caption("Slate: " + sel_date.strftime('%A, %B %d, %Y') + "  |  Pitcher matchup, Park factor, Weather, Batting order")
st.divider()

# STEP 1 - ADD GAME
st.markdown("### Step 1 - Add Games")
with st.expander("Add a New Game", expanded=not st.session_state.games):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Teams and Venue**")
        away_t = st.text_input("Away Team", placeholder="LAD")
        home_t = st.text_input("Home Team", placeholder="NYY")
        g_time = st.text_input("Game Time (ET)", placeholder="7:05 ET")
        park   = st.selectbox("Ballpark", list(PARK_FACTORS.keys()))
    with c2:
        st.markdown("**Weather**")
        temp = st.number_input("Temp (F)", 40, 110, 75, key="gt")
        wind = st.number_input("Wind (mph)", 0, 50, 10, key="gw")
        dome = st.checkbox("Dome / Roof Closed")
        st.markdown("**Away Starting Pitcher**")
        apn = st.text_input("Name", placeholder="Gerrit Cole", key="apn")
        ape = st.number_input("ERA",  0.0, 15.0, 4.0, 0.01, key="ape")
        apw = st.number_input("WHIP", 0.5, 3.0,  1.25, 0.01, key="apw")
        aph = st.number_input("HR/9", 0.0, 4.0,  1.0,  0.01, key="aph")
    with c3:
        st.markdown("**Home Starting Pitcher**")
        hpn = st.text_input("Name", placeholder="Logan Webb", key="hpn")
        hpe = st.number_input("ERA",  0.0, 15.0, 4.0, 0.01, key="hpe")
        hpw = st.number_input("WHIP", 0.5, 3.0,  1.25, 0.01, key="hpw")
        hph = st.number_input("HR/9", 0.0, 4.0,  1.0,  0.01, key="hph")

    if st.button("Add Game"):
        if away_t and home_t:
            gid = away_t + " @ " + home_t
            if gid in [g["id"] for g in st.session_state.games]:
                st.warning("Game already added.")
            else:
                st.session_state.games.append({
                    "id": gid, "away": away_t, "home": home_t, "time": g_time,
                    "park": park, "park_factor": PARK_FACTORS[park],
                    "temp": temp, "wind": wind, "dome": dome,
                    "away_pitcher": {"name":apn,"era":ape,"whip":apw,"hr9":aph},
                    "home_pitcher": {"name":hpn,"era":hpe,"whip":hpw,"hr9":hph},
                })
                st.session_state.batters[gid] = {"away":[], "home":[]}
                st.success("Added: " + gid)
        else:
            st.error("Enter both team names.")

if st.session_state.games:
    ncols = min(len(st.session_state.games), 5)
    cols  = st.columns(ncols)
    for i, g in enumerate(st.session_state.games):
        with cols[i % ncols]:
            card_html = (
                '<div class="metric-card">'
                '<div style="font-weight:700;color:#28251d;font-size:.9rem;">' + g["id"] + '</div>'
                '<div style="color:#7a7974;font-size:.75rem;">' + g["time"] + ' | ' + g["park"][:20] + '</div>'
                '<div style="color:#7a7974;font-size:.72rem;margin-top:4px;">'
                'Away SP: ' + (g["away_pitcher"]["name"] or "TBD") + ' ERA ' + str(g["away_pitcher"]["era"]) + '<br>'
                'Home SP: ' + (g["home_pitcher"]["name"] or "TBD") + ' ERA ' + str(g["home_pitcher"]["era"]) +
                '</div></div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

# STEP 2 - LINEUPS
if st.session_state.games:
    st.divider()
    st.markdown("### Step 2 - Enter Lineups")
    gsel = st.selectbox("Select Game", [g["id"] for g in st.session_state.games])
    sg   = next(g for g in st.session_state.games if g["id"] == gsel)
    away_label = sg["away"] + " (vs " + (sg["home_pitcher"]["name"] or "TBD") + ")"
    home_label = sg["home"] + " (vs " + (sg["away_pitcher"]["name"] or "TBD") + ")"
    ta, th = st.tabs([away_label, home_label])

    for tab, side, opp in [(ta, "away", "home"), (th, "home", "away")]:
        with tab:
            op = sg[f"{opp}_pitcher"]
            st.caption("Facing: " + (op["name"] or "TBD") + " | ERA " + str(op["era"]) + " | WHIP " + str(op["whip"]) + " | HR/9 " + str(op["hr9"]))
            with st.form("bf_" + gsel + "_" + side):
                fc1, fc2, fc3 = st.columns(3)
                with fc1: bn = st.text_input("Batter Name")
                with fc2: ba = st.number_input("AVG", 0.05, 0.50, 0.260, 0.001, format="%.3f")
                with fc3: bo = st.selectbox("Order", list(range(1, 10)))
                if st.form_submit_button("Add Batter"):
                    if bn:
                        st.session_state.batters[gsel][side].append({"name":bn,"avg":ba,"order":bo})
                        st.success("Added: " + bn)
                    else:
                        st.warning("Enter a name.")
            bl = st.session_state.batters.get(gsel, {}).get(side, [])
            if bl:
                bdf = pd.DataFrame(bl).sort_values("order").rename(columns={"name":"Batter","avg":"AVG","order":"Order"})
                st.dataframe(bdf, use_container_width=True, hide_index=True,
                             column_config={"AVG": st.column_config.NumberColumn(format="%.3f")})

# STEP 3 - RUN
st.divider()
st.markdown("### Step 3 - Run Analysis")
if st.button("Score All Batters"):
    rows = []
    for game in st.session_state.games:
        gid = game["id"]
        pf  = game["park_factor"]
        wx  = wx_mod(game["temp"], game["wind"], game["dome"])
        for side, opp in [("away","home"), ("home","away")]:
            op = game[f"{opp}_pitcher"]
            for b in st.session_state.batters.get(gid, {}).get(side, []):
                sc  = score_batter(b["avg"], b["order"], op["era"], op["whip"], op["hr9"], pf, wx, w_era, w_whip)
                flt = {k:v for k,v in sc.items() if k in allowed}
                if not flt: continue
                best = max(flt, key=flt.get)
                rows.append({
                    "Game":gid, "Time":game["time"], "Batter":b["name"],
                    "Order":b["order"], "AVG":b["avg"],
                    "Opp Pitcher":op["name"], "ERA":op["era"], "WHIP":op["whip"], "HR/9":op["hr9"],
                    "Park Factor":pf, "Wx Mod":round(wx,3),
                    **sc, "Best Market":best, "Best Score":flt[best],
                })
    if not rows:
        st.warning("No batters to score. Add lineups in Step 2 first.")
    else:
        df = pd.DataFrame(rows)
        df = df[(df["AVG"] >= min_avg) & (df["ERA"] <= max_era) & (df["Order"] <= max_ord)]
        df = df.sort_values("Best Score", ascending=False)
        st.session_state["results_df"] = df
        st.success("Scored " + str(len(df)) + " batters!")

# RESULTS
if "results_df" in st.session_state:
    df = st.session_state["results_df"]
    if df.empty:
        st.info("No results match current filters.")
    else:
        st.divider()
        st.markdown("## Results")
        top = df.iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        for col, val, lbl in [
            (k1, str(len(df)), "Batters Scored"),
            (k2, str(top["Batter"]), "Top Batter"),
            (k3, str(top["Best Market"]), "Best Market"),
            (k4, str(top["Best Score"]), "Top Score"),
        ]:
            with col:
                st.markdown('<div class="metric-card"><div class="metric-value">' + val + '</div>'
                            '<div class="metric-label">' + lbl + '</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        all_t, t_hits, t_rbi, t_hr, t_runs = st.tabs(["All Ranked", "Hits / Runs", "RBI", "Home Run", "Runs Scored"])

        with all_t:
            st.dataframe(
                df[["Game","Batter","Order","AVG","Opp Pitcher","ERA","WHIP","Park Factor","Best Market","Best Score"]].reset_index(drop=True),
                use_container_width=True, hide_index=True,
                column_config={
                    "Best Score":  st.column_config.ProgressColumn("Best Score", min_value=0, max_value=float(df["Best Score"].max())),
                    "AVG":         st.column_config.NumberColumn(format="%.3f"),
                    "Park Factor": st.column_config.NumberColumn(format="%.2f"),
                }
            )

        for tab, mkt in [(t_hits,"Hits/Runs"),(t_rbi,"RBI"),(t_hr,"Home Run"),(t_runs,"Runs Scored")]:
            with tab:
                sub = df[df["Best Market"] == mkt]
                if sub.empty:
                    st.info("No top picks for " + mkt + " with current filters.")
                    continue
                cc, ct = st.columns([3, 2])
                with cc:
                    fig = go.Figure(go.Bar(
                        y=sub.head(12)["Batter"] + " | " + sub.head(12)["Game"],
                        x=sub.head(12)[mkt], orientation="h",
                        marker_color=MARKET_COLORS[mkt],
                        text=["ERA " + str(e) for e in sub.head(12)["ERA"]],
                        textposition="inside", insidetextanchor="start",
                        textfont=dict(color="white", size=11),
                    ))
                    fig.update_layout(
                        title="Top " + mkt + " Picks",
                        yaxis=dict(autorange="reversed"), height=420,
                        plot_bgcolor="#f9f8f5", paper_bgcolor="#f7f6f2",
                        margin=dict(l=10,r=10,t=40,b=20), font=dict(family="Inter"),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                with ct:
                    for _, row in sub.head(8).iterrows():
                        avg_str = ".{:03d}".format(int(round(row["AVG"], 3) * 1000))
                        card = (
                            '<div class="batter-card">'
                            '<div class="batter-name">' + str(row["Batter"]) + '</div>'
                            '<div class="batter-meta">' + str(row["Game"]) + ' | #' + str(int(row["Order"])) + ' | ' + avg_str + '</div>'
                            '<div class="batter-meta">vs ' + str(row["Opp Pitcher"]) + ' ERA ' + str(row["ERA"]) + ' WHIP ' + str(row["WHIP"]) + '</div>'
                            '<div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;">'
                            '<span class="badge ' + MARKET_BADGES[mkt] + '">' + mkt + '</span>'
                            '<span style="font-weight:700;color:' + MARKET_COLORS[mkt] + ';font-size:1rem;">Score: ' + str(row[mkt]) + '</span>'
                            '</div></div>'
                        )
                        st.markdown(card, unsafe_allow_html=True)

        st.divider()
        st.download_button(
            "Download Full Results CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="mlb_props_" + str(date.today()) + ".csv",
            mime="text/csv",
        )
