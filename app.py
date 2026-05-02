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

# ── CSS — warm slate palette ──────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

    [data-testid="stSidebar"]        { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    .block-container { padding-top: 1.5rem !important; max-width: 1200px; }
    * { font-family: 'Inter', sans-serif; }

    /* ── Header ── */
    .nfl-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        color: white;
        padding: 1.1rem 1.8rem;
        border-radius: 12px;
        margin-bottom: 1.6rem;
        display: flex;
        align-items: center;
        gap: 1rem;
        border-left: 5px solid #e8714a;
        box-shadow: 0 2px 12px rgba(0,0,0,0.15);
    }
    .nfl-header h1 {
        margin: 0;
        font-family: 'Oswald', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #f5f0e8;
    }
    .nfl-header p { margin: 0.15rem 0 0; opacity: 0.55; font-size: 0.8rem; color: #f5f0e8; }

    /* ── Section labels ── */
    .section-label {
        font-family: 'Oswald', sans-serif;
        font-size: 0.68rem;
        letter-spacing: 2.5px;
        text-transform: uppercase;
        color: #9a8f82;
        margin-bottom: 0.7rem;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid rgba(200,185,165,0.2);
    }

    /* ── Score banner ── */
    .score-banner {
        background: linear-gradient(135deg, #1a1a2e 0%, #1e1e35 100%);
        color: #f5f0e8;
        border-radius: 12px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.3rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border: 1px solid rgba(232,113,74,0.2);
        box-shadow: 0 2px 16px rgba(0,0,0,0.2);
    }
    .score-team-name { font-family:'Oswald',sans-serif; font-size:1.3rem; font-weight:600; letter-spacing:0.5px; color:#f5f0e8; }
    .score-record    { font-size:0.73rem; color:#9a8f82; margin-top:3px; }
    .score-num       { font-family:'Oswald',sans-serif; font-size:3.2rem; font-weight:700; color:#f5f0e8; }
    .score-sep       { font-size:1.5rem; color:#4a4a6a; padding:0 0.7rem; }
    .status-pill     { background:#e8714a; color:white; font-size:0.68rem; font-weight:700;
                       padding:0.22rem 0.8rem; border-radius:20px; text-transform:uppercase;
                       letter-spacing:0.8px; display:inline-block; font-family:'Oswald',sans-serif; }
    .status-pill.final { background:#4a4a5a; }
    .status-pill.pre   { background:#2d5a8e; }

    /* ── Period filter radio ── */
    .stRadio > div { flex-direction:row; gap:6px; flex-wrap:wrap; }
    .stRadio > div > label {
        background: rgba(232,113,74,0.08);
        border: 1px solid rgba(232,113,74,0.25);
        border-radius: 20px;
        padding: 4px 16px;
        font-size: 0.78rem;
        cursor: pointer;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        color: #c8a882;
        transition: all 0.15s;
    }

    /* ── Buttons ── */
    div[data-testid="stButton"] > button {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        border-radius: 8px;
        border: 1px solid rgba(232,113,74,0.4);
        background: transparent;
        color: #e8714a;
        font-size: 0.85rem;
        padding: 0.4rem 1rem;
        transition: all 0.15s;
    }
    div[data-testid="stButton"] > button:hover {
        background: #e8714a;
        color: white;
        border-color: #e8714a;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab"] {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
    }

    /* ── Period note ── */
    .period-note {
        background: rgba(232,113,74,0.07);
        border-left: 3px solid #e8714a;
        border-radius: 0 6px 6px 0;
        padding: 0.4rem 0.9rem;
        font-size: 0.77rem;
        color: #9a8f82;
        margin-bottom: 0.7rem;
    }

    .empty-state {
        text-align:center;
        padding:3rem 1rem;
        color:#9a8f82;
        font-size:0.93rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

for key, default in {
    "view":             "calendar",
    "selected_game_id": None,
    "selected_game":    None,
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
def load_games_for_week(week, season_type):
    """Cached fetch for a single week."""
    return get_live_games(week=week)

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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_games_for_month(year, month):
    """
    Fetch ALL game types for a given month.
    Tries every week of every season type and collects games
    whose date falls in year/month.
    Season types: 1=preseason, 2=regular, 3=playoffs
    Weeks:        preseason 0-4, regular 1-18, playoffs 1-5
    """
    all_games = []
    seen_ids  = set()

    season_configs = [
        (2, range(1, 19)),   # Regular season  weeks 1-18
        (3, range(1, 6)),    # Playoffs        weeks 1-5  (WC/Div/Conf/SB + Pro Bowl)
        (1, range(0, 5)),    # Preseason       weeks 0-4
    ]

    for season_type, weeks in season_configs:
        for week in weeks:
            try:
                games = load_games_for_week(week, season_type)
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
            except Exception:
                pass

    return all_games

# ══════════════════════════════════════════════════════════════════════════════
#  CALENDAR VIEW
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.view == "calendar":

    MONTH_NAMES = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]

    year  = st.session_state.cal_year
    month = st.session_state.cal_month

    with st.spinner(f"Loading {MONTH_NAMES[month-1]} {year}…"):
        month_games = fetch_games_for_month(year, month)

    # Group games by ISO date string
    games_by_date: dict = {}
    for g in month_games:
        try:
            gdate = datetime.fromisoformat(g["date"].replace("Z","")).date()
            ds    = gdate.isoformat()
            games_by_date.setdefault(ds, []).append(g)
        except Exception:
            pass

    # ── Month navigation ──────────────────────────────────────────────────────
    nav1, nav2, nav3, _ = st.columns([1, 2, 1, 6])
    with nav1:
        if st.button("← Prev"):
            m = st.session_state.cal_month - 1
            y = st.session_state.cal_year
            if m < 1: m = 12; y -= 1
            st.session_state.cal_month = m
            st.session_state.cal_year  = y
            st.rerun()
    with nav2:
        st.markdown(
            f"<div style='text-align:center;font-weight:700;padding-top:5px;"
            f"font-family:Oswald,sans-serif;font-size:1.1rem;letter-spacing:0.5px;"
            f"color:#c8a882'>{MONTH_NAMES[month-1]} {year}</div>",
            unsafe_allow_html=True,
        )
    with nav3:
        if st.button("Next →"):
            m = st.session_state.cal_month + 1
            y = st.session_state.cal_year
            if m > 12: m = 1; y += 1
            st.session_state.cal_month = m
            st.session_state.cal_year  = y
            st.rerun()

    # ── Serialise for JS ──────────────────────────────────────────────────────
    today_str   = date.today().isoformat()
    first_dow   = (date(year, month, 1).weekday() + 1) % 7   # Sunday = 0
    days_in_mon = cal_mod.monthrange(year, month)[1]

    cal_data = {}
    for ds, games in games_by_date.items():
        has_live = any(g["status_state"] == "in" for g in games)
        cal_data[ds] = {
            "count":    len(games),
            "has_live": has_live,
            "games": [
                {
                    "id":          g["id"],
                    "away_abbr":   g["away"]["abbr"],
                    "away_logo":   g["away"].get("logo",""),
                    "away_score":  g["away"]["score"],
                    "away_record": g["away"]["record"],
                    "away_team":   g["away"]["team"],
                    "home_abbr":   g["home"]["abbr"],
                    "home_logo":   g["home"].get("logo",""),
                    "home_score":  g["home"]["score"],
                    "home_record": g["home"]["record"],
                    "home_team":   g["home"]["team"],
                    "state":       g["status_state"],
                    "period":      g["period"],
                    "status":      g["status"],
                    "venue":       g.get("venue",""),
                }
                for g in games
            ],
        }

    cal_json = json.dumps(cal_data)

    # ── Calendar + inline day panel (single HTML block, no scrollbar) ─────────
    calendar_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Inter', system-ui, sans-serif;
    background: transparent;
    color: #c8bfb5;
  }}

  /* ── Calendar grid ── */
  .cal-wrap {{ width: 100%; }}

  .dow-row {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 3px;
    margin-bottom: 3px;
  }}
  .dow {{
    text-align: center;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #6a6070;
    padding: 4px 0 6px;
  }}

  .day-row {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 3px;
    margin-bottom: 3px;
  }}

  .day {{
    min-height: 68px;
    border-radius: 7px;
    border: 1px solid rgba(200,185,165,0.08);
    padding: 6px 7px;
    background: rgba(255,255,255,0.02);
    position: relative;
    transition: border-color 0.15s, background 0.15s;
    cursor: default;
  }}
  .day.empty {{
    border-color: transparent;
    background: transparent;
    pointer-events: none;
  }}
  .day.has-games {{
    border-color: rgba(232,113,74,0.3);
    background: rgba(232,113,74,0.04);
    cursor: pointer;
  }}
  .day.has-games:hover {{
    border-color: rgba(232,113,74,0.7);
    background: rgba(232,113,74,0.09);
  }}
  .day.today {{
    border-color: rgba(232,113,74,0.6) !important;
    background: rgba(232,113,74,0.06) !important;
  }}
  .day.selected {{
    border-color: #e8714a !important;
    background: rgba(232,113,74,0.13) !important;
    box-shadow: 0 0 0 1px #e8714a;
  }}

  .day-num {{
    font-size: 0.72rem;
    font-weight: 600;
    color: #6a6070;
    line-height: 1;
  }}
  .day.has-games .day-num {{ color: #c8a882; font-weight: 700; }}
  .day.today     .day-num {{ color: #e8714a; }}
  .day.selected  .day-num {{ color: #e8714a; }}

  .game-badge {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 9px;
    background: rgba(232,113,74,0.12);
    border: 1px solid rgba(232,113,74,0.22);
    border-radius: 20px;
    padding: 3px 9px 3px 7px;
    font-size: 0.65rem;
    font-weight: 700;
    color: #c8a882;
    letter-spacing: 0.2px;
    white-space: nowrap;
  }}
  .day.today    .game-badge,
  .day.selected .game-badge {{
    background: rgba(232,113,74,0.18);
    border-color: rgba(232,113,74,0.45);
    color: #e8714a;
  }}
  .live-dot {{
    width: 6px; height: 6px;
    background: #e8714a;
    border-radius: 50%;
    flex-shrink: 0;
    animation: pulse 1.2s infinite;
  }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.2}} }}

  /* ── Day panel — sits BELOW the calendar rows, no scroll ── */
  .day-panel {{
    display: none;
    border: 1px solid rgba(232,113,74,0.25);
    border-radius: 10px;
    overflow: hidden;
    margin-top: 10px;
    background: #16161e;
  }}
  .day-panel.open {{ display: block; }}

  .panel-header {{
    background: rgba(232,113,74,0.12);
    border-bottom: 1px solid rgba(232,113,74,0.18);
    padding: 9px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .panel-title {{
    font-family: 'Oswald', sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #e8a87a;
  }}
  .panel-close {{
    cursor: pointer;
    color: #9a8f82;
    font-size: 1rem;
    line-height: 1;
    padding: 0 2px;
    transition: color 0.15s;
  }}
  .panel-close:hover {{ color: #e8714a; }}

  /* Game rows inside panel */
  .game-row {{
    display: flex;
    align-items: center;
    padding: 12px 16px;
    gap: 10px;
    border-bottom: 1px solid rgba(200,185,165,0.07);
    transition: background 0.1s;
  }}
  .game-row:last-child {{ border-bottom: none; }}
  .game-row:hover {{ background: rgba(232,113,74,0.05); }}

  .team-block {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }}
  .team-logo {{
    width: 34px; height: 34px;
    object-fit: contain;
    flex-shrink: 0;
  }}
  .team-abbr   {{ font-weight: 700; font-size: 0.92rem; color: #ddd5c8; }}
  .team-record {{ font-size: 0.64rem; color: #6a6070; margin-top: 1px; }}

  .score-block {{
    min-width: 90px;
    text-align: center;
    font-size: 1.35rem;
    font-weight: 800;
    font-family: 'Courier New', monospace;
    color: #ddd5c8;
    flex-shrink: 0;
  }}
  .vs-label {{ font-size: 0.72rem; font-weight: 600; color: #4a4060; }}

  .status-badge {{
    font-size: 0.61rem;
    font-weight: 700;
    letter-spacing: 0.7px;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 12px;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .s-live  {{ background: #e8714a; color: white; }}
  .s-final {{ background: #3a3a4a; color: #c8bfb5; }}
  .s-sched {{ background: rgba(200,185,165,0.1); color: #9a8f82; }}

  .box-btn {{
    background: #e8714a;
    color: white;
    border: none;
    border-radius: 7px;
    padding: 7px 14px;
    font-size: 0.75rem;
    font-weight: 700;
    cursor: pointer;
    letter-spacing: 0.3px;
    flex-shrink: 0;
    transition: background 0.15s, transform 0.1s;
    font-family: 'Oswald', sans-serif;
  }}
  .box-btn:hover {{ background: #d4603a; transform: translateY(-1px); }}

  /* Legend */
  .legend {{
    display: flex;
    gap: 16px;
    align-items: center;
    margin-top: 10px;
    font-size: 0.68rem;
    color: #6a6070;
  }}
  .l-box {{
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 2px;
    margin-right: 4px;
    vertical-align: middle;
  }}
</style>
</head>
<body>
<div class="cal-wrap">

  <!-- Day-of-week headers -->
  <div class="dow-row">
    <div class="dow">Sun</div>
    <div class="dow">Mon</div>
    <div class="dow">Tue</div>
    <div class="dow">Wed</div>
    <div class="dow">Thu</div>
    <div class="dow">Fri</div>
    <div class="dow">Sat</div>
  </div>

  <!-- Calendar rows rendered by JS -->
  <div id="cal-rows"></div>

  <!-- Day panel — always rendered below all rows -->
  <div class="day-panel" id="day-panel">
    <div class="panel-header">
      <div class="panel-title" id="panel-title">Games</div>
      <span class="panel-close" onclick="closePanel()">&#x2715;</span>
    </div>
    <div id="panel-body"></div>
  </div>

  <!-- Legend -->
  <div class="legend">
    <span>
      <span class="l-box" style="background:rgba(232,113,74,0.1);border:1px solid rgba(232,113,74,0.35)"></span>
      Has games
    </span>
    <span>
      <span class="l-box" style="background:rgba(232,113,74,0.08);border:1px solid rgba(232,113,74,0.6)"></span>
      Today
    </span>
    <span>
      <span style="display:inline-block;width:7px;height:7px;background:#e8714a;border-radius:50%;margin-right:4px;vertical-align:middle"></span>
      Live
    </span>
  </div>

</div>

<script>
const CAL    = {cal_json};
const TODAY  = '{today_str}';
const FDOW   = {first_dow};
const DAYS   = {days_in_mon};
const YEAR   = {year};
const MONTH  = String({month}).padStart(2,'0');

let selectedDs = null;

function pad(n) {{ return String(n).padStart(2,'0'); }}

// Build rows of 7 days each
const container = document.getElementById('cal-rows');
let cells = [];

// Empty leading cells
for (let i = 0; i < FDOW; i++) cells.push(null);

// Day cells
for (let d = 1; d <= DAYS; d++) {{
  cells.push(d);
}}

// Pad to complete last row
while (cells.length % 7 !== 0) cells.push(null);

// Render rows
for (let r = 0; r < cells.length / 7; r++) {{
  const row = document.createElement('div');
  row.className = 'day-row';

  for (let c = 0; c < 7; c++) {{
    const d   = cells[r * 7 + c];
    const el  = document.createElement('div');

    if (d === null) {{
      el.className = 'day empty';
    }} else {{
      const ds      = YEAR + '-' + MONTH + '-' + pad(d);
      const info    = CAL[ds];
      const isToday = ds === TODAY;
      const hasG    = !!info;

      let cls = 'day';
      if (hasG)    cls += ' has-games';
      if (isToday) cls += ' today';
      el.className = cls;
      el.dataset.ds = ds;

      let html = `<div class="day-num">${{d}}</div>`;
      if (hasG) {{
        const hasLive = info.has_live;
        html += `<div class="game-badge">
          ${{hasLive ? '<div class="live-dot"></div>' : ''}}
          ${{info.count}} game${{info.count > 1 ? 's' : ''}}
        </div>`;
        el.onclick = function() {{ togglePanel(ds, el); }};
      }}

      el.innerHTML = html;
    }}

    row.appendChild(el);
  }}

  container.appendChild(row);
}}

function togglePanel(ds, el) {{
  const panel = document.getElementById('day-panel');
  if (selectedDs === ds && panel.classList.contains('open')) {{
    closePanel();
    return;
  }}
  // Deselect previous
  document.querySelectorAll('.day.selected').forEach(d => d.classList.remove('selected'));
  el.classList.add('selected');
  selectedDs = ds;
  renderPanel(ds);
  panel.classList.add('open');
  // Scroll panel into view smoothly inside the iframe
  setTimeout(() => {{
    panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}, 50);
}}

function closePanel() {{
  document.getElementById('day-panel').classList.remove('open');
  document.querySelectorAll('.day.selected').forEach(d => d.classList.remove('selected'));
  selectedDs = null;
}}

function renderPanel(ds) {{
  const info  = CAL[ds];
  const title = document.getElementById('panel-title');
  const body  = document.getElementById('panel-body');

  const d = new Date(ds + 'T12:00:00');
  title.textContent = d.toLocaleDateString('en-US', {{ weekday:'long', month:'long', day:'numeric' }});
  body.innerHTML = '';

  info.games.forEach(g => {{
    const st       = g.state;
    const badgeCls = st === 'in' ? 's-live' : st === 'post' ? 's-final' : 's-sched';
    const badgeTxt = st === 'in' ? 'Live · Q' + g.period : st === 'post' ? 'Final' : 'Scheduled';
    const scoreHtml = st !== 'pre'
      ? `<span>${{g.away_score}}</span> <span style="color:#4a4060;font-size:.9rem">–</span> <span>${{g.home_score}}</span>`
      : `<span class="vs-label">VS</span>`;

    const row = document.createElement('div');
    row.className = 'game-row';
    row.innerHTML = `
      <div class="team-block">
        ${{g.away_logo ? `<img class="team-logo" src="${{g.away_logo}}" onerror="this.style.display='none'">` : ''}}
        <div>
          <div class="team-abbr">${{g.away_abbr}}</div>
          <div class="team-record">${{g.away_record}}</div>
        </div>
      </div>
      <div class="score-block">${{scoreHtml}}</div>
      <div class="team-block" style="flex-direction:row-reverse;text-align:right">
        ${{g.home_logo ? `<img class="team-logo" src="${{g.home_logo}}" onerror="this.style.display='none'">` : ''}}
        <div>
          <div class="team-abbr">${{g.home_abbr}}</div>
          <div class="team-record">${{g.home_record}}</div>
        </div>
      </div>
      <span class="status-badge ${{badgeCls}}">${{badgeTxt}}</span>
      <button class="box-btn" onclick="selectGame('${{g.id}}')">Box Score</button>
    `;
    body.appendChild(row);
  }});
}}

function selectGame(id) {{
  // Navigate parent to add query param — triggers Streamlit rerun
  const url = new URL(window.parent.location.href);
  url.searchParams.set('game_id', id);
  window.parent.location.href = url.toString();
}}
</script>
</body>
</html>
"""

    # Height must be tall enough for the full calendar + panel without internal scroll
    components.html(calendar_html, height=820, scrolling=False)

    # ── Handle game selection via query params ────────────────────────────────
    qp = st.query_params
    if "game_id" in qp:
        selected_id = qp["game_id"]
        found = None
        for ds, games in games_by_date.items():
            for g in games:
                if g["id"] == selected_id:
                    found = g
                    break
            if found:
                break

        if found:
            st.session_state.selected_game_id = selected_id
            st.session_state.selected_game    = found
            st.session_state.view = "boxscore"
            st.query_params.clear()
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  BOX SCORE VIEW
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "boxscore":

    game    = st.session_state.selected_game
    game_id = st.session_state.selected_game_id

    if not game or not game_id:
        st.session_state.view = "calendar"
        st.rerun()

    # ── Back + Refresh ────────────────────────────────────────────────────────
    b1, b2, _ = st.columns([1.8, 1.4, 7])
    with b1:
        if st.button("← Back to Schedule"):
            st.session_state.view = "calendar"
            st.rerun()
    with b2:
        if st.button("🔄 Refresh Stats"):
            st.cache_data.clear()
            st.rerun()

    # ── Score Banner ──────────────────────────────────────────────────────────
    away = game["away"];  home = game["home"]
    sc   = {"in":"","post":"final","pre":"pre"}.get(game["status_state"],"")
    clk  = (
        f'<span style="color:#9a8f82;font-size:0.74rem;margin-left:8px">'
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
        <div style="color:#6a6070;font-size:0.72rem;margin-top:5px">{game.get('venue','')}</div>
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
                    s[c] = "background:rgba(232,113,74,0.08);font-weight:600"
            if "Total" in df.columns:
                s["Total"] = "font-weight:800;background:rgba(232,113,74,0.14)"
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
        pf  = period_filter
        k   = get_pbp_key(pf)
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

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        f"Updated: {datetime.now().strftime('%H:%M:%S')}  ·  "
        "ESPN public API  ·  Not affiliated with ESPN or the NFL"
    )
