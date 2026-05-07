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
            options=[year - 1, year, year + 1],
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
        """Show per-period offensive stat.
        Full Game uses ESPN boxscore (accurate); periods use play-by-play."""
        stats_key = _PERIOD_KEY.get(period_filter, period_filter)
        if stats_key == "Full Game":
            df = data.get(category)
        else:
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
        # Remove Pos column if present
        if isinstance(df, pd.DataFrame) and "Pos" in df.columns:
            df = df.drop(columns=["Pos"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    tabs = st.tabs(["Passing","Rushing","Receiving","Defense","Kicking"])
    with tabs[0]: show_period_df("passing",   "YDS")
    with tabs[1]: show_period_df("rushing",   "YDS")
    with tabs[2]: show_period_df("receiving", "YDS")
    with tabs[3]:
        if period_filter == "Full Game":
            show_df(data["defense"], period_filter, "TOT", drop_cols=["Pos"])
        else:
            st.info("ℹ️ Defensive stats are only available for Full Game. Per-quarter/half breakdowns are not provided in this view.")
    with tabs[4]:
        if period_filter == "Full Game":
            show_df(data["kicking"], period_filter, drop_cols=["Pos"])
        else:
            st.info("ℹ️ Kicking stats are only available for Full Game. Per-quarter/half breakdowns are not provided in this view.")

    # ── Prop Checker ──────────────────────────────────────────────────────────
    with st.expander("🎯 Prop Checker by Quarter", expanded=False):
        st.caption(
            "Set a minimum threshold. Each player shows their stat per quarter "
            "with ✅ (hit) or ❌ (missed). The final column shows if they hit it in ALL quarters."
        )
        # Determine active group: passing=1, rushing=2, receiving=3, none=0
        _q_pass_on = bool(st.session_state.get("thr_pass_yds",0) or st.session_state.get("thr_pass_td",0))
        _q_rush_on = bool(st.session_state.get("thr_rush_yds",0) or st.session_state.get("thr_rush_td",0))
        _q_recv_on = bool(st.session_state.get("thr_recv_rec",0) or st.session_state.get("thr_recv_yds",0) or st.session_state.get("thr_recv_td",0))
        _q_dis_pass = _q_rush_on or _q_recv_on
        _q_dis_rush = _q_pass_on or _q_recv_on
        _q_dis_recv = _q_pass_on or _q_rush_on
        pc1, pc2, pc3, pc4, pc5, pc6, pc7 = st.columns(7)
        with pc1:
            thr_pass_yds = st.number_input("Pass YDS ≥",   min_value=0, value=0, step=1, key="thr_pass_yds", disabled=_q_dis_pass)
            if thr_pass_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_pass_yds}</div>", unsafe_allow_html=True)
        with pc2:
            thr_pass_td  = st.number_input("Pass TD ≥",    min_value=0, value=0, step=1, key="thr_pass_td",  disabled=_q_dis_pass)
            if thr_pass_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_pass_td}</div>", unsafe_allow_html=True)
        with pc3:
            thr_rush_yds = st.number_input("Rush YDS ≥",   min_value=0, value=0, step=1, key="thr_rush_yds", disabled=_q_dis_rush)
            if thr_rush_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_rush_yds}</div>", unsafe_allow_html=True)
        with pc4:
            thr_rush_td  = st.number_input("Rush TD ≥",    min_value=0, value=0, step=1, key="thr_rush_td",  disabled=_q_dis_rush)
            if thr_rush_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_rush_td}</div>", unsafe_allow_html=True)
        with pc5:
            thr_recv_rec = st.number_input("Receptions ≥", min_value=0, value=0, step=1, key="thr_recv_rec", disabled=_q_dis_recv)
            if thr_recv_rec > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_recv_rec}</div>", unsafe_allow_html=True)
        with pc6:
            thr_recv_yds = st.number_input("Rec YDS ≥",    min_value=0, value=0, step=1, key="thr_recv_yds", disabled=_q_dis_recv)
            if thr_recv_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_recv_yds}</div>", unsafe_allow_html=True)
        with pc7:
            thr_recv_td  = st.number_input("Rec TD ≥",     min_value=0, value=0, step=1, key="thr_recv_td",  disabled=_q_dis_recv)
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
        if _q_pass_on:
            show_prop_or_stats("passing", "YDS")
        elif _q_rush_on:
            show_prop_or_stats("rushing", "YDS")
        elif _q_recv_on:
            show_prop_or_stats("receiving", "YDS")

    with st.expander("📊 Prop Checker by Half", expanded=False):
        st.caption(
            "Set a minimum threshold. Each player shows their stat per half "
            "with ✅ (hit) or ❌ (missed). The final column shows if they hit it in BOTH halves."
        )
        _h_pass_on = bool(st.session_state.get("thr_h_pass_yds",0) or st.session_state.get("thr_h_pass_td",0))
        _h_rush_on = bool(st.session_state.get("thr_h_rush_yds",0) or st.session_state.get("thr_h_rush_td",0))
        _h_recv_on = bool(st.session_state.get("thr_h_recv_rec",0) or st.session_state.get("thr_h_recv_yds",0) or st.session_state.get("thr_h_recv_td",0))
        _h_dis_pass = _h_rush_on or _h_recv_on
        _h_dis_rush = _h_pass_on or _h_recv_on
        _h_dis_recv = _h_pass_on or _h_rush_on
        ph1, ph2, ph3, ph4, ph5, ph6, ph7 = st.columns(7)
        with ph1:
            thr_h_pass_yds = st.number_input("Pass YDS ≥",   min_value=0, value=0, step=1, key="thr_h_pass_yds", disabled=_h_dis_pass)
            if thr_h_pass_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_pass_yds}</div>", unsafe_allow_html=True)
        with ph2:
            thr_h_pass_td  = st.number_input("Pass TD ≥",    min_value=0, value=0, step=1, key="thr_h_pass_td",  disabled=_h_dis_pass)
            if thr_h_pass_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_pass_td}</div>", unsafe_allow_html=True)
        with ph3:
            thr_h_rush_yds = st.number_input("Rush YDS ≥",   min_value=0, value=0, step=1, key="thr_h_rush_yds", disabled=_h_dis_rush)
            if thr_h_rush_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_rush_yds}</div>", unsafe_allow_html=True)
        with ph4:
            thr_h_rush_td  = st.number_input("Rush TD ≥",    min_value=0, value=0, step=1, key="thr_h_rush_td",  disabled=_h_dis_rush)
            if thr_h_rush_td  > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_rush_td}</div>", unsafe_allow_html=True)
        with ph5:
            thr_h_recv_rec = st.number_input("Receptions ≥", min_value=0, value=0, step=1, key="thr_h_recv_rec", disabled=_h_dis_recv)
            if thr_h_recv_rec > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_recv_rec}</div>", unsafe_allow_html=True)
        with ph6:
            thr_h_recv_yds = st.number_input("Rec YDS ≥",    min_value=0, value=0, step=1, key="thr_h_recv_yds", disabled=_h_dis_recv)
            if thr_h_recv_yds > 0: st.markdown(f"<div style='color:#22c55e;font-size:0.7rem;font-weight:700;margin-top:-12px'>● Active: ≥{thr_h_recv_yds}</div>", unsafe_allow_html=True)
        with ph7:
            thr_h_recv_td  = st.number_input("Rec TD ≥",     min_value=0, value=0, step=1, key="thr_h_recv_td",  disabled=_h_dis_recv)
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
        if _h_pass_on:
            show_half_prop_or_stats("passing", "YDS")
        elif _h_rush_on:
            show_half_prop_or_stats("rushing", "YDS")
        elif _h_recv_on:
            show_half_prop_or_stats("receiving", "YDS")

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
            (_re.compile(r'rushing yards?|rushing yds?|rush yards?|rush yds?|rush yd\\b', _re.I),   "Rushing Yards"),
            (_re.compile(r'rushing tds?|rushing touchdowns?', _re.I), "Rushing TDs"),
            (_re.compile(r'passing yards?|passing yds?', _re.I),   "Passing Yards"),
            (_re.compile(r'passing tds?|passing touchdowns?', _re.I), "Passing TDs"),
            (_re.compile(r'receiving yards?|receiving yds?|rec yards?|rec yds?', _re.I), "Receiving Yards"),
            (_re.compile(r'receptions?', _re.I),                   "Receptions"),
            (_re.compile(r'interceptions?', _re.I),                "Interceptions"),
            (_re.compile(r'sacks?|record a sack', _re.I),          "Sacks"),
            (_re.compile(r'completions?|completed passes?', _re.I),          "Completions"),
            (_re.compile(r'receiving tds?|receiving touchdowns?|rec tds?', _re.I), "Receiving TDs"),
        ]
        COND_MAP_RE = [
            (_re.compile(r'each quarter', _re.I),  "each quarter"),
            (_re.compile(r'each half',    _re.I),  "each half"),
        ]
        _INLINE_PERIOD = _re.compile(r'\\b([1-4])([QH])\\b', _re.I)
        THRESHOLD_RE = _re.compile(r'(\d+\.?\d*)\+?\s*(?:or more)?')
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
        graded = []
        try:
            for i, line in enumerate(clean_lines):
                # Skip team/game market lines — handled separately below
                import re as _re_skip
                if _re_skip.match(r'^(each team|both teams|points scored|\d+[+]?\s*(?:tds?|touchdowns?|field goals?|fgs?|scored))', line, _re_skip.I):
                    continue
                # Skip team/game lines handled by team props
                if _re_skip.search(r'any quarter.*scoreless|scoreless.*quarter', line, _re_skip.I):
                    continue
                if _re_skip.search(r'to\s+score\s+in\s+all\s+four\s+quarters', line, _re_skip.I):
                    continue
                if _re_skip.search(r'special teams?\s+to\s+score', line, _re_skip.I):
                    continue
                if _re_skip.search(r'to\s+beat\s+.+?\s+in\s+overtime', line, _re_skip.I):
                    continue
                if _re_skip.match(r'^no\s+touchdown\s+in\s+the\s+game', line, _re_skip.I):
                    continue
                if _re_skip.match(r'^successful\s+2\s*pt\s+conversion', line, _re_skip.I):
                    continue
                # "to score the first TD" — grade immediately if it matches
                if _re.search(r'to\s+score\s+the\s+first\s+td', line, _re.I) and "special teams" not in line.lower():
                    _ftd_pls = []
                    _or_ftd = _re.match(r'^(.+?)\s+or\s+(.+?)\s+to\s+score\s+the\s+first\s+td', line, _re.I)
                    _single_ftd = _re.match(r'^(.+?)\s+to\s+score\s+the\s+first\s+td', line, _re.I)
                    if _or_ftd:
                        _ftd_pls = [_or_ftd.group(1).strip(), _or_ftd.group(2).strip()]
                    elif _single_ftd:
                        _ftd_pls = [_single_ftd.group(1).strip()]
                    if _ftd_pls:
                        _sdf_ftd2 = data.get("scoring", pd.DataFrame())
                        _won_ftd = None
                        _ftd_detail2 = "No TDs"
                        _ALL_TD_T = {"rushing touchdown","passing touchdown","receiving touchdown",
                                     "punt return touchdown","kickoff return touchdown",
                                     "blocked punt touchdown","blocked field goal touchdown",
                                     "interception return touchdown","fumble return touchdown","touchdown"}
                        if _sdf_ftd2 is not None and not _sdf_ftd2.empty and "Type" in _sdf_ftd2.columns:
                            _td_r = _sdf_ftd2[_sdf_ftd2["Type"].str.lower().isin(_ALL_TD_T)]
                            if not _td_r.empty:
                                _fdesc = _td_r.iloc[0].get("Description", "")
                                _ftd_detail2 = _fdesc[:60]
                                _won_ftd = any(p.split()[-1].lower() in _fdesc.lower() for p in _ftd_pls)
                        _ftd_res = "✅ Won" if _won_ftd is True else ("❗ Error" if _won_ftd is None else "❌ Lost")
                        graded.append({"Prop": line, "Data": f"First TD: {_ftd_detail2}", "Result": _ftd_res})
                        continue
                stat = None
                for pat, label in STAT_MAP_RE:
                    if pat.search(line):
                        stat = label
                        break
                tm = THRESHOLD_RE.search(line)
                threshold = float(tm.group(1)) if tm else None
                # For sack props "Record a Sack" implies threshold of 1
                if threshold is None and stat == "Sacks":
                    threshold = 1.0
                condition = "game total"
                for pat, label in COND_MAP_RE:
                    if pat.search(line):
                        condition = label
                        break
                dual   = PLAYERS_RE.match(line)
                single = SINGLE_RE.match(line) if not dual else None
                alt    = None

                # ── New prop formats ────────────────────────────────────────
                # "Bo Nix and Dak Prescott to Combine for 500+ Passing Yards"
                # "Bo Nix or Dak Prescott to record 400+ Passing Yards"
                # "Both Bo Nix and Dak Prescott to Each Complete 25+ Passes"
                # "CeeDee Lamb, Courtland Sutton, and George Pickens to Combine for 4+ TDs"
                _COMBINE_STAT_RE = _re.compile(
                    r'(\d+\.?\d*)\+?\s*(passing tds?|pass tds?|rushing tds?|rush tds?|receiving tds?|rec tds?|tds?|touchdowns?|passing yards?|rushing yards?|receiving yards?|rec yards?|rec yds?|rush yards?|rush yds?|completions?|passes?|receptions?)', _re.I)
                _OR_RE      = _re.compile(r'^(.+?)\s+or\s+(.+?)\s+to\s+(?:record|have|score)', _re.I)
                _EACH_RE    = _re.compile(r'^(?:both\s+)?(.+?)\s+and\s+(.+?)\s+to\s+each\s+(?:complete|record|have|score)', _re.I)
                _CMB5_RE    = _re.compile(r'^(.+?),\s+(.+?),\s+(.+?),\s+(.+?),?\s+and\s+(.+?)\s+to\s+combine', _re.I)
                _CMB4_RE    = _re.compile(r'^(.+?),\s+(.+?),\s+(.+?),?\s+and\s+(.+?)\s+to\s+combine', _re.I)
                _CMB3_RE    = _re.compile(r'^(.+?),\s+(.+?),?\s+and\s+(.+?)\s+to\s+combine', _re.I)
                _CMB2_RE    = _re.compile(r'^(.+?)\s+and\s+(.+?)\s+to\s+combine', _re.I)

                _cm = _COMBINE_STAT_RE.search(line)
                if _cm:
                    _thr = float(_cm.group(1))
                    _stat_raw = _cm.group(2).strip().lower()
                    # Map to category/col
                    _SMAP = {
                        "passing tds":"passing/TD","pass tds":"passing/TD",
                        "rushing tds":"rushing/TD","rush tds":"rushing/TD",
                        "receiving tds":"receiving/TD","rec tds":"receiving/TD",
                        "tds":"multi/TD","touchdowns":"multi/TD","td":"multi/TD","touchdown":"multi/TD",
                        "passing yards":"passing/YDS","rushing yards":"rushing/YDS",
                        "receiving yards":"receiving/YDS","rec yards":"receiving/YDS",
                        "rec yds":"receiving/YDS","rush yards":"rushing/YDS","rush yds":"rushing/YDS",
                        "completions":"passing/COMP","passes":"passing/COMP","completed passes":"passing/COMP",
                        "receptions":"receiving/REC","reception":"receiving/REC",
                    }
                    _cat_col = next((v for k,v in sorted(_SMAP.items(), key=lambda x:-len(x[0])) if k in _stat_raw), None)
                    if _cat_col:
                        _cat, _col = _cat_col.split("/")
                        _or_m   = _OR_RE.match(line)
                        _each_m = _EACH_RE.match(line)
                        _c5_m   = _CMB5_RE.match(line)
                        _c4_m   = _CMB4_RE.match(line)
                        _c3_m   = _CMB3_RE.match(line)
                        _c2_m   = _CMB2_RE.match(line)
                        if _or_m:
                            props.append({'line_index': i, 'player': _or_m.group(1).strip(),
                                'player2': _or_m.group(2).strip(),
                                'players_list': [_or_m.group(1).strip(), _or_m.group(2).strip()],
                                'stat': _stat_raw, 'threshold': _thr, 'condition': condition,
                                'operator': 'or', 'category': _cat, 'col': _col, 'raw_line': line})
                            continue
                        elif _each_m:
                            props.append({'line_index': i, 'player': _each_m.group(1).strip(),
                                'player2': _each_m.group(2).strip(), 'stat': _stat_raw,
                                'threshold': _thr, 'condition': condition, 'operator': 'each',
                                'players_list': [_each_m.group(1).strip(), _each_m.group(2).strip()],
                                'category': _cat, 'col': _col, 'raw_line': line})
                            continue
                        elif _c5_m:
                            props.append({"line_index": i,
                                "players_list": [_c5_m.group(1).strip(), _c5_m.group(2).strip(), _c5_m.group(3).strip(),
                                                 _c5_m.group(4).strip(), _c5_m.group(5).strip()],
                                "player": _c5_m.group(1).strip(), "stat": _stat_raw, "threshold": _thr,
                                "condition": condition, "operator": "combine",
                                "category": _cat, "col": _col, "raw_line": line})
                            continue
                        elif _c4_m:
                            props.append({"line_index": i,
                                "players_list": [_c4_m.group(1).strip(), _c4_m.group(2).strip(),
                                                 _c4_m.group(3).strip(), _c4_m.group(4).strip()],
                                "player": _c4_m.group(1).strip(), "stat": _stat_raw, "threshold": _thr,
                                "condition": condition, "operator": "combine",
                                "category": _cat, "col": _col, "raw_line": line})
                            continue
                        elif _c3_m:
                            props.append({"line_index": i,
                                "players_list": [_c3_m.group(1).strip(), _c3_m.group(2).strip(), _c3_m.group(3).strip()],
                                "player": _c3_m.group(1).strip(),
                                "stat": _stat_raw, "threshold": _thr, "condition": condition,
                                "operator": "combine", "category": _cat, "col": _col, "raw_line": line})
                            continue
                        elif _c2_m:
                            props.append({"line_index": i,
                                "players_list": [_c2_m.group(1).strip(), _c2_m.group(2).strip()],
                                "player": _c2_m.group(1).strip(),
                                "stat": _stat_raw, "threshold": _thr, "condition": condition,
                                "operator": "combine", "category": _cat, "col": _col, "raw_line": line})
                            continue
                pm = _INLINE_PERIOD.search(line)
                if pm and condition == "game total":
                    n2, t2 = pm.group(1), pm.group(2).upper()
                    condition = f"Q{n2}" if t2 == "Q" else ("1st Half" if n2 in "12" else "2nd Half")
                operator = "under" if _re.search(r'under', line, _re.I) else "over"
                if not stat or threshold is None or (not dual and not single and not alt):
                    error_rows.append({"line_index": i, "raw_line": line})
                    continue
                if dual:
                    for player in [dual.group(1).strip(), dual.group(2).strip()]:
                        props.append({"line_index": i, "player": player, "stat": stat,
                                      "threshold": threshold, "condition": condition,
                                      "operator": operator, "raw_line": line})
                else:
                    player_raw = (single or alt).group(1).strip()
                    props.append({"line_index": i, "player": player_raw, "stat": stat,
                                  "threshold": threshold, "condition": condition,
                                  "operator": operator, "raw_line": line})
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
                                _key = _full.lower().strip()
                                _full_name_team[_key] = _team_abbr
                                import re as _rn2
                                _norm = _rn2.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$', '', _key, flags=_rn2.I).strip()
                                if _norm != _key:
                                    _full_name_team[_norm] = _team_abbr
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
            Full Game uses ESPN boxscore (accurate); periods use play-by-play."""
            abbr = _abbr_from_name(player)

            if period_key == "Full Game":
                # Use ESPN official boxscore for accuracy
                pdf = data.get(category, pd.DataFrame())
                if pdf is None or pdf.empty or "Player" not in pdf.columns:
                    return pd.DataFrame()
                # Try standard abbr (R.Harvey), then full-first-name abbr (RJ.Harvey)
                m = pdf[pdf["Player"] == abbr]
                if m.empty:
                    parts = player.strip().split()
                    if len(parts) >= 2:
                        full_abbr = f"{parts[0]}.{parts[-1]}"  # RJ.Harvey
                        m = pdf[pdf["Player"] == full_abbr]
                if m.empty:
                    # Last name fallback
                    parts = player.strip().split()
                    m = pdf[pdf["Player"].str.contains(parts[-1], case=False, na=False)]
                if not m.empty and _game_teams and "Team" in m.columns:
                    m = m[m["Team"].str.upper().isin(_game_teams)]
                return m

            pdf = by_period.get(period_key, {}).get(category, pd.DataFrame())
            if pdf is None or pdf.empty or "Player" not in pdf.columns:
                return pd.DataFrame()

            m = pdf[pdf["Player"] == abbr]
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
            # Defense (sacks): check by_period and ESPN defense df
            if category == 'defense':
                # Use _full_name_team — same approach that fixed Kenneth Walker III.
                # Built from ESPN boxscore with both raw + suffix-stripped keys.
                # Covers ALL players who appeared in the game including all defenders.
                import re as _ren
                name_lower = player.strip().lower()
                norm_lower = _ren.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$',
                                      '', name_lower, flags=_ren.I).strip()
                for _n in [name_lower, norm_lower]:
                    if _n in _full_name_team:
                        t = _full_name_team[_n].upper()
                        if not _game_teams or t in _game_teams:
                            return True
                return False

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
            try:
                if category == 'defense':
                    import re as _ren2
                    name_lower = player.strip().lower()
                    norm_lower = _ren2.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$',
                                          '', name_lower, flags=_ren2.I).strip()

                    # For per-period sacks: use play-by-play parsed data (by_period)
                    # PBP stores abbreviated names (C.Barmore) — build abbr from full name
                    parts = player.strip().split()
                    suffix_w = {'jr','jr.','sr','sr.','ii','iii','iv'}
                    last_w   = next((p for p in reversed(parts) if p.lower() not in suffix_w), parts[-1])
                    abbr     = f"{parts[0][0]}.{last_w}" if len(parts) >= 2 else player

                    pbp_def = by_period.get(period_key, {}).get('defense', pd.DataFrame())
                    if pbp_def is not None and not pbp_def.empty and 'Player' in pbp_def.columns:
                        # PBP df has data for this period — player in it means they sacked
                        m = pbp_def[pbp_def['Player'] == abbr]
                        return float(m.iloc[0].get('SACKS', 0)) if not m.empty else 0.0

                    # PBP df empty for this period — only fall back to ESPN full-game
                    # if period_key is Full Game, otherwise treat as 0 sacks this period
                    if period_key != 'Full Game':
                        return 0.0

                    # Full Game scope: use ESPN cumulative defense df
                    df2 = data.get('defense', pd.DataFrame())
                    if df2 is not None and not df2.empty and 'Player' in df2.columns and 'SACKS' in df2.columns:
                        pl = df2['Player'].str.lower()
                        m2 = df2[pl.eq(name_lower) | pl.eq(norm_lower)]
                        if not m2.empty:
                            return float(pd.to_numeric(m2.iloc[0].get('SACKS', 0), errors='coerce') or 0)
                    return 0.0
                match = _find_player(player, category, period_key)
                _row_r = match.iloc[0]
                if col == 'COMP' and 'C/ATT' in _row_r.index:
                    try: return float(str(_row_r['C/ATT']).split('/')[0])
                    except: return 0.0
                return float(pd.to_numeric(_row_r.get(col, 0), errors='coerce') or 0) if not match.empty else 0.0
            except Exception:
                return 0.0
            match = _find_player(player, category, period_key)
            _row_r = match.iloc[0]
            if col == 'COMP' and 'C/ATT' in _row_r.index:
                try: return float(str(_row_r['C/ATT']).split('/')[0])
                except: return 0.0
            return float(pd.to_numeric(_row_r.get(col, 0), errors='coerce') or 0) if not match.empty else 0.0

        def grade_prop(prop: dict) -> dict:
            player    = prop.get("player","")
            stat      = prop.get("stat","").lower()
            threshold = float(prop.get("threshold", 0))
            condition = prop.get("condition","game total").lower()
            operator  = prop.get("operator","over").lower()

            # Handle combine/or/each operators early — before stat_map lookup
            if operator in ("combine","or","each"):
                players_list = prop.get("players_list", [prop.get("player",""), prop.get("player2","")])
                cat2 = prop.get("category","")
                col2 = prop.get("col","YDS")
                thr2 = threshold
                def _fg2(p, c, cl):
                    df2 = data.get(c, pd.DataFrame())
                    if df2 is None or df2.empty or "Player" not in df2.columns: return None
                    abbr2 = _abbr_from_name(p)
                    m2 = df2[df2["Player"] == abbr2]
                    if m2.empty:
                        import re as _r3; nl2=p.strip().lower()
                        nm2=_r3.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$','',nl2,flags=_r3.I).strip()
                        pl2=df2["Player"].str.lower(); m2=df2[pl2.eq(nl2)|pl2.eq(nm2)]
                    if m2.empty:
                        parts2=p.strip().split()
                        m2=df2[df2["Player"].str.contains(parts2[-1],case=False,na=False)]
                        if not m2.empty and _game_teams and "Team" in df2.columns:
                            m2=m2[m2["Team"].str.upper().isin(_game_teams)]
                    if m2.empty: return None
                    row2 = m2.iloc[0]
                    # Completions: ESPN stores as "C/ATT" e.g. "19/29" — extract comp part
                    if cl == "COMP" and "C/ATT" in row2.index:
                        try: return float(str(row2["C/ATT"]).split("/")[0])
                        except: return 0.0
                    return float(pd.to_numeric(row2.get(cl, 0), errors="coerce") or 0)
                def _mltd2(p):
                    return (_fg2(p,"rushing","TD") or 0)+(_fg2(p,"receiving","TD") or 0)
                vals2={}; all_found2=True
                for p2 in players_list:
                    v2=_mltd2(p2) if cat2=="multi" else _fg2(p2,cat2,col2)
                    if v2 is None: all_found2=False; v2=0
                    vals2[p2]=v2
                total2=sum(vals2.values())
                detail2=" | ".join(f"{p2.split()[-1]}: {v2:.0f}" for p2,v2 in vals2.items())
                players_str2=" & ".join(players_list)
                if operator=="combine":
                    won2=total2>=thr2 if all_found2 else None
                    scope2=f"Total: {total2:.0f} | {detail2}"
                elif operator=="or":
                    won2=any(v2>=thr2 for v2 in vals2.values()) if all_found2 else None
                    scope2=detail2
                else:
                    won2=all(v2>=thr2 for v2 in vals2.values()) if all_found2 else None
                    scope2=detail2
                return {
                    "player": players_str2, "stat": prop.get("stat",""),
                    "threshold": thr2, "condition": scope2,
                    "period_results": {}, "won": won2 is True,
                    "raw_line": prop.get("raw_line",""),
                    "_pre_graded": True,
                }

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
                "completions":      ("passing",    "COMP"),
                "completion":       ("passing",    "COMP"),
                "completed passes": ("passing",    "COMP"),
                "receiving tds":    ("receiving",  "TD"),
                "receiving td":     ("receiving",  "TD"),
                "rec tds":          ("receiving",  "TD"),
                "rec td":           ("receiving",  "TD"),
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
                operator2 = prop.get('operator','over')
                if operator2 in ('combine','or','each'):
                    players_list = prop.get('players_list', [prop.get('player',''), prop.get('player2','')])
                    cat2 = prop.get('category','')
                    col2 = prop.get('col','TD')
                    thr2 = threshold
                    def _fg(p, c, cl):
                        df2 = data.get(c, pd.DataFrame())
                        if df2 is None or df2.empty or 'Player' not in df2.columns: return None
                        abbr2 = _abbr_from_name(p)
                        m2 = df2[df2['Player'] == abbr2]
                        if m2.empty:
                            import re as _r3; nl2 = p.strip().lower()
                            import re as _r4; nm2 = _r4.sub(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$','',nl2,flags=_r4.I).strip()
                            pl2 = df2['Player'].str.lower()
                            m2 = df2[pl2.eq(nl2)|pl2.eq(nm2)]
                        if m2.empty:
                            parts2 = p.strip().split()
                            m2 = df2[df2['Player'].str.contains(parts2[-1], case=False, na=False)]
                            if not m2.empty and _game_teams and 'Team' in df2.columns:
                                m2 = m2[m2['Team'].str.upper().isin(_game_teams)]
                        return float(pd.to_numeric(m2.iloc[0].get(cl,0), errors='coerce') or 0) if not m2.empty else None
                    def _multi_td2(p):
                        return (_fg(p,'rushing','TD') or 0) + (_fg(p,'receiving','TD') or 0)
                    vals2 = {}
                    all_found2 = True
                    for p2 in players_list:
                        v2 = _multi_td2(p2) if cat2 == 'multi' else _fg(p2, cat2, col2)
                        if v2 is None: all_found2 = False; v2 = 0
                        vals2[p2] = v2
                    total2 = sum(vals2.values())
                    detail2 = ' | '.join(f"{p2.split()[-1]}: {v2:.0f}" for p2,v2 in vals2.items())
                    players_str2 = ' & '.join(players_list)
                    if operator2 == 'combine':
                        won2 = total2 >= thr2 if all_found2 else None
                        scope2 = f'Total:{total2:.0f} | {detail2}'
                    elif operator2 == 'or':
                        won2 = any(v2 >= thr2 for v2 in vals2.values()) if all_found2 else None
                        scope2 = detail2
                    else:
                        won2 = all(v2 >= thr2 for v2 in vals2.values()) if all_found2 else None
                        scope2 = detail2
                    return {
                        'player': players_str2, 'stat': prop.get('stat',''),
                        'threshold': thr2, 'condition': scope2,
                        'period_results': {}, 'won': won2 is True,
                        'raw_line': prop.get('raw_line',''),
                        '_pre_graded': True,
                    }
                return {
                    'player': player, 'stat': prop.get('stat',''),
                    'threshold': threshold, 'condition': prop.get('condition',''),
                    'period_results': {}, 'won': None, 'raw_line': prop.get('raw_line',''),
                }

            # If player doesn't appear in this game's data at all → N/A
            if not player_found_in_game(player, category):
                return {
                    "player": player, "stat": prop.get("stat",""),
                    "threshold": threshold, "condition": prop.get("condition",""),
                    "period_results": {}, "won": None, "raw_line": prop.get("raw_line",""),
                }

            def hit(v: float) -> bool:
                if operator == "under":   return v < threshold
                if operator == "exactly": return v == threshold
                return v >= threshold
            _INLINE_MAP = {"Q1":"Q1","Q2":"Q2","Q3":"Q3","Q4":"Q4","1st Half":"1H","2nd Half":"2H"}


            period_results = {}
            _pk = _INLINE_MAP.get(condition)

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
            elif _pk:
                v = get_player_val(player, category, col, _pk)
                period_results[condition] = f"{'✅' if hit(v) else '❌'} {v:.0f}"
                won = hit(v)
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
                "raw_line":       prop.get("raw_line",""),
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
            # Pre-graded (combine/or/each) → use result directly
            if any(r.get('_pre_graded') for r in results):
                pg = next(r for r in results if r.get('_pre_graded'))
                overall_won = None if pg['won'] is None else bool(pg['won'])
            elif any(r['won'] is None for r in results):
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
                "each quarter": "Each Quarter",
                "each half":    "Each Half",
                "game total":   "Game",
            }.get(condition.lower(), condition)
            raw_line = results[0].get("raw_line", f"{threshold:.0f}+ {stat_short}")
            pr = results[0].get("period_results", {})
            if pr:
                parts_pr = []
                for k, v in pr.items():
                    # v is like "✅ 247" or "❌ 14" — extract number and icon
                    v_parts = v.strip().split()
                    icon = v_parts[0] if v_parts else ""
                    num  = v_parts[-1] if len(v_parts) > 1 else v_parts[0]
                    if k == "Game":
                        parts_pr.append(f"{num}")
                    else:
                        parts_pr.append(f"{k}: {num}")
                detail = " | ".join(parts_pr)
                if list(pr.keys()) == ["Game"]:
                    scope_display = f"Game: {parts_pr[0]}"
                else:
                    scope_display = f"{scope_short} | {detail}"
            else:
                scope_display = scope_short
            return {
                "Prop":   raw_line,
                "Data":   scope_display,
                "Result": "✅ Won" if overall_won is True else ("❗ Error" if overall_won is None else "❌ Lost"),
            }

        def safe_grade(group):
            try:
                return grade_prop_group(group)
            except Exception as _ge:
                p = group[0] if group else {}
                return {
                    "Prop":   p.get("raw_line","") or p.get("player","?"),
                    "Data":   "—",
                    "Result": "❗ Error",
                }
        graded += [safe_grade(group) for group in by_line.values()]
        for er in error_rows:
            graded.append({
                "Prop":   er.get("raw_line",""),
                "Data":   "—",
                "Result": "❗ Error",
            })

        def _color(val):
            if isinstance(val, str):
                if val.startswith('✅'): return 'color:#22c55e;font-weight:700'
                if val.startswith('❌'): return 'color:#ef4444;font-weight:700'
                if val.startswith('❗'): return 'color:#f59e0b;font-weight:700'
            return ''

        def _sort(df, col):
            if df.empty or 'Result' not in df.columns: return df
            df = df.copy()
            df['_w'] = df['Result'].apply(lambda x: 0 if 'Won' in str(x) else (1 if 'Error' in str(x) else 2))
            return df.sort_values(['_w', col]).drop(columns=['_w']).reset_index(drop=True)

        # ── Player props table ─────────────────────────────────────────
        gdf = pd.DataFrame(graded) if graded else pd.DataFrame()
        if not gdf.empty:
            gdf = _sort(gdf, 'Prop')
            np_  = len(gdf)
            nw_  = sum(1 for v in gdf['Result'] if 'Won'   in str(v))
            nl_  = sum(1 for v in gdf['Result'] if 'Lost'  in str(v))
            ne_  = sum(1 for v in gdf['Result'] if 'Error' in str(v))
            st.markdown(f'**👤 Player Props** — {np_} props · ✅ {nw_} Won · ❗ {ne_} Error · ❌ {nl_} Lost')
            ps = [c for c in gdf.columns if c not in ('Prop','Data')]
            st.dataframe(gdf.style.map(_color, subset=ps), use_container_width=True, hide_index=True)

        # ── Grade team props ──────────────────────────────────────────────
        import re as _re_t
        TEAM_LINE_RE = _re_t.compile(r'^(each team|both teams|points scored|\d+[+]?\s*(?:tds?|touchdowns?|field goals?|fgs?|scored))', _re_t.I)
        RUSH_TD_T    = _re_t.compile(r'(\d+)\+?\s*rushing tds?', _re_t.I)
        PASS_TD_T    = _re_t.compile(r'(\d+)\+?\s*passing tds?', _re_t.I)
        ANY_TD_T     = _re_t.compile(r'(\d+)\+?\s*tds?', _re_t.I)
        FG_T         = _re_t.compile(r'(\d+)\+?\s*(?:made\s+)?(?:fgs?|field goals?)', _re_t.I)
        COND_T       = [
            (_re_t.compile(r'each quarter|all four quarters', _re_t.I), "each quarter"),
            (_re_t.compile(r'each half', _re_t.I), "each half"),
        ]

        team_graded = []
        scoring_df  = data.get("scoring", pd.DataFrame())
        linescore   = data.get("linescore", pd.DataFrame())

        def _plays_in(period_label):
            if scoring_df is None or scoring_df.empty or "Quarter" not in scoring_df.columns:
                return []
            # scoring_df "Quarter" column uses same labels as linescore: Q1, Q2 etc
            rows = scoring_df[scoring_df["Quarter"] == period_label]
            return rows["Type"].str.lower().tolist() if "Type" in rows.columns else []

        def _pts_in(period_label):
            if linescore is None or linescore.empty or period_label not in linescore.columns:
                return 0
            try:
                return int(pd.to_numeric(linescore[period_label], errors="coerce").fillna(0).sum())
            except Exception:
                return 0

        def _check_reqs(reqs, period_label, each_team):
            plays = _plays_in(period_label) if period_label else (
                scoring_df["Type"].str.lower().tolist() if scoring_df is not None and not scoring_df.empty and "Type" in scoring_df.columns else [])
            pts   = _pts_in(period_label) if period_label else 0
            for req_type, req_n in reqs:
                if req_type == "rushing_td":
                    ok = sum(1 for p in plays if "rush" in p and "touchdown" in p) >= req_n
                elif req_type == "passing_td":
                    ok = sum(1 for p in plays if "pass" in p and "touchdown" in p) >= req_n
                elif req_type == "any_td":
                    ok = sum(1 for p in plays if "touchdown" in p) >= req_n
                elif req_type == "fg":
                    ok = sum(1 for p in plays if "field goal" in p) >= req_n
                else:  # score / points
                    if scoring_df is not None and not scoring_df.empty and "Quarter" in scoring_df.columns:
                        q_rows = scoring_df[scoring_df["Quarter"] == period_label]
                        if each_team and "Team" in scoring_df.columns:
                            # Each team must have scored in this period
                            teams_scored = set(q_rows["Team"].dropna().unique())
                            ok = len(teams_scored) >= 2
                        else:
                            ok = len(q_rows) > 0
                    else:
                        ok = pts > 0
                if not ok:
                    return False
            return True

        _SCORELESS_RE2 = _re_t.compile(r'any quarter.*scoreless|scoreless.*quarter', _re_t.I)
        _ST_FIRST_RE   = _re_t.compile(r'^([\w\s]+?)\s+special teams?\s+to\s+score\s+the\s+first\s+td', _re_t.I)
        _ST_TD_RE      = _re_t.compile(r'^([\w\s]+?)\s+special teams?\s+to\s+score\s+(?:a|the first)?\s*td', _re_t.I)
        _OT_WIN_RE     = _re_t.compile(r'^([\w\s]+?)\s+to\s+beat\s+(?:the\s+)?([\w\s]+?)\s+in\s+overtime', _re_t.I)
        _NO_TD_RE      = _re_t.compile(r'^no\s+touchdown\s+in\s+the\s+game', _re_t.I)
        _FIRST_TD_RE   = _re_t.compile(r'^([\w\s]+?)\s+(?:or\s+([\w\s]+?)\s+)?to\s+score\s+the\s+first\s+td', _re_t.I)
        _TWO_PT_RE     = _re_t.compile(r'^successful\s+2\s*pt\s+conversion', _re_t.I)

        # Special teams TD types from ESPN scoring summary
        # Excludes interception return (defensive) and fumble return (defensive)
        _ST_TYPES = {"punt return touchdown", "kickoff return touchdown",
                     "blocked punt touchdown", "blocked field goal touchdown",
                     "blocked kick touchdown"}
        _ALL_TD_TYPES = {"rushing touchdown", "passing touchdown", "receiving touchdown",
                         "punt return touchdown", "kickoff return touchdown",
                         "fumble return touchdown", "blocked punt touchdown",
                         "blocked field goal touchdown", "interception return touchdown",
                         "touchdown"}
        _TEAM_Q_RE2    = _re_t.compile(r'^([\w\s]+?)\s+to\s+score\s+in\s+all\s+four\s+quarters', _re_t.I)

        # Team name → ESPN abbreviation lookup
        _NFL_TEAMS = {
            "arizona":"ARI","cardinals":"ARI",
            "atlanta":"ATL","falcons":"ATL",
            "baltimore":"BAL","ravens":"BAL",
            "buffalo":"BUF","bills":"BUF",
            "carolina":"CAR","panthers":"CAR",
            "chicago":"CHI","bears":"CHI",
            "cincinnati":"CIN","bengals":"CIN",
            "cleveland":"CLE","browns":"CLE",
            "dallas":"DAL","cowboys":"DAL",
            "denver":"DEN","broncos":"DEN",
            "detroit":"DET","lions":"DET",
            "green bay":"GB","packers":"GB",
            "houston":"HOU","texans":"HOU",
            "indianapolis":"IND","colts":"IND",
            "jacksonville":"JAX","jaguars":"JAX",
            "kansas city":"KC","chiefs":"KC",
            "las vegas":"LV","raiders":"LV",
            "la chargers":"LAC","los angeles chargers":"LAC","chargers":"LAC",
            "la rams":"LAR","los angeles rams":"LAR","rams":"LAR",
            "miami":"MIA","dolphins":"MIA",
            "minnesota":"MIN","vikings":"MIN",
            "new england":"NE","patriots":"NE",
            "new orleans":"NO","saints":"NO",
            "new york giants":"NYG","giants":"NYG",
            "new york jets":"NYJ","jets":"NYJ",
            "philadelphia":"PHI","eagles":"PHI",
            "pittsburgh":"PIT","steelers":"PIT",
            "san francisco":"SF","49ers":"SF","niners":"SF",
            "seattle":"SEA","seahawks":"SEA",
            "tampa bay":"TB","buccaneers":"TB","bucs":"TB",
            "tennessee":"TEN","titans":"TEN",
            "washington":"WSH","commanders":"WSH",
        }

        def _resolve_team(raw):
            """Resolve any team name format to ESPN abbreviation.
            Handles: DAL, Dallas, Cowboys, Dallas Cowboys, DAL Cowboys etc."""
            raw = raw.strip()
            # Try direct abbr first (DAL, DEN)
            if raw.upper() in _game_teams:
                return raw.upper()
            low = raw.lower()
            # Try exact lookup (catches "dallas cowboys", "dallas", "cowboys" etc)
            if low in _NFL_TEAMS:
                return _NFL_TEAMS[low]
            # Try each word — catches "Cowboys", "Dallas", "Patriots"
            for word in low.split():
                if word in _NFL_TEAMS:
                    return _NFL_TEAMS[word]
            # Try any word stripped of trailing s ("cowboys" → "cowboy" not needed
            # since we have the full nickname in lookup)
            # Partial match against game teams as last resort
            for abbr in _game_teams:
                if abbr.lower() in low or low in abbr.lower():
                    return abbr
            return raw.upper()

        def _any_score_in_q(q_label):
            """Return True if any scoring play occurred in this quarter."""
            sdf = data.get("scoring", pd.DataFrame())
            if sdf is None or sdf.empty or "Quarter" not in sdf.columns:
                return False
            return (sdf["Quarter"] == q_label).any()

        def _team_scored_in_q(team_abbr, q_label):
            """Return True if specific team had a scoring play in this quarter."""
            sdf = data.get("scoring", pd.DataFrame())
            if sdf is None or sdf.empty or "Quarter" not in sdf.columns:
                return False
            rows = sdf[sdf["Quarter"] == q_label]
            if "Team" not in rows.columns: return rows.shape[0] > 0
            return rows["Team"].str.upper().eq(team_abbr.upper()).any()

        for i, line in enumerate(clean_lines):
            # ── No Touchdown in Game ──────────────────────────────────────────
            if _NO_TD_RE.match(line):
                _sdf_n = data.get("scoring", pd.DataFrame())
                _td_types = _ALL_TD_TYPES
                if _sdf_n is not None and not _sdf_n.empty and "Type" in _sdf_n.columns:
                    _has_td = _sdf_n["Type"].str.lower().isin(_td_types).any()
                else:
                    _has_td = False
                _td_count = _sdf_n["Type"].str.lower().isin(_td_types).sum() if _sdf_n is not None and not _sdf_n.empty and "Type" in _sdf_n.columns else 0
                won = not _has_td
                team_graded.append({"Prop": line, "Data": f"TDs: {_td_count}",
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            # ── Successful 2pt Conversion ──────────────────────────────────────
            if _TWO_PT_RE.match(line):
                _sdf_2 = data.get("scoring", pd.DataFrame())
                if _sdf_2 is not None and not _sdf_2.empty and "Type" in _sdf_2.columns:
                    # Only successful 2pt conversions appear in ESPN's scoringPlays
                    # Check Type field — exclude rows where Description says "Failed"
                    _2pt_mask = _sdf_2["Type"].str.lower().str.contains("two.point|2.point", na=False)
                    if "Description" in _sdf_2.columns:
                        _2pt_mask = _2pt_mask & ~_sdf_2["Description"].str.lower().str.contains("failed", na=False)
                    _has_2pt = _2pt_mask.any()
                else:
                    _has_2pt = False
                if _has_2pt and _sdf_2 is not None and not _sdf_2.empty:
                    _2pt_rows = _sdf_2[
                        _sdf_2["Type"].str.lower().str.contains("two.point|2.point", na=False) &
                        ~_sdf_2["Description"].str.lower().str.contains("failed", na=False)
                    ] if "Description" in _sdf_2.columns else pd.DataFrame()
                    _2pt_data = _2pt_rows.iloc[0]["Description"][:60] if not _2pt_rows.empty else "Successful"
                else:
                    _2pt_data = "No 2pt Conversion"
                team_graded.append({"Prop": line, "Data": _2pt_data,
                    "Result": "✅ Won" if _has_2pt else "❌ Lost"})
                continue

            # ── Overtime Win ───────────────────────────────────────────────────
            _ot_m = _OT_WIN_RE.match(line)
            if _ot_m:
                _winner_raw = _ot_m.group(1).strip()
                _winner_abbr = _resolve_team(_winner_raw)
                _sdf_ot = data.get("scoring", pd.DataFrame())
                # Check if any scoring play in OT period
                _has_ot = False
                _ot_winner = None
                if _sdf_ot is not None and not _sdf_ot.empty and "Quarter" in _sdf_ot.columns:
                    _ot_plays = _sdf_ot[_sdf_ot["Quarter"].str.startswith("OT", na=False)]
                    _has_ot = not _ot_plays.empty
                    if _has_ot:
                        # Winner is team with higher score in last OT play
                        _last = _ot_plays.iloc[-1]
                        _aw = int(pd.to_numeric(_last.get("Away Score", 0), errors="coerce") or 0)
                        _hw = int(pd.to_numeric(_last.get("Home Score", 0), errors="coerce") or 0)
                        # Determine home/away from linescore
                        _ls_ot = data.get("linescore", pd.DataFrame())
                        if not _ls_ot.empty and "Team" in _ls_ot.columns:
                            _away_t = _ls_ot.iloc[0]["Team"] if len(_ls_ot) > 0 else ""
                            _home_t = _ls_ot.iloc[1]["Team"] if len(_ls_ot) > 1 else ""
                            _ot_winner = _away_t if _aw > _hw else _home_t
                # If no OT, get regular game winner from final scores
                if not _has_ot and not _sdf_ot.empty:
                    _last_all = _sdf_ot.iloc[-1]
                    _aw_f = int(pd.to_numeric(_last_all.get("Away Score", 0), errors="coerce") or 0)
                    _hw_f = int(pd.to_numeric(_last_all.get("Home Score", 0), errors="coerce") or 0)
                    _ls_ot2 = data.get("linescore", pd.DataFrame())
                    if not _ls_ot2.empty and "Team" in _ls_ot2.columns:
                        _away_t2 = _ls_ot2.iloc[0]["Team"] if len(_ls_ot2) > 0 else ""
                        _home_t2 = _ls_ot2.iloc[1]["Team"] if len(_ls_ot2) > 1 else ""
                        _ot_winner = _away_t2 if _aw_f > _hw_f else _home_t2
                won = _has_ot and (_ot_winner and _ot_winner.upper() == _winner_abbr)
                _data_ot = f"OT: {'Yes' if _has_ot else 'No'} | Winner: {_ot_winner or '—'}"
                team_graded.append({"Prop": line, "Data": _data_ot,
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            # ── Special Teams First TD ─────────────────────────────────────────
            _stf_m = _ST_FIRST_RE.match(line)
            if _stf_m:
                _st_team = _resolve_team(_stf_m.group(1).strip())
                _sdf_stf = data.get("scoring", pd.DataFrame())
                won = False
                _first_desc = "No TDs"
                if _sdf_stf is not None and not _sdf_stf.empty and "Type" in _sdf_stf.columns:
                    _td_rows = _sdf_stf[_sdf_stf["Type"].str.lower().isin(_ALL_TD_TYPES)]
                    if not _td_rows.empty:
                        _first_td = _td_rows.iloc[0]
                        _first_desc = f"{_first_td.get('Team','')} {_first_td.get('Type','')}"
                        _is_st = _first_td["Type"].lower() in _ST_TYPES
                        _right_team = _first_td.get("Team","").upper() == _st_team
                        won = _is_st and _right_team
                team_graded.append({"Prop": line, "Data": f"First TD: {_first_desc}",
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            # ── Special Teams any TD ───────────────────────────────────────────
            _st_m = _ST_TD_RE.match(line)
            if _st_m:
                _st_team2 = _resolve_team(_st_m.group(1).strip())
                _sdf_st = data.get("scoring", pd.DataFrame())
                won = False
                _st_detail = "No ST TD"
                if _sdf_st is not None and not _sdf_st.empty and "Type" in _sdf_st.columns:
                    _st_plays = _sdf_st[
                        (_sdf_st["Type"].str.lower().isin(_ST_TYPES)) &
                        (_sdf_st["Team"].str.upper() == _st_team2)
                    ] if "Team" in _sdf_st.columns else pd.DataFrame()
                    won = not _st_plays.empty
                    _st_detail = " | ".join(_st_plays["Type"].tolist()) if won else f"No {_st_team2} Special Teams TD"
                team_graded.append({"Prop": line, "Data": _st_detail,
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            # ── First TD scorer (player) → goes to player props graded ──────────
            _ftd_m = _FIRST_TD_RE.match(line)
            if _ftd_m and "special teams" not in line.lower():
                _p1 = _ftd_m.group(1).strip()
                _p2 = _ftd_m.group(2).strip() if _ftd_m.group(2) else None
                _players_ftd = [p for p in [_p1, _p2] if p]
                _sdf_ftd = data.get("scoring", pd.DataFrame())
                won = None
                _ftd_detail = "No TDs"
                if _sdf_ftd is not None and not _sdf_ftd.empty and "Type" in _sdf_ftd.columns:
                    _td_rows2 = _sdf_ftd[_sdf_ftd["Type"].str.lower().isin(_ALL_TD_TYPES)]
                    if not _td_rows2.empty:
                        _first_desc2 = _td_rows2.iloc[0].get("Description", "")
                        _ftd_detail = _first_desc2[:60]
                        won = any(
                            p.split()[-1].lower() in _first_desc2.lower()
                            for p in _players_ftd
                        )
                _ftd_res = "✅ Won" if won is True else ("❗ Error" if won is None else "❌ Lost")
                graded.append({"Prop": line, "Data": f"First TD: {_ftd_detail}", "Result": _ftd_res})
                continue

            if _SCORELESS_RE2.search(line):
                _sdf_s = data.get("scoring", pd.DataFrame())
                def _q_totals(sdf):
                    """Derive per-quarter points (both teams) from cumulative scoring_df."""
                    if sdf is None or sdf.empty: return {}
                    lpq = sdf.groupby("Quarter", sort=False).last().reset_index()
                    prev_a, prev_h, out = 0, 0, {}
                    for q in ["Q1","Q2","Q3","Q4"]:
                        r = lpq[lpq["Quarter"] == q]
                        if r.empty: out[q] = 0; continue
                        a = int(pd.to_numeric(r.iloc[0]["Away Score"], errors="coerce") or 0)
                        h = int(pd.to_numeric(r.iloc[0]["Home Score"], errors="coerce") or 0)
                        out[q] = (a - prev_a) + (h - prev_h)
                        prev_a, prev_h = a, h
                    return out
                _qtot = _q_totals(_sdf_s)
                q_had_score = {q: _any_score_in_q(q) for q in ["Q1","Q2","Q3","Q4"]}
                won = any(not v for v in q_had_score.values())
                _score_detail = ' | '.join(f'{q}: {_qtot.get(q, 0)}' for q in ["Q1","Q2","Q3","Q4"])
                team_graded.append({'Prop': line, 'Data': _score_detail,
                    'Result': '✅ Won' if won else '❌ Lost'})
                continue
            _tq_m = _TEAM_Q_RE2.match(line)
            if _tq_m:
                team_abbr = _resolve_team(_tq_m.group(1).strip())
                q_had_score = {q: _team_scored_in_q(team_abbr, q) for q in ['Q1','Q2','Q3','Q4']}
                won = all(q_had_score.values())
                _sdf_t = data.get("scoring", pd.DataFrame())
                def _team_q_pts_from_sdf(t, sdf):
                    """Derive per-quarter points for one team from cumulative scoring_df."""
                    if sdf is None or sdf.empty: return {}
                    # Determine Away or Home by seeing which score column moves with this team
                    t_rows = sdf[sdf["Team"].str.upper() == t.upper()] if "Team" in sdf.columns else pd.DataFrame()
                    if t_rows.empty: return {q: 0 for q in ["Q1","Q2","Q3","Q4"]}
                    # Check first scoring play of this team
                    fr = t_rows.iloc[0]
                    # Get score before this play (prior row or 0)
                    idx0 = t_rows.index[0]
                    prev = sdf.loc[:idx0-1].iloc[-1] if idx0 > 0 else None
                    prev_a = int(pd.to_numeric(prev["Away Score"], errors="coerce") or 0) if prev is not None else 0
                    prev_h = int(pd.to_numeric(prev["Home Score"], errors="coerce") or 0) if prev is not None else 0
                    delta_a = int(pd.to_numeric(fr["Away Score"], errors="coerce") or 0) - prev_a
                    delta_h = int(pd.to_numeric(fr["Home Score"], errors="coerce") or 0) - prev_h
                    col = "Away Score" if delta_a > 0 else "Home Score"
                    # Now derive per-quarter from cumulative col
                    lpq = sdf.groupby("Quarter", sort=False).last().reset_index()
                    prev_val, out = 0, {}
                    for q in ["Q1","Q2","Q3","Q4"]:
                        r = lpq[lpq["Quarter"] == q]
                        if r.empty: out[q] = 0; continue
                        val = int(pd.to_numeric(r.iloc[0][col], errors="coerce") or 0)
                        out[q] = val - prev_val
                        prev_val = val
                    return out
                _tq_scores = _team_q_pts_from_sdf(team_abbr, _sdf_t)
                _tq_detail = ' | '.join(f'{q}: {_tq_scores.get(q, 0)}' for q in ["Q1","Q2","Q3","Q4"])
                team_graded.append({'Prop': line, 'Data': _tq_detail,
                    'Result': '✅ Won' if won else '❌ Lost'})
                continue
            if not TEAM_LINE_RE.match(line):
                continue
            is_each = "each team" in line.lower() or "both teams" in line.lower()
            cond    = next((lbl for pat,lbl in COND_T if pat.search(line)), "each quarter")
            rtd = RUSH_TD_T.search(line)
            ptd = PASS_TD_T.search(line)
            atd_m = _re_t.search(r'(\d+)\+?\s*tds?', line, _re_t.I)
            atd = atd_m if atd_m and not rtd and not ptd else None
            fg  = FG_T.search(line)
            reqs = []
            if rtd: reqs.append(("rushing_td", int(rtd.group(1))))
            if ptd: reqs.append(("passing_td", int(ptd.group(1))))
            if atd: reqs.append(("any_td", int(atd.group(1))))
            if fg:  reqs.append(("fg", int(fg.group(1))))
            if not reqs: reqs.append(("score", 1))
            if cond == "each quarter":
                periods = ["Q1","Q2","Q3","Q4"]
            elif cond == "each half":
                periods = ["1H","2H"]
            else:
                periods = ["game total"]  # whole game, no period split
            if periods == ["game total"]:
                won = _check_reqs(reqs, None, is_each)
            else:
                won = all(_check_reqs(reqs, p, is_each) for p in periods)

            # Build Data column from scoring_df directly
            plbl = {"Q1":"Q1","Q2":"Q2","Q3":"Q3","Q4":"Q4","1H":"1st Half","2H":"2nd Half"}
            sorted_teams = sorted(_game_teams)
            req_lbls = {"rushing_td":"Rush TD","passing_td":"Pass TD","any_td":"TD","fg":"FG","score":"Pts"}

            def _sdf_types(team=None, period=None):
                """Get Type list from scoring_df filtered by team and/or period."""
                if scoring_df is None or scoring_df.empty: return []
                df = scoring_df.copy()
                if period and "Quarter" in df.columns:
                    df = df[df["Quarter"] == period]
                if team and "Team" in df.columns:
                    df = df[df["Team"].str.upper() == team.upper()]
                return df["Type"].str.lower().tolist() if "Type" in df.columns else []

            def _count_from_types(types_list, req_type):
                if req_type == "rushing_td": return sum(1 for t in types_list if "rush" in t and "touchdown" in t)
                if req_type == "passing_td": return sum(1 for t in types_list if ("pass" in t or "receiving" in t) and "touchdown" in t)
                if req_type == "any_td":     return sum(1 for t in types_list if "touchdown" in t)
                if req_type == "fg":         return sum(1 for t in types_list if "field goal" in t and "good" in t)
                return 0

            def _pts_from_types(types_list):
                """Estimate points from scoring play types."""
                total = 0
                for t in types_list:
                    if "touchdown" in t: total += 6
                    elif "field goal" in t and "good" in t: total += 3
                    elif "extra point" in t: total += 1
                    elif "two-point" in t or "two point" in t: total += 2
                return total

            if is_each and reqs[0][0] == "score":
                # Each Team to Score in All Four Quarters
                team_data_parts = []
                for team in sorted_teams:
                    q_parts = " | ".join(
                        f"{plbl.get(p,p)}: {_pts_from_types(_sdf_types(team=team, period=p))}"
                        for p in periods)
                    team_data_parts.append(f"{team} {q_parts}")
                data_str = " | ".join(team_data_parts)

            elif is_each:
                # Each Team to Score 1+ Rush TD & 1+ Pass TD [in Each Half/Quarter]
                team_data_parts = []
                for team in sorted_teams:
                    period_parts = []
                    for p in periods:
                        types_t = _sdf_types(team=team, period=p)
                        req_strs_t = [f"{req_lbls.get(rt,rt)}: {_count_from_types(types_t, rt)}" for rt, rn in reqs]
                        period_parts.append(f"{plbl.get(p,p)} {' & '.join(req_strs_t)}")
                    team_data_parts.append(f"{team} {' | '.join(period_parts)}")
                data_str = " | ".join(team_data_parts)

            elif len(periods) == 1 and periods[0] == "game total":
                # Game-level each-team prop (no period) — show per-team totals
                team_data_parts = []
                for team in sorted_teams:
                    types_t = _sdf_types(team=team)
                    req_strs_t = [f"{req_lbls.get(rt,rt)}: {_count_from_types(types_t, rt)}" for rt, rn in reqs]
                    team_data_parts.append(f"{team} {' & '.join(req_strs_t)}")
                data_str = " | ".join(team_data_parts)

            else:
                # Non-each-team props — combined totals per period
                period_parts = []
                for p in periods:
                    types_p = _sdf_types(period=p)
                    if reqs[0][0] == "score":
                        req_strs_p = [f"Pts: {_pts_from_types(types_p)}"]
                    else:
                        req_strs_p = [f"{req_lbls.get(rt,rt)}: {_count_from_types(types_p, rt)}" for rt, rn in reqs]
                    period_parts.append(f"{plbl.get(p,p)}: {' & '.join(req_strs_p)}")
                data_str = " | ".join(period_parts)

            team_graded.append({"Prop": clean_lines[i], "Data": data_str,
                                 "Result": "✅ Won" if won else "❌ Lost"})

        # Fallback if nothing graded
        if not graded and not team_graded:
            st.info('No props could be parsed. Check your input format.')

        # ── Team / game props table ────────────────────────────────────────────
        if team_graded:
            tdf = pd.DataFrame(team_graded)
            tdf["_w"] = tdf["Result"].apply(lambda x: 0 if "Won" in str(x) else (1 if "Error" in str(x) else 2))
            tdf = tdf.sort_values(["_w","Prop"]).drop(columns=["_w"], errors="ignore").reset_index(drop=True)
            ntw = sum(1 for v in tdf["Result"] if "Won" in str(v))
            nte = sum(1 for v in tdf["Result"] if "Error" in str(v))
            ntl = len(tdf) - ntw - nte
            st.markdown(f"**🏟 Team / Game Props** — {len(tdf)} props · ✅ {ntw} Won · ❗ {nte} Error · ❌ {ntl} Lost")
            ts = [c for c in tdf.columns if c not in ("Prop","Data")]
            def _color_t(val):
                if isinstance(val, str):
                    if val.startswith("✅"): return "color:#22c55e;font-weight:700"
                    if val.startswith("❌"): return "color:#ef4444;font-weight:700"
                    if val.startswith("❗"): return "color:#f59e0b;font-weight:700"
                return ""
            st.dataframe(tdf.style.map(_color_t, subset=ts), use_container_width=True, hide_index=True)
