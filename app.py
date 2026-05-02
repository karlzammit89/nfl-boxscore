"""
app.py  —  NFL Box Scores
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

# ── Eastern Time helpers ──────────────────────────────────────────────────────

def to_et(utc_str: str) -> datetime:
    try:
        utc_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        offset = timedelta(hours=-4) if 3 <= utc_dt.month <= 10 else timedelta(hours=-5)
        return utc_dt.replace(tzinfo=None) + offset
    except Exception:
        return datetime.now()

def et_date(utc_str: str) -> date:
    return to_et(utc_str).date()

def et_date_str(utc_str: str) -> str:
    return et_date(utc_str).isoformat()

def et_time_str(utc_str: str) -> str:
    try:
        return to_et(utc_str).strftime("%-I:%M %p ET")
    except Exception:
        return ""

def et_now() -> datetime:
    utc_now = datetime.now(timezone.utc)
    offset  = timedelta(hours=-4) if 3 <= utc_now.month <= 10 else timedelta(hours=-5)
    return utc_now.replace(tzinfo=None) + offset

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NFL Box Scores",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

[data-testid="stSidebar"]        { display: none; }
[data-testid="collapsedControl"] { display: none; }
.block-container { padding-top: 1.2rem !important; max-width: 1100px; }
html, body, * { font-family: 'Inter', system-ui, sans-serif; }

/* ─── HEADER ─────────────────────────────────────── */
.app-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 18px 24px;
    background: #1a1a2e;
    border-radius: 12px;
    margin-bottom: 22px;
    border-left: 5px solid #e63946;
    box-sizing: border-box;
    width: 100%;
    overflow: hidden;
}
.app-header .title { font-size: 1.3rem; font-weight: 800; color: #ffffff; letter-spacing: -0.3px; white-space: nowrap; }
.app-header .sub   { font-size: 0.72rem; color: #8899aa; margin-top: 3px; white-space: nowrap; }

/* ─── SECTION LABEL ──────────────────────────────── */
.sec-label {
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: #8899aa;
    margin-bottom: 10px;
    padding-bottom: 7px;
    border-bottom: 2px solid #eef0f4;
}

/* ─── MONTH TITLE ────────────────────────────────── */
.month-title {
    text-align: center;
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--text-color, #1a1a2e);
    padding-top: 4px;
    letter-spacing: -0.3px;
}

/* ─── CALENDAR ───────────────────────────────────── */
.dow-label {
    text-align: center;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #8899aa;
    padding: 4px 0 10px;
}

/* Base cell — transparent bg inherits page, visible border both modes */
.cal-cell {
    min-height: 72px;
    border-radius: 10px;
    padding: 9px 10px;
    border: 1.5px solid rgba(128,128,128,0.25);
    background: var(--secondary-background-color);
    color: rgba(128,128,128,0.6);
    font-size: 0.74rem;
    font-weight: 600;
    position: relative;
    user-select: none;
}
.cal-cell.empty {
    border-color: transparent;
    background: transparent;
    pointer-events: none;
}
/* Days with games — clickable, visually distinct */
.cal-cell.active {
    border-color: #2563eb;
    background: var(--secondary-background-color);
    color: #2563eb;
    cursor: pointer;
    transition: border-color .15s, box-shadow .15s, transform .1s;
}
.cal-cell.active:hover {
    border-color: #1d4ed8;
    box-shadow: 0 4px 14px rgba(37,99,235,0.18);
    transform: translateY(-1px);
}
.cal-cell.today {
    border-color: #e63946 !important;
    background: var(--secondary-background-color) !important;
    color: #e63946 !important;
}
.cal-cell.today.active {
    cursor: pointer;
}

/* Game count pill */
.game-pip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 8px;
    font-size: 0.62rem;
    font-weight: 700;
    color: #2563eb;
    background: #dbeafe;
    border-radius: 6px;
    padding: 2px 8px;
}
.cal-cell.today .game-pip { background: #fecdd3; color: #be123c; }

/* Live pulse dot */
.pip-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #e63946;
    flex-shrink: 0;
    animation: blink 1.3s infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

/* ─── LEGEND ─────────────────────────────────────── */
.cal-legend {
    display: flex;
    gap: 18px;
    font-size: 0.67rem;
    color: #8899aa;
    margin-top: 12px;
    align-items: center;
}
.l-sw {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 3px;
    margin-right: 5px;
    vertical-align: middle;
}

/* ─── NAV BUTTONS ────────────────────────────────── */
div[data-testid="stButton"] > button {
    background: #1a1a2e;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 0.78rem;
    font-weight: 600;
    padding: 7px 0;
    width: 100%;
    transition: background .15s, transform .1s;
    letter-spacing: 0.2px;
}
div[data-testid="stButton"] > button:hover {
    background: #2563eb;
    transform: translateY(-1px);
}

/* ─── GAME CARD (day view) ───────────────────────── */
.game-card {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 18px;
    background: #ffffff;
    border: 1.5px solid #e8eaf0;
    border-radius: 12px;
    margin-bottom: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    transition: border-color .15s, box-shadow .15s;
}
.game-card:hover { border-color: #2563eb; box-shadow: 0 3px 12px rgba(37,99,235,0.1); }

.team-name  { font-weight: 700; font-size: 0.92rem; color: #1a1a2e; }
.team-rec   { font-size: 0.65rem; color: #8899aa; margin-top: 2px; }
.game-score { font-size: 1.4rem; font-weight: 800; color: #1a1a2e; min-width: 90px; text-align: center; letter-spacing: -0.5px; }
.game-time  { font-size: 0.75rem; color: #2563eb; font-weight: 600; min-width: 90px; text-align: center; }
.venue-txt  { font-size: 0.63rem; color: #b0bac8; text-align: right; flex: 1; }

.s-tag   { font-size: 0.61rem; font-weight: 700; letter-spacing: 0.6px;
            text-transform: uppercase; padding: 4px 10px; border-radius: 6px; white-space: nowrap; }
.s-live  { background: #fef2f2; color: #dc2626; border: 1.5px solid #fca5a5; }
.s-final { background: #f1f5f9; color: #475569; border: 1.5px solid #cbd5e1; }
.s-sched { background: #eff6ff; color: #2563eb; border: 1.5px solid #93c5fd; }

/* ─── SCORE BANNER ───────────────────────────────── */
.score-banner {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #ffffff;
    border-radius: 14px;
    padding: 22px 30px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 20px rgba(26,26,46,0.22);
}
.bn-name  { font-size: 1.1rem; font-weight: 700; color: #ffffff; }
.bn-rec   { font-size: 0.68rem; color: #667788; margin-top: 3px; }
.bn-score { font-size: 3rem; font-weight: 800; color: #ffffff; letter-spacing: -2px; }
.bn-sep   { font-size: 1.3rem; color: #334455; padding: 0 10px; }
.bn-st    { font-size: 0.63rem; font-weight: 700; letter-spacing: 0.7px;
             text-transform: uppercase; padding: 4px 10px; border-radius: 6px; display: inline-block; }
.bn-live  { background: #dc2626; color: #fff; }
.bn-final { background: #334455; color: #8899aa; }
.bn-pre   { background: #1e3a5f; color: #60a5fa; }
.bn-venue { font-size: 0.67rem; color: #445566; margin-top: 6px; }

/* ─── PERIOD FILTER ──────────────────────────────── */
.stRadio > div { flex-direction: row; gap: 7px; flex-wrap: wrap; }
.stRadio > div > label {
    background: #f1f5f9;
    border: 1.5px solid #e2e8f0;
    border-radius: 8px;
    padding: 5px 15px;
    font-size: 0.75rem;
    font-weight: 600;
    color: #334155;
    cursor: pointer;
}

/* ─── TABS ───────────────────────────────────────── */
.stTabs [data-baseweb="tab"] { font-size: 0.82rem; font-weight: 600; }

/* ─── PERIOD NOTE ────────────────────────────────── */
.period-note {
    background: #fffbeb;
    border-left: 3px solid #f59e0b;
    padding: 7px 12px;
    font-size: 0.75rem;
    color: #78716c;
    border-radius: 0 7px 7px 0;
    margin-bottom: 10px;
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

MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
  <span style="font-size:1.6rem;flex-shrink:0;line-height:1">🏈</span>
  <div style="min-width:0">
    <div class="title">NFL Box Scores</div>
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
    all_games: list = []
    seen_ids:  set  = set()
    for season_type, weeks in [(2, range(1,23)), (3, range(1,6)), (1, range(0,5))]:
        for week in weeks:
            for g in _fetch_week(int(week), season_type):
                if g["id"] in seen_ids:
                    continue
                try:
                    gd = et_date(g["date"])
                    if gd.year == year and gd.month == month:
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

    games_by_date: dict = {}
    for g in month_games:
        games_by_date.setdefault(et_date_str(g["date"]), []).append(g)

    # ── Navigation ────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("← Prev", use_container_width=True):
            m, y = st.session_state.cal_month - 1, st.session_state.cal_year
            if m < 1: m, y = 12, y - 1
            st.session_state.cal_month, st.session_state.cal_year = m, y
            st.rerun()
    with c2:
        # Fix 4: strong dark colour so month title is clearly visible
        st.markdown(
            f"<div class='month-title'>{MONTH_NAMES[month-1]} {year}</div>",
            unsafe_allow_html=True,
        )
    with c3:
        if st.button("Next →", use_container_width=True):
            m, y = st.session_state.cal_month + 1, st.session_state.cal_year
            if m > 12: m, y = 1, y + 1
            st.session_state.cal_month, st.session_state.cal_year = m, y
            st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Day-of-week headers
    for col, d in zip(st.columns(7), ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]):
        with col:
            st.markdown(f"<div class='dow-label'>{d}</div>", unsafe_allow_html=True)

    # Build grid cells
    today_str   = et_now().date().isoformat()
    first_dow   = (date(year, month, 1).weekday() + 1) % 7
    days_in_mon = cal_mod.monthrange(year, month)[1]
    cells       = [None] * first_dow + list(range(1, days_in_mon + 1))
    while len(cells) % 7:
        cells.append(None)

    # Fix 5: days with games use st.button styled to look like the cell
    # We overlay a transparent button on top of the rendered cell HTML
    for row_start in range(0, len(cells), 7):
        cols = st.columns(7)
        for ci, day in enumerate(cells[row_start:row_start + 7]):
            with cols[ci]:
                if day is None:
                    st.markdown("<div class='cal-cell empty'></div>", unsafe_allow_html=True)
                    continue

                ds        = f"{year}-{month:02d}-{day:02d}"
                day_games = games_by_date.get(ds, [])
                has_games = bool(day_games)
                is_today  = ds == today_str
                has_live  = any(g["status_state"] == "in" for g in day_games)

                if is_today and has_games:
                    cls = "cal-cell today active"
                elif is_today:
                    cls = "cal-cell today"
                elif has_games:
                    cls = "cal-cell active"
                else:
                    cls = "cal-cell"

                pip = ""
                if has_games:
                    dot = "<span class='pip-dot'></span>" if has_live else ""
                    n   = len(day_games)
                    pip = f"<div class='game-pip'>{dot}{n} game{'s' if n>1 else ''}</div>"

                if has_games:
                    # Fix 5: entire cell is the button — use label with HTML
                    # We render the visual cell then immediately a zero-height
                    # button that covers it via negative margin trick.
                    # Cleanest Streamlit-native approach: render cell HTML,
                    # then a button whose CSS makes it look invisible/full-width.
                    st.markdown(f"<div class='{cls}'>{day}{pip}</div>", unsafe_allow_html=True)

                    # Style this specific button to be compact and blend
                    # (the global button style is overridden per-cell below)
                    btn_key = f"d_{ds}"
                    clicked = st.button(
                        f"Select {day}",
                        key=btn_key,
                        use_container_width=True,
                        help=f"{len(day_games)} game{'s' if len(day_games)>1 else ''} — click to view",
                    )
                    if clicked:
                        st.session_state.selected_date       = ds
                        st.session_state.selected_date_games = day_games
                        st.session_state.view = "day"
                        st.rerun()
                else:
                    st.markdown(f"<div class='{cls}'>{day}</div>", unsafe_allow_html=True)

    # Fix 1: removed "no games" message entirely

    # Legend
    st.markdown("""
    <div class="cal-legend">
      <span><span class="l-sw" style="border:1.5px solid #2563eb"></span>Has games</span>
      <span><span class="l-sw" style="border:1.5px solid #e63946"></span>Today</span>
      <span>
        <span style="display:inline-block;width:8px;height:8px;background:#e63946;
          border-radius:50%;margin-right:5px;vertical-align:middle;animation:blink 1.3s infinite">
        </span>Live
      </span>
    </div>
    """, unsafe_allow_html=True)

    # Inject CSS to hide the button label text and make buttons invisible/minimal
    # so only the game-pip cell above is visible — clicking the button area selects the day
    st.markdown("""
    <style>
    /* Make calendar day buttons look invisible — the visual cell above is the UI */
    [data-testid="stButton"] > button[title*="game"] {
        background: transparent !important;
        border: none !important;
        color: transparent !important;
        font-size: 0 !important;
        height: 6px !important;
        min-height: unset !important;
        padding: 0 !important;
        margin-top: -4px !important;
        cursor: pointer !important;
        box-shadow: none !important;
        transform: none !important;
    }
    [data-testid="stButton"] > button[title*="game"]:hover {
        background: transparent !important;
        transform: none !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — DAY
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "day":

    ds    = st.session_state.selected_date or ""
    games = st.session_state.selected_date_games or []

    if not ds or not games:
        st.session_state.view = "calendar"
        st.rerun()

    try:
        d_obj      = date.fromisoformat(ds)
        date_label = d_obj.strftime("%A, %B %-d %Y")
    except Exception:
        date_label = ds

    # Fix 2: back button only, no breadcrumb text beside it
    b_col, _ = st.columns([1.4, 8])
    with b_col:
        if st.button("← Calendar", use_container_width=True):
            st.session_state.view = "calendar"
            st.rerun()

    st.markdown(
        f'<div class="sec-label" style="margin-top:14px">'
        f'{date_label} &nbsp;·&nbsp; {len(games)} game{"s" if len(games)>1 else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    def sort_key(g):
        return ({"in":0,"post":1,"pre":2}.get(g["status_state"],3), g.get("date",""))

    for g in sorted(games, key=sort_key):
        away  = g["away"]; home = g["home"]
        state = g["status_state"]

        if state == "in":
            tag = f'<span class="s-tag s-live">● Live · Q{g["period"]}</span>'
        elif state == "post":
            tag = '<span class="s-tag s-final">Final</span>'
        else:
            tag = '<span class="s-tag s-sched">Scheduled</span>'

        if state == "pre":
            mid = f'<div class="game-time">{et_time_str(g["date"])}</div>'
        else:
            mid = f'<div class="game-score">{away["score"]} – {home["score"]}</div>'

        al = f'<img src="{away["logo"]}" style="width:38px;height:38px;object-fit:contain">' if away.get("logo") else ""
        hl = f'<img src="{home["logo"]}" style="width:38px;height:38px;object-fit:contain">' if home.get("logo") else ""

        c_card, c_btn = st.columns([6, 1])
        with c_card:
            st.markdown(f"""
            <div class="game-card">
              <div style="display:flex;align-items:center;gap:10px;flex:1">
                {al}
                <div>
                  <div class="team-name">{away["abbr"]}</div>
                  <div class="team-rec">{away["record"]}</div>
                </div>
              </div>
              {mid}
              <div style="display:flex;align-items:center;gap:10px;flex:1;flex-direction:row-reverse">
                {hl}
                <div style="text-align:right">
                  <div class="team-name">{home["abbr"]}</div>
                  <div class="team-rec">{home["record"]}</div>
                </div>
              </div>
              {tag}
              <div class="venue-txt">{g.get("venue","")}</div>
            </div>
            """, unsafe_allow_html=True)
        with c_btn:
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

    try:
        ds         = st.session_state.selected_date or ""
        date_label = date.fromisoformat(ds).strftime("%b %-d")
    except Exception:
        date_label = "Schedule"

    # Fix 2: back buttons only — no breadcrumb text
    b1, b2, b3, _ = st.columns([1.4, 1.6, 1.2, 5])
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

    # Score Banner
    away  = game["away"]; home = game["home"]
    state = game["status_state"]

    if state == "in":
        status_html = (
            f'<span class="bn-st bn-live">Live</span>'
            f'<span style="color:#667788;font-size:0.72rem;margin-left:9px">'
            f'{game["clock"]} · Q{game["period"]}</span>'
        )
    elif state == "post":
        status_html = '<span class="bn-st bn-final">Final</span>'
    else:
        status_html = (
            f'<span class="bn-st bn-pre">Scheduled</span>'
            f'<span style="color:#60a5fa;font-size:0.72rem;margin-left:9px">'
            f'{et_time_str(game["date"])}</span>'
        )

    al = f'<img src="{away["logo"]}" style="width:54px;height:54px;object-fit:contain">' if away.get("logo") else ""
    hl = f'<img src="{home["logo"]}" style="width:54px;height:54px;object-fit:contain">' if home.get("logo") else ""

    st.markdown(f"""
    <div class="score-banner">
      <div style="display:flex;align-items:center;gap:16px">
        {al}
        <div>
          <div class="bn-name">{away["team"]}</div>
          <div class="bn-rec">{away["record"]}</div>
        </div>
      </div>
      <div style="text-align:center">
        <div>
          <span class="bn-score">{away["score"]}</span>
          <span class="bn-sep">–</span>
          <span class="bn-score">{home["score"]}</span>
        </div>
        <div style="margin-top:9px">{status_html}</div>
        <div class="bn-venue">{game.get("venue","")}</div>
      </div>
      <div style="display:flex;align-items:center;gap:16px;flex-direction:row-reverse">
        {hl}
        <div style="text-align:right">
          <div class="bn-name">{home["team"]}</div>
          <div class="bn-rec">{home["record"]}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Loading box score…"):
        data = load_all_stats(game_id)
    pbp = data["pbp"]

    # Linescore
    st.markdown('<div class="sec-label">Score by Quarter</div>', unsafe_allow_html=True)
    ls_df = data["linescore"]
    if ls_df is not None and not ls_df.empty:
        def style_ls(df):
            s = pd.DataFrame("", index=df.index, columns=df.columns)
            for c in ["1H","2H"]:
                if c in df.columns:
                    s[c] = "background:#eff6ff;font-weight:700;color:#1e40af"
            if "Total" in df.columns:
                s["Total"] = "background:#1a1a2e;font-weight:800;color:#ffffff"
            return s
        st.dataframe(ls_df.style.apply(style_ls, axis=None), use_container_width=True, hide_index=True)
    else:
        st.info("Linescore not yet available.")

    # Period filter
    st.markdown('<div class="sec-label" style="margin-top:20px">Player Stats</div>', unsafe_allow_html=True)

    available = ["Full Game"]
    for pk, lbl in [("1H","1st Half"),("2H","2nd Half"),("Q1","Q1"),("Q2","Q2"),("Q3","Q3"),("Q4","Q4")]:
        if pk in pbp and not pbp[pk].empty:
            available.append(lbl)
    for k in pbp:
        if k.startswith("OT") and not pbp[k].empty and k not in available:
            available.append(k)

    period_filter = st.radio("Period:", options=available, horizontal=True, label_visibility="collapsed")

    def get_pbp_key(pf):
        return {"1st Half":"1H","2nd Half":"2H"}.get(pf, pf)

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
                tmp = out.copy()
                tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                out = tmp.sort_values(sort, ascending=False)
            except Exception:
                pass
        st.dataframe(out, use_container_width=True, hide_index=True)

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

    st.markdown('<div class="sec-label" style="margin-top:20px">Scoring Summary</div>', unsafe_allow_html=True)
    sdf = data["scoring"]
    if sdf is not None and not sdf.empty:
        pf = period_filter
        if pf == "Full Game":               fsdf = sdf
        elif pf in ("1st Half","2nd Half"): fsdf = sdf[sdf["Half"] == pf]
        elif pf.startswith("OT"):           fsdf = sdf[sdf["Half"].str.startswith("OT", na=False)]
        else:                               fsdf = sdf[sdf["Quarter"] == pf]
        if fsdf.empty:
            st.info(f"No scoring plays in {pf}.")
        else:
            for half in fsdf["Half"].unique():
                hdf = fsdf[fsdf["Half"] == half]
                st.markdown(f"**{half}**")
                st.dataframe(hdf.drop(columns=["Half"]), use_container_width=True, hide_index=True)
    else:
        st.info("No scoring plays yet.")

    st.markdown('<div class="sec-label" style="margin-top:20px">Play-by-Play</div>', unsafe_allow_html=True)
    if pbp:
        pf = period_filter
        k  = get_pbp_key(pf)
        if pf == "Full Game":
            show = {x: pbp[x] for x in ["Q1","Q2","Q3","Q4"] if x in pbp}
            show.update({x: pbp[x] for x in pbp if x.startswith("OT")})
        elif pf == "1st Half": show = {x: pbp[x] for x in ["Q1","Q2"] if x in pbp}
        elif pf == "2nd Half": show = {x: pbp[x] for x in ["Q3","Q4"] if x in pbp}
        else:                  show = {k: pbp[k]} if k in pbp else {}
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
        f"Updated {et_now().strftime('%-I:%M %p')} ET  ·  "
        "ESPN public API  ·  Not affiliated with ESPN or the NFL"
    )
