"""
app.py  —  NFL Live Box Score Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
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

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NFL Box Score",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS — clean white theme ───────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

    [data-testid="stSidebar"]        { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    .block-container { padding-top: 1.5rem !important; max-width: 1200px; }
    * { font-family: 'Inter', sans-serif; }

    /* Header */
    .nfl-header {
        background: #013369;
        color: white;
        padding: 1.1rem 1.8rem;
        border-radius: 12px;
        margin-bottom: 1.6rem;
        display: flex;
        align-items: center;
        gap: 1rem;
        border-left: 5px solid #D50A0A;
    }
    .nfl-header h1 {
        margin: 0;
        font-family: 'Oswald', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }
    .nfl-header p { margin: 0.1rem 0 0; opacity: 0.6; font-size: 0.8rem; }

    /* Section labels */
    .section-label {
        font-family: 'Oswald', sans-serif;
        font-size: 0.68rem;
        letter-spacing: 2.5px;
        text-transform: uppercase;
        color: #888;
        margin-bottom: 0.7rem;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid #e8e8e8;
    }

    /* Breadcrumb */
    .breadcrumb {
        font-size: 0.75rem;
        color: #aaa;
        padding-top: 8px;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.3px;
    }
    .breadcrumb b { color: #013369; }

    /* Score banner */
    .score-banner {
        background: #013369;
        color: white;
        border-radius: 12px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.3rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .score-team-name { font-family:'Oswald',sans-serif; font-size:1.3rem; font-weight:600; letter-spacing:0.5px; }
    .score-record    { font-size:0.73rem; opacity:0.55; margin-top:3px; }
    .score-num       { font-family:'Oswald',sans-serif; font-size:3.2rem; font-weight:700; }
    .score-sep       { font-size:1.5rem; opacity:0.25; padding:0 0.7rem; }
    .status-pill     { background:#D50A0A; color:white; font-size:0.68rem; font-weight:700;
                       padding:0.22rem 0.8rem; border-radius:20px; text-transform:uppercase;
                       letter-spacing:0.8px; display:inline-block; font-family:'Oswald',sans-serif; }
    .status-pill.final { background:rgba(255,255,255,0.15); }
    .status-pill.pre   { background:rgba(255,255,255,0.1); }

    /* Game card */
    .game-card {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 12px 16px;
        background: white;
        border: 1px solid #e8e8e8;
        border-radius: 10px;
        margin-bottom: 8px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }

    /* Period filter */
    .stRadio > div { flex-direction:row; gap:6px; flex-wrap:wrap; }
    .stRadio > div > label {
        background: #f5f5f5;
        border: 1px solid #e0e0e0;
        border-radius: 20px;
        padding: 4px 16px;
        font-size: 0.78rem;
        cursor: pointer;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        color: #555;
    }

    /* Buttons */
    div[data-testid="stButton"] > button {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        border-radius: 8px;
        border: 1.5px solid #013369;
        background: white;
        color: #013369;
        font-size: 0.84rem;
        padding: 0.42rem 0;
        width: 100%;
        transition: all 0.15s;
    }
    div[data-testid="stButton"] > button:hover {
        background: #013369;
        color: white;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
    }

    /* Period note */
    .period-note {
        background: #fff8f0;
        border-left: 3px solid #D50A0A;
        border-radius: 0 6px 6px 0;
        padding: 0.4rem 0.9rem;
        font-size: 0.77rem;
        color: #888;
        margin-bottom: 0.7rem;
    }

    /* Calendar grid */
    .cal-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 4px;
        margin-top: 4px;
    }
    .cal-dow {
        text-align: center;
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 1.8px;
        text-transform: uppercase;
        color: #aaa;
        padding: 4px 0 8px;
    }
    .cal-day {
        min-height: 64px;
        border-radius: 8px;
        border: 1px solid #efefef;
        padding: 6px 7px;
        background: white;
        font-size: 0.72rem;
        font-weight: 600;
        color: #bbb;
    }
    .cal-day.has-games {
        border-color: #013369;
        background: #f0f4fa;
        color: #013369;
        font-weight: 700;
    }
    .cal-day.today {
        border-color: #D50A0A !important;
        background: #fff5f5 !important;
        color: #D50A0A !important;
    }
    .cal-day.empty {
        border-color: transparent;
        background: transparent;
    }
    .game-count-badge {
        display: inline-block;
        margin-top: 8px;
        background: #013369;
        color: white;
        font-size: 0.6rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 20px;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.3px;
    }
    .cal-day.today .game-count-badge { background: #D50A0A; }

    /* Live dot */
    .live-dot {
        display: inline-block;
        width: 6px; height: 6px;
        background: #D50A0A;
        border-radius: 50%;
        margin-right: 3px;
        vertical-align: middle;
        animation: blink 1.2s infinite;
    }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

    /* Legend */
    .cal-legend {
        display: flex;
        gap: 16px;
        font-size: 0.68rem;
        color: #aaa;
        margin-top: 10px;
    }
    .legend-box {
        display: inline-block;
        width: 10px; height: 10px;
        border-radius: 2px;
        margin-right: 4px;
        vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

for key, default in {
    "view":                 "calendar",
    "selected_game_id":     None,
    "selected_game":        None,
    "selected_date":        None,
    "selected_date_games":  [],
    "cal_year":             datetime.now().year,
    "cal_month":            datetime.now().month,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nfl-header">
  <div style="font-size:2rem">🏈</div>
  <div>
    <h1>NFL Box Score</h1>
    <p>Live stats · Quarter &amp; half splits · Play-by-play</p>
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
    Fetch all games (regular + playoffs + preseason) for a given month.

    Key fix: get_live_games now accepts season_type so ESPN's
    seasontype param is actually sent correctly.

    Playoff structure (season_type=3):
      week 1 = Wild Card weekend
      week 2 = Divisional round
      week 3 = Conference Championships
      week 4 = Pro Bowl
      week 5 = Super Bowl
    """
    all_games: list = []
    seen_ids:  set  = set()

    configs = [
        (2, range(1, 23)),   # Regular season (includes weeks 1-18, buffer to 22)
        (3, range(1, 6)),    # All playoff rounds weeks 1-5
        (1, range(0, 5)),    # Preseason weeks 0-4
    ]

    for season_type, weeks in configs:
        for week in weeks:
            games = _fetch_week(int(week), season_type)
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

    # ── Navigation ────────────────────────────────────────────────────────────
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
            f"color:#013369'>{MONTH_NAMES[month-1]} {year}</div>",
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

    # ── Calendar grid (pure Streamlit — no HTML component, no JS) ─────────────
    today_str   = date.today().isoformat()
    first_dow   = (date(year, month, 1).weekday() + 1) % 7   # Sun=0
    days_in_mon = cal_mod.monthrange(year, month)[1]

    # Day-of-week headers
    DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    dow_cols = st.columns(7)
    for i, d in enumerate(DOW):
        with dow_cols[i]:
            st.markdown(
                f"<div class='cal-dow'>{d}</div>",
                unsafe_allow_html=True,
            )

    # Build list of cells: None = empty, int = day number
    cells = [None] * first_dow + list(range(1, days_in_mon + 1))
    while len(cells) % 7 != 0:
        cells.append(None)

    # Render rows of 7
    for row_start in range(0, len(cells), 7):
        row_cells = cells[row_start:row_start + 7]
        cols = st.columns(7)
        for col_idx, day in enumerate(row_cells):
            with cols[col_idx]:
                if day is None:
                    st.markdown("<div class='cal-day empty'></div>", unsafe_allow_html=True)
                else:
                    ds        = f"{year}-{month:02d}-{day:02d}"
                    is_today  = ds == today_str
                    day_games = games_by_date.get(ds, [])
                    has_games = len(day_games) > 0
                    has_live  = any(g["status_state"] == "in" for g in day_games)

                    day_cls = "cal-day"
                    if has_games: day_cls += " has-games"
                    if is_today:  day_cls += " today"

                    if has_games:
                        live_html  = "<span class='live-dot'></span>" if has_live else ""
                        badge_html = (
                            f"<div class='game-count-badge'>"
                            f"{live_html}{len(day_games)} game{'s' if len(day_games)>1 else ''}"
                            f"</div>"
                        )
                        st.markdown(
                            f"<div class='{day_cls}'>{day}<br>{badge_html}</div>",
                            unsafe_allow_html=True,
                        )
                        # Clickable button underneath the visual cell
                        if st.button(
                            "View",
                            key=f"day_{ds}",
                            use_container_width=True,
                        ):
                            st.session_state.selected_date       = ds
                            st.session_state.selected_date_games = day_games
                            st.session_state.view = "day"
                            st.rerun()
                    else:
                        st.markdown(
                            f"<div class='{day_cls}'>{day}</div>",
                            unsafe_allow_html=True,
                        )

    # Legend
    st.markdown("""
    <div class="cal-legend">
      <span><span class="legend-box" style="background:#f0f4fa;border:1px solid #013369"></span>Has games</span>
      <span><span class="legend-box" style="background:#fff5f5;border:1px solid #D50A0A"></span>Today</span>
      <span><span class="live-dot" style="width:7px;height:7px"></span>Live game</span>
    </div>
    """, unsafe_allow_html=True)

    if not month_games:
        st.markdown(
            "<div style='text-align:center;padding:2rem;color:#aaa'>"
            "No games found this month. NFL season runs August – February."
            "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW: DAY  — games on selected date
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "day":

    ds    = st.session_state.selected_date or ""
    games = st.session_state.selected_date_games or []

    if not ds or not games:
        st.session_state.view = "calendar"
        st.rerun()

    try:
        d_obj      = datetime.fromisoformat(ds)
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
            f'<div class="breadcrumb">Calendar &rsaquo; <b>{date_label}</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div class="section-label">{date_label} — '
        f'{len(games)} game{"s" if len(games)>1 else ""}</div>',
        unsafe_allow_html=True,
    )

    for g in games:
        away  = g["away"]; home = g["home"]
        state = g["status_state"]

        if state == "in":
            badge = f'<span style="background:#D50A0A;color:white;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:10px">🔴 LIVE · Q{g["period"]}</span>'
        elif state == "post":
            badge = '<span style="background:#f0f0f0;color:#555;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:10px">Final</span>'
        else:
            badge = '<span style="background:#e8f0fe;color:#013369;font-size:0.65rem;font-weight:700;padding:3px 10px;border-radius:10px">Scheduled</span>'

        score_str  = f"{away['score']}  –  {home['score']}" if state != "pre" else "vs"
        away_logo  = f'<img src="{away["logo"]}" style="width:38px;height:38px;object-fit:contain;vertical-align:middle">' if away.get("logo") else ""
        home_logo  = f'<img src="{home["logo"]}" style="width:38px;height:38px;object-fit:contain;vertical-align:middle">' if home.get("logo") else ""

        c_info, c_btn = st.columns([6, 1])
        with c_info:
            st.markdown(f"""
            <div class="game-card">
              <div style="display:flex;align-items:center;gap:10px;flex:1">
                {away_logo}
                <div>
                  <div style="font-weight:700;font-size:0.95rem;color:#013369">{away['abbr']}</div>
                  <div style="font-size:0.65rem;color:#aaa">{away['record']}</div>
                </div>
              </div>
              <div style="font-family:'Oswald',sans-serif;font-size:1.3rem;font-weight:700;color:#013369;min-width:80px;text-align:center">{score_str}</div>
              <div style="display:flex;align-items:center;gap:10px;flex:1;flex-direction:row-reverse">
                {home_logo}
                <div style="text-align:right">
                  <div style="font-weight:700;font-size:0.95rem;color:#013369">{home['abbr']}</div>
                  <div style="font-size:0.65rem;color:#aaa">{home['record']}</div>
                </div>
              </div>
              <div>{badge}</div>
              <div style="font-size:0.65rem;color:#ccc">{g.get('venue','')}</div>
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

    try:
        ds         = st.session_state.selected_date or ""
        d_obj      = datetime.fromisoformat(ds)
        date_label = d_obj.strftime("%b %-d")
    except Exception:
        date_label = "Schedule"

    away_abbr = game["away"]["abbr"]
    home_abbr = game["home"]["abbr"]

    # Back buttons + breadcrumb
    b1, b2, b3, bc = st.columns([1.4, 1.4, 1.2, 5])
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
            f'<div class="breadcrumb">Calendar &rsaquo; '
            f'<b>{date_label}</b> &rsaquo; '
            f'<b>{away_abbr} vs {home_abbr}</b></div>',
            unsafe_allow_html=True,
        )

    # Score Banner
    away = game["away"]; home = game["home"]
    sc   = {"in":"","post":"final","pre":"pre"}.get(game["status_state"],"")
    clk  = (
        f'<span style="opacity:0.6;font-size:0.74rem;margin-left:8px">'
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
        <div style="opacity:0.4;font-size:0.72rem;margin-top:5px">{game.get('venue','')}</div>
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

    # Load stats
    with st.spinner("Loading box score…"):
        data = load_all_stats(game_id)
    pbp = data["pbp"]

    # Linescore
    st.markdown('<div class="section-label">Score by Quarter</div>', unsafe_allow_html=True)
    ls_df = data["linescore"]
    if ls_df is not None and not ls_df.empty:
        def hl_ls(df):
            s = pd.DataFrame("", index=df.index, columns=df.columns)
            for c in ["1H","2H"]:
                if c in df.columns:
                    s[c] = "background:#f0f4fa;font-weight:600"
            if "Total" in df.columns:
                s["Total"] = "font-weight:800;background:#e8f0fe"
            return s
        st.dataframe(ls_df.style.apply(hl_ls, axis=None), use_container_width=True, hide_index=True)
    else:
        st.info("Linescore not available yet.")

    # Period filter
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Player Stats</div>', unsafe_allow_html=True)

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

    t1,t2,t3,t4,t5,t6,t7 = st.tabs(["Passing","Rushing","Receiving","Defense","Kicking","Returning","Team"])
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

    # Scoring summary
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Scoring Summary</div>', unsafe_allow_html=True)
    sdf = data["scoring"]
    if sdf is not None and not sdf.empty:
        pf = period_filter
        if pf == "Full Game":       fsdf = sdf
        elif pf in ("1st Half","2nd Half"): fsdf = sdf[sdf["Half"] == pf]
        elif pf.startswith("OT"):   fsdf = sdf[sdf["Half"].str.startswith("OT", na=False)]
        else:                       fsdf = sdf[sdf["Quarter"] == pf]
        if fsdf.empty:
            st.info(f"No scoring plays in {pf}.")
        else:
            for half in fsdf["Half"].unique():
                hdf = fsdf[fsdf["Half"] == half]
                st.markdown(f"**{half}**")
                st.dataframe(hdf.drop(columns=["Half"]), use_container_width=True, hide_index=True)
    else:
        st.info("No scoring plays yet.")

    # Play-by-play
    st.markdown('<div class="section-label" style="margin-top:1.5rem">Play-by-Play</div>', unsafe_allow_html=True)
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
    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}  ·  ESPN public API  ·  Not affiliated with ESPN or the NFL")
