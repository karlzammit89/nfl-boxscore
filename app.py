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
    get_player_stats_by_period,
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

# ── CSS — structural only, zero color overrides ───────────────────────────────

st.markdown("""
<style>
[data-testid="stSidebar"]        { display: none; }
[data-testid="collapsedControl"] { display: none; }
.block-container { padding-top: 2.5rem !important; max-width: 1100px; }

/* Calendar grid — layout only */
.cal-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
    margin-bottom: 4px;
}
.dow-lbl {
    text-align: center;
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    opacity: 0.65;
    padding: 2px 0 12px;
}
/* Day cell — identical structure for all days */
.cal-day {
    min-height: 70px;
    border-radius: 8px;
    border: 1px solid rgba(128,128,128,0.15);
    padding: 8px 9px;
    font-size: 0.73rem;
    font-weight: 600;
    opacity: 0.4;
    position: relative;
    box-sizing: border-box;
}
/* Game days — slightly more visible border, full opacity, pointer */
.cal-day.has-g {
    opacity: 1;
    border-color: rgba(128,128,128,0.35);
}
/* Today — red border accent only */
.cal-day.today {
    border-color: rgba(255, 75, 75, 0.7) !important;
    opacity: 1;
}
.cal-day.today .dn { color: rgb(255, 75, 75); }
.cal-day.empty {
    border-color: transparent !important;
    opacity: 0;
    pointer-events: none;
}
/* .gpip and .ldot defined below in calendar section */
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }
.ldot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: rgb(255, 75, 75);
    flex-shrink: 0;
    animation: blink 1.3s infinite;
}

/* Score banner — layout only */
.score-banner {
    border-radius: 10px;
    padding: 20px 26px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border: 1px solid rgba(128,128,128,0.15);
}

/* Game card — fixed layout keeps score centred regardless of content */
.game-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 13px 16px;
    border-radius: 10px;
    border: 1px solid rgba(128,128,128,0.15);
    margin-bottom: 8px;
}
/* Each team block takes equal remaining space */
.tm-block { display:flex; align-items:center; gap:10px; flex:1; min-width:0; }
.tm-block.right { flex-direction:row-reverse; text-align:right; }

/* Status chips */
.chip-live  { color: rgb(255,75,75);   font-size:0.65rem; font-weight:700; }
.chip-final { opacity: 0.55;            font-size:0.65rem; font-weight:700; }
.chip-sched { color: rgb(100,160,255); font-size:0.65rem; font-weight:700; }

/* Period note */
.period-note {
    border-left: 3px solid rgba(245,158,11,0.7);
    padding: 5px 10px;
    font-size: 0.75rem;
    opacity: 0.7;
    border-radius: 0 5px 5px 0;
    margin-bottom: 8px;
}

/* Center-align dataframe cells */
[data-testid="stDataFrame"] td {
    text-align: center !important;
}
[data-testid="stDataFrame"] th {
    text-align: center !important;
}
/* Keep Player and Team columns left-aligned */
[data-testid="stDataFrame"] td:first-child,
[data-testid="stDataFrame"] td:nth-child(2),
[data-testid="stDataFrame"] th:first-child,
[data-testid="stDataFrame"] th:nth-child(2) {
    text-align: left !important;
}

/* Section divider label */
.sec-div {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    opacity: 0.4;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(128,128,128,0.15);
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

st.markdown("## 🏈 NFL Box Scores")
st.caption("Live stats · Quarter & half splits · All times Eastern")
st.divider()

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_week(week: int, season_type: int) -> list:
    try:
        return get_live_games(week=week, season_type=season_type)
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_games_for_month(year: int, month: int) -> list:
    all_games, seen_ids = [], set()
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
        "by_period":  get_player_stats_by_period(game_id),
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

    # ── Month / Year picker — native st.selectbox, no buttons needed ────────
    # Selectboxes trigger instant reruns on change with no page flash,
    # and are completely immune to any button CSS.
    _, c1, c2, _ = st.columns([1, 1.5, 1, 1])
    with c1:
        selected_month = st.selectbox(
            "Month",
            options=list(range(1, 13)),
            format_func=lambda m: MONTH_NAMES[m - 1],
            index=month - 1,
            key="pick_month",
            label_visibility="collapsed",
        )
    with c2:
        selected_year = st.selectbox(
            "Year",
            options=[year - 1, year],
            index=1,
            key="pick_year",
            label_visibility="collapsed",
        )

    if selected_month != month or selected_year != year:
        st.session_state.cal_month = selected_month
        st.session_state.cal_year  = selected_year
        st.rerun()

    # Day-of-week header row
    st.markdown(
        "<div class='cal-grid'>" +
        "".join(f"<div class='dow-lbl'>{d}</div>"
                for d in ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]) +
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Calendar grid ─────────────────────────────────────────────────────────
    # The ONLY reliable way to make cells clickable in Streamlit without JS
    # is to use st.button inside st.columns. We render each game-day cell as
    # a styled st.button so it IS the interactive element — no overlay needed.
    # Non-game days and empty cells are plain st.markdown divs.
    #
    # The button label contains the day number + game count, styled via CSS
    # that targets ONLY buttons with the key prefix "cal_YYYY-MM-DD".

    today_str   = et_now().date().isoformat()
    first_dow   = (date(year, month, 1).weekday() + 1) % 7
    days_in_mon = cal_mod.monthrange(year, month)[1]
    cells       = [None] * first_dow + list(range(1, days_in_mon + 1))
    while len(cells) % 7:
        cells.append(None)

    for row_start in range(0, len(cells), 7):
        cols = st.columns(7)
        for ci, day in enumerate(cells[row_start:row_start + 7]):
            with cols[ci]:
                if day is None:
                    # Empty cell — pure HTML, no interactivity
                    st.markdown("<div class='cal-day empty'></div>",
                                unsafe_allow_html=True)
                    continue

                ds        = f"{year}-{month:02d}-{day:02d}"
                day_games = games_by_date.get(ds, [])
                has_games = bool(day_games)
                is_today  = ds == today_str
                has_live  = any(g["status_state"] == "in" for g in day_games)

                if has_games:
                    n         = len(day_games)
                    dot       = "<span class='ldot'></span>" if has_live else ""
                    today_cls = " today" if is_today else ""
                    pill      = (
                        f"<div class='gpip'>{dot}"
                        f"{n} game{'s' if n > 1 else ''}</div>"
                    )
                    st.markdown(
                        f"<div class='cal-day has-g{today_cls}'>"
                        f"<span class='dn'>{day}</span>{pill}</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "select",
                        key=f"cal_{ds}",
                        use_container_width=True,
                    ):
                        st.session_state.selected_date       = ds
                        st.session_state.selected_date_games = day_games
                        st.session_state.view = "day"
                        st.rerun()

                else:
                    today_cls = " today" if is_today else ""
                    st.markdown(
                        f"<div class='cal-day{today_cls}'>"
                        f"<div class='dn'>{day}</div></div>",
                        unsafe_allow_html=True,
                    )

    st.markdown("""
    <style>
    .gpip {
        display:        inline-flex                      !important;
        align-items:    center                           !important;
        gap:            4px                              !important;
        position:       absolute                         !important;
        bottom:         8px                              !important;
        left:           8px                              !important;
        font-size:      0.58rem                          !important;
        font-weight:    700                              !important;
        padding:        2px 7px                          !important;
        border-radius:  20px                             !important;
        border:         1px solid rgba(128,128,128,0.3) !important;
        background:     rgba(128,128,128,0.1)            !important;
        opacity:        0.9                              !important;
        letter-spacing: 0.2px                            !important;
        text-transform: uppercase                        !important;
    }
    .cal-day.today .gpip {
        border-color: rgba(255,75,75,0.4)               !important;
        background:   rgba(255,75,75,0.1)               !important;
        color:        rgb(255,75,75)                     !important;
    }
    /* Invisible overlay — targets ALL secondary buttons since we can't reliably
       scope by DOM depth. Nav buttons are restored explicitly below. */
    button[data-testid="stBaseButton-secondary"] {
        background:  transparent !important;
        border:      none        !important;
        box-shadow:  none        !important;
        color:       transparent !important;
        height:      74px        !important;
        min-height:  74px        !important;
        margin-top: -78px        !important;
        padding:     0           !important;
        cursor:      pointer     !important;
        width:       100%        !important;
        display:     block       !important;
        position:    relative    !important;
        z-index:     10          !important;
        opacity:     0           !important;
    }
    /* Nav buttons removed — no restore rule needed */
    </style>
    """, unsafe_allow_html=True)

    # Legend
    st.caption("Cells with text = has games  ·  🔴 = live game  ·  Red border = today")


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

    b1, _ = st.columns([1.5, 8])
    with b1:
        if st.button("← Calendar", use_container_width=True):
            st.session_state.view = "calendar"
            st.rerun()

    st.markdown(
        f"<div class='sec-div' style='margin-top:12px'>"
        f"{date_label} · {len(games)} game{'s' if len(games)>1 else ''}</div>",
        unsafe_allow_html=True,
    )

    def sort_key(g):
        return ({"in":0,"post":1,"pre":2}.get(g["status_state"],3), g.get("date",""))

    for g in sorted(games, key=sort_key):
        away  = g["away"]; home = g["home"]
        state = g["status_state"]

        if state == "in":
            chip = f'<span class="chip-live">● LIVE · Q{g["period"]}</span>'
        elif state == "post":
            chip = '<span class="chip-final">Final</span>'
        else:
            chip = f'<span class="chip-sched">{et_time_str(g["date"])}</span>'

        score_html = (
            f'<div style="font-size:1.3rem;font-weight:800;width:110px;min-width:110px;'
            f'text-align:center;flex-shrink:0">'
            f'{away["score"]} – {home["score"]}</div>'
            if state != "pre" else
            f'<div style="width:110px;min-width:110px;flex-shrink:0;'
            f'text-align:center;font-size:0.85rem;opacity:0.5">vs</div>'
        )

        al = (f'<img src="{away["logo"]}" style="width:36px;height:36px;object-fit:contain">'
              if away.get("logo") else "")
        hl = (f'<img src="{home["logo"]}" style="width:36px;height:36px;object-fit:contain">'
              if home.get("logo") else "")

        c_card, c_btn = st.columns([6, 1])
        with c_card:
            st.markdown(f"""
            <div class="game-card">
              <div class="tm-block">
                {al}
                <div style="min-width:0">
                  <div style="font-weight:700;font-size:0.9rem">{away["abbr"]}</div>
                  <div style="font-size:0.63rem;opacity:0.45;margin-top:1px">{away["record"]}</div>
                </div>
              </div>
              {score_html}
              <div class="tm-block right">
                {hl}
                <div style="min-width:0">
                  <div style="font-weight:700;font-size:0.9rem">{home["abbr"]}</div>
                  <div style="font-size:0.63rem;opacity:0.45;margin-top:1px">{home["record"]}</div>
                </div>
              </div>
              {chip}
              <div style="font-size:0.62rem;opacity:0.35;width:88px;min-width:88px;
                          flex-shrink:0;text-align:right;line-height:1.35;
                          white-space:normal;word-break:break-word">{g.get("venue","")}</div>
            </div>
            """, unsafe_allow_html=True)
        with c_btn:
            st.markdown("<div style='margin-top:7px'>", unsafe_allow_html=True)
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

    b1, b2, b3, _ = st.columns([1.5, 1.6, 1.3, 5])
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

    away  = game["away"]; home = game["home"]
    state = game["status_state"]

    if state == "in":
        status_md = f"🔴 **Live** · {game['clock']} · Q{game['period']}"
    elif state == "post":
        status_md = "**Final**"
    else:
        status_md = f"🕐 **Scheduled** · {et_time_str(game['date'])}"

    al = (f'<img src="{away["logo"]}" style="width:54px;height:54px;object-fit:contain">'
          if away.get("logo") else "")
    hl = (f'<img src="{home["logo"]}" style="width:54px;height:54px;object-fit:contain">'
          if home.get("logo") else "")

    st.markdown(f"""
    <div class="score-banner">
      <div style="display:flex;align-items:center;gap:14px">
        {al}
        <div>
          <div style="font-size:1.05rem;font-weight:700">{away["team"]}</div>
          <div style="font-size:0.67rem;opacity:0.4;margin-top:2px">{away["record"]}</div>
        </div>
      </div>
      <div style="text-align:center">
        <div style="font-size:2.8rem;font-weight:800;letter-spacing:-1px">
          {away["score"]} <span style="opacity:0.2">–</span> {home["score"]}
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:14px;flex-direction:row-reverse">
        {hl}
        <div style="text-align:right">
          <div style="font-size:1.05rem;font-weight:700">{home["team"]}</div>
          <div style="font-size:0.67rem;opacity:0.4;margin-top:2px">{home["record"]}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Status + venue as native Streamlit elements (auto-themed)
    st.markdown(f"{status_md}  ·  <span style='opacity:0.4;font-size:0.8rem'>{game.get('venue','')}</span>",
                unsafe_allow_html=True)
    st.divider()

    with st.spinner("Loading box score…"):
        data = load_all_stats(game_id)
    pbp       = data["pbp"]
    by_period = data.get("by_period", {})

    # Linescore removed from UI

    # Period filter
    st.markdown("<div class='sec-div' style='margin-top:18px'>Player Stats</div>",
                unsafe_allow_html=True)

    # Standard periods only — no OT
    available = ["Full Game", "Q1", "Q2", "Q3", "Q4", "1st Half", "2nd Half"]

    period_filter = st.radio("Period:", options=available,
                             horizontal=True, label_visibility="collapsed")

    def get_pbp_key(pf):
        return {"1st Half":"1H","2nd Half":"2H"}.get(pf, pf)

    def show_df(df, pf, sort=None, drop_cols=None):
        if df is None or df.empty:
            st.info("No data available.")
            return
        if drop_cols:
            df = df.drop(columns=[c for c in drop_cols if c in df.columns])
        if sort and sort in df.columns:
            try:
                tmp = df.copy()
                tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                df = tmp.sort_values(sort, ascending=False)
            except Exception:
                pass
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Key map: display label → internal key used in by_period
    _PERIOD_KEY = {"1st Half":"1H","2nd Half":"2H"}

    def show_period_df(category: str, sort="YDS"):
        """Show per-period offensive stat from by_period dict."""
        stats_key   = _PERIOD_KEY.get(period_filter, period_filter)
        period_data = by_period.get(stats_key, {})
        df = period_data.get(category)
        if df is None or (hasattr(df, "empty") and df.empty):
            st.info(f"No {category} data available for {period_filter}.")
            return
        if sort and sort in df.columns:
            try:
                tmp = df.copy()
                tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                df = tmp.sort_values(sort, ascending=False)
            except Exception:
                pass
        st.dataframe(df, use_container_width=True, hide_index=True)

    tabs = st.tabs(["Passing","Rushing","Receiving"])
    with tabs[0]: show_period_df("passing",   "YDS")
    with tabs[1]: show_period_df("rushing",   "YDS")
    with tabs[2]: show_period_df("receiving", "YDS")

    # ── Prop Checker ──────────────────────────────────────────────────────────
    with st.expander("🎯 Prop Checker by Quarter", expanded=False):
        st.caption(
            "Set a minimum threshold. Each player shows their stat per quarter "
            "with ✅ (hit) or ❌ (missed). The final column shows if they hit it in ALL quarters."
        )
        pc1, pc2, pc3, pc4, pc5, pc6, pc7 = st.columns(7)
        with pc1:
            thr_pass_yds = st.number_input("Pass YDS ≥",   min_value=0, value=0, step=1, key="thr_pass_yds")
            if thr_pass_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_pass_yds}</div>", unsafe_allow_html=True)
        with pc2:
            thr_pass_td  = st.number_input("Pass TD ≥",    min_value=0, value=0, step=1, key="thr_pass_td")
            if thr_pass_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_pass_td}</div>", unsafe_allow_html=True)
        with pc3:
            thr_rush_yds = st.number_input("Rush YDS ≥",   min_value=0, value=0, step=1, key="thr_rush_yds")
            if thr_rush_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_rush_yds}</div>", unsafe_allow_html=True)
        with pc4:
            thr_rush_td  = st.number_input("Rush TD ≥",    min_value=0, value=0, step=1, key="thr_rush_td")
            if thr_rush_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_rush_td}</div>", unsafe_allow_html=True)
        with pc5:
            thr_recv_rec = st.number_input("Receptions ≥", min_value=0, value=0, step=1, key="thr_recv_rec")
            if thr_recv_rec > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_recv_rec}</div>", unsafe_allow_html=True)
        with pc6:
            thr_recv_yds = st.number_input("Rec YDS ≥",    min_value=0, value=0, step=1, key="thr_recv_yds")
            if thr_recv_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_recv_yds}</div>", unsafe_allow_html=True)
        with pc7:
            thr_recv_td  = st.number_input("Rec TD ≥",     min_value=0, value=0, step=1, key="thr_recv_td")
            if thr_recv_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_recv_td}</div>", unsafe_allow_html=True)

    def build_prop_table(category: str) -> pd.DataFrame | None:
        """
        Build a per-player, per-quarter prop result table.
        Columns: Player | Team | Q1 | Q2 | Q3 | Q4 | All Quarters
        Each Qx cell shows the raw stat value + ✅/❌ vs threshold.
        All Quarters = ✅ only if every quarter hit the threshold.
        Returns None if no active threshold for this category.
        """
        quarters = ["Q1", "Q2", "Q3", "Q4"]

        # Determine active thresholds and stat column for this category
        if category == "passing":
            thr_yds, thr_td = thr_pass_yds, thr_pass_td
            if thr_yds == 0 and thr_td == 0:
                return None
            stat_col = "YDS"
            td_col   = "TD"
        elif category == "rushing":
            thr_yds, thr_td = thr_rush_yds, thr_rush_td
            if thr_yds == 0 and thr_td == 0:
                return None
            stat_col = "YDS"
            td_col   = "TD"
        elif category == "receiving":
            thr_yds, thr_td = thr_recv_yds, thr_recv_td
            thr_rec = thr_recv_rec
            if thr_yds == 0 and thr_td == 0 and thr_rec == 0:
                return None
            stat_col = "YDS"
            td_col   = "TD"
        else:
            return None

        # Collect all unique players across all quarters
        all_players: dict = {}   # player_name → {"Team": str}
        for q in quarters:
            qdf = by_period.get(q, {}).get(category)
            if qdf is not None and not qdf.empty:
                for _, row in qdf.iterrows():
                    name = row.get("Player", "")
                    if name and name not in all_players:
                        all_players[name] = {"Team": row.get("Team", "")}

        if not all_players:
            return pd.DataFrame()

        rows = []
        for player, meta in all_players.items():
            row = {"Player": player, "Team": meta["Team"]}
            all_hit = True
            for q in quarters:
                qdf = by_period.get(q, {}).get(category)
                # Get this player's stats in this quarter
                yds_val = 0
                td_val  = 0
                if qdf is not None and not qdf.empty and "Player" in qdf.columns:
                    pmatch = qdf[qdf["Player"] == player]
                    if not pmatch.empty:
                        yds_val = int(pmatch.iloc[0].get(stat_col, 0))
                        td_val  = int(pmatch.iloc[0].get(td_col,  0))

                if category == "receiving":
                    rec_val = 0
                    if qdf is not None and not qdf.empty and "Player" in qdf.columns:
                        pmatch2 = qdf[qdf["Player"] == player]
                        if not pmatch2.empty:
                            rec_val = int(pmatch2.iloc[0].get("REC", 0))
                    yds_ok = (yds_val >= thr_yds) if thr_yds > 0 else True
                    td_ok  = (td_val  >= thr_td)  if thr_td  > 0 else True
                    rec_ok = (rec_val >= thr_recv_rec) if thr_recv_rec > 0 else True
                    hit    = yds_ok and td_ok and rec_ok
                else:
                    yds_ok = (yds_val >= thr_yds) if thr_yds > 0 else True
                    td_ok  = (td_val  >= thr_td)  if thr_td  > 0 else True
                    hit    = yds_ok and td_ok
                if not hit:
                    all_hit = False

                # Format cell: show value + icon
                icon = '✅' if hit else '❌'
                if category == "receiving":
                    parts = []
                    if thr_recv_rec > 0: parts.append(f"{rec_val}rec")
                    if thr_yds > 0:     parts.append(f"{yds_val}yds")
                    if thr_td > 0:      parts.append(f"{td_val}td")
                    cell = f"{icon} {' / '.join(parts)}" if parts else icon
                elif thr_yds > 0 and thr_td > 0:
                    cell = f"{icon} {yds_val}yds / {td_val}td"
                elif thr_yds > 0:
                    cell = f"{icon} {yds_val}yds"
                else:
                    cell = f"{icon} {td_val}td"
                row[q] = cell

            row["All Quarters"] = "✅ Won" if all_hit else "❌ Lost"
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # Sort: Won first, then by player name
        df["_sort"] = df["All Quarters"].apply(lambda x: 0 if "Won" in x else 1)
        df = df.sort_values(["_sort", "Player"]).drop(columns=["_sort"]).reset_index(drop=True)
        return df

    def show_prop_or_stats(category: str, sort="YDS"):
        """Show prop table if thresholds set, else show normal stat table."""
        prop_df = build_prop_table(category)
        if prop_df is not None:
            # Prop mode
            if prop_df.empty:
                st.info(f"No {category} data available.")
                return
            def color_cells(val):
                if isinstance(val, str):
                    if val.startswith("✅"): return "color: #22c55e; font-weight: 700"
                    if val.startswith("❌"): return "color: #ef4444; font-weight: 700"
                return ""
            cols_to_style = [c for c in prop_df.columns if c not in ("Player","Team")]
            st.dataframe(
                prop_df.style.map(color_cells, subset=cols_to_style),
                use_container_width=True, hide_index=True
            )
        else:
            # Normal mode — show selected period stats
            stats_key   = _PERIOD_KEY.get(period_filter, period_filter)
            period_data = by_period.get(stats_key, {})
            df = period_data.get(category)
            if df is None or (hasattr(df, "empty") and df.empty):
                st.info(f"No {category} data available for {period_filter}.")
                return
            if sort and sort in df.columns:
                try:
                    tmp = df.copy()
                    tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                    df = tmp.sort_values(sort, ascending=False)
                except Exception:
                    pass
            st.dataframe(df, use_container_width=True, hide_index=True)

    # Quarter prop results — only shown when thresholds are active
    qtr_active = any([
        thr_pass_yds, thr_pass_td,
        thr_rush_yds, thr_rush_td,
        thr_recv_rec, thr_recv_yds, thr_recv_td,
    ])
    if qtr_active:
        st.markdown("<div class='sec-div' style='margin-top:8px'>Prop Checker by Quarter — Results</div>",
                    unsafe_allow_html=True)
        qtabs = st.tabs(["Passing","Rushing","Receiving"])
        with qtabs[0]: show_prop_or_stats("passing",   "YDS")
        with qtabs[1]: show_prop_or_stats("rushing",   "YDS")
        with qtabs[2]: show_prop_or_stats("receiving", "YDS")

    with st.expander("📊 Prop Checker by Half", expanded=False):
        st.caption(
            "Set a minimum threshold. Each player shows their stat per half "
            "with ✅ (hit) or ❌ (missed). The final column shows if they hit it in BOTH halves."
        )
        ph1, ph2, ph3, ph4, ph5, ph6, ph7 = st.columns(7)
        with ph1:
            thr_h_pass_yds = st.number_input("Pass YDS ≥",   min_value=0, value=0, step=1, key="thr_h_pass_yds")
            if thr_h_pass_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_pass_yds}</div>", unsafe_allow_html=True)
        with ph2:
            thr_h_pass_td  = st.number_input("Pass TD ≥",    min_value=0, value=0, step=1, key="thr_h_pass_td")
            if thr_h_pass_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_pass_td}</div>", unsafe_allow_html=True)
        with ph3:
            thr_h_rush_yds = st.number_input("Rush YDS ≥",   min_value=0, value=0, step=1, key="thr_h_rush_yds")
            if thr_h_rush_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_rush_yds}</div>", unsafe_allow_html=True)
        with ph4:
            thr_h_rush_td  = st.number_input("Rush TD ≥",    min_value=0, value=0, step=1, key="thr_h_rush_td")
            if thr_h_rush_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_rush_td}</div>", unsafe_allow_html=True)
        with ph5:
            thr_h_recv_rec = st.number_input("Receptions ≥", min_value=0, value=0, step=1, key="thr_h_recv_rec")
            if thr_h_recv_rec > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_recv_rec}</div>", unsafe_allow_html=True)
        with ph6:
            thr_h_recv_yds = st.number_input("Rec YDS ≥",    min_value=0, value=0, step=1, key="thr_h_recv_yds")
            if thr_h_recv_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_recv_yds}</div>", unsafe_allow_html=True)
        with ph7:
            thr_h_recv_td  = st.number_input("Rec TD ≥",     min_value=0, value=0, step=1, key="thr_h_recv_td")
            if thr_h_recv_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_recv_td}</div>", unsafe_allow_html=True)

    def build_half_prop_table(category: str) -> pd.DataFrame | None:
        halves = ["1H", "2H"]
        half_labels = {"1H": "1st Half", "2H": "2nd Half"}

        if category == "passing":
            thr_yds, thr_td = thr_h_pass_yds, thr_h_pass_td
            if thr_yds == 0 and thr_td == 0:
                return None
            stat_col, td_col = "YDS", "TD"
        elif category == "rushing":
            thr_yds, thr_td = thr_h_rush_yds, thr_h_rush_td
            if thr_yds == 0 and thr_td == 0:
                return None
            stat_col, td_col = "YDS", "TD"
        elif category == "receiving":
            thr_yds  = thr_h_recv_yds
            thr_td   = thr_h_recv_td
            thr_rec  = thr_h_recv_rec
            if thr_yds == 0 and thr_td == 0 and thr_rec == 0:
                return None
            stat_col, td_col = "YDS", "TD"
        else:
            return None

        all_players: dict = {}
        for h in halves:
            hdf = by_period.get(h, {}).get(category)
            if hdf is not None and not hdf.empty:
                for _, row in hdf.iterrows():
                    name = row.get("Player", "")
                    if name and name not in all_players:
                        all_players[name] = {"Team": row.get("Team", "")}

        if not all_players:
            return pd.DataFrame()

        rows = []
        for player, meta in all_players.items():
            row = {"Player": player, "Team": meta["Team"]}
            all_hit = True
            for h in halves:
                hdf = by_period.get(h, {}).get(category)
                yds_val, td_val, rec_val = 0, 0, 0
                if hdf is not None and not hdf.empty and "Player" in hdf.columns:
                    pmatch = hdf[hdf["Player"] == player]
                    if not pmatch.empty:
                        yds_val = int(pmatch.iloc[0].get(stat_col, 0))
                        td_val  = int(pmatch.iloc[0].get(td_col, 0))
                        if category == "receiving":
                            rec_val = int(pmatch.iloc[0].get("REC", 0))

                if category == "receiving":
                    yds_ok = (yds_val >= thr_yds) if thr_yds > 0 else True
                    td_ok  = (td_val  >= thr_td)  if thr_td  > 0 else True
                    rec_ok = (rec_val >= thr_rec)  if thr_rec > 0 else True
                    hit    = yds_ok and td_ok and rec_ok
                else:
                    yds_ok = (yds_val >= thr_yds) if thr_yds > 0 else True
                    td_ok  = (td_val  >= thr_td)  if thr_td  > 0 else True
                    hit    = yds_ok and td_ok

                if not hit:
                    all_hit = False

                icon = "✅" if hit else "❌"
                if category == "receiving":
                    parts = []
                    if thr_rec > 0:  parts.append(f"{rec_val}rec")
                    if thr_yds > 0:  parts.append(f"{yds_val}yds")
                    if thr_td > 0:   parts.append(f"{td_val}td")
                    cell = f"{icon} {' / '.join(parts)}" if parts else icon
                elif thr_yds > 0 and thr_td > 0:
                    cell = f"{icon} {yds_val}yds / {td_val}td"
                elif thr_yds > 0:
                    cell = f"{icon} {yds_val}yds"
                else:
                    cell = f"{icon} {td_val}td"

                row[half_labels[h]] = cell

            row["Both Halves"] = "✅ Won" if all_hit else "❌ Lost"
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["_sort"] = df["Both Halves"].apply(lambda x: 0 if "Won" in x else 1)
        return df.sort_values(["_sort","Player"]).drop(columns=["_sort"]).reset_index(drop=True)

    def show_half_prop_or_stats(category: str, sort="YDS"):
        prop_df = build_half_prop_table(category)
        if prop_df is not None:
            if prop_df.empty:
                st.info(f"No {category} data available.")
                return
            def color_cells(val):
                if isinstance(val, str):
                    if val.startswith("✅"): return "color: #22c55e; font-weight: 700"
                    if val.startswith("❌"): return "color: #ef4444; font-weight: 700"
                return ""
            cols_to_style = [c for c in prop_df.columns if c not in ("Player","Team")]
            st.dataframe(
                prop_df.style.map(color_cells, subset=cols_to_style),
                use_container_width=True, hide_index=True
            )
        else:
            stats_key   = _PERIOD_KEY.get(period_filter, period_filter)
            period_data = by_period.get(stats_key, {})
            df = period_data.get(category)
            if df is None or (hasattr(df, "empty") and df.empty):
                st.info(f"No {category} data available for {period_filter}.")
                return
            if sort and sort in df.columns:
                try:
                    tmp = df.copy()
                    tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                    df = tmp.sort_values(sort, ascending=False)
                except Exception:
                    pass
            st.dataframe(df, use_container_width=True, hide_index=True)

    # Half prop results — only shown when thresholds are active
    half_active = any([
        thr_h_pass_yds, thr_h_pass_td,
        thr_h_rush_yds, thr_h_rush_td,
        thr_h_recv_rec, thr_h_recv_yds, thr_h_recv_td,
    ])
    if half_active:
        st.markdown("<div class='sec-div' style='margin-top:8px'>Prop Checker by Half — Results</div>",
                    unsafe_allow_html=True)
        htabs = st.tabs(["Passing","Rushing","Receiving"])
        with htabs[0]: show_half_prop_or_stats("passing",   "YDS")
        with htabs[1]: show_half_prop_or_stats("rushing",   "YDS")
        with htabs[2]: show_half_prop_or_stats("receiving", "YDS")

    st.divider()

    # ── Prop Text Grader ──────────────────────────────────────────────────────
    st.markdown("<div class='sec-div'>🎯 Prop Grader — Enter Props as Text</div>",
                unsafe_allow_html=True)
    st.caption(
        "Enter one prop per line in plain English. "
        "Examples:\n"
        "• Bijan Robinson to record 10+ Rushing Yards in Each Quarter\n"
        "• Tua Tagovailoa Over 250 Passing Yards Game Total\n"
        "• Tyreek Hill 3+ Receptions Each Half"
    )

    prop_text = st.text_area(
        "Props",
        placeholder=(
            "Bijan Robinson to record 10+ Rushing Yards in Each Quarter+240\n"
            "Bijan Robinson & Kyren Williams to Each Record 5+ Rushing Yards in Each Quarter+330\n"
            "Kirk Cousins to record 100+ Passing Yards in Each Half+120"
        ),
        height=200,
        key="prop_text_input",
        label_visibility="collapsed",
    )

    run_grader = st.button("⚡ Grade Props", key="grade_btn")

    if run_grader and prop_text.strip():
        def strip_odds(line: str) -> str:
            """Remove trailing +240 / -115 odds from a prop line."""
            import re as _re2
            m = _re2.search(r'[+-]\d+\s*$', line.strip())
            return line[:m.start()].strip() if m else line.strip()

        raw_lines   = [l.strip() for l in prop_text.strip().splitlines() if l.strip()]
        clean_lines = [strip_odds(l) for l in raw_lines]

        # Parse props with regex — no API call needed
        import re as _re

        STAT_MAP_RE = [
            (_re.compile(r'rushing yards?|rushing yds?', _re.I),   "Rushing Yards"),
            (_re.compile(r'rushing tds?|rushing touchdowns?', _re.I), "Rushing TDs"),
            (_re.compile(r'passing yards?|passing yds?', _re.I),   "Passing Yards"),
            (_re.compile(r'passing tds?|passing touchdowns?', _re.I), "Passing TDs"),
            (_re.compile(r'receiving yards?|receiving yds?', _re.I), "Receiving Yards"),
            (_re.compile(r'receptions?', _re.I),                   "Receptions"),
            (_re.compile(r'interceptions?', _re.I),                "Interceptions"),
        ]
        COND_MAP_RE = [
            (_re.compile(r'each quarter', _re.I),  "each quarter"),
            (_re.compile(r'each half',    _re.I),  "each half"),
        ]
        THRESHOLD_RE = _re.compile(r'(\d+)\+?\s*(?:or more)?')
        PLAYERS_RE   = _re.compile(
            r'^(.+?)(?:\s+(?:&|and)\s+(.+?))\s+to\s+each\s+(?:record|have)', _re.I)
        SINGLE_RE    = _re.compile(r'^(.+?)\s+to\s+(?:record|have|score)', _re.I)
        RUSH_TD_RE2  = _re.compile(r'(\d+)\+?\s*rushing tds?', _re.I)
        PASS_TD_RE2  = _re.compile(r'(\d+)\+?\s*passing tds?', _re.I)
        ANY_TD_RE    = _re.compile(r'(\d+)\+?\s*tds?(?!.*fg)', _re.I)
        FG_RE2       = _re.compile(r'(\d+)\+?\s*(?:fgs?|field goals?)', _re.I)
        COND_MAP_RE2 = [
            (_re.compile(r'each quarter|all four quarters', _re.I), 'each quarter'),
            (_re.compile(r'each half', _re.I), 'each half'),
        ]

        NAME_ALIASES = {
            "kenneth walker iii": "kenneth walker",
            "patrick mahomes ii": "patrick mahomes",
            "odell beckham jr":   "odell beckham",
            "odell beckham jr.":  "odell beckham",
            "robert griffin iii": "robert griffin",
        }

        def normalise_name(n: str) -> str:
            import re as _rn
            n = n.strip()
            n = _rn.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\s*$', '', n, flags=_rn.I).strip()
            return NAME_ALIASES.get(n.lower(), n)

        props = []
        error_rows = []
        try:
            for i, line in enumerate(clean_lines):
                stat = None
                for pat, label in STAT_MAP_RE:
                    if pat.search(line):
                        stat = label
                        break
                tm = THRESHOLD_RE.search(line)
                threshold = float(tm.group(1)) if tm else None
                condition = "game total"
                for pat, label in COND_MAP_RE:
                    if pat.search(line):
                        condition = label
                        break
                dual   = PLAYERS_RE.match(line)
                single = SINGLE_RE.match(line) if not dual else None
                if not stat or threshold is None or (not dual and not single):
                    error_rows.append({"line_index": i, "raw_line": line})
                    continue
                if dual:
                    for player in [normalise_name(dual.group(1)),
                                   normalise_name(dual.group(2))]:
                        props.append({"line_index": i, "player": player,
                                      "stat": stat, "threshold": threshold,
                                      "condition": condition, "operator": "over"})
                else:
                    props.append({"line_index": i,
                                  "player": normalise_name(single.group(1)),
                                  "stat": stat, "threshold": threshold,
                                  "condition": condition, "operator": "over"})
        except Exception as e:
            st.error(f"Could not parse props: {e}")
            props = []
            error_rows = []

        # Teams in this game — used to validate players
        _game_teams = set()
        try:
            _game_teams.add(game["away"]["abbr"].upper())
            _game_teams.add(game["home"]["abbr"].upper())
        except Exception:
            pass

        # Build full-name → team lookup from boxscore (displayName = 'Brian Robinson')
        # Lets us distinguish Bijan Robinson (ATL) vs Brian Robinson (WSH) by full name + team.
        _full_name_team: dict = {}   # full_name_lower → team_abbr
        _game_abbrs:     set  = set()  # espn abbrs (B.Robinson) in this game
        _game_players:   dict = {}   # abbr → team (kept for _find_player)

        try:
            from nfl.api import get_game_summary as _gsum
            _summary = _gsum(game_id)
            if _summary:
                for _tdata in _summary.get('boxscore', {}).get('players', []):
                    _team_abbr = _tdata.get('team', {}).get('abbreviation', '').upper()
                    for _cat in _tdata.get('statistics', []):
                        for _ath in _cat.get('athletes', []):
                            _full = _ath.get('athlete', {}).get('displayName', '')
                            if _full:
                                _full_name_team[_full.lower()] = _team_abbr
        except Exception:
            pass

        for _cat in ['passing', 'rushing', 'receiving']:
            _fg_df = by_period.get('Full Game', {}).get(_cat, pd.DataFrame())
            if _fg_df is not None and not _fg_df.empty and 'Player' in _fg_df.columns:
                for _, _row in _fg_df.iterrows():
                    _abbr = _row['Player']; _team = _row.get('Team', '')
                    if _abbr:
                        _game_abbrs.add(_abbr)
                        _game_players[_abbr] = _team
        def _abbr_from_name(player: str) -> str:
            """Convert 'Bijan Robinson' → 'B.Robinson'."""
            parts = player.strip().split()
            if len(parts) < 2:
                return player
            return f"{parts[0][0].upper()}.{parts[-1]}"

        def _name_matches_game(player: str) -> bool:
            """
            True only if the player's abbreviated form exists uniquely in this game.
            If B.Robinson exists but the user typed 'Bijan' and the game player
            could be 'Brian', we cannot confirm — return False (→ N/A).
            
            We confirm a match when:
              1. The abbr exists in _game_players, AND
              2. The first name provided is consistent with the abbr initial, AND
              3. If the full name is ≥2 chars first name, it starts with the same
                 letter (can't go further without external data).
            
            For the Bijan/Brian collision: both produce B.Robinson.
            We resolve by checking: does any other player in the game share
            the same abbr? If so, we cannot confirm → N/A.
            Actually ESPN guarantees unique abbrs per team so B.Robinson is unique
            per team. But Bijan (ATL) vs Brian (WSH) — if B.Robinson is WSH, 
            and we typed 'Bijan Robinson' → the game has B.Robinson (Brian, WSH).
            We CANNOT distinguish Bijan from Brian with initials alone.
            
            Practical rule: if the first name provided is ≥4 chars, we keep it
            ambiguous (N/A) unless we have a strong signal. If ≤3 chars (e.g. 'Dak',
            'Cam'), initial match is sufficient. This isn't perfect but handles
            common cases. Better: accept the match and let the team filter decide.
            The real guard is _game_teams — if Bijan's team (ATL) isn't in the game,
            it won't matter that B.Robinson matched because team filter removes it.
            """
            abbr = _abbr_from_name(player)
            return abbr in _game_players

        def _find_player(player: str, category: str, period_key: str):
            """Return matching row or empty DataFrame.
            Uses pre-validated game player list so only real participants match.
            """
            pdf = by_period.get(period_key, {}).get(category, pd.DataFrame())
            if pdf is None or pdf.empty or "Player" not in pdf.columns:
                return pd.DataFrame()

            abbr = _abbr_from_name(player)

            # Exact abbreviated name match
            m = pdf[pdf["Player"] == abbr]

            # Filter to teams in this game
            if not m.empty and _game_teams and "Team" in m.columns:
                m = m[m["Team"].str.upper().isin(_game_teams)]

            return m

        def player_found_in_game(player: str, category: str) -> bool:
            """Full-name + team validation.
            1. If boxscore full names are available: match exact full name and
               confirm their team is one of the two teams in this game.
               This correctly distinguishes Bijan Robinson (ATL) vs Brian Robinson (WSH).
            2. Fallback (no boxscore): check ESPN abbr in game abbr set.
            """
            name_lower = player.strip().lower()
            if _full_name_team:
                if name_lower not in _full_name_team:
                    return False
                player_team = _full_name_team[name_lower].upper()
                return not _game_teams or player_team in _game_teams
            # Fallback
            abbr = _abbr_from_name(player)
            return abbr in _game_abbrs

        def get_player_val(player: str, category: str, col: str, period_key: str) -> float:
            match = _find_player(player, category, period_key)
            return float(match.iloc[0].get(col, 0)) if not match.empty else 0.0

        def grade_prop(prop: dict) -> dict:
            player    = prop.get("player","")
            stat      = prop.get("stat","").lower()
            threshold = float(prop.get("threshold", 0))
            condition = prop.get("condition","game total").lower()
            operator  = prop.get("operator","over").lower()

            stat_map = {
                "rushing yards":   ("rushing",   "YDS"),
                "rushing yds":     ("rushing",   "YDS"),
                "rushing td":      ("rushing",   "TD"),
                "rushing tds":     ("rushing",   "TD"),
                "passing yards":   ("passing",   "YDS"),
                "passing yds":     ("passing",   "YDS"),
                "passing td":      ("passing",   "TD"),
                "passing tds":     ("passing",   "TD"),
                "interceptions":   ("passing",   "INT"),
                "receptions":      ("receiving", "REC"),
                "receiving yards": ("receiving", "YDS"),
                "receiving yds":   ("receiving", "YDS"),
                "receiving td":    ("receiving", "TD"),
                "receiving tds":   ("receiving", "TD"),
                    "sack":            ("defense",   "SACKS"),
                    "sacks":           ("defense",   "SACKS"),
                    "record a sack":   ("defense",   "SACKS"),
            }
            category, col = None, None
            for key, val in stat_map.items():
                if key in stat:
                    category, col = val
                    break

            if not category:
                return {
                    "player": player, "stat": prop.get("stat",""),
                    "threshold": threshold, "condition": prop.get("condition",""),
                    "period_results": {}, "won": None,
                }

            # If player doesn't appear in this game's data at all → N/A
            if not player_found_in_game(player, category):
                return {
                    "player": player, "stat": prop.get("stat",""),
                    "threshold": threshold, "condition": prop.get("condition",""),
                    "period_results": {}, "won": None,
                }

            def hit(v: float) -> bool:
                if operator == "under":   return v < threshold
                if operator == "exactly": return v == threshold
                return v >= threshold

            period_results = {}

            if "each quarter" in condition:
                for q in ["Q1","Q2","Q3","Q4"]:
                    v = get_player_val(player, category, col, q)
                    period_results[q] = f"{'✅' if hit(v) else '❌'} {v:.0f}"
                won = all(hit(get_player_val(player, category, col, q)) for q in ["Q1","Q2","Q3","Q4"])
            elif "each half" in condition:
                for h, lbl in [("1H","1st Half"),("2H","2nd Half")]:
                    v = get_player_val(player, category, col, h)
                    period_results[lbl] = f"{'✅' if hit(v) else '❌'} {v:.0f}"
                won = all(hit(get_player_val(player, category, col, h)) for h in ["1H","2H"])
            else:
                v = get_player_val(player, category, col, "Full Game")
                period_results["Game"] = f"{'✅' if hit(v) else '❌'} {v:.0f}"
                won = hit(v)

            return {
                "player":         player,
                "stat":           prop.get("stat",""),
                "threshold":      threshold,
                "condition":      prop.get("condition",""),
                "period_results": period_results,
                "won":            won,
            }

        # Group props by line_index so dual-player props are graded together
        from collections import defaultdict as _dd
        by_line = _dd(list)
        for p in props:
            by_line[p.get('line_index', id(p))].append(p)
        def grade_prop_group(group: list) -> dict:
            """Grade one or more players for the same prop line.
            For multi-player props, ALL players must hit the threshold
            in ALL periods for the selection to Win."""
            results = [grade_prop(p) for p in group]

            players_str = " & ".join(r["player"] for r in results)
            first       = results[0]
            stat        = first.get("stat","")
            threshold   = first.get("threshold", 0)
            condition   = first.get("condition","")
            # Overall: ALL players must have won
            if any(r['won'] is None for r in results):
                overall_won = None
            else:
                overall_won = all(r['won'] for r in results)

            stat_short = {
                "Rushing Yards":   "Rush Yds",
                "Rushing TDs":     "Rush TDs",
                "Passing Yards":   "Pass Yds",
                "Passing TDs":     "Pass TDs",
                "Receiving Yards": "Rec Yds",
                "Receptions":      "Rec",
                "Interceptions":   "INTs",
            }.get(stat, stat)
            scope_short = {
                "each quarter": "Each Qrt",
                "each half":    "Each HF",
                "game total":   "Game",
            }.get(condition.lower(), condition)
            return {
                "Players": players_str,
                "Prop":    f"{threshold:.0f}+ {stat_short}",
                "Scope":   scope_short,
                "Result":  "✅ Won" if overall_won is True else ("⚠️ N/A" if overall_won is None else "❌ Lost"),
            }

        graded = [grade_prop_group(group) for group in by_line.values()]
        for er in error_rows:
            graded.append({
                "Players": er.get("raw_line","")[:60],
                "Prop":    "—",
                "Scope":   "—",
                "Result":  "❗ Error",
            })

        def _color(val):
            if isinstance(val, str):
                if val.startswith('✅'): return 'color:#22c55e;font-weight:700'
                if val.startswith('❌'): return 'color:#ef4444;font-weight:700'
                if val.startswith('⚠️'): return 'color:#f59e0b;font-weight:700'
                if val.startswith('❗'): return 'color:#a855f7;font-weight:700'
            return ''

        def _sort(df, col):
            if df.empty or 'Result' not in df.columns: return df
            df = df.copy()
            df['_w'] = df['Result'].apply(lambda x: 0 if 'Won' in str(x) else (2 if 'N/A' in str(x) else 1))
            return df.sort_values(['_w', col]).drop(columns=['_w']).reset_index(drop=True)

        # ── Player props table ─────────────────────────────────────────
        gdf = pd.DataFrame(graded) if graded else pd.DataFrame()
        if not gdf.empty:
            gdf = _sort(gdf, 'Players')
            np_ = len(gdf); nw_ = sum(1 for v in gdf['Result'] if 'Won' in str(v))
            st.markdown(f'**👤 Player Props** — {np_} props · {nw_} ✅ Won · {np_-nw_} ❌/⚠️')
            ps = [c for c in gdf.columns if c not in ('Players','Prop','Scope')]
            st.dataframe(gdf.style.map(_color, subset=ps), use_container_width=True, hide_index=True)

        # Fallback if nothing graded
        if not graded:
            st.info('No player props could be parsed. Check that lines include a player name, stat type and threshold.')

        # ── Team / game props table ────────────────────────────────────
