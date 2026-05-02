"""
app.py  —  NFL Live Box Score Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timezone, timedelta
import calendar as cal_mod

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

# ── Eastern Time helper ───────────────────────────────────────────────────────

def to_et(utc_str: str) -> datetime:
    """Parse ESPN UTC ISO string → Eastern Time datetime."""
    try:
        utc_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        # EST = UTC-5, EDT = UTC-4 (DST: 2nd Sun Mar → 1st Sun Nov)
        et_offset = timedelta(hours=-4)   # EDT (Apr–Oct)
        # Simple DST check
        month = utc_dt.month
        if month < 3 or month == 12 or (month == 11 and utc_dt.day > 7):
            et_offset = timedelta(hours=-5)  # EST
        return utc_dt + et_offset
    except Exception:
        return datetime.now()

def et_date(utc_str: str) -> date:
    """Return the Eastern Time date for a UTC string."""
    return to_et(utc_str).date()

def et_time_str(utc_str: str) -> str:
    """Return formatted time string in ET, e.g. '1:00 PM ET'."""
    try:
        et = to_et(utc_str)
        return et.strftime("%-I:%M %p ET")
    except Exception:
        return ""

def et_date_str(utc_str: str) -> str:
    """Return ET date string for grouping."""
    return et_date(utc_str).isoformat()

def et_now() -> datetime:
    """Current time in Eastern."""
    utc_now = datetime.now(timezone.utc)
    month = utc_now.month
    offset = timedelta(hours=-4) if 3 <= month <= 10 else timedelta(hours=-5)
    return utc_now.replace(tzinfo=None) + offset

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NFL Box Score",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    [data-testid="stSidebar"]        { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    .block-container { padding-top: 1.2rem !important; max-width: 1100px; }
    html, body, * { font-family: 'Inter', system-ui, sans-serif; }

    /* ── Header ───────────────────────────────────── */
    .app-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 14px 20px;
        background: #111;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .app-header .title  { font-size: 1.25rem; font-weight: 700; color: #fff; letter-spacing: -0.3px; }
    .app-header .sub    { font-size: 0.75rem; color: #666; margin-top: 1px; }

    /* ── Section label ────────────────────────────── */
    .sec-label {
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #999;
        margin-bottom: 10px;
        padding-bottom: 6px;
        border-bottom: 1px solid #f0f0f0;
    }

    /* ── Breadcrumb ───────────────────────────────── */
    .breadcrumb {
        font-size: 0.78rem;
        color: #999;
        padding-top: 6px;
    }
    .breadcrumb .crumb-active { color: #111; font-weight: 600; }

    /* ── Calendar cells ───────────────────────────── */
    .dow-label {
        text-align: center;
        font-size: 0.62rem;
        font-weight: 600;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #bbb;
        padding: 4px 0 10px;
    }
    .cal-cell {
        min-height: 70px;
        border-radius: 8px;
        padding: 8px;
        border: 1px solid #f0f0f0;
        background: #fafafa;
        color: #ccc;
        font-size: 0.72rem;
        font-weight: 500;
    }
    .cal-cell.empty  { border-color: transparent; background: transparent; }
    .cal-cell.active { border-color: #ddd; background: #fff; color: #111; }
    .cal-cell.active:hover { border-color: #bbb; }
    .cal-cell.today  { border-color: #111 !important; background: #fff !important; color: #111 !important; }
    .game-pip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 7px;
        font-size: 0.62rem;
        font-weight: 600;
        color: #555;
        background: #f3f3f3;
        border-radius: 6px;
        padding: 2px 7px;
    }
    .cal-cell.today .game-pip { background: #111; color: #fff; }
    .pip-dot {
        width: 5px; height: 5px;
        border-radius: 50%;
        background: #e00;
        animation: blink 1.4s infinite;
        flex-shrink: 0;
    }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }

    /* ── View button ──────────────────────────────── */
    div[data-testid="stButton"] > button {
        background: #fff;
        color: #111;
        border: 1.5px solid #ddd;
        border-radius: 7px;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 6px 0;
        width: 100%;
        transition: border-color .15s, background .15s;
    }
    div[data-testid="stButton"] > button:hover {
        border-color: #111;
        background: #111;
        color: #fff;
    }

    /* ── Game card (day view) ─────────────────────── */
    .game-card {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 14px 16px;
        background: #fff;
        border: 1px solid #ebebeb;
        border-radius: 10px;
        margin-bottom: 8px;
    }
    .team-name  { font-weight: 700; font-size: 0.9rem; color: #111; }
    .team-rec   { font-size: 0.65rem; color: #aaa; margin-top: 1px; }
    .game-score {
        font-size: 1.3rem;
        font-weight: 700;
        color: #111;
        min-width: 86px;
        text-align: center;
        letter-spacing: -0.5px;
    }
    .game-time  { font-size: 0.72rem; color: #888; min-width: 86px; text-align: center; }
    .status-tag {
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        padding: 3px 9px;
        border-radius: 6px;
        white-space: nowrap;
    }
    .tag-live  { background: #fef2f2; color: #e00; border: 1px solid #fecaca; }
    .tag-final { background: #f5f5f5; color: #555; border: 1px solid #e5e5e5; }
    .tag-sched { background: #f0f7ff; color: #2563eb; border: 1px solid #bfdbfe; }

    /* ── Score banner (box score view) ───────────── */
    .score-banner {
        background: #111;
        color: #fff;
        border-radius: 10px;
        padding: 20px 28px;
        margin-bottom: 18px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .bn-team-name { font-size: 1.1rem; font-weight: 700; }
    .bn-team-rec  { font-size: 0.7rem; color: #777; margin-top: 2px; }
    .bn-score     { font-size: 2.8rem; font-weight: 800; letter-spacing: -1px; }
    .bn-sep       { font-size: 1.2rem; color: #444; padding: 0 8px; }
    .bn-status    { font-size: 0.65rem; font-weight: 700; letter-spacing: 0.5px;
                    text-transform: uppercase; padding: 3px 9px; border-radius: 6px; display: inline-block; }
    .bn-live      { background: #e00; color: #fff; }
    .bn-final     { background: #333; color: #aaa; }
    .bn-pre       { background: #1e3a5f; color: #7aaed6; }
    .bn-venue     { font-size: 0.68rem; color: #555; margin-top: 5px; }

    /* ── Period filter ────────────────────────────── */
    .stRadio > div { flex-direction: row; gap: 6px; flex-wrap: wrap; }
    .stRadio > div > label {
        background: #f5f5f5;
        border: 1px solid #e5e5e5;
        border-radius: 6px;
        padding: 5px 14px;
        font-size: 0.75rem;
        font-weight: 500;
        color: #444;
        cursor: pointer;
    }

    /* ── Tabs ─────────────────────────────────────── */
    .stTabs [data-baseweb="tab"] { font-size: 0.82rem; font-weight: 500; }

    /* ── Period note ──────────────────────────────── */
    .period-note {
        background: #fffbeb;
        border-left: 3px solid #f59e0b;
        padding: 6px 12px;
        font-size: 0.76rem;
        color: #78716c;
        border-radius: 0 6px 6px 0;
        margin-bottom: 10px;
    }

    /* ── Legend ───────────────────────────────────── */
    .cal-legend {
        display: flex;
        gap: 16px;
        font-size: 0.67rem;
        color: #aaa;
        margin-top: 10px;
        align-items: center;
    }
    .l-swatch {
        display: inline-block;
        width: 9px; height: 9px;
        border-radius: 2px;
        margin-right: 4px;
        vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

for k, v in {
    "view":                "calendar",
    "selected_game_id":    None,
    "selected_game":       None,
    "selected_date":       None,
    "selected_date_games": [],
    "cal_year":            et_now().year,
    "cal_month":           et_now().month,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
  <span style="font-size:1.5rem">🏈</span>
  <div>
    <div class="title">NFL Box Score</div>
    <div class="sub">Live stats · Quarter &amp; half splits · All times Eastern</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_week(week: int, season_type: int) -> list:
    try:
        return get_live_games(week=week, season_type=season_type)
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_games_for_month(year: int, month: int) -> list:
    """
    Fetch all game types (regular + playoffs + preseason) for given ET month.
    Groups by Eastern Time date so games at e.g. 1 AM UTC appear on correct day.
    """
    all_games: list = []
    seen_ids:  set  = set()

    configs = [
        (2, range(1, 23)),   # Regular season weeks 1–22
        (3, range(1, 6)),    # Playoffs: WC(1) Div(2) Conf(3) ProBowl(4) SB(5)
        (1, range(0, 5)),    # Preseason weeks 0–4
    ]

    for season_type, weeks in configs:
        for week in weeks:
            games = _fetch_week(int(week), season_type)
            for g in games:
                if g["id"] in seen_ids:
                    continue
                try:
                    # Use ET date for grouping — critical for late-night games
                    gdate = et_date(g["date"])
                    if gdate.year == year and gdate.month == month:
                        all_games.append(g)
                        seen_ids.add(g["id"])
                except Exception:
                    pass

    return all_games

@st.cache_data(ttl=30, show_spinner=False)
def load_all_stats(game_id: str) -> dict:
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

# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — CALENDAR
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.view == "calendar":

    year  = st.session_state.cal_year
    month = st.session_state.cal_month

    with st.spinner(f"Loading {MONTH_NAMES[month-1]} {year}…"):
        month_games = fetch_games_for_month(year, month)

    # Group by Eastern Time date string
    games_by_date: dict = {}
    for g in month_games:
        ds = et_date_str(g["date"])
        games_by_date.setdefault(ds, []).append(g)

    # ── Nav ───────────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("← Prev", use_container_width=True):
            m, y = st.session_state.cal_month - 1, st.session_state.cal_year
            if m < 1: m, y = 12, y - 1
            st.session_state.cal_month, st.session_state.cal_year = m, y
            st.rerun()
    with c2:
        st.markdown(
            f"<div style='text-align:center;font-size:1rem;font-weight:700;"
            f"color:#111;padding-top:4px'>{MONTH_NAMES[month-1]} {year}</div>",
            unsafe_allow_html=True,
        )
    with c3:
        if st.button("Next →", use_container_width=True):
            m, y = st.session_state.cal_month + 1, st.session_state.cal_year
            if m > 12: m, y = 1, y + 1
            st.session_state.cal_month, st.session_state.cal_year = m, y
            st.rerun()

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Day-of-week headers ───────────────────────────────────────────────────
    DOW      = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    hdr_cols = st.columns(7)
    for i, d in enumerate(DOW):
        with hdr_cols[i]:
            st.markdown(f"<div class='dow-label'>{d}</div>", unsafe_allow_html=True)

    # ── Grid ─────────────────────────────────────────────────────────────────
    today_str   = et_now().date().isoformat()
    first_dow   = (date(year, month, 1).weekday() + 1) % 7
    days_in_mon = cal_mod.monthrange(year, month)[1]
    cells       = [None] * first_dow + list(range(1, days_in_mon + 1))
    while len(cells) % 7:
        cells.append(None)

    for row_start in range(0, len(cells), 7):
        row  = cells[row_start:row_start + 7]
        cols = st.columns(7)
        for ci, day in enumerate(row):
            with cols[ci]:
                if day is None:
                    st.markdown("<div class='cal-cell empty'></div>", unsafe_allow_html=True)
                    continue

                ds         = f"{year}-{month:02d}-{day:02d}"
                day_games  = games_by_date.get(ds, [])
                has_games  = bool(day_games)
                is_today   = ds == today_str
                has_live   = any(g["status_state"] == "in" for g in day_games)

                if is_today:
                    cell_cls = "cal-cell today"
                elif has_games:
                    cell_cls = "cal-cell active"
                else:
                    cell_cls = "cal-cell"

                pip_html = ""
                if has_games:
                    dot = "<span class='pip-dot'></span>" if has_live else ""
                    cnt = len(day_games)
                    pip_html = f"<div class='game-pip'>{dot}{cnt} game{'s' if cnt>1 else ''}</div>"

                st.markdown(
                    f"<div class='{cell_cls}'><div>{day}</div>{pip_html}</div>",
                    unsafe_allow_html=True,
                )

                if has_games:
                    if st.button("View", key=f"d_{ds}", use_container_width=True):
                        st.session_state.selected_date       = ds
                        st.session_state.selected_date_games = day_games
                        st.session_state.view = "day"
                        st.rerun()

    # Legend
    st.markdown("""
    <div class="cal-legend">
      <span><span class="l-swatch" style="background:#f3f3f3;border:1px solid #ddd"></span>Has games</span>
      <span><span class="l-swatch" style="background:#111"></span>Today</span>
      <span><span class="pip-dot" style="width:7px;height:7px;display:inline-block;
            background:#e00;border-radius:50%;vertical-align:middle;margin-right:4px"></span>Live</span>
    </div>
    """, unsafe_allow_html=True)

    if not month_games:
        st.info("No games found this month. The NFL season runs August – February.")


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — DAY  (game list for selected date)
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "day":

    ds    = st.session_state.selected_date or ""
    games = st.session_state.selected_date_games or []

    if not ds or not games:
        st.session_state.view = "calendar"
        st.rerun()

    # Format ET date label
    try:
        d_obj      = date.fromisoformat(ds)
        date_label = d_obj.strftime("%A, %B %-d %Y")
    except Exception:
        date_label = ds

    # Back + breadcrumb
    b1, bc = st.columns([1.4, 8])
    with b1:
        if st.button("← Calendar", use_container_width=True):
            st.session_state.view = "calendar"
            st.rerun()
    with bc:
        st.markdown(
            f'<div class="breadcrumb">Calendar '
            f'<span style="color:#ccc">›</span> '
            f'<span class="crumb-active">{date_label}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div class="sec-label" style="margin-top:14px">'
        f'{date_label} · {len(games)} game{"s" if len(games)>1 else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Sort: live first, then by ET kickoff time
    def sort_key(g):
        order = {"in": 0, "post": 1, "pre": 2}
        return (order.get(g["status_state"], 3), g.get("date",""))

    for g in sorted(games, key=sort_key):
        away  = g["away"]; home = g["home"]
        state = g["status_state"]

        # Status tag
        if state == "in":
            tag = f'<span class="status-tag tag-live">● Live · Q{g["period"]}</span>'
        elif state == "post":
            tag = '<span class="status-tag tag-final">Final</span>'
        else:
            tag = '<span class="status-tag tag-sched">Scheduled</span>'

        # Score or kickoff time in ET
        if state == "pre":
            center_html = f'<div class="game-time">{et_time_str(g["date"])}</div>'
        else:
            center_html = f'<div class="game-score">{away["score"]} – {home["score"]}</div>'

        al = f'<img src="{away["logo"]}" style="width:36px;height:36px;object-fit:contain">' if away.get("logo") else ""
        hl = f'<img src="{home["logo"]}" style="width:36px;height:36px;object-fit:contain">' if home.get("logo") else ""

        col_card, col_btn = st.columns([6, 1])
        with col_card:
            st.markdown(f"""
            <div class="game-card">
              <div style="display:flex;align-items:center;gap:10px;flex:1">
                {al}
                <div>
                  <div class="team-name">{away["abbr"]}</div>
                  <div class="team-rec">{away["record"]}</div>
                </div>
              </div>
              {center_html}
              <div style="display:flex;align-items:center;gap:10px;flex:1;
                          flex-direction:row-reverse">
                {hl}
                <div style="text-align:right">
                  <div class="team-name">{home["abbr"]}</div>
                  <div class="team-rec">{home["record"]}</div>
                </div>
              </div>
              {tag}
              <div style="font-size:0.65rem;color:#ccc;min-width:80px;
                          text-align:right">{g.get("venue","")}</div>
            </div>
            """, unsafe_allow_html=True)
        with col_btn:
            st.markdown("<div style='margin-top:8px'>", unsafe_allow_html=True)
            if st.button("Box Score", key=f"bs_{g['id']}", use_container_width=True):
                st.session_state.selected_game_id = g["id"]
                st.session_state.selected_game    = g
                st.session_state.view = "boxscore"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — BOX SCORE
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "boxscore":

    game    = st.session_state.selected_game
    game_id = st.session_state.selected_game_id

    if not game or not game_id:
        st.session_state.view = "calendar"
        st.rerun()

    # Format date label in ET
    try:
        ds         = st.session_state.selected_date or ""
        d_obj      = date.fromisoformat(ds)
        date_label = d_obj.strftime("%b %-d")
    except Exception:
        date_label = "Schedule"

    away_abbr = game["away"]["abbr"]
    home_abbr = game["home"]["abbr"]

    # Back buttons + breadcrumb
    b1, b2, b3, bc = st.columns([1.4, 1.6, 1.2, 5])
    with b1:
        if st.button("← Calendar", use_container_width=True):
            st.session_state.view = "calendar"
            st.rerun()
    with b2:
        if st.button(f"← {date_label}", use_container_width=True):
            st.session_state.view = "day"
            st.rerun()
    with b3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with bc:
        st.markdown(
            f'<div class="breadcrumb">'
            f'Calendar <span style="color:#ccc">›</span> '
            f'<span style="color:#555">{date_label}</span> '
            f'<span style="color:#ccc">›</span> '
            f'<span class="crumb-active">{away_abbr} vs {home_abbr}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Score Banner ──────────────────────────────────────────────────────────
    away = game["away"]; home = game["home"]
    state = game["status_state"]

    if state == "in":
        status_html = (
            f'<span class="bn-status bn-live">Live</span>'
            f'<span style="color:#555;font-size:0.72rem;margin-left:8px">'
            f'{game["clock"]} · Q{game["period"]}</span>'
        )
    elif state == "post":
        status_html = '<span class="bn-status bn-final">Final</span>'
    else:
        # Show ET kickoff for scheduled games
        status_html = (
            f'<span class="bn-status bn-pre">Scheduled</span>'
            f'<span style="color:#666;font-size:0.72rem;margin-left:8px">'
            f'{et_time_str(game["date"])}</span>'
        )

    al = f'<img src="{away["logo"]}" style="width:52px;height:52px;object-fit:contain">' if away.get("logo") else ""
    hl = f'<img src="{home["logo"]}" style="width:52px;height:52px;object-fit:contain">' if home.get("logo") else ""

    st.markdown(f"""
    <div class="score-banner">
      <div style="display:flex;align-items:center;gap:14px">
        {al}
        <div>
          <div class="bn-team-name">{away["team"]}</div>
          <div class="bn-team-rec">{away["record"]}</div>
        </div>
      </div>
      <div style="text-align:center">
        <div>
          <span class="bn-score">{away["score"]}</span>
          <span class="bn-sep"> – </span>
          <span class="bn-score">{home["score"]}</span>
        </div>
        <div style="margin-top:8px">{status_html}</div>
        <div class="bn-venue">{game.get("venue","")}</div>
      </div>
      <div style="display:flex;align-items:center;gap:14px;flex-direction:row-reverse">
        {hl}
        <div style="text-align:right">
          <div class="bn-team-name">{home["team"]}</div>
          <div class="bn-team-rec">{home["record"]}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Load stats ────────────────────────────────────────────────────────────
    with st.spinner("Loading box score…"):
        data = load_all_stats(game_id)
    pbp = data["pbp"]

    # ── Linescore ─────────────────────────────────────────────────────────────
    st.markdown('<div class="sec-label">Score by Quarter</div>', unsafe_allow_html=True)
    ls_df = data["linescore"]
    if ls_df is not None and not ls_df.empty:
        def style_ls(df):
            s = pd.DataFrame("", index=df.index, columns=df.columns)
            for c in ["1H", "2H"]:
                if c in df.columns:
                    s[c] = "background:#f8f8f8;font-weight:600"
            if "Total" in df.columns:
                s["Total"] = "background:#f0f0f0;font-weight:700"
            return s
        st.dataframe(
            ls_df.style.apply(style_ls, axis=None),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Linescore not yet available.")

    # ── Period filter ─────────────────────────────────────────────────────────
    st.markdown('<div class="sec-label" style="margin-top:18px">Player Stats</div>', unsafe_allow_html=True)

    available = ["Full Game"]
    for pk, lbl in [("1H","1st Half"),("2H","2nd Half"),("Q1","Q1"),("Q2","Q2"),("Q3","Q3"),("Q4","Q4")]:
        if pk in pbp and not pbp[pk].empty:
            available.append(lbl)
    for k in pbp:
        if k.startswith("OT") and not pbp[k].empty and k not in available:
            available.append(k)

    period_filter = st.radio(
        "Period:",
        options=available,
        horizontal=True,
        label_visibility="collapsed",
    )

    def get_pbp_key(pf):
        return {"1st Half": "1H", "2nd Half": "2H"}.get(pf, pf)

    def filter_df(df, pf):
        if pf == "Full Game" or df is None or df.empty:
            return df
        k = get_pbp_key(pf)
        if k not in pbp or pbp[k].empty:
            return pd.DataFrame()
        teams = pbp[k]["Team"].dropna().unique().tolist()
        if not teams or "Team" not in df.columns:
            return df
        out = df[df["Team"].isin(teams)]
        return out if not out.empty else df

    def show_df(df, pf, sort=None):
        if df is None or df.empty:
            st.info("No data available.")
            return
        out = filter_df(df, pf)
        if out is None or out.empty:
            st.info(f"No data for {pf}.")
            return
        if pf != "Full Game":
            st.markdown(
                '<div class="period-note">Showing players active in this period. '
                'ESPN provides cumulative game totals — see Play-by-Play for play-level detail.</div>',
                unsafe_allow_html=True,
            )
        if sort and sort in out.columns:
            try:
                tmp       = out.copy()
                tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                out       = tmp.sort_values(sort, ascending=False)
            except Exception:
                pass
        st.dataframe(out, use_container_width=True, hide_index=True)

    # Stat tabs
    tabs = st.tabs(["Passing","Rushing","Receiving","Defense","Kicking","Returning","Team"])
    with tabs[0]: show_df(data["passing"],   period_filter, "YDS")
    with tabs[1]: show_df(data["rushing"],   period_filter, "YDS")
    with tabs[2]: show_df(data["receiving"], period_filter, "YDS")
    with tabs[3]: show_df(data["defense"],   period_filter, "TOT")
    with tabs[4]: show_df(data["kicking"],   period_filter)
    with tabs[5]: show_df(data["returning"], period_filter, "YDS")
    with tabs[6]:
        t = data["team"]
        if t is not None and not t.empty:
            st.dataframe(t, use_container_width=True, hide_index=True)
        else:
            st.info("No team data.")

    # ── Scoring Summary ───────────────────────────────────────────────────────
    st.markdown('<div class="sec-label" style="margin-top:18px">Scoring Summary</div>', unsafe_allow_html=True)
    sdf = data["scoring"]
    if sdf is not None and not sdf.empty:
        pf = period_filter
        if pf == "Full Game":
            fsdf = sdf
        elif pf in ("1st Half", "2nd Half"):
            fsdf = sdf[sdf["Half"] == pf]
        elif pf.startswith("OT"):
            fsdf = sdf[sdf["Half"].str.startswith("OT", na=False)]
        else:
            fsdf = sdf[sdf["Quarter"] == pf]

        if fsdf.empty:
            st.info(f"No scoring plays in {pf}.")
        else:
            for half in fsdf["Half"].unique():
                hdf = fsdf[fsdf["Half"] == half]
                st.markdown(f"**{half}**")
                st.dataframe(
                    hdf.drop(columns=["Half"]),
                    use_container_width=True,
                    hide_index=True,
                )
    else:
        st.info("No scoring plays yet.")

    # ── Play-by-Play ──────────────────────────────────────────────────────────
    st.markdown('<div class="sec-label" style="margin-top:18px">Play-by-Play</div>', unsafe_allow_html=True)
    if pbp:
        pf = period_filter
        k  = get_pbp_key(pf)
        if pf == "Full Game":
            show = {x: pbp[x] for x in ["Q1","Q2","Q3","Q4"] if x in pbp}
            show.update({x: pbp[x] for x in pbp if x.startswith("OT")})
        elif pf == "1st Half":
            show = {x: pbp[x] for x in ["Q1","Q2"] if x in pbp}
        elif pf == "2nd Half":
            show = {x: pbp[x] for x in ["Q3","Q4"] if x in pbp}
        else:
            show = {k: pbp[k]} if k in pbp else {}

        if show:
            ptabs = st.tabs(list(show.keys()))
            for tab, key in zip(ptabs, show.keys()):
                with tab:
                    df   = show[key]
                    cols = [c for c in ["Clock","Team","Down & Distance","Description","Yards","Play Type"] if c in df.columns]
                    st.dataframe(df[cols], use_container_width=True, hide_index=True)
        else:
            st.info(f"No play-by-play for {pf}.")
    else:
        st.info("Play-by-play not yet available.")

    st.markdown("---")
    st.caption(
        f"Updated {datetime.now().strftime('%-I:%M %p')} ET  ·  "
        "Data: ESPN public API  ·  Not affiliated with ESPN or the NFL"
    )
