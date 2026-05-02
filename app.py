"""
app.py  —  NFL Live Box Score Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from nfl.api import get_live_games
from nfl.stats import (
    build_linescore_df,
    get_passing_stats,
    get_rushing_stats,
    get_receiving_stats,
    get_defensive_stats,
    get_kicking_stats,
    get_returning_stats,
    get_team_stats,
    get_scoring_summary,
    get_pbp_by_quarter,
)

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NFL Live Box Score",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Header */
    .nfl-header {
        background: linear-gradient(135deg, #013369 0%, #D50A0A 100%);
        color: white;
        padding: 1.2rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .nfl-header h1 { margin: 0; font-size: 1.8rem; letter-spacing: 0.5px; }
    .nfl-header p  { margin: 0.2rem 0 0; opacity: 0.85; font-size: 0.9rem; }

    /* Score banner */
    .score-banner {
        background: #0d1117;
        color: white;
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .score-team { font-size: 1.1rem; font-weight: 600; }
    .score-num  { font-size: 2.2rem; font-weight: 800; font-family: monospace; }
    .score-sep  { font-size: 1.4rem; color: #888; padding: 0 0.8rem; }
    .status-pill {
        background: #D50A0A;
        color: white;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .status-pill.final { background: #444; }
    .status-pill.pre   { background: #013369; }

    /* Section headers */
    .section-head {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #888;
        border-bottom: 1px solid #eee;
        padding-bottom: 0.4rem;
        margin: 1.5rem 0 0.8rem;
    }

    /* Linescore table emphasis */
    .linescore-wrap table {
        width: 100%;
        border-collapse: collapse;
    }

    /* Hide index */
    .stDataFrame thead th:first-child { display: none; }
    .stDataFrame tbody td:first-child { display: none; }

    /* Quarter tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: #f5f5f5;
        border-radius: 6px;
        padding: 4px 14px;
        font-size: 0.85rem;
    }

    /* Refresh button */
    div[data-testid="stButton"] > button {
        background: #013369;
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        padding: 0.5rem 1.2rem;
        width: 100%;
    }
    div[data-testid="stButton"] > button:hover {
        background: #D50A0A;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🏈 NFL Box Score")
    st.markdown("---")

    season_type = st.selectbox(
        "Season type",
        options=[2, 3, 1],
        format_func=lambda x: {1: "Preseason", 2: "Regular Season", 3: "Playoffs"}[x],
    )

    week = st.number_input("Week (leave 0 for current)", min_value=0, max_value=22, value=0)
    week_val = int(week) if int(week) > 0 else None

    refresh = st.button("🔄 Refresh Data")

    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    st.caption("Data: ESPN (unofficial)")

# ── Load Games ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def load_games(week_val, season_type):
    return get_live_games(week=week_val)

if refresh:
    st.cache_data.clear()

with st.spinner("Fetching NFL games..."):
    games = load_games(week_val, season_type)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nfl-header">
  <h1>🏈 NFL Live Box Score</h1>
  <p>Real-time player stats · Quarter & half splits · Scoring summary</p>
</div>
""", unsafe_allow_html=True)

if not games:
    st.warning("No games found for this week. Try changing the week or season type.")
    st.stop()

# ── Game Selector ─────────────────────────────────────────────────────────────

live_games    = [g for g in games if g["status_state"] == "in"]
final_games   = [g for g in games if g["status_state"] == "post"]
sched_games   = [g for g in games if g["status_state"] == "pre"]

def game_label(g):
    status = g["status"]
    if g["status_state"] == "in":
        status = f"🔴 LIVE — {g['clock']} Q{g['period']}"
    elif g["status_state"] == "post":
        status = "✅ Final"
    else:
        status = f"📅 {g['date'][:10]}"
    return f"{g['away']['abbr']} @ {g['home']['abbr']}  |  {status}"

ordered = live_games + final_games + sched_games
if not ordered:
    st.info("No games available.")
    st.stop()

selected_label = st.selectbox(
    "Select a game",
    options=[game_label(g) for g in ordered],
)
game = ordered[[game_label(g) for g in ordered].index(selected_label)]
game_id = game["id"]

# ── Score Banner ──────────────────────────────────────────────────────────────

status_class = {"in": "", "post": "final", "pre": "pre"}.get(game["status_state"], "")

away = game["away"]
home = game["home"]

st.markdown(f"""
<div class="score-banner">
  <div>
    <div class="score-team">{away['team']}</div>
    <div style="font-size:0.8rem;color:#aaa;">{away['record']}</div>
  </div>
  <div style="text-align:center">
    <div>
      <span class="score-num">{away['score']}</span>
      <span class="score-sep">—</span>
      <span class="score-num">{home['score']}</span>
    </div>
    <div style="margin-top:6px">
      <span class="status-pill {status_class}">{game['status']}</span>
      {'<span style="color:#aaa;font-size:0.8rem;margin-left:8px">'+game["clock"]+' · Q'+str(game["period"])+'</span>' if game["status_state"]=="in" else ""}
    </div>
    <div style="color:#666;font-size:0.78rem;margin-top:4px">{game.get("venue","")}</div>
  </div>
  <div style="text-align:right">
    <div class="score-team">{home['team']}</div>
    <div style="font-size:0.8rem;color:#aaa;">{home['record']}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Load All Stats ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def load_all_stats(game_id):
    return {
        "linescore":   build_linescore_df(game_id),
        "passing":     get_passing_stats(game_id),
        "rushing":     get_rushing_stats(game_id),
        "receiving":   get_receiving_stats(game_id),
        "defense":     get_defensive_stats(game_id),
        "kicking":     get_kicking_stats(game_id),
        "returning":   get_returning_stats(game_id),
        "team":        get_team_stats(game_id),
        "scoring":     get_scoring_summary(game_id),
        "pbp":         get_pbp_by_quarter(game_id),
    }

with st.spinner("Loading box score..."):
    data = load_all_stats(game_id)

# ── Linescore ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Quarter-by-Quarter Score</div>', unsafe_allow_html=True)

ls_df = data["linescore"]
if not ls_df.empty:
    # Highlight the Total column
    def highlight_total(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        if "Total" in df.columns:
            styles["Total"] = "font-weight: bold; background-color: #f0f0f0"
        if "1H" in df.columns:
            styles["1H"] = "background-color: #e8f4fd"
        if "2H" in df.columns:
            styles["2H"] = "background-color: #e8f4fd"
        return styles

    st.dataframe(
        ls_df.style.apply(highlight_total, axis=None),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Linescore not yet available.")

# ── Main Tabs ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Player & Team Stats</div>', unsafe_allow_html=True)

tab_pass, tab_rush, tab_rec, tab_def, tab_kick, tab_ret, tab_team = st.tabs([
    "⬆ Passing", "🏃 Rushing", "🙌 Receiving",
    "🛡 Defense", "👟 Kicking", "↩ Returning", "📊 Team Totals"
])

def show_stat_df(df: pd.DataFrame, default_sort: str = None, ascending=False):
    if df.empty:
        st.info("No data available yet.")
        return
    if default_sort and default_sort in df.columns:
        try:
            df = df.copy()
            df[default_sort] = pd.to_numeric(df[default_sort], errors="coerce")
            df = df.sort_values(default_sort, ascending=ascending)
        except Exception:
            pass
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_pass:
    show_stat_df(data["passing"], "YDS")

with tab_rush:
    show_stat_df(data["rushing"], "YDS")

with tab_rec:
    show_stat_df(data["receiving"], "YDS")

with tab_def:
    show_stat_df(data["defense"], "TOT")

with tab_kick:
    show_stat_df(data["kicking"])

with tab_ret:
    show_stat_df(data["returning"], "YDS")

with tab_team:
    show_stat_df(data["team"])

# ── Scoring Summary ───────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Scoring Summary</div>', unsafe_allow_html=True)

score_df = data["scoring"]
if not score_df.empty:
    # Group display by half
    for half in ["1st Half", "2nd Half"] + [c for c in score_df["Half"].unique() if "OT" in str(c)]:
        half_df = score_df[score_df["Half"] == half]
        if half_df.empty:
            continue
        st.markdown(f"**{half}**")
        st.dataframe(
            half_df.drop(columns=["Half"]),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("No scoring plays yet.")

# ── Play-by-Play by Quarter ───────────────────────────────────────────────────

st.markdown('<div class="section-head">Play-by-Play by Quarter & Half</div>', unsafe_allow_html=True)

pbp = data["pbp"]
if pbp:
    quarter_keys = [k for k in ["Q1", "Q2", "1H", "Q3", "Q4", "2H"] if k in pbp]
    ot_keys = [k for k in pbp if k.startswith("OT")]
    all_keys = quarter_keys + ot_keys

    if all_keys:
        pbp_tabs = st.tabs(all_keys)
        for tab, key in zip(pbp_tabs, all_keys):
            with tab:
                df = pbp[key]
                # Drop raw Period col, keep clean display cols
                display_cols = ["Quarter", "Clock", "Team", "Down & Distance", "Description", "Yards", "Play Type"]
                display_cols = [c for c in display_cols if c in df.columns]
                st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("Play-by-play data not available for this game yet.")

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption(
    "Data sourced from ESPN's public API · Not affiliated with ESPN or the NFL · "
    "For personal/educational use only"
)
