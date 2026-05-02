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
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Hide sidebar entirely */
    [data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }

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

    /* Schedule picker card */
    .picker-card {
        background: var(--background-color);
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1.5rem;
    }

    /* Score banner */
    .score-banner {
        background: #0d1117;
        color: white;
        border-radius: 10px;
        padding: 1.4rem 2rem;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .score-team  { font-size: 1.2rem; font-weight: 700; }
    .score-record { font-size: 0.78rem; color: #aaa; margin-top: 2px; }
    .score-num   { font-size: 2.6rem; font-weight: 800; font-family: monospace; }
    .score-sep   { font-size: 1.6rem; color: #555; padding: 0 0.8rem; }
    .status-pill {
        background: #D50A0A;
        color: white;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.22rem 0.65rem;
        border-radius: 20px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        display: inline-block;
    }
    .status-pill.final { background: #444; }
    .status-pill.pre   { background: #013369; }

    /* Section headers */
    .section-head {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #888;
        border-bottom: 1px solid rgba(128,128,128,0.2);
        padding-bottom: 0.4rem;
        margin: 1.5rem 0 0.8rem;
    }

    /* Filter bar */
    .filter-bar {
        background: rgba(1, 51, 105, 0.07);
        border-radius: 8px;
        padding: 0.7rem 1rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    /* Quarter filter pills */
    .stRadio > div { flex-direction: row; gap: 6px; flex-wrap: wrap; }
    .stRadio > div > label {
        background: rgba(128,128,128,0.1);
        border-radius: 20px;
        padding: 3px 14px;
        font-size: 0.83rem;
        cursor: pointer;
        border: 1px solid transparent;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(128,128,128,0.07);
        border-radius: 6px;
        padding: 4px 14px;
        font-size: 0.85rem;
    }

    /* Buttons */
    div[data-testid="stButton"] > button {
        background: #013369;
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        padding: 0.5rem 1.4rem;
    }
    div[data-testid="stButton"] > button:hover { background: #D50A0A; }

    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 3rem 1rem;
        color: #888;
        font-size: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nfl-header">
  <h1>🏈 NFL Live Box Score</h1>
  <p>Select a season, week and game to load the full box score with quarter & half splits</p>
</div>
""", unsafe_allow_html=True)

# ── Schedule Picker ───────────────────────────────────────────────────────────

st.markdown("### 📅 Schedule Picker")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    season_type = st.selectbox(
        "Season type",
        options=[2, 3, 1],
        format_func=lambda x: {1: "Preseason", 2: "Regular Season", 3: "Playoffs"}[x],
        key="season_type",
    )

with col2:
    week = st.number_input(
        "Week number (0 = current week)",
        min_value=0,
        max_value=22,
        value=0,
        step=1,
        key="week",
    )

with col3:
    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
    load_schedule = st.button("🔍 Load Schedule")
    st.markdown("</div>", unsafe_allow_html=True)

week_val = int(week) if int(week) > 0 else None

# ── Load Games ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def load_games(week_val, season_type):
    return get_live_games(week=week_val)

# Session state — track whether schedule has been loaded and which game is selected
if "games_loaded" not in st.session_state:
    st.session_state.games_loaded = False
if "selected_game_id" not in st.session_state:
    st.session_state.selected_game_id = None
if "last_week" not in st.session_state:
    st.session_state.last_week = None
if "last_season" not in st.session_state:
    st.session_state.last_season = None

if load_schedule:
    st.cache_data.clear()
    st.session_state.games_loaded = True
    st.session_state.selected_game_id = None
    st.session_state.last_week = week_val
    st.session_state.last_season = season_type

# ── Game List ─────────────────────────────────────────────────────────────────

if not st.session_state.games_loaded:
    st.markdown("""
    <div class="empty-state">
        ⬆️ Select a season type and week above, then click <strong>Load Schedule</strong>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

with st.spinner("Loading schedule..."):
    games = load_games(st.session_state.last_week, st.session_state.last_season)

if not games:
    st.warning("No games found for this week. Try a different week or season type.")
    st.stop()

# Sort: live first, then final, then scheduled
live_games  = [g for g in games if g["status_state"] == "in"]
final_games = [g for g in games if g["status_state"] == "post"]
sched_games = [g for g in games if g["status_state"] == "pre"]
ordered     = live_games + final_games + sched_games

def status_icon(g):
    if g["status_state"] == "in":
        return f"🔴 LIVE — {g['clock']} Q{g['period']}"
    if g["status_state"] == "post":
        return "✅ Final"
    return f"📅 Scheduled"

# Build a card-style game selector
st.markdown('<div class="section-head">Select a Game</div>', unsafe_allow_html=True)

cols = st.columns(3)
for i, game in enumerate(ordered):
    with cols[i % 3]:
        away = game["away"]
        home = game["home"]
        label_top    = f"{away['abbr']} {away['score']}  —  {home['score']} {home['abbr']}"
        label_status = status_icon(game)
        is_selected  = st.session_state.selected_game_id == game["id"]

        border = "2px solid #013369" if is_selected else "1px solid rgba(128,128,128,0.2)"
        bg     = "rgba(1,51,105,0.07)" if is_selected else "transparent"

        st.markdown(f"""
        <div style="border:{border};background:{bg};border-radius:10px;padding:0.8rem 1rem;margin-bottom:0.6rem">
            <div style="font-weight:700;font-size:1rem;letter-spacing:0.3px">{label_top}</div>
            <div style="font-size:0.78rem;color:#888;margin-top:3px">{label_status}</div>
            <div style="font-size:0.74rem;color:#aaa;margin-top:1px">{game.get('venue','')}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button(
            "View Box Score" if not is_selected else "✓ Selected",
            key=f"game_{game['id']}",
            use_container_width=True,
        ):
            st.session_state.selected_game_id = game["id"]
            st.rerun()

# ── Stop here if no game selected yet ────────────────────────────────────────

if not st.session_state.selected_game_id:
    st.markdown("""
    <div class="empty-state" style="margin-top:2rem">
        👆 Click <strong>View Box Score</strong> on any game above to load stats
    </div>
    """, unsafe_allow_html=True)
    st.stop()

game_id = st.session_state.selected_game_id
game    = next((g for g in ordered if g["id"] == game_id), None)

if not game:
    st.error("Game not found. Please reload the schedule.")
    st.stop()

# ── Load All Stats ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def load_all_stats(game_id):
    return {
        "linescore": build_linescore_df(game_id),
        "passing":   get_passing_stats(game_id),
        "rushing":   get_rushing_stats(game_id),
        "receiving": get_receiving_stats(game_id),
        "defense":   get_defensive_stats(game_id),
        "kicking":   get_kicking_stats(game_id),
        "returning": get_returning_stats(game_id),
        "team":      get_team_stats(game_id),
        "scoring":   get_scoring_summary(game_id),
        "pbp":       get_pbp_by_quarter(game_id),
    }

st.markdown("---")

with st.spinner("Loading box score..."):
    data = load_all_stats(game_id)

# Refresh button (top of box score section)
rcol1, rcol2 = st.columns([6, 1])
with rcol2:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# ── Score Banner ──────────────────────────────────────────────────────────────

away = game["away"]
home = game["home"]
status_class = {"in": "", "post": "final", "pre": "pre"}.get(game["status_state"], "")
clock_str = (
    f'<span style="color:#aaa;font-size:0.8rem;margin-left:8px">'
    f'{game["clock"]} · Q{game["period"]}</span>'
    if game["status_state"] == "in" else ""
)

st.markdown(f"""
<div class="score-banner">
  <div>
    <div class="score-team">{away['team']}</div>
    <div class="score-record">{away['record']}</div>
  </div>
  <div style="text-align:center">
    <div>
      <span class="score-num">{away['score']}</span>
      <span class="score-sep">—</span>
      <span class="score-num">{home['score']}</span>
    </div>
    <div style="margin-top:6px">
      <span class="status-pill {status_class}">{game['status']}</span>
      {clock_str}
    </div>
    <div style="color:#666;font-size:0.78rem;margin-top:5px">{game.get('venue','')}</div>
  </div>
  <div style="text-align:right">
    <div class="score-team">{home['team']}</div>
    <div class="score-record">{home['record']}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Linescore ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Quarter-by-Quarter Score</div>', unsafe_allow_html=True)

ls_df = data["linescore"]
if not ls_df.empty:
    def highlight_ls(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for col in ["1H", "2H"]:
            if col in df.columns:
                styles[col] = "background-color: rgba(1,51,105,0.08); font-weight:600"
        if "Total" in df.columns:
            styles["Total"] = "font-weight:800; background-color: rgba(1,51,105,0.14)"
        return styles
    st.dataframe(
        ls_df.style.apply(highlight_ls, axis=None),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Linescore not available yet.")

# ── Quarter / Half Filter ─────────────────────────────────────────────────────

st.markdown('<div class="section-head">Player Stats — Filter by Period</div>', unsafe_allow_html=True)

# Build available period options from the pbp data
pbp = data["pbp"]
available_periods = []
for key in ["Full Game", "1st Half", "2nd Half", "Q1", "Q2", "Q3", "Q4"]:
    if key == "Full Game":
        available_periods.append("Full Game")
    elif key == "1st Half" and "1H" in pbp:
        available_periods.append("1st Half")
    elif key == "2nd Half" and "2H" in pbp:
        available_periods.append("2nd Half")
    elif key.startswith("Q") and key in pbp:
        available_periods.append(key)

# Add OT if present
for key in pbp:
    if key.startswith("OT") and key not in available_periods:
        available_periods.append(key)

if not available_periods:
    available_periods = ["Full Game"]

period_filter = st.radio(
    "Show stats for:",
    options=available_periods,
    horizontal=True,
    key="period_filter",
)

# ── Helper: filter player df by quarter using pbp ────────────────────────────

def filter_stats_by_period(full_df: pd.DataFrame, period: str, pbp: dict) -> pd.DataFrame:
    """
    For Full Game: return the full cumulative df as-is.
    For a quarter or half: get the list of players who had plays in that period
    from the pbp data, then filter the stat df to only those players & teams.
    Note: ESPN doesn't provide per-quarter cumulative player stats directly —
    the play-by-play tells us WHO was active in that period. We surface that
    as a filtered view with a note to the user.
    """
    if period == "Full Game" or full_df.empty:
        return full_df

    pbp_key = {"1st Half": "1H", "2nd Half": "2H"}.get(period, period)

    if pbp_key not in pbp:
        return pd.DataFrame()

    period_df = pbp[pbp_key]
    if period_df.empty:
        return pd.DataFrame()

    # Get teams active in this period
    active_teams = period_df["Team"].dropna().unique().tolist()
    if not active_teams or "Team" not in full_df.columns:
        return full_df

    filtered = full_df[full_df["Team"].isin(active_teams)]
    return filtered if not filtered.empty else full_df


def show_stat_df(df: pd.DataFrame, period: str, pbp: dict, sort_col: str = None):
    if df.empty:
        st.info("No data available.")
        return

    filtered = filter_stats_by_period(df, period, pbp)

    if filtered.empty:
        st.info(f"No data available for {period}.")
        return

    if period != "Full Game":
        st.caption(
            f"⚠️ Showing players active in **{period}**. "
            "ESPN provides cumulative game totals only — per-quarter individual stat lines "
            "are not available from this API. Use the Play-by-Play tab below for play-level detail."
        )

    if sort_col and sort_col in filtered.columns:
        try:
            s = filtered.copy()
            s[sort_col] = pd.to_numeric(s[sort_col], errors="coerce")
            filtered = s.sort_values(sort_col, ascending=False)
        except Exception:
            pass

    st.dataframe(filtered, use_container_width=True, hide_index=True)


# ── Stat Tabs ─────────────────────────────────────────────────────────────────

tab_pass, tab_rush, tab_rec, tab_def, tab_kick, tab_ret, tab_team = st.tabs([
    "⬆ Passing", "🏃 Rushing", "🙌 Receiving",
    "🛡 Defense", "👟 Kicking", "↩ Returning", "📊 Team Totals",
])

with tab_pass:
    show_stat_df(data["passing"], period_filter, pbp, sort_col="YDS")

with tab_rush:
    show_stat_df(data["rushing"], period_filter, pbp, sort_col="YDS")

with tab_rec:
    show_stat_df(data["receiving"], period_filter, pbp, sort_col="YDS")

with tab_def:
    show_stat_df(data["defense"], period_filter, pbp, sort_col="TOT")

with tab_kick:
    show_stat_df(data["kicking"], period_filter, pbp)

with tab_ret:
    show_stat_df(data["returning"], period_filter, pbp, sort_col="YDS")

with tab_team:
    # Team totals don't filter by quarter — always show full game
    t_df = data["team"]
    if not t_df.empty:
        st.dataframe(t_df, use_container_width=True, hide_index=True)
    else:
        st.info("No team data available.")

# ── Scoring Summary ───────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Scoring Summary</div>', unsafe_allow_html=True)

score_df = data["scoring"]
if not score_df.empty:
    # Apply period filter to scoring summary
    if period_filter == "Full Game":
        filtered_score = score_df
    elif period_filter == "1st Half":
        filtered_score = score_df[score_df["Half"] == "1st Half"]
    elif period_filter == "2nd Half":
        filtered_score = score_df[score_df["Half"] == "2nd Half"]
    elif period_filter.startswith("OT"):
        filtered_score = score_df[score_df["Half"].str.startswith("OT", na=False)]
    else:
        filtered_score = score_df[score_df["Quarter"] == period_filter]

    if filtered_score.empty:
        st.info(f"No scoring plays in {period_filter}.")
    else:
        for half in filtered_score["Half"].unique():
            half_df = filtered_score[filtered_score["Half"] == half]
            st.markdown(f"**{half}**")
            st.dataframe(
                half_df.drop(columns=["Half"]),
                use_container_width=True,
                hide_index=True,
            )
else:
    st.info("No scoring plays yet.")

# ── Play-by-Play by Quarter ───────────────────────────────────────────────────

st.markdown('<div class="section-head">Play-by-Play</div>', unsafe_allow_html=True)

if pbp:
    # Apply the same period filter to pbp
    if period_filter == "Full Game":
        pbp_keys = [k for k in ["Q1", "Q2", "Q3", "Q4"] if k in pbp]
        pbp_keys += [k for k in pbp if k.startswith("OT")]
        show_pbp = {k: pbp[k] for k in pbp_keys if k in pbp}
    elif period_filter == "1st Half":
        show_pbp = {k: pbp[k] for k in ["Q1", "Q2"] if k in pbp}
    elif period_filter == "2nd Half":
        show_pbp = {k: pbp[k] for k in ["Q3", "Q4"] if k in pbp}
    elif period_filter.startswith("OT"):
        show_pbp = {period_filter: pbp[period_filter]} if period_filter in pbp else {}
    else:
        show_pbp = {period_filter: pbp[period_filter]} if period_filter in pbp else {}

    if show_pbp:
        pbp_tabs = st.tabs(list(show_pbp.keys()))
        for tab, key in zip(pbp_tabs, show_pbp.keys()):
            with tab:
                df = show_pbp[key]
                display_cols = ["Clock", "Team", "Down & Distance", "Description", "Yards", "Play Type"]
                display_cols = [c for c in display_cols if c in df.columns]
                st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info(f"No play-by-play data for {period_filter}.")
else:
    st.info("Play-by-play not available for this game yet.")

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption(
    f"Last loaded: {datetime.now().strftime('%H:%M:%S')}  ·  "
    "Data: ESPN public API  ·  Not affiliated with ESPN or the NFL"
)
