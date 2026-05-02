"""
app.py  —  NFL Live Box Score Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date
import calendar as cal_mod
import json

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
    page_title="NFL Box Score",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

    [data-testid="stSidebar"]        { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    .block-container { padding-top: 1.5rem !important; max-width: 1200px; }
    * { font-family: 'Inter', sans-serif; }

    /* ── Header ── */
    .nfl-header {
        background: linear-gradient(135deg, #0f1f0f 0%, #1a2e1a 100%);
        color: white;
        padding: 1.1rem 1.8rem;
        border-radius: 12px;
        margin-bottom: 1.6rem;
        display: flex;
        align-items: center;
        gap: 1rem;
        border-left: 5px solid #4caf72;
        box-shadow: 0 2px 16px rgba(0,0,0,0.25);
    }
    .nfl-header h1 {
        margin: 0;
        font-family: 'Oswald', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #e8f5e8;
    }
    .nfl-header p { margin: 0.15rem 0 0; opacity: 0.5; font-size: 0.8rem; color: #e8f5e8; }

    /* ── Section labels ── */
    .section-label {
        font-family: 'Oswald', sans-serif;
        font-size: 0.68rem;
        letter-spacing: 2.5px;
        text-transform: uppercase;
        color: #7a9a7a;
        margin-bottom: 0.7rem;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid rgba(76,175,114,0.18);
    }

    /* ── Nav buttons — identical fixed size ── */
    div[data-testid="stButton"] > button {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        border-radius: 8px;
        border: 1px solid rgba(76,175,114,0.4);
        background: transparent;
        color: #4caf72;
        font-size: 0.85rem;
        padding: 0.45rem 0;
        width: 100%;
        text-align: center;
        transition: all 0.15s;
        white-space: nowrap;
    }
    div[data-testid="stButton"] > button:hover {
        background: #4caf72;
        color: #0f1f0f;
        border-color: #4caf72;
        font-weight: 700;
    }

    /* ── Score banner ── */
    .score-banner {
        background: linear-gradient(135deg, #0f1f0f 0%, #152515 100%);
        color: #e8f5e8;
        border-radius: 12px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.3rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border: 1px solid rgba(76,175,114,0.2);
        box-shadow: 0 2px 16px rgba(0,0,0,0.2);
    }
    .score-team-name { font-family:'Oswald',sans-serif; font-size:1.3rem; font-weight:600; letter-spacing:0.5px; color:#e8f5e8; }
    .score-record    { font-size:0.73rem; color:#5a7a5a; margin-top:3px; }
    .score-num       { font-family:'Oswald',sans-serif; font-size:3.2rem; font-weight:700; color:#e8f5e8; }
    .score-sep       { font-size:1.5rem; color:#2a4a2a; padding:0 0.7rem; }
    .status-pill     { background:#4caf72; color:#0f1f0f; font-size:0.68rem; font-weight:700;
                       padding:0.22rem 0.8rem; border-radius:20px; text-transform:uppercase;
                       letter-spacing:0.8px; display:inline-block; font-family:'Oswald',sans-serif; }
    .status-pill.final { background:#2a3a2a; color:#7a9a7a; }
    .status-pill.pre   { background:#1a3a2a; color:#4caf72; }

    /* ── Period filter radio ── */
    .stRadio > div { flex-direction:row; gap:6px; flex-wrap:wrap; }
    .stRadio > div > label {
        background: rgba(76,175,114,0.07);
        border: 1px solid rgba(76,175,114,0.22);
        border-radius: 20px;
        padding: 4px 16px;
        font-size: 0.78rem;
        cursor: pointer;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        color: #7aba8a;
        transition: all 0.15s;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab"] {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
    }

    /* ── Period note ── */
    .period-note {
        background: rgba(76,175,114,0.06);
        border-left: 3px solid #4caf72;
        border-radius: 0 6px 6px 0;
        padding: 0.4rem 0.9rem;
        font-size: 0.77rem;
        color: #5a7a5a;
        margin-bottom: 0.7rem;
    }

    .empty-state {
        text-align:center;
        padding:3rem 1rem;
        color:#5a7a5a;
        font-size:0.93rem;
    }

    /* ── Breadcrumb ── */
    .breadcrumb {
        font-size: 0.75rem;
        color: #5a7a5a;
        margin-bottom: 1rem;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
    }
    .breadcrumb span { color: #4caf72; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

for key, default in {
    "view":             "calendar",   # "calendar" | "day" | "boxscore"
    "selected_game_id": None,
    "selected_game":    None,
    "selected_date":    None,         # ISO string for day view
    "selected_date_games": [],        # games on selected day
    "cal_year":         datetime.now().year,
    "cal_month":        datetime.now().month,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nfl-header">
  <div style="font-size:2.1rem">🏈</div>
  <div>
    <h1>NFL Box Score</h1>
    <p>Live stats · Quarter &amp; half splits · Play-by-play</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_week(week: int, season_type: int):
    try:
        return get_live_games(week=week)
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_games_for_month(year: int, month: int) -> list:
    """
    Exhaustively fetch every game type for the given month.
    Playoff fix: ESPN uses season_type=3, weeks 1-5 AND also sometimes
    exposes them under season_type=2 week 19-22, so we check both.
    """
    all_games: list = []
    seen_ids:  set  = set()

    configs = [
        (2, range(1, 23)),   # Regular + any late-season overflow weeks 1-22
        (3, range(1, 6)),    # Playoffs: Wild Card(1) Div(2) Conf(3) ProBowl(4) SB(5)
        (1, range(0, 5)),    # Preseason weeks 0-4
    ]

    for season_type, weeks in configs:
        for week in weeks:
            games = _fetch_week(week, season_type)
            for g in games:
                if g["id"] in seen_ids:
                    continue
                try:
                    gdate = datetime.fromisoformat(g["date"].replace("Z","")).date()
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

MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: CALENDAR
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.view == "calendar":

    year  = st.session_state.cal_year
    month = st.session_state.cal_month

    with st.spinner(f"Loading {MONTH_NAMES[month-1]} {year}…"):
        month_games = fetch_games_for_month(year, month)

    games_by_date: dict = {}
    for g in month_games:
        try:
            gdate = datetime.fromisoformat(g["date"].replace("Z","")).date()
            games_by_date.setdefault(gdate.isoformat(), []).append(g)
        except Exception:
            pass

    # ── Navigation — equal-width columns so buttons are same size ────────────
    nav1, nav2, nav3 = st.columns([1, 2, 1])
    with nav1:
        if st.button("← Prev", use_container_width=True):
            m = st.session_state.cal_month - 1
            y = st.session_state.cal_year
            if m < 1: m = 12; y -= 1
            st.session_state.cal_month = m
            st.session_state.cal_year  = y
            st.rerun()
    with nav2:
        st.markdown(
            f"<div style='text-align:center;font-weight:700;padding-top:5px;"
            f"font-family:Oswald,sans-serif;font-size:1.15rem;letter-spacing:0.5px;"
            f"color:#4caf72'>{MONTH_NAMES[month-1]} {year}</div>",
            unsafe_allow_html=True,
        )
    with nav3:
        if st.button("Next →", use_container_width=True):
            m = st.session_state.cal_month + 1
            y = st.session_state.cal_year
            if m > 12: m = 1; y += 1
            st.session_state.cal_month = m
            st.session_state.cal_year  = y
            st.rerun()

    # ── Build calendar HTML ───────────────────────────────────────────────────
    today_str   = date.today().isoformat()
    first_dow   = (date(year, month, 1).weekday() + 1) % 7  # Sun=0
    days_in_mon = cal_mod.monthrange(year, month)[1]

    cal_data = {}
    for ds, games in games_by_date.items():
        cal_data[ds] = {
            "count":    len(games),
            "has_live": any(g["status_state"] == "in" for g in games),
        }

    cal_json = json.dumps(cal_data)

    calendar_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,sans-serif;background:transparent;color:#b8d4b8}}
.dow-row,.day-row{{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;margin-bottom:3px}}
.dow{{text-align:center;font-size:0.58rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#3a5a3a;padding:4px 0 7px}}
.day{{min-height:66px;border-radius:7px;border:1px solid rgba(76,175,114,0.08);padding:6px 7px;background:rgba(255,255,255,0.01);cursor:default;transition:border-color 0.15s,background 0.15s}}
.day.empty{{border-color:transparent;background:transparent;pointer-events:none}}
.day.has-games{{border-color:rgba(76,175,114,0.28);background:rgba(76,175,114,0.04);cursor:pointer}}
.day.has-games:hover{{border-color:rgba(76,175,114,0.6);background:rgba(76,175,114,0.09)}}
.day.today{{border-color:rgba(76,175,114,0.55)!important;background:rgba(76,175,114,0.06)!important}}
.day.selected{{border-color:#4caf72!important;background:rgba(76,175,114,0.13)!important;box-shadow:0 0 0 1px #4caf72}}
.day-num{{font-size:0.7rem;font-weight:600;color:#3a5a3a;line-height:1}}
.day.has-games .day-num{{color:#7aba8a;font-weight:700}}
.day.today .day-num{{color:#4caf72}}
.day.selected .day-num{{color:#4caf72}}
.badge{{display:inline-flex;align-items:center;gap:4px;margin-top:9px;background:rgba(76,175,114,0.11);border:1px solid rgba(76,175,114,0.2);border-radius:20px;padding:3px 8px;font-size:0.62rem;font-weight:700;color:#7aba8a;white-space:nowrap}}
.day.today .badge,.day.selected .badge{{background:rgba(76,175,114,0.18);border-color:rgba(76,175,114,0.42);color:#4caf72}}
.live-dot{{width:6px;height:6px;background:#4caf72;border-radius:50%;flex-shrink:0;animation:pulse 1.2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.2}}}}
.legend{{display:flex;gap:14px;align-items:center;margin-top:10px;font-size:0.66rem;color:#3a5a3a}}
.lbox{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:middle}}
</style>
</head><body>
<div class="dow-row">
  <div class="dow">Sun</div><div class="dow">Mon</div><div class="dow">Tue</div>
  <div class="dow">Wed</div><div class="dow">Thu</div><div class="dow">Fri</div><div class="dow">Sat</div>
</div>
<div id="cal"></div>
<div class="legend">
  <span><span class="lbox" style="background:rgba(76,175,114,0.1);border:1px solid rgba(76,175,114,0.32)"></span>Has games</span>
  <span><span class="lbox" style="background:rgba(76,175,114,0.07);border:1px solid rgba(76,175,114,0.55)"></span>Today</span>
  <span><span style="display:inline-block;width:7px;height:7px;background:#4caf72;border-radius:50%;margin-right:4px;vertical-align:middle;animation:pulse 1.2s infinite"></span>Live</span>
</div>
<script>
const CAL={cal_json};
const TODAY='{today_str}';
const FDOW={first_dow};
const DAYS={days_in_mon};
const YEAR={year};
const MON=String({month}).padStart(2,'0');
function pad(n){{return String(n).padStart(2,'0')}}
const container=document.getElementById('cal');
let cells=[];
for(let i=0;i<FDOW;i++) cells.push(null);
for(let d=1;d<=DAYS;d++) cells.push(d);
while(cells.length%7!==0) cells.push(null);
for(let r=0;r<cells.length/7;r++){{
  const row=document.createElement('div');
  row.className='day-row';
  for(let c=0;c<7;c++){{
    const d=cells[r*7+c];
    const el=document.createElement('div');
    if(d===null){{el.className='day empty';}}
    else{{
      const ds=YEAR+'-'+MON+'-'+pad(d);
      const info=CAL[ds];
      const isToday=ds===TODAY;
      const hasG=!!info;
      let cls='day'+(hasG?' has-games':'')+(isToday?' today':'');
      el.className=cls;
      el.dataset.ds=ds;
      let h=`<div class="day-num">${{d}}</div>`;
      if(hasG){{
        h+=`<div class="badge">${{info.has_live?'<div class="live-dot"></div>':''}}${{info.count}} game${{info.count>1?'s':''}}</div>`;
        el.onclick=function(){{selectDate(ds,el)}};
      }}
      el.innerHTML=h;
    }}
    row.appendChild(el);
  }}
  container.appendChild(row);
}}
function selectDate(ds,el){{
  window.parent.postMessage({{type:'nfl_date',ds:ds}},'*');
  // Also use query param as reliable fallback
  const url=new URL(window.parent.location.href);
  url.searchParams.set('sel_date',ds);
  url.searchParams.delete('game_id');
  window.parent.location.href=url.toString();
}}
</script>
</body></html>"""

    components.html(calendar_html, height=520, scrolling=False)

    # ── Handle date selection ─────────────────────────────────────────────────
    qp = st.query_params
    if "sel_date" in qp:
        ds    = qp["sel_date"]
        games = games_by_date.get(ds, [])
        if games:
            st.session_state.selected_date       = ds
            st.session_state.selected_date_games = games
            st.session_state.view = "day"
            st.query_params.clear()
            st.rerun()
        else:
            st.query_params.clear()


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: DAY  (games on selected date)
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "day":

    ds    = st.session_state.selected_date or ""
    games = st.session_state.selected_date_games or []

    if not ds or not games:
        st.session_state.view = "calendar"
        st.rerun()

    # Format date label
    try:
        d_obj      = datetime.fromisoformat(ds)
        date_label = d_obj.strftime("%A, %B %-d %Y")
    except Exception:
        date_label = ds

    # ── Breadcrumb + back ─────────────────────────────────────────────────────
    bc1, bc2 = st.columns([1.4, 8])
    with bc1:
        if st.button("← Calendar", use_container_width=True):
            st.session_state.view = "calendar"
            st.rerun()
    with bc2:
        st.markdown(
            f'<div class="breadcrumb">Calendar &rsaquo; <span>{date_label}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(f'<div class="section-label">{date_label} — {len(games)} game{"s" if len(games)>1 else ""}</div>', unsafe_allow_html=True)

    # ── Game cards ────────────────────────────────────────────────────────────
    for g in games:
        away  = g["away"]; home = g["home"]
        state = g["status_state"]

        if state == "in":
            badge_html = f'<span style="background:#4caf72;color:#0f1f0f;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:10px;font-family:Oswald,sans-serif;letter-spacing:0.5px">🟢 LIVE · Q{g["period"]}</span>'
        elif state == "post":
            badge_html = '<span style="background:#2a3a2a;color:#7aba8a;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:10px;font-family:Oswald,sans-serif;letter-spacing:0.5px">Final</span>'
        else:
            badge_html = '<span style="background:#1a3a2a;color:#4caf72;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:10px;font-family:Oswald,sans-serif;letter-spacing:0.5px">Scheduled</span>'

        score_str = f"{away['score']}  –  {home['score']}" if state != "pre" else "vs"

        away_logo_html = f'<img src="{away["logo"]}" style="width:40px;height:40px;object-fit:contain;vertical-align:middle;margin-right:8px">' if away.get("logo") else ""
        home_logo_html = f'<img src="{home["logo"]}" style="width:40px;height:40px;object-fit:contain;vertical-align:middle;margin-right:8px">' if home.get("logo") else ""

        c_info, c_btn = st.columns([6, 1])
        with c_info:
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:16px;padding:10px 14px;
                        background:rgba(76,175,114,0.04);border:1px solid rgba(76,175,114,0.14);
                        border-radius:10px;margin-bottom:6px">
              <div style="display:flex;align-items:center;flex:1">
                {away_logo_html}
                <div>
                  <div style="font-weight:700;font-size:1rem;color:#c8e8c8">{away['abbr']}</div>
                  <div style="font-size:0.68rem;color:#3a5a3a">{away['record']}</div>
                </div>
              </div>
              <div style="font-family:'Oswald',sans-serif;font-size:1.3rem;font-weight:700;
                          color:#e8f5e8;min-width:80px;text-align:center">{score_str}</div>
              <div style="display:flex;align-items:center;flex:1;flex-direction:row-reverse">
                {home_logo_html}
                <div style="text-align:right;margin-right:8px">
                  <div style="font-weight:700;font-size:1rem;color:#c8e8c8">{home['abbr']}</div>
                  <div style="font-size:0.68rem;color:#3a5a3a">{home['record']}</div>
                </div>
              </div>
              <div>{badge_html}</div>
              <div style="font-size:0.68rem;color:#3a5a3a">{g.get('venue','')}</div>
            </div>
            """, unsafe_allow_html=True)
        with c_btn:
            st.markdown("<div style='margin-top:10px'>", unsafe_allow_html=True)
            if st.button("Box Score", key=f"bs_{g['id']}", use_container_width=True):
                st.session_state.selected_game_id = g["id"]
                st.session_state.selected_game    = g
                st.session_state.view = "boxscore"
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: BOX SCORE
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "boxscore":

    game    = st.session_state.selected_game
    game_id = st.session_state.selected_game_id

    if not game or not game_id:
        st.session_state.view = "calendar"
        st.rerun()

    # ── Breadcrumb + back buttons ─────────────────────────────────────────────
    try:
        ds         = st.session_state.selected_date or ""
        d_obj      = datetime.fromisoformat(ds)
        date_label = d_obj.strftime("%b %-d")
    except Exception:
        date_label = "Schedule"

    away_abbr = game["away"]["abbr"]
    home_abbr = game["home"]["abbr"]

    b1, b2, b3, b4 = st.columns([1.4, 1.4, 1.4, 5])
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
    with b4:
        st.markdown(
            f'<div class="breadcrumb" style="padding-top:8px">Calendar &rsaquo; '
            f'<span>{date_label}</span> &rsaquo; '
            f'<span>{away_abbr} vs {home_abbr}</span></div>',
            unsafe_allow_html=True,
        )

    # ── Score Banner ──────────────────────────────────────────────────────────
    away = game["away"]; home = game["home"]
    sc   = {"in":"","post":"final","pre":"pre"}.get(game["status_state"],"")
    clk  = (
        f'<span style="color:#5a7a5a;font-size:0.74rem;margin-left:8px">'
        f'{game["clock"]} · Q{game["period"]}</span>'
        if game["status_state"] == "in" else ""
    )
    al = f'<img src="{away["logo"]}" style="width:56px;height:56px;object-fit:contain">' if away.get("logo") else ""
    hl = f'<img src="{home["logo"]}" style="width:56px;height:56px;object-fit:contain">' if home.get("logo") else ""

    st.markdown(f"""
    <div class="score-banner">
      <div style="display:flex;align-items:center;gap:14px">
        {al}
        <div>
          <div class="score-team-name">{away['team']}</div>
          <div class="score-record">{away['record']}</div>
        </div>
      </div>
      <div style="text-align:center">
        <div>
          <span class="score-num">{away['score']}</span>
          <span class="score-sep"> – </span>
          <span class="score-num">{home['score']}</span>
        </div>
        <div style="margin-top:7px">
          <span class="status-pill {sc}">{game['status']}</span>
          {clk}
        </div>
        <div style="color:#3a5a3a;font-size:0.72rem;margin-top:5px">{game.get('venue','')}</div>
      </div>
      <div style="display:flex;align-items:center;gap:14px;flex-direction:row-reverse">
        {hl}
        <div style="text-align:right">
          <div class="score-team-name">{home['team']}</div>
          <div class="score-record">{home['record']}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Load stats ────────────────────────────────────────────────────────────
    with st.spinner("Loading box score…"):
        data = load_all_stats(game_id)
    pbp = data["pbp"]

    # ── Linescore ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Score by Quarter</div>', unsafe_allow_html=True)
    ls_df = data["linescore"]
    if ls_df is not None and not ls_df.empty:
        def hl_ls(df):
            s = pd.DataFrame("", index=df.index, columns=df.columns)
            for c in ["1H","2H"]:
                if c in df.columns:
                    s[c] = "background:rgba(76,175,114,0.08);font-weight:600"
            if "Total" in df.columns:
                s["Total"] = "font-weight:800;background:rgba(76,175,114,0.14)"
            return s
        st.dataframe(ls_df.style.apply(hl_ls, axis=None), use_container_width=True, hide_index=True)
    else:
        st.info("Linescore not available yet.")

    # ── Period filter ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Player Stats</div>', unsafe_allow_html=True)

    available = ["Full Game"]
    for pbp_key, label in [("1H","1st Half"),("2H","2nd Half"),("Q1","Q1"),("Q2","Q2"),("Q3","Q3"),("Q4","Q4")]:
        if pbp_key in pbp and not pbp[pbp_key].empty:
            available.append(label)
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

    # ── Stat Tabs ─────────────────────────────────────────────────────────────
    t1,t2,t3,t4,t5,t6,t7 = st.tabs([
        "Passing","Rushing","Receiving","Defense","Kicking","Returning","Team"
    ])
    with t1: show_df(data["passing"],   period_filter, "YDS")
    with t2: show_df(data["rushing"],   period_filter, "YDS")
    with t3: show_df(data["receiving"], period_filter, "YDS")
    with t4: show_df(data["defense"],   period_filter, "TOT")
    with t5: show_df(data["kicking"],   period_filter)
    with t6: show_df(data["returning"], period_filter, "YDS")
    with t7:
        t = data["team"]
        if t is not None and not t.empty:
            st.dataframe(t, use_container_width=True, hide_index=True)
        else:
            st.info("No team data.")

    # ── Scoring Summary ───────────────────────────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Scoring Summary</div>', unsafe_allow_html=True)
    sdf = data["scoring"]
    if sdf is not None and not sdf.empty:
        pf = period_filter
        if pf == "Full Game":
            fsdf = sdf
        elif pf in ("1st Half","2nd Half"):
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
                st.dataframe(hdf.drop(columns=["Half"]), use_container_width=True, hide_index=True)
    else:
        st.info("No scoring plays yet.")

    # ── Play-by-Play ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Play-by-Play</div>', unsafe_allow_html=True)
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
        f"Updated: {datetime.now().strftime('%H:%M:%S')}  ·  "
        "ESPN public API  ·  Not affiliated with ESPN or the NFL"
    )
