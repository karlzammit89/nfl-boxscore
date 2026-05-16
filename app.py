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
    get_reconciliation_status,
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
    "recon_game_ids":      "",
    "recon_results":       None,
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

_hc1, _hc2 = st.columns([8, 1.5])
with _hc1:
    st.markdown("## 🏈 NFL Box Scores")
with _hc2:
    st.markdown("<div style='margin-top:14px'>", unsafe_allow_html=True)
    if st.button("🔍 Reconcile", use_container_width=True, key="btn_reconcile_nav"):
        st.session_state.view = "reconcile"
        st.rerun()
st.divider()

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60*60*24*30, show_spinner=False)  # 30-day cache per athlete
def _cached_athlete_name(athlete_id: str, season: str) -> str:
    """Resolve ESPN athlete ID to displayName, cached 30 days."""
    from nfl.api import get_athlete_displayname
    return get_athlete_displayname(athlete_id, season)


def _patch_athlete_resolver():
    """
    Monkey-patch nfl.api.get_athlete_displayname to use Streamlit's 30-day cache.
    Called once at startup so all stats computations benefit from caching.
    """
    import nfl.api as _nfl_api
    _nfl_api.get_athlete_displayname = _cached_athlete_name


_patch_athlete_resolver()


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

    # Logo map for use throughout this view
    _logo_map = {}
    try:
        _logo_map[game["away"]["abbr"].upper()] = game["away"].get("logo","")
        _logo_map[game["home"]["abbr"].upper()] = game["home"].get("logo","")
    except Exception:
        pass

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


    # Linescore box score
    with st.spinner("Loading box score…"):
        data = load_all_stats(game_id)
    pbp       = data["pbp"]
    by_period = data.get("by_period", {})

    # ── DEBUG: Fix confirmation panel ─────────────────────────────────────────
    with st.expander("🔍 DEBUG — Fix confirmation (C1–C6)", expanded=False):
        import json as _dj, re as _dre, urllib.request as _dur

        def _fetch(url):
            _req = _dur.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
            with _dur.urlopen(_req, timeout=15) as _r:
                return _dj.loads(_r.read())

        _BASE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
        _ID_RE2 = _dre.compile(r"/athletes/([0-9]+)")
        _TM_RE2 = _dre.compile(r"/teams/([0-9]+)")

        try:
            _raw = _fetch(_BASE + f"/events/{game_id}/competitions/{game_id}/plays?limit=400")
            _plays = _raw.get("items", [])
            _play_count = _raw.get("count", 0)
        except Exception as _e:
            st.error(f"Could not fetch plays: {_e}")
            _plays = []; _play_count = 0

        import pandas as _dpd
        from nfl.api import get_game_summary as _dgs2
        from nfl.stats import get_passing_stats as _dps2

        _sum2 = _dgs2(game_id) or {}
        _box  = _sum2.get("boxscore", {})

        # Build game roster: player name → team abbr
        _roster_names = set()
        _roster_by_name = {}  # last_name_lower → full display name
        for _tb in _box.get("players", []):
            _t_abbr = _tb.get("team", {}).get("abbreviation", "")
            for _cat in _tb.get("statistics", []):
                for _athl in _cat.get("athletes", []):
                    _pname = _athl.get("athlete", {}).get("displayName", "")
                    if _pname:
                        _roster_names.add(_pname)
                        _roster_by_name[_pname.split()[-1].lower()] = _pname

        # Build team ID → abbreviation map
        _tid_abbr = {}
        for _tb in _sum2.get("boxscore", {}).get("teams", []):
            _tid = str(_tb.get("team", {}).get("id", ""))
            _tab = _tb.get("team", {}).get("abbreviation", "")
            if _tid and _tab: _tid_abbr[_tid] = _tab

        def _team_from_ref(ref):
            _m = _TM_RE2.search(ref or "")
            return _tid_abbr.get(_m.group(1), "") if _m else ""

        # ── C1: RC-NAME — show athlete IDs that resolve to wrong names ────────
        st.markdown("### C1 — RC-NAME: Athlete ID → resolved name vs game roster")
        st.caption(
            "For every participant in this game's plays, shows the athlete_id, "
            "the name returned by the cache, and whether that name appears in the "
            "ESPN boxscore roster. ❌ = cache returning wrong/stale name."
        )
        _name_check = {}  # aid → (resolved_name, in_roster)
        for _pl in _plays:
            for _pt in _pl.get("participants", []):
                _ref = _pt.get("athlete", {}).get("$ref", "")
                _aid = (_ID_RE2.search(_ref) or type("",(),{"group":lambda s,n:""})()).group(1)
                if _aid and _aid not in _name_check:
                    from nfl.api import get_athlete_displayname as _gadn
                    _rname = _gadn(_aid, "2025") or _gadn(_aid, "") or ""
                    _in_roster = _rname in _roster_names if _rname else False
                    _name_check[_aid] = (_rname, _in_roster)

        _nc_rows = [{"athlete_id": aid, "resolved_name": name,
                     "in_roster?": "✅ YES" if ok else "❌ NO — stale/wrong",
                     "role": next((p.get("type","") for pl in _plays
                                   for p in pl.get("participants",[])
                                   if (_ID_RE2.search(p.get("athlete",{}).get("$ref","")) or
                                       type("",(),{"group":lambda s,n:""})()).group(1)==aid), "?")}
                    for aid, (name, ok) in sorted(_name_check.items())]
        _wrong = [r for r in _nc_rows if "NO" in r["in_roster?"]]
        st.markdown(f"**Total unique athlete IDs: {len(_nc_rows)} | Wrong names: {len(_wrong)}**")
        if _wrong:
            st.dataframe(_dpd.DataFrame(_wrong), use_container_width=True, hide_index=True)
        with st.expander("Show all resolved names"):
            st.dataframe(_dpd.DataFrame(_nc_rows), use_container_width=True, hide_index=True)

        st.divider()

        # ── C2: RC-TRICK — show _official_passers set and psr_name for flagged plays ─
        st.markdown("### C2 — RC-TRICK: What does _official_passers contain?")
        st.caption(
            "Shows the official passer last-name set built from ESPN's boxscore, "
            "and for every play where a non-QB passer is suspected, shows the "
            "resolved psr_name and whether it appears in the set."
        )
        try:
            _off_pass = _dps2(game_id)
            if _off_pass is not None and not _off_pass.empty and "Player" in _off_pass.columns:
                _official_passers = set(_off_pass["Player"].str.split().str[-1].str.lower())
                st.markdown(f"**_official_passers set ({len(_official_passers)} names):**")
                st.code(str(sorted(_official_passers)))

                # Find any play where passer role is present but name not in official passers
                _trick_rows = []
                for _pl in _plays:
                    for _pt in _pl.get("participants", []):
                        if _pt.get("type") != "passer": continue
                        _ref = _pt.get("athlete", {}).get("$ref", "")
                        _aid = (_ID_RE2.search(_ref) or type("",(),{"group":lambda s,n:""})()).group(1)
                        _rname = _name_check.get(_aid, ("?", False))[0]
                        _last = _rname.split(".")[-1].strip().lower() if "." in _rname else _rname.split()[-1].lower() if _rname else ""
                        _in_set = _last in _official_passers
                        _ptype = (_pl.get("type",{}).get("text","") or "").lower()
                        if not _in_set:
                            _trick_rows.append({
                                "play_type": _ptype,
                                "psr_name":  _rname,
                                "psr_last":  _last,
                                "in_official_passers?": "❌ NOT IN SET",
                                "athlete_id": _aid,
                                "text": str(_pl.get("text",""))[:80],
                            })
                if _trick_rows:
                    st.markdown("**Plays where passer role present but name NOT in official_passers:**")
                    st.dataframe(_dpd.DataFrame(_trick_rows), use_container_width=True, hide_index=True)
                else:
                    st.success("All passer-role plays match official passers — RC-TRICK filter works correctly.")
            else:
                st.warning("Official passing stats empty — _official_passers would be empty set → RC-TRICK check skipped for all plays.")
        except Exception as _e2:
            st.error(f"C2 error: {_e2}")

        st.divider()

        # ── C3: RC-INT — show INT plays and whether passer role is present ────
        st.markdown("### C3 — RC-INT: Interception plays — passer role present?")
        st.caption(
            "For every 'pass interception return' play, shows whether ESPN "
            "attached a 'passer' participant role. If NO → the text-parse fallback "
            "fires and the result goes to a name-string key instead of athlete_id. "
            "Also shows what the text-parse regex would extract."
        )
        _int_plays = [_pl for _pl in _plays
                      if (_pl.get("type",{}).get("text","") or "").lower() == "pass interception return"]
        if _int_plays:
            _int_rows = []
            for _pl in _int_plays:
                _roles  = {_pt.get("type","") for _pt in _pl.get("participants",[])}
                _psr_present = "passer" in _roles
                _txt = str(_pl.get("text",""))
                _int_m = _dre.search(
                    r"(?:\([^)]*\)\s*)?([A-Z]\.[A-Za-z\-']+(?:\s+(?:Jr|Sr|II|III|IV)\.?)?)\s+pass",
                    _txt)
                _parsed_name = _int_m.group(1) if _int_m else "❌ REGEX MISS"
                _per = (_pl.get("period") or {}).get("number","?")
                # If psr IS present, get the athlete_id
                _psr_id = ""
                for _pt in _pl.get("participants",[]):
                    if _pt.get("type") == "passer":
                        _ref = _pt.get("athlete",{}).get("$ref","")
                        _psr_id = (_ID_RE2.search(_ref) or type("",(),{"group":lambda s,n:""})()).group(1)
                _int_rows.append({
                    "Q": f"Q{_per}",
                    "passer role?": "✅ YES → uses athlete_id" if _psr_present else "❌ NO → uses parsed name",
                    "psr_athlete_id": _psr_id or "N/A",
                    "text_parse_result": _parsed_name,
                    "key_mismatch?": "⚠️ MISMATCH — name key ≠ id key" if not _psr_present and _parsed_name != "❌ REGEX MISS" else ("✅ OK" if _psr_present else "❌ MISS"),
                    "text": _txt[:90],
                })
            st.dataframe(_dpd.DataFrame(_int_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No 'pass interception return' plays found in this game.")

        st.divider()

        # ── C4: RC-OFFPEN — show isPenalty plays and pos_team resolution ──────
        st.markdown("### C4 — RC-OFFPEN: isPenalty plays — pos_team resolution")
        st.caption(
            "For every isPenalty=True play with offensive roles, shows: "
            "the pos_team from play.$ref (primary), pos_team from participant.$ref (fallback), "
            "the extracted penalty team from text, and whether they match. "
            "'❌ EMPTY' = _pos_team cannot be determined → play NOT skipped regardless of penalty."
        )
        _pen_rows = []
        for _pl in _plays:
            if not _pl.get("isPenalty"): continue
            _roles = {_pt.get("type","") for _pt in _pl.get("participants",[])}
            if not (_roles & {"passer","receiver","rusher"}): continue
            if _pl.get("scoringPlay"): continue

            _ptype = (_pl.get("type",{}).get("text","") or "").lower()
            _txt = (str(_pl.get("text","")) or "").upper()
            _yds = _pl.get("statYardage",0)
            _per = (_pl.get("period") or {}).get("number","?")

            # Primary pos_team from play
            _play_team_ref = _pl.get("team",{}).get("$ref","")
            _pos_primary = _team_from_ref(_play_team_ref)

            # Fallback: participant team ref
            _pos_fallback = ""
            for _pt in _pl.get("participants",[]):
                if _pt.get("type") in ("passer","rusher","receiver"):
                    _pt_ref = _pt.get("athlete",{}).get("$ref","")
                    _pt_tm = _TM_RE2.search(_pt_ref)
                    if _pt_tm:
                        _pos_fallback = _tid_abbr.get(_pt_tm.group(1),"")
                        if _pos_fallback: break

            _pos_team_used = _pos_primary or _pos_fallback

            # Penalty team from text
            _pen_m = _dre.search(r"PENALTY ON ([A-Z]{2,3})[^A-Z]", _txt)
            _pen_team = _pen_m.group(1) if _pen_m else "❌ REGEX MISS"

            _match = _pen_team == _pos_team_used if (_pos_team_used and _pen_team != "❌ REGEX MISS") else None
            _would_skip = "✅ YES — skipped" if _match else ("❌ NO — NOT skipped" if _match is False else "⚠️ pos_team empty — NOT skipped")

            _pen_rows.append({
                "Q": f"Q{_per}",
                "play_type": _ptype,
                "yds": _yds,
                "pos_primary": _pos_primary or "❌ EMPTY",
                "pos_fallback": _pos_fallback or "❌ EMPTY",
                "pos_team_used": _pos_team_used or "❌ EMPTY",
                "penalty_team": _pen_team,
                "would_skip?": _would_skip,
                "text": str(_pl.get("text",""))[:80],
            })

        if _pen_rows:
            st.dataframe(_dpd.DataFrame(_pen_rows), use_container_width=True, hide_index=True)
            _not_skipped = [r for r in _pen_rows if "NOT skipped" in r["would_skip?"]]
            _empty = [r for r in _pen_rows if "empty" in r["would_skip?"].lower()]
            st.markdown(f"**Not skipped (offensive): {len(_not_skipped)} | pos_team empty: {len(_empty)}**")
        else:
            st.success("No isPenalty=True offensive plays in this game.")

        st.divider()

        # ── C5: RC-CAR — find the ONE missing carry per player ────────────────
        st.markdown("### C5 — RC-CAR: Find the missing carry")
        st.caption(
            "Shows ALL plays with a rusher participant role, grouped by player. "
            "Enter a player's last name to filter. "
            "Compare count here to official CAR — the difference reveals the missing play."
        )
        _c5_player = st.text_input("Filter by rusher last name (e.g. Stroud, Allen, Williams)", key="c5_player")
        _rush_plays = []
        for _pl in _plays:
            for _pt in _pl.get("participants",[]):
                if _pt.get("type") != "rusher": continue
                _ref = _pt.get("athlete",{}).get("$ref","")
                _aid = (_ID_RE2.search(_ref) or type("",(),{"group":lambda s,n:""})()).group(1)
                _rname = _name_check.get(_aid,("?",False))[0]
                if _c5_player and _c5_player.lower() not in _rname.lower(): continue
                _ptype = (_pl.get("type",{}).get("text","") or "").lower()
                _yds = _pl.get("statYardage",0)
                _per = (_pl.get("period") or {}).get("number","?")
                _is_pen  = _pl.get("isPenalty",False)
                _txt = str(_pl.get("text",""))
                # What would our code do with this play?
                _in_skip = _ptype in {
                    "end period","end of half","end of game","end of regulation",
                    "timeout","coin toss","kickoff","punt","penalty","uncategorized",
                    "field goal good","field goal missed","extra point good","safety",
                    "kickoff return touchdown","punt return touchdown","placeholder",""
                }
                _rush_plays.append({
                    "Q": f"Q{_per}",
                    "rusher": _rname,
                    "athlete_id": _aid,
                    "play_type": _ptype,
                    "yds": _yds,
                    "isPenalty": _is_pen,
                    "in_SKIP_TYPES?": "⚠️ SKIPPED" if _in_skip else "✅ counted",
                    "would_count?": "✅ yes" if not _in_skip and _ptype in {"rush","scramble","rushing touchdown"} else
                                    ("✅ catch-all" if not _in_skip else "❌ SKIPPED"),
                    "text": _txt[:80],
                })
        if _rush_plays:
            # Summary by player
            by_rusher = {}
            for row in _rush_plays:
                n = row["rusher"]
                if n not in by_rusher: by_rusher[n] = {"counted":0,"skipped":0,"catch_all":0}
                if "SKIPPED" in row["in_SKIP_TYPES?"]: by_rusher[n]["skipped"]+=1
                elif "catch-all" in row["would_count?"]: by_rusher[n]["catch_all"]+=1
                else: by_rusher[n]["counted"]+=1
            _sum_rows = [{"rusher":n,"our_CAR_count":d["counted"],"catch_all":d["catch_all"],
                          "skipped":d["skipped"],"total_rusher_plays":d["counted"]+d["catch_all"]+d["skipped"]}
                         for n,d in sorted(by_rusher.items())]
            st.markdown("**CAR count summary per rusher:**")
            st.dataframe(_dpd.DataFrame(_sum_rows), use_container_width=True, hide_index=True)
            st.markdown("**All rusher-role plays:**")
            st.dataframe(_dpd.DataFrame(_rush_plays), use_container_width=True, hide_index=True)
        else:
            st.info("No rusher-role plays found (or no match for filter).")

        st.divider()

        # ── C6: RC-NEG — show all receiving plays with negative yards ─────────
        st.markdown("### C6 — RC-NEG: Negative-yard receiving plays")
        st.caption(
            "Shows all receiving plays where statYardage < 0. "
            "Key columns: isPenalty flag, scoringPlay flag, and whether "
            "the current guard (isPenalty=True AND yds<0) would skip it."
        )
        _neg_recv = []
        for _pl in _plays:
            _yds = _pl.get("statYardage",0)
            if _yds >= 0: continue
            _roles = {_pt.get("type","") for _pt in _pl.get("participants",[])}
            if "receiver" not in _roles: continue
            _per = (_pl.get("period") or {}).get("number","?")
            _is_pen   = _pl.get("isPenalty",False)
            _is_score = _pl.get("scoringPlay",False)
            _ptype = (_pl.get("type",{}).get("text","") or "").lower()
            # Receiver name
            _rcv_name = ""
            for _pt in _pl.get("participants",[]):
                if _pt.get("type") == "receiver":
                    _ref2 = _pt.get("athlete",{}).get("$ref","")
                    _aid2 = (_ID_RE2.search(_ref2) or type("",(),{"group":lambda s,n:""})()).group(1)
                    _rcv_name = _name_check.get(_aid2,("?",False))[0]
            _current_guard_skips = _is_pen and not _is_score
            _extended_guard_skips = _yds < -10 and not _is_score
            _neg_recv.append({
                "Q": f"Q{_per}",
                "receiver": _rcv_name,
                "play_type": _ptype,
                "yds": _yds,
                "isPenalty": _is_pen,
                "scoringPlay": _is_score,
                "current_guard_skips?": "✅ SKIPPED" if _current_guard_skips else "❌ NOT skipped",
                "extended_guard_skips?": "✅ SKIPPED" if _extended_guard_skips else "❌ NOT skipped",
                "text": str(_pl.get("text",""))[:80],
            })
        if _neg_recv:
            st.dataframe(_dpd.DataFrame(_neg_recv), use_container_width=True, hide_index=True)
            _still_counted = [r for r in _neg_recv if "NOT skipped" in r["current_guard_skips?"] and "NOT skipped" in r["extended_guard_skips?"]]
            _ext_would_fix = [r for r in _neg_recv if "NOT skipped" in r["current_guard_skips?"] and "SKIPPED" in r["extended_guard_skips?"]]
            st.markdown(f"**Current guard misses: {len([r for r in _neg_recv if 'NOT skipped' in r['current_guard_skips?']])} | "
                        f"Extended guard would additionally catch: {len(_ext_would_fix)} | "
                        f"Still uncaught after extended guard: {len(_still_counted)}**")
        else:
            st.success("No negative-yard receiving plays in this game.")

        # Play count warning
        st.divider()
        if _play_count > len(_plays):
            st.warning(f"⚠️ API returned {_play_count} total plays but only {len(_plays)} fetched (limit=400). "
                       f"Missing {_play_count - len(_plays)} plays — some carries/stats may be from unfetched plays.")
        else:
            st.success(f"✅ All {_play_count} plays fetched ({len(_plays)} items).")
    # ── END DEBUG ─────────────────────────────────────────────────────────────






    # Build linescore from scoring_df (cumulative score diffs per team per quarter)
    _scoring_disp = data.get("scoring", pd.DataFrame())
    _ls_raw = data.get("linescore", pd.DataFrame())

    def _build_ls_from_scoring(sdf, ls_raw):
        """Build linescore table from scoring summary cumulative scores."""
        if sdf is None or sdf.empty or "Away Score" not in sdf.columns:
            return ls_raw  # fallback to raw linescore
        teams_away = sdf.groupby("Quarter").last().reset_index() if "Quarter" in sdf.columns else pd.DataFrame()
        if teams_away.empty: return ls_raw
        # Get final cumulative scores per quarter
        last_per_q = sdf.groupby("Quarter", sort=False).last().reset_index()
        quarters = ["Q1","Q2","Q3","Q4"]
        # Identify away/home teams from linescore if available
        if ls_raw is not None and not ls_raw.empty and "Team" in ls_raw.columns:
            away_t = ls_raw.iloc[0]["Team"] if len(ls_raw) > 0 else "Away"
            home_t = ls_raw.iloc[1]["Team"] if len(ls_raw) > 1 else "Home"
        else:
            # Derive from scoring_df first play
            away_t = sdf.iloc[0].get("Team","Away") if not sdf.empty else "Away"
            home_t = sdf[sdf["Team"] != away_t].iloc[0].get("Team","Home") if len(sdf[sdf["Team"]!=away_t])>0 else "Home"
        # Detect OT quarters in scoring data
        all_quarters_in_sdf = sdf["Quarter"].dropna().unique().tolist() if "Quarter" in sdf.columns else []
        ot_quarters = sorted([q for q in all_quarters_in_sdf if str(q).startswith("OT")])

        rows = []
        for team, col in [(away_t, "Away Score"), (home_t, "Home Score")]:
            row = {"Team": team}
            prev = 0
            total = 0
            h1 = 0
            h2 = 0
            for q in quarters:
                qr = last_per_q[last_per_q["Quarter"] == q]
                if not qr.empty:
                    val = int(pd.to_numeric(qr.iloc[0][col], errors="coerce") or 0)
                    pts = val - prev
                    prev = val
                else:
                    pts = 0
                row[q] = pts
                total += pts
                if q in ("Q1","Q2"): h1 += pts
                else: h2 += pts
            row["1H"] = h1
            row["2H"] = h2
            # Add OT: sum all OT quarter scores into single "OT" column
            if ot_quarters:
                ot_pts = 0
                for otq in ot_quarters:
                    qr = last_per_q[last_per_q["Quarter"] == otq]
                    if not qr.empty:
                        val = int(pd.to_numeric(qr.iloc[0][col], errors="coerce") or 0)
                        pts = val - prev
                        prev = val
                        ot_pts += pts
                row["OT"] = ot_pts
                total += ot_pts
            row["T"] = total
            rows.append(row)
        return pd.DataFrame(rows)

    _ls_built = _build_ls_from_scoring(_scoring_disp, _ls_raw)

    if _ls_built is not None and not _ls_built.empty:
        _ls_cols = [c for c in ["Team","Q1","Q2","Q3","Q4","1H","2H","OT","T"] if c in _ls_built.columns]
        _ls_show = _ls_built[_ls_cols]

        # Render as styled HTML table matching screenshot
        def _ls_html(df):
            q_cols  = [c for c in ["Q1","Q2","Q3","Q4"] if c in df.columns]
            h_cols  = [c for c in ["1H","2H"] if c in df.columns]
            ot_cols = [c for c in ["OT"] if c in df.columns]
            t_cols  = [c for c in ["T"] if c in df.columns]
            # Build logo lookup from game dict
            _logos = {}
            try:
                _logos[game["away"]["abbr"].upper()] = game["away"].get("logo","")
                _logos[game["home"]["abbr"].upper()] = game["home"].get("logo","")
            except: pass
            sep_style = "border-left:2px solid rgba(255,255,255,0.15);"
            def th(c, sep=False):
                s = sep_style if sep else ""
                return f"<th style='opacity:0.45;font-size:11px;font-weight:500;padding:0 10px;{s}'>{c}</th>"
            def td(val, bold=False, sep=False):
                s = sep_style if sep else ""
                fw = "font-weight:700;" if bold else "opacity:0.85;"
                return f"<td style='{fw}padding:4px 20px;{s}'>{int(val)}</td>"
            header = "".join([th(c) for c in q_cols]
                           + ([th("H1",True),th("H2")] if h_cols else [])
                           + ([th("OT",True)] if ot_cols else [])
                           + ([th("T",True)] if t_cols else []))
            rows_html = ""
            for _, r in df.iterrows():
                team_abbr = str(r["Team"]).upper()
                logo_url = _logos.get(team_abbr,"")
                logo_img = f'<img src="{logo_url}" style="width:24px;height:24px;object-fit:contain;margin-right:8px;vertical-align:middle">' if logo_url else ""
                team_cell = f"<td style='font-weight:700;text-align:left;padding-right:30px;white-space:nowrap'>{logo_img}{team_abbr}</td>"
                cells = "".join([td(r.get(c,0)) for c in q_cols]
                              + ([td(r.get("1H",0),sep=True),td(r.get("2H",0))] if h_cols else [])
                              + ([td(r.get("OT",0),sep=True)] if ot_cols else [])
                              + ([td(r.get("T",0),bold=True,sep=True)] if t_cols else []))
                rows_html += f"<tr style='line-height:2.2'>{team_cell}{cells}</tr>"
            return f"""<div style="display:flex;justify-content:center;margin:4px 0;width:100%">
            <table style="border-collapse:collapse;font-size:13px;text-align:center;width:70%;min-width:420px">
              <thead><tr><th style="text-align:left;padding-right:20px"></th>{header}</tr></thead>
              <tbody>{rows_html}</tbody>
            </table></div>"""

        st.markdown(_ls_html(_ls_show), unsafe_allow_html=True)
    st.divider()

    # ── Reconciliation status ─────────────────────────────────────────────────
    _recon = get_reconciliation_status(data, game_id)
    if _recon["passed"]:
        st.success("✅ Reconciliation Passed — All Quarter/Half stats match official totals.")
    else:
        st.error("❌ Reconciliation Failed — Some plays are missing in the Quarter/Half splits.")
        _rows = []
        for player, cat, col, pbp, official, _ in _recon["mismatches"]:
            diff = pbp - official
            _rows.append({
                "Player":     player,
                "Stat":       cat.capitalize(),
                "Col":        col,
                "Q/H Total":  pbp,
                "Game Total": official,
                "Missing":    str(diff),
            })
        _mdf = pd.DataFrame(_rows)
        st.dataframe(
            _mdf.style.map(
                lambda v: "color:#f59e0b;font-weight:700" if str(v).startswith("-") else "",
                subset=["Missing"]
            ),
            use_container_width=True,
            hide_index=True,
        )


    # Period filter
    st.markdown("<div class='sec-div' style='margin-top:18px'>Player Stats</div>",
                unsafe_allow_html=True)

    # Standard periods only — no OT
    # Include OT option only when OT data exists in this game
    _has_ot_data = bool(by_period.get("OT"))
    available = ["Full Game", "Q1", "Q2", "Q3", "Q4", "H1", "H2"]
    if _has_ot_data:
        available.append("OT")

    period_filter = st.radio("Period:", options=available,
                             horizontal=True, label_visibility="collapsed")

    def get_pbp_key(pf):
        return {"H1": "H1", "H2": "H2"}.get(pf, pf)

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
        st.markdown(_render_stats_df_html(df), unsafe_allow_html=True)

    # Key map: display label → internal key used in by_period
    _PERIOD_KEY = {"H1": "1H", "H2": "2H", "OT": "OT"}

    def _render_stats_df_html(df):
        """Render stats df as HTML with logos in Team column."""
        cols = list(df.columns)
        ths = "".join(
            f"<th style='text-align:{'left' if c in ('Player','Team') else 'center'};padding:6px 10px;font-size:12px;opacity:0.5;font-weight:500'>{c}</th>"
            for c in cols
        )
        rows_html = ""
        for _, r in df.iterrows():
            cells = ""
            for c in cols:
                val = str(r[c]) if pd.notna(r[c]) else ""
                if c == "Team":
                    logo = _logo_map.get(val.upper(), "")
                    cell = f"<td style='padding:5px 10px;text-align:center'><img src='{logo}' style='width:22px;height:22px;object-fit:contain' title='{val}'></td>" if logo else f"<td style='padding:5px 10px;text-align:center;font-size:12px'>{val}</td>"
                elif c == "Player":
                    cell = f"<td style='padding:5px 10px;font-size:12px;font-weight:500'>{val}</td>"
                else:
                    cell = f"<td style='padding:5px 10px;text-align:center;font-size:12px'>{val}</td>"
                cells += cell
            rows_html += f"<tr style='border-bottom:0.5px solid rgba(128,128,128,0.15)'>{cells}</tr>"
        return f"""<div style='overflow-x:auto;width:100%'>
        <table style='border-collapse:collapse;width:100%;font-size:12px'>
          <thead><tr style='border-bottom:1px solid rgba(128,128,128,0.2)'>{ths}</tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""

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
        st.markdown(_render_stats_df_html(df), unsafe_allow_html=True)

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

    def _render_prop_df_html(df):
        """Render prop checker df as HTML with logos in Team column."""
        cols = list(df.columns)
        # Header row
        ths = "".join(
            f"<th style='text-align:left;padding:6px 10px;font-size:12px;opacity:0.5;font-weight:500'>{c}</th>"
            for c in cols
        )
        rows_html = ""
        for _, r in df.iterrows():
            cells = ""
            for c in cols:
                val = str(r[c])
                if c == "Team":
                    logo = _logo_map.get(val.upper(), "")
                    cell = f"<td style='padding:5px 10px;text-align:center'><img src='{logo}' style='width:22px;height:22px;object-fit:contain' title='{val}'></td>" if logo else f"<td style='padding:5px 10px'>{val}</td>"
                elif val.startswith("✅"):
                    cell = f"<td style='padding:5px 10px;color:#22c55e;font-weight:700;font-size:12px'>{val}</td>"
                elif val.startswith("❌"):
                    cell = f"<td style='padding:5px 10px;color:#ef4444;font-weight:700;font-size:12px'>{val}</td>"
                else:
                    cell = f"<td style='padding:5px 10px;font-size:12px'>{val}</td>"
                cells += cell
            rows_html += f"<tr style='border-bottom:0.5px solid rgba(128,128,128,0.15)'>{cells}</tr>"
        return f"""<div style='overflow-x:auto;width:100%'>
        <table style='border-collapse:collapse;width:100%;font-size:12px'>
          <thead><tr style='border-bottom:1px solid rgba(128,128,128,0.2)'>{ths}</tr></thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""

    def show_prop_or_stats(category: str, sort="YDS"):
        """Show prop table if thresholds set, else show normal stat table."""
        prop_df = build_prop_table(category)
        if prop_df is not None:
            # Prop mode
            if prop_df.empty:
                st.info(f"No {category} data available.")
                return
            st.markdown(_render_prop_df_html(prop_df), unsafe_allow_html=True)
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
        half_labels = {"1H": "H1", "2H": "H2"}

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
            st.markdown(_render_prop_df_html(prop_df), unsafe_allow_html=True)
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
        "Enter one prop per line, examples show in the box below:\n"
    )

    prop_text = st.text_area(
        "Props",
        placeholder=(
            "Bijan Robinson to record 10+ Rushing Yards in Each Quarter\n"
            "Tyreek Hill 3+ Receptions in Each Half\n"
        ),
        height=200,
        key="prop_text_input",
        label_visibility="collapsed",
    )

    run_grader = st.button("⚡ Grade Props", key="grade_btn")


    graded = []
    team_graded = []
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
            (_re.compile(r'rush(?:ing)? yards?|rush(?:ing)? yds?|rush yd\b', _re.I),   "Rushing Yards"),
            (_re.compile(r'rush(?:ing)? tds?|rush(?:ing)? touchdowns?', _re.I), "Rushing TDs"),
            (_re.compile(r'pass(?:ing)? yards?|pass(?:ing)? yds?', _re.I),   "Passing Yards"),
            (_re.compile(r'pass(?:ing)? tds?|pass(?:ing)? touchdowns?', _re.I), "Passing TDs"),
            (_re.compile(r'receiv(?:ing|e)? yards?|receiv(?:ing|e)? yds?', _re.I), "Receiving Yards"),
            (_re.compile(r'receptions?|\brec\b(?!\s*tds?|\s*touchdowns?|\s+yards?|\s+yds?)', _re.I), "Receptions"),
            (_re.compile(r'interceptions?', _re.I),                "Interceptions"),
            (_re.compile(r'sacks?|record a sack', _re.I),          "Sacks"),
            (_re.compile(r'completions?|completed passes?', _re.I),          "Completions"),
            (_re.compile(r'receiv(?:ing|e)? tds?|receiv(?:ing|e)? touchdowns?|rec tds?', _re.I), "Receiving TDs"),
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
            return NAME_ALIASES.get(n.lower(), n.title())

        props = []
        error_rows = []
        graded = []
        _ftd_deferred = []  # first TD props to grade after player_found_in_game is defined
        try:
            for i, line in enumerate(clean_lines):
                # Skip team/game market lines — handled separately below
                import re as _re_skip
                if _re_skip.match(r'^(each team|both teams|points scored|\d+[+]?\s*(?:made\s+)?(?:tds?|touchdowns?|field goals?|fgs?|scored))', line, _re_skip.I):
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
                if _re_skip.match(r'^succe(?:ss|s)ful\s+(?:2\s*(?:pt\s*)?point|2\s*pt|two\s*(?:pt\s*)?point|two\s*pt)\s+conversion', line, _re_skip.I):
                    continue
                # Team-specific 2pt: "[Team] to [have|record] a Successful 2pt Conversion"
                if _re_skip.search(r'\bto\s+(?:(?:have|record)\s+a?\s*)?succe(?:ss|s)ful\s+(?:2\s*(?:pt\s*)?point|2\s*pt|two\s*(?:pt\s*)?point|two\s*pt)\s+conversion', line, _re_skip.I):
                    continue
                if _re_skip.match(r'^opening kick', line, _re_skip.I):
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
        
                        import re as _re_ftd
                        def _get_td_scorer(desc, td_type):
                            """Extract the scoring player from ESPN TD description."""
                            td_lower = td_type.lower()
                            # Passing/Receiving TD: scorer is receiver before 'N Yd pass from'
                            if "passing" in td_lower or "receiving" in td_lower:
                                m = _re_ftd.match(r'^(.+?)\s+\d+\s+[Yy]d\s+pass\s+from\s+', desc)
                                if m:
                                    return m.group(1).strip().lower()
                            # Rushing TD: scorer is rusher before 'N Yd run' or 'N Yd rush'
                            if "rushing" in td_lower:
                                m = _re_ftd.match(r'^(.+?)\s+\d+\s+[Yy]d\s+(?:run|rush)', desc)
                                if m:
                                    return m.group(1).strip().lower()
                            # Any TD / return TD: first token(s) before yardage
                            m = _re_ftd.match(r'^(.+?)\s+\d+', desc)
                            if m:
                                return m.group(1).strip().lower()
                        _first_type_ftd = _td_r.iloc[0].get("Type","") if "Type" in _td_r.columns else ""
                        _scorer_ftd = _get_td_scorer(_fdesc, _first_type_ftd)
                        _won_ftd = any(p.split()[-1].lower() in _scorer_ftd for p in _ftd_pls)
                        _ftd_deferred.append({
                            "prop_line": line, "players": _ftd_pls,
                            "won": _won_ftd, "detail": _ftd_detail2})
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
                            _p1e = _each_m.group(1).strip()
                            _p2e = _each_m.group(2).strip()
                            if condition == "game total":
                                # Game total EACH → use early-return combine block
                                props.append({'line_index': i, 'player': _p1e,
                                    'player2': _p2e, 'stat': _stat_raw,
                                    'threshold': _thr, 'condition': condition, 'operator': 'each',
                                    'players_list': [_p1e, _p2e],
                                    'category': _cat, 'col': _col, 'raw_line': line})
                            else:
                                # Period-based EACH (each quarter/half) → two separate props
                                # so grade_prop handles per-period grading with all() logic
                                for _pe in [_p1e, _p2e]:
                                    props.append({'line_index': i, 'player': _pe,
                                        'stat': _stat_raw, 'threshold': _thr,
                                        'condition': condition, 'operator': 'over',
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
                    for player in [dual.group(1).strip().title(), dual.group(2).strip().title()]:
                        props.append({"line_index": i, "player": player, "stat": stat,
                                      "threshold": threshold, "condition": condition,
                                      "operator": operator, "raw_line": line})
                else:
                    player_raw = (single or alt).group(1).strip().title()
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
            """Convert player name to ESPN abbreviation.
            'Bijan Robinson' → 'B.Robinson'
            'Amon-Ra St. Brown' → 'A.St. Brown'
            'D\'Andre Swift' → 'D.Swift'
            """
            parts = player.strip().split()
            if len(parts) < 2:
                return player
            first_initial = parts[0][0].upper()
            if len(parts) == 2:
                return f"{first_initial}.{parts[1]}"
            # 3+ parts: check if middle parts look like name prefixes (St., De, La, etc.)
            # ESPN keeps them as part of the last name: "A.St. Brown"
            return f"{first_initial}.{' '.join(parts[1:])}"

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
                # Use official boxscore for accuracy
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
                    if v2 is None:
                        # Player not in that stat df — check if they're in the game at all
                        in_game = (player_found_in_game(normalise_name(p2), "passing")
                                   or player_found_in_game(normalise_name(p2), "rushing")
                                   or player_found_in_game(normalise_name(p2), "receiving")
                                   or player_found_in_game(normalise_name(p2), "defense"))
                        if not in_game:
                            all_found2 = False  # truly not in this game
                        v2 = 0  # in game with 0 of this stat → valid 0
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
                if not all_found2:
                    # A player is "not in this game" only if they don't appear
                    # in the game roster at all — not merely because they have 0
                    # of a specific stat (e.g. WR with 0 rush yards is still in the game)
                    not_found = [p2 for p2 in players_list
                                 if not player_found_in_game(normalise_name(p2), "passing")
                                 and not player_found_in_game(normalise_name(p2), "rushing")
                                 and not player_found_in_game(normalise_name(p2), "receiving")
                                 and not player_found_in_game(normalise_name(p2), "defense")]
                    scope2 = f"{', '.join(not_found) if not_found else 'Player'} not in this game"
                    won2 = None
                return {
                    "player": players_str2, "stat": prop.get("stat",""),
                    "threshold": thr2, "condition": scope2,
                    "period_results": {}, "won": won2 is True if won2 is not None else None,
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
                    "period_results": {"Error": f"{player} not in this game"},
                    "won": None, "raw_line": prop.get("raw_line",""),
                }

            def hit(v: float) -> bool:
                if operator == "under":   return v < threshold
                if operator == "exactly": return v == threshold
                return v >= threshold
            _INLINE_MAP = {"Q1":"Q1","Q2":"Q2","Q3":"Q3","Q4":"Q4","1st Half":"H1","2nd Half":"H2","H1":"H1","H2":"H2"}


            period_results = {}
            _pk = _INLINE_MAP.get(condition)

            if "each quarter" in condition:
                for q in ["Q1","Q2","Q3","Q4"]:
                    v = get_player_val(player, category, col, q)
                    period_results[q] = f"{'✅' if hit(v) else '❌'} {v:.0f}"
                won = all(hit(get_player_val(player, category, col, q)) for q in ["Q1","Q2","Q3","Q4"])
            elif "each half" in condition:
                for h, lbl in [("1H","H1"),("2H","H2")]:
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

            # Build Data column — merge all players period_results
            def _fmt_pr(pr):
                """Format period_results dict into display string."""
                if not pr: return ""
                if "Error" in pr: return pr["Error"]
                parts = []
                for k, v in pr.items():
                    num = v.strip().split()[-1] if v.strip() else v
                    parts.append(f"{num}" if k == "Game" else f"{k}: {num}")
                return " ".join(parts)

            if len(results) > 1:
                # Multiple players (e.g. "X & Y to Each Record ...") — show per-player
                player_parts = []
                for r in results:
                    pname = r.get("player","?").split()[-1]  # last name
                    pr_str = _fmt_pr(r.get("period_results",{}))
                    if pr_str:
                        player_parts.append(f"{pname} {pr_str}")
                    else:
                        player_parts.append(pname)
                scope_display = " | ".join(player_parts)
            else:
                pr = results[0].get("period_results", {})
                if pr:
                    if "Error" in pr:
                        scope_display = pr["Error"]
                    else:
                        parts_pr = []
                        for k, v in pr.items():
                            num = v.strip().split()[-1] if v.strip() else v
                            parts_pr.append(f"{num}" if k == "Game" else f"{k}: {num}")
                        if list(pr.keys()) == ["Game"]:
                            scope_display = f"Game: {parts_pr[0]}"
                        else:
                            scope_display = f"{scope_short} | {" ".join(parts_pr)}"
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
                    "Data":   f"Unexpected error: {str(_ge)[:60]}",
                    "Result": "❗ Error",
                }
        # Process deferred first TD props — now player_found_in_game is available
        for _ftd_d in _ftd_deferred:
            _pls = _ftd_d["players"]
            _not_in = [p for p in _pls
                if not player_found_in_game(normalise_name(p), "passing")
                and not player_found_in_game(normalise_name(p), "rushing")
                and not player_found_in_game(normalise_name(p), "receiving")]
            if _not_in:
                graded.append({"Prop": _ftd_d["prop_line"],
                    "Data": f"{_not_in[0]} not in this game", "Result": "❗ Error"})
            else:
                _w = _ftd_d["won"]
                graded.append({"Prop": _ftd_d["prop_line"],
                    "Data": f"First TD: {_ftd_d['detail']}",
                    "Result": "✅ Won" if _w is True else ("❗ Error" if _w is None else "❌ Lost")})

        graded += [safe_grade(group) for group in by_line.values()]
        for er in error_rows:
            graded.append({
                "Prop":   er.get("raw_line",""),
                "Data":   "Market format not supported",
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
        st.warning("⚠️ Please report any issues with resulting such as incorrect result given and also report any ❗ Error results returned for further investigation/improvements.")
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
        TEAM_LINE_RE = _re_t.compile(r'^(each team|both teams|points scored|\d+[+]?\s*(?:made\s+)?(?:tds?|touchdowns?|field goals?|fgs?|scored))', _re_t.I)
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
            rows = scoring_df[scoring_df["Quarter"] == period_label]
            return rows["TypeID"].astype(str).tolist() if "TypeID" in rows.columns else []

        def _pts_in(period_label):
            if linescore is None or linescore.empty or period_label not in linescore.columns:
                return 0
            try:
                return int(pd.to_numeric(linescore[period_label], errors="coerce").fillna(0).sum())
            except Exception:
                return 0

        def _detect_2pt(sdf, team_abbr=None):
            """Detect successful 2pt conversion using score deltas.
            A successful 2pt conversion causes a score increase of exactly +2 (standalone)
            or +8 (when ESPN combines TD+2pt in one scoring row).
            Much more reliable than parsing ESPN Type/Description text fields.
            Returns (has_2pt: bool, data_str: str)
            """
            if sdf is None or sdf.empty:
                return False, "No 2pt Conversion"
            if "Away Score" not in sdf.columns or "Home Score" not in sdf.columns:
                return False, "No 2pt Conversion"

            # Determine which score column to check for team-specific market
            _col = None
            if team_abbr and "Team" in sdf.columns:
                # Find which column (Away/Home) belongs to this team
                _team_rows = sdf[sdf["Team"].str.upper() == team_abbr.upper()]
                if not _team_rows.empty:
                    _fi = _team_rows.index[0]
                    _prev = sdf.loc[:_fi-1].iloc[-1] if _fi > 0 else None
                    if _prev is not None:
                        _da = int(pd.to_numeric(_team_rows.iloc[0]["Away Score"], errors="coerce") or 0) - int(pd.to_numeric(_prev["Away Score"], errors="coerce") or 0)
                        _col = "Away Score" if _da > 0 else "Home Score"

            prev_away = 0; prev_home = 0
            for _, row in sdf.iterrows():
                cur_away = int(pd.to_numeric(row.get("Away Score", 0), errors="coerce") or 0)
                cur_home = int(pd.to_numeric(row.get("Home Score", 0), errors="coerce") or 0)
                da = cur_away - prev_away
                dh = cur_home - prev_home

                # Check for 2pt delta: +2 (standalone row) or +8 (TD+2pt combined)
                _is_2pt = False
                if _col == "Away Score":
                    _is_2pt = da in (2, 8)
                elif _col == "Home Score":
                    _is_2pt = dh in (2, 8)
                else:
                    # Generic: either team
                    _is_2pt = da in (2, 8) or dh in (2, 8)

                if _is_2pt:
                    _team_name = str(row.get("Team", ""))
                    _desc = str(row.get("Description", ""))[:60]
                    _delta = da if da in (2, 8) else dh
                    _score_str = f"{cur_away}-{cur_home}"
                    _data = f"{_team_name}: score {_score_str} (+{_delta})"
                    if _desc:
                        _data += f" | {_desc}"
                    return True, _data

                prev_away = cur_away
                prev_home = cur_home

            label = f"{team_abbr} " if team_abbr else ""
            return False, f"No {label}2pt Conversion"

        def _check_reqs(reqs, period_label, each_team):
            plays = _plays_in(period_label) if period_label else (
                scoring_df["TypeID"].astype(str).tolist()
                if scoring_df is not None and not scoring_df.empty and "TypeID" in scoring_df.columns
                else [])
            pts = _pts_in(period_label) if period_label else 0
            for req_type, req_n in reqs:
                if req_type == "rushing_td":
                    ok = sum(1 for tid in plays if tid in _RUSH_TD_IDS) >= req_n
                elif req_type == "passing_td":
                    ok = sum(1 for tid in plays if tid in _PASS_TD_IDS) >= req_n
                elif req_type == "any_td":
                    ok = sum(1 for tid in plays if tid in _ALL_TD_IDS) >= req_n
                elif req_type == "fg":
                    ok = sum(1 for tid in plays if tid in _FG_IDS) >= req_n
                else:  # score / points
                    if scoring_df is not None and not scoring_df.empty and "Quarter" in scoring_df.columns:
                        q_rows = scoring_df[scoring_df["Quarter"] == period_label]
                        if each_team and "Team" in scoring_df.columns:
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
        _TWO_PT_RE     = _re_t.compile(r'^succe(?:ss|s)ful\s+(?:2\s*(?:pt\s*)?point|2\s*pt|two\s*(?:pt\s*)?point|two\s*pt)\s+conversion', _re_t.I)
        # Team-specific 2pt: "[Team] to Have a Successful 2pt Conversion"
        _TEAM_TWO_PT_RE = _re_t.compile(
            r'^(.+?)\s+to\s+(?:(?:have|record)\s+a?\s*)?succe(?:ss|s)ful\s+'
            r'(?:2\s*(?:pt\s*)?point|2\s*pt|two\s*(?:pt\s*)?point|two\s*pt)\s+conversion',
            _re_t.I
        )
        _KICK_TD_RE    = _re_t.compile(r'^opening kick(?:off)?.*(?:return|returned).*td|opening kickoff.*touchdown', _re_t.I)

        # ── Verified ESPN TypeID sets — 100% confirmed from live data ──────────
        _ALL_TD_IDS  = {"18","32","34","36","37","39","67","68"}  # all TD types
        _FG_IDS      = {"59"}           # Field Goal Good
        _RUSH_TD_IDS = {"68"}           # Rushing Touchdown
        _PASS_TD_IDS = {"67"}           # Passing Touchdown (covers receiving TD too)
        _ST_TD_IDS   = {"18","32","34","37"}  # ST TDs: Blocked FG, KR TD, PR TD, Blocked Punt TD
        # Legacy text set — used only for _FIRST_TD_RE description parsing
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
                if _sdf_n is not None and not _sdf_n.empty and "TypeID" in _sdf_n.columns:
                    _td_mask  = _sdf_n["TypeID"].astype(str).isin(_ALL_TD_IDS)
                    _has_td   = _td_mask.any()
                    _td_count = int(_td_mask.sum())
                else:
                    _has_td   = False
                    _td_count = 0
                won = not _has_td
                team_graded.append({"Prop": line, "Data": f"TDs: {_td_count}",
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            # ── Team-specific 2pt Conversion ─────────────────────────────────
            _t2pt_m = _TEAM_TWO_PT_RE.match(line)
            if _t2pt_m:
                _t2pt_raw = _t2pt_m.group(1).strip()
                _t2pt_abbr = _resolve_team(_t2pt_raw)
                if _game_teams and _t2pt_abbr not in _game_teams:
                    team_graded.append({"Prop": line, "Data": f"{_t2pt_abbr} not in this game",
                        "Result": "❗ Error"})
                    continue
                _has_2pt, _2pt_data = _detect_2pt(data.get("scoring", pd.DataFrame()), team_abbr=_t2pt_abbr)
                team_graded.append({"Prop": line, "Data": _2pt_data,
                    "Result": "✅ Won" if _has_2pt else "❌ Lost"})
                continue

            # ── Successful 2pt Conversion — score delta approach ────────────────
            if _TWO_PT_RE.match(line):
                _sdf_2 = data.get("scoring", pd.DataFrame())
                _has_2pt, _2pt_data = _detect_2pt(_sdf_2, team_abbr=None)
                team_graded.append({"Prop": line, "Data": _2pt_data,
                    "Result": "✅ Won" if _has_2pt else "❌ Lost"})
                continue

            # ── Overtime Win ───────────────────────────────────────────────────
            _ot_m = _OT_WIN_RE.match(line)
            if _ot_m:
                _winner_raw = _ot_m.group(1).strip()
                _loser_raw  = _ot_m.group(2).strip()
                _winner_abbr = _resolve_team(_winner_raw)
                _loser_abbr  = _resolve_team(_loser_raw)
                # Validate BOTH teams are in this game
                _ot_not_found = [n for t, n in [(_winner_abbr, _winner_raw), (_loser_abbr, _loser_raw)]
                                  if _game_teams and t not in _game_teams]
                if _ot_not_found:
                    if len(_ot_not_found) == 2:
                        _ot_err_msg = "Both teams not in this game"
                    else:
                        _ot_err_msg = f"{_ot_not_found[0]} not in this game"
                    team_graded.append({"Prop": line,
                        "Data": _ot_err_msg,
                        "Result": "❗ Error"})
                    continue
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
                if _game_teams and _st_team not in _game_teams:
                    team_graded.append({"Prop": line, "Data": f"{_st_team} not in this game",
                        "Result": "❗ Error"})
                    continue
                _sdf_stf = data.get("scoring", pd.DataFrame())
                won = False
                _first_desc = "No TDs"
                if _sdf_stf is not None and not _sdf_stf.empty and "TypeID" in _sdf_stf.columns:
                    _td_rows = _sdf_stf[_sdf_stf["TypeID"].astype(str).isin(_ALL_TD_IDS)]
                    if not _td_rows.empty:
                        _first_td   = _td_rows.iloc[0]
                        _first_desc = f"{_first_td.get('Team','')} {_first_td.get('Type','')}"
                        _is_st      = str(_first_td.get("TypeID","")) in _ST_TD_IDS
                        _right_team = _first_td.get("Team","").upper() == _st_team
                        won = _is_st and _right_team
                team_graded.append({"Prop": line, "Data": f"First TD: {_first_desc}",
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            # ── Special Teams any TD ───────────────────────────────────────────
            _st_m = _ST_TD_RE.match(line)
            if _st_m:
                _st_team2 = _resolve_team(_st_m.group(1).strip())
                if _game_teams and _st_team2 not in _game_teams:
                    team_graded.append({"Prop": line, "Data": f"{_st_team2} not in this game",
                        "Result": "❗ Error"})
                    continue
                _sdf_st = data.get("scoring", pd.DataFrame())
                won = False
                _st_detail = "No ST TD"
                if _sdf_st is not None and not _sdf_st.empty and "TypeID" in _sdf_st.columns:
                    _st_plays = _sdf_st[
                        (_sdf_st["TypeID"].astype(str).isin(_ST_TD_IDS)) &
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

                        import re as _re_ftd2
                        def _get_td_scorer2(desc, td_type):
                            """Extract the scoring player from ESPN TD description."""
                            td_lower = td_type.lower()
                            # Passing/Receiving TD: scorer is receiver before 'N Yd pass from'
                            if "passing" in td_lower or "receiving" in td_lower:
                                m = _re_ftd2.match(r'^(.+?)\s+\d+\s+[Yy]d\s+pass\s+from\s+', desc)
                                if m:
                                    return m.group(1).strip().lower()
                            # Rushing TD: scorer is rusher before 'N Yd run' or 'N Yd rush'
                            if "rushing" in td_lower:
                                m = _re_ftd2.match(r'^(.+?)\s+\d+\s+[Yy]d\s+(?:run|rush)', desc)
                                if m:
                                    return m.group(1).strip().lower()
                            # Any TD / return TD: first token(s) before yardage
                            m = _re_ftd2.match(r'^(.+?)\s+\d+', desc)
                            if m:
                                return m.group(1).strip().lower()
                            return desc.lower()
                        _first_type2 = _td_rows2.iloc[0].get("Type","") if "Type" in _td_rows2.columns else ""
                        _scorer2 = _get_td_scorer2(_first_desc2, _first_type2)
                        won = any(p.split()[-1].lower() in _scorer2 for p in _players_ftd)

                _ftd_deferred.append({
                    "prop_line": line, "players": _players_ftd,
                    "won": won, "detail": _ftd_detail})
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
                _tq_raw = _tq_m.group(1).strip().lower()
                _is_each_team = _tq_raw in ("each team", "both teams")
                if _is_each_team:
                    # Grade for each team using scoring_df cumulative diffs (reliable)
                    _sdf_etq = data.get("scoring", pd.DataFrame())
                    def _team_q_from_sdf(team, period):
                        """Points scored by team in quarter from scoring_df cumulative scores."""
                        if _sdf_etq is None or _sdf_etq.empty: return 0
                        _df = _sdf_etq.copy()
                        if "Quarter" in _df.columns: _df = _df[_df["Quarter"] == period]
                        if "Team" in _df.columns: _df = _df[_df["Team"].str.upper() == team.upper()]
                        if _df.empty: return 0
                        # Determine team's score column (Away or Home)
                        _all = _sdf_etq[_sdf_etq["Team"].str.upper() == team.upper()] if "Team" in _sdf_etq.columns else pd.DataFrame()
                        if _all.empty: return 0
                        _fi = _all.index[0]
                        _prev = _sdf_etq.loc[:_fi-1].iloc[-1] if _fi > 0 else None
                        _pa = int(pd.to_numeric(_prev["Away Score"], errors="coerce") or 0) if _prev is not None else 0
                        _ph = int(pd.to_numeric(_prev["Home Score"], errors="coerce") or 0) if _prev is not None else 0
                        _fr = _all.iloc[0]
                        _da = int(pd.to_numeric(_fr["Away Score"], errors="coerce") or 0) - _pa
                        _col = "Away Score" if _da > 0 else "Home Score"
                        # Get last row in this period for this team's score column
                        _all_q = _sdf_etq.copy()
                        if "Quarter" in _all_q.columns: _all_q = _all_q[_all_q["Quarter"] == period]
                        _prev_q = _sdf_etq[~_sdf_etq.index.isin(_all_q.index)]
                        _prev_q = _prev_q[_prev_q.index < _all_q.index[0]] if not _all_q.empty and len(_prev_q) > 0 else pd.DataFrame()
                        if _all_q.empty: return 0
                        _end_val = int(pd.to_numeric(_all_q.iloc[-1][_col], errors="coerce") or 0)
                        _start_val = int(pd.to_numeric(_prev_q.iloc[-1][_col], errors="coerce") or 0) if not _prev_q.empty else 0
                        return max(0, _end_val - _start_val)

                    _team_data_parts = []
                    _won_all = True
                    for _t in sorted(_game_teams):
                        _q_pts = {q: _team_q_from_sdf(_t, q) for q in ["Q1","Q2","Q3","Q4"]}
                        _won_t = all(v > 0 for v in _q_pts.values())
                        if not _won_t: _won_all = False
                        _team_data_parts.append(f"{_t} " + ", ".join(f"{q}: {v}" for q,v in _q_pts.items()))
                    _tq_data = " | ".join(_team_data_parts) if _team_data_parts else "No data"
                    team_graded.append({"Prop": line, "Data": _tq_data,
                        "Result": "✅ Won" if _won_all else "❌ Lost"})
                    continue
                team_abbr = _resolve_team(_tq_raw)
                if _game_teams and team_abbr not in _game_teams:
                    team_graded.append({"Prop": line, "Data": f"{team_abbr} not in this game",
                        "Result": "❗ Error"})
                    continue
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
            # ── Opening Kickoff Return for TD ──────────────────────────────────
            if _KICK_TD_RE.search(line):
                won = False
                _kr_detail = "No kickoff return TD on opening play"
                try:
                    from nfl.api import get_core_plays as _gcp
                    _core_plays = _gcp(game_id)
                    # Skip non-play entries — Coin Toss = type.id 70
                    _first_real = next(
                        (p for p in _core_plays
                         if str(p.get("type", {}).get("id", "")) != "70"),
                        None
                    )
                    if _first_real:
                        _first_type_id = str(_first_real.get("type", {}).get("id", ""))
                        _first_desc    = str(_first_real.get("text", ""))[:60]
                        won = _first_type_id == "32"   # 32 = Kickoff Return Touchdown (verified)
                        _kr_detail = f"First play: {_first_desc}"
                except Exception:
                    # Fallback: first scoring play with verified type.id 32
                    _sdf_kr = data.get("scoring", pd.DataFrame())
                    if _sdf_kr is not None and not _sdf_kr.empty and "TypeID" in _sdf_kr.columns:
                        won = str(_sdf_kr.iloc[0].get("TypeID", "")) == "32"
                        _kr_detail = f"First score: {str(_sdf_kr.iloc[0].get('Description',''))[:60]}"
                team_graded.append({"Prop": line, "Data": _kr_detail,
                    "Result": "✅ Won" if won else "❌ Lost"})
                continue

            if not TEAM_LINE_RE.match(line):
                continue

            # Validate each-team markets against allowed patterns (N+ is flexible)
            import re as _re_em
            _EACH_PATTERNS = [
                _re_em.compile(r'^each team to score \d+\+? tds? in each quarter$', _re_em.I),
                _re_em.compile(r'^each team to score \d+\+? tds? & \d+\+? fgs? in each half$', _re_em.I),
                _re_em.compile(r'^each team to score \d+\+? rushing tds? & \d+\+? passing tds?$', _re_em.I),
                _re_em.compile(r'^each team to score \d+\+? rushing tds? & \d+\+? passing tds? in each half$', _re_em.I),
            ]
            is_each = "each team" in line.lower() or "both teams" in line.lower()
            if is_each and not any(p.match(line.strip()) for p in _EACH_PATTERNS):
                team_graded.append({"Prop": line, "Data": "Market format not supported",
                    "Result": "❗ Error"})
                continue
            cond    = next((lbl for pat,lbl in COND_T if pat.search(line)), "game total")
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
            plbl = {"Q1":"Q1","Q2":"Q2","Q3":"Q3","Q4":"Q4","1H":"H1","2H":"H2"}
            sorted_teams = sorted(_game_teams)
            def _fmt_req_strs(reqs, types_list):
                """Format requirement counts. If single any_td, omit label."""
                _only_td = len(reqs) == 1 and reqs[0][0] == "any_td"
                parts = []
                for rt, rn in reqs:
                    lbl = req_lbls.get(rt, rt)
                    val = _count_from_types(types_list, rt)
                    if _only_td or not lbl:
                        parts.append(str(val))
                    else:
                        parts.append(f"{lbl}: {val}")
                return " & ".join(parts)

            req_lbls = {"rushing_td":"Rush","passing_td":"Pass","any_td":"TD","fg":"FG","score":""}

            # Verified ESPN TypeID / ScoringTypeName constants
            _RUSH_TD_ID = "68"    # Rushing Touchdown
            _PASS_TD_ID = "67"    # Passing Touchdown (covers receiving TD too)

            def _sdf_types(team=None, period=None):
                """Return list of TypeID strings from scoring_df, filtered by team and/or period."""
                if scoring_df is None or scoring_df.empty: return []
                df = scoring_df.copy()
                if period:
                    if period == "1H":
                        if "Half" in df.columns:
                            df = df[df["Half"] == "1st Half"]
                        elif "Quarter" in df.columns:
                            df = df[df["Quarter"].isin(["Q1","Q2"])]
                    elif period == "2H":
                        if "Half" in df.columns:
                            df = df[df["Half"] == "2nd Half"]
                        elif "Quarter" in df.columns:
                            df = df[df["Quarter"].isin(["Q3","Q4"])]
                    elif period in ("Q1","Q2","Q3","Q4") and "Quarter" in df.columns:
                        df = df[df["Quarter"] == period]
                if team and "Team" in df.columns:
                    df = df[df["Team"].str.upper() == team.upper()]
                return df["TypeID"].astype(str).tolist() if "TypeID" in df.columns else []

            def _count_from_types(ids_list, req_type):
                """Count plays matching req_type from list of TypeID strings."""
                if req_type == "rushing_td": return sum(1 for i in ids_list if i in _RUSH_TD_IDS)
                if req_type == "passing_td": return sum(1 for i in ids_list if i in _PASS_TD_IDS)
                if req_type == "any_td":     return sum(1 for i in ids_list if i in _ALL_TD_IDS)
                if req_type == "fg":         return sum(1 for i in ids_list if i in _FG_IDS)
                return 0

            def _pts_from_sdf(df_slice):
                """Exact per-quarter points from Away+Home Score cumulative diffs.
                Uses ESPN's reported scores directly — accurate including XP and 2PT."""
                if df_slice is None or df_slice.empty: return 0
                if "Away Score" not in df_slice.columns or "Home Score" not in df_slice.columns:
                    return 0
                # Sum all scoring play deltas in this slice
                # Each row has cumulative scores; we want points scored IN this period
                # which equals last row - score before first row
                try:
                    last = df_slice.iloc[-1]
                    # Score before this slice started
                    all_idx = scoring_df.index if scoring_df is not None else df_slice.index
                    first_idx = df_slice.index[0]
                    prior = scoring_df.loc[:first_idx].iloc[:-1] if scoring_df is not None and len(scoring_df.loc[:first_idx]) > 1 else None
                    prev_away = int(prior.iloc[-1]["Away Score"]) if prior is not None and not prior.empty else 0
                    prev_home = int(prior.iloc[-1]["Home Score"]) if prior is not None and not prior.empty else 0
                    pts = (int(last["Away Score"]) - prev_away) + (int(last["Home Score"]) - prev_home)
                    return max(0, pts)
                except Exception:
                    return 0

            if is_each and reqs[0][0] == "score":
                # Each Team to Score in All Four Quarters
                # Use linescore which has per-team per-quarter scores directly
                from nfl.stats import build_linescore_df as _bls_t
                _ls_t = _bls_t(game_id)
                team_data_parts = []
                for team in sorted_teams:
                    if _ls_t is not None and not _ls_t.empty and "Team" in _ls_t.columns:
                        _tr = _ls_t[_ls_t["Team"].str.upper() == team.upper()]
                        if not _tr.empty:
                            q_parts = ", ".join(
                                f"{p}: {int(pd.to_numeric(_tr.iloc[0].get(p, 0), errors='coerce') or 0)}"
                                for p in periods)
                            team_data_parts.append(f"{team} {q_parts}")
                            continue
                    # Fallback: use score column diffs from scoring_df (exact, includes XP/2PT)
                    q_parts = ", ".join(
                        f"{p}: {_pts_from_sdf(_sdf_types(team=team, period=p) and scoring_df[scoring_df['Quarter']==p] if scoring_df is not None and not scoring_df.empty and 'Quarter' in scoring_df.columns else None)}"
                        for p in periods)
                    team_data_parts.append(f"{team} {q_parts}")
                data_str = " | ".join(team_data_parts)

            elif is_each and periods == ["game total"]:
                # Game-level each-team: "Each Team to Score 1+ Rush TD & 1+ Pass TD"
                team_data_parts = []
                for team in sorted_teams:
                    types_t = _sdf_types(team=team)
                    team_data_parts.append(f"{team} {_fmt_req_strs(reqs, types_t)}")
                data_str = " | ".join(team_data_parts)

            elif is_each:
                # Period-split each-team: "Each Team to Score 1+ TD & 1+ FG in Each Half"
                team_data_parts = []
                for team in sorted_teams:
                    period_parts = []
                    _only_td_req = len(reqs) == 1 and reqs[0][0] == "any_td"
                    for p in periods:
                        types_t = _sdf_types(team=team, period=p)
                        _fmt = _fmt_req_strs(reqs, types_t)
                        if _only_td_req:
                            period_parts.append(f"{plbl.get(p,p)}: {_fmt}")
                        else:
                            period_parts.append(f"{plbl.get(p,p)} {_fmt}")
                    team_data_parts.append(f"{team} {', '.join(period_parts)}")
                data_str = " | ".join(team_data_parts)

            elif periods == ["game total"] and is_each:
                # Game-level each-team prop (no quarter/half split) — per-team game totals
                team_data_parts = []
                for team in sorted_teams:
                    types_t = _sdf_types(team=team)
                    req_strs_t = [f"{req_lbls.get(rt,rt)}: {_count_from_types(types_t, rt)}" for rt, rn in reqs]
                    team_data_parts.append(f"{team} {' & '.join(req_strs_t)}")
                data_str = " | ".join(team_data_parts)
            elif periods == ["game total"]:
                # Game-level non-each prop — combined totals
                types_all = _sdf_types()
                if reqs[0][0] == "score":
                    # Use exact score diffs: sum of all Away+Home score changes
                    _all_pts = 0
                    if scoring_df is not None and not scoring_df.empty:
                        try:
                            _last = scoring_df.iloc[-1]
                            _all_pts = int(_last.get("Away Score",0)) + int(_last.get("Home Score",0))
                        except Exception:
                            pass
                    data_str = f"Pts: {_all_pts}"
                else:
                    req_strs = [f"{req_lbls.get(rt,rt)}: {_count_from_types(types_all, rt)}" for rt, rn in reqs]
                    data_str = " & ".join(req_strs)

            else:
                # Non-each-team props — combined totals per period
                period_parts = []
                for p in periods:
                    types_p = _sdf_types(period=p)
                    if reqs[0][0] == "score":
                        # Exact quarter points from score column diffs
                        _qdf = scoring_df[scoring_df["Quarter"] == p] if scoring_df is not None and not scoring_df.empty and "Quarter" in scoring_df.columns else None
                        req_strs_p = [str(_pts_from_sdf(_qdf))]
                    else:
                        req_strs_p = []
                        for rt, rn in reqs:
                            lbl = req_lbls.get(rt, rt)
                            val = _count_from_types(types_p, rt)
                            req_strs_p.append(f"{val}" if not lbl else f"{lbl}: {val}")
                    period_parts.append(f"{plbl.get(p,p)}: {' & '.join(req_strs_p)}")
                data_str = ", ".join(period_parts)

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




    with st.expander("📋 Supported Markets", expanded=False):
        st.markdown("""
**👤 Player Props**

*Single player — game total*
- `[Player] to record N+ [stat]`

*Single player — per period*
- `[Player] to record N+ [stat] in Each Quarter`
- `[Player] to record N+ [stat] in Each Half`

*Two players — either hits threshold*
- `[Player] or [Player] to record N+ [stat]`

*Two players — both must hit threshold*
- `Both [Player] and [Player] to Each Record N+ [stat]`
- `Both [Player] and [Player] to Each Record N+ [stat] in Each Quarter`
- `Both [Player] and [Player] to Each Record N+ [stat] in Each Half`

*Two or more players — combined total*
- `[Player] and [Player] to Combine for N+ [stat]` (up to 5 players)

*First TD scorer*
- `[Player] to Score the First TD`
- `[Player] or [Player] to Score the First TD`

*Defensive*
- `[Player] to record N+ Sacks`
- `[Player] to Record a Sack`
- `[Player] to record N+ Sacks in Each Quarter`
- `[Player] to record N+ Sacks in Each Half`

---

**🏟 Team / Game Props**

*Team scoring — quarters*
- `[Team] to Score in All Four Quarters`
- `Each Team to Score in All Four Quarters`
- `Any Quarter to End Scoreless`
- `Points Scored in Each Quarter`
- `N+ TDs to be Scored in Each Quarter`
- `N+ Made Field Goals in Each Quarter`

*Team scoring — halves (exact format, N+ is flexible)*
- `Each Team to Score N+ TD in Each Quarter`
- `Each Team to Score N+ TD & N+ FG in Each Half`
- `Each Team to Score N+ Rushing TDs & N+ Passing TDs`
- `Each Team to Score N+ Rushing TDs & N+ Passing TDs in Each Half`

*Touchdowns*
- `[Team] Special Teams to Score a TD`
- `[Team] Special Teams to Score the First TD`
- `Opening Kickoff to be Returned for a Touchdown`
- `No Touchdown in the Game`

*Other*
- `[Team] to Beat the [Team] in Overtime`
- `[Team] to record/have Successful 2pt Conversion`
- `Successful 2pt Conversion` / `Successful 2 point Conversion` / `Successful two point Conversion` / `Successful two pt Conversion` / `Succesful 2pt Conversion` *(typo-tolerant)*

---

⚠️ **Notes**
- Player names are **not case-sensitive** — `andrew billings` and `Andrew Billings` both work
- Player names must be in this game or result will be ❗ Error
- Team names accept abbreviations (DAL), city (Dallas), nickname (Cowboys) or full name (Dallas Cowboys)
- N+ means any positive number e.g. 1+, 2+, 25+
        """)

    with st.expander("📊 Supported Stats", expanded=False):
        st.markdown("""
**🏃 Rushing**

| You can write | Resolves to |
|---|---|
| `Rushing Yards` | Rushing Yards |
| `Rush Yards` | Rushing Yards |
| `Rushing Yds` | Rushing Yards |
| `Rush Yds` | Rushing Yards |
| `Rushing TDs` | Rushing TDs |
| `Rushing TD` | Rushing TDs |
| `Rush TDs` | Rushing TDs |
| `Rush TD` | Rushing TDs |
| `Rushing Touchdowns` | Rushing TDs |

---

**✈️ Passing**

| You can write | Resolves to |
|---|---|
| `Passing Yards` | Passing Yards |
| `Pass Yards` | Passing Yards |
| `Passing Yds` | Passing Yards |
| `Pass Yds` | Passing Yards |
| `Passing TDs` | Passing TDs |
| `Passing TD` | Passing TDs |
| `Pass TDs` | Passing TDs |
| `Pass TD` | Passing TDs |
| `Passing Touchdowns` | Passing TDs |
| `Completions` | Completions |
| `Completed Passes` | Completions |
| `Interceptions` | Interceptions |
| `Sacks` | Sacks |
| `Record a Sack` | Sacks |

---

**🙌 Receiving**

| You can write | Resolves to |
|---|---|
| `Receiving Yards` | Receiving Yards |
| `Receive Yards` | Receiving Yards |
| `Receiving Yds` | Receiving Yards |
| `Receive Yds` | Receiving Yards |
| `Receiving TDs` | Receiving TDs |
| `Receiving TD` | Receiving TDs |
| `Receive TDs` | Receiving TDs |
| `Receive TD` | Receiving TDs |
| `Rec TDs` | Receiving TDs |
| `Receiving Touchdowns` | Receiving TDs |
| `Receptions` | Receptions |
| `Reception` | Receptions |
| `Rec` | Receptions |

---

⚠️ **Notes**
- `Rec Yards` is **not supported** — use `Receiving Yards` instead
- Stat names are not case-sensitive
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  VIEW — RECONCILE  (temporary — remove this block + the header button to clean up)
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "reconcile":

    b1, _ = st.columns([1.5, 8])
    with b1:
        if st.button("← Calendar", use_container_width=True, key="recon_back"):
            st.session_state.view = "calendar"
            st.rerun()

    st.markdown("<div class='sec-div' style='margin-top:12px'>🔍 Multi-Game Reconciliation</div>",
                unsafe_allow_html=True)

    # ── Mode selector ─────────────────────────────────────────────────────────
    _mode = st.radio(
        "Mode",
        options=["Paste IDs", "Single Day", "Full Week", "Full Month"],
        horizontal=True,
        label_visibility="collapsed",
        key="recon_mode",
    )

    import re as _re_rc
    _now = et_now()

    _rc1, _rc2 = st.columns([4, 1])
    with _rc1:
        if _mode == "Paste IDs":
            st.caption("Enter one game ID per line or comma-separated. You can also enter a YYYY-MM-DD date to expand to all games that day.")
            _recon_input = st.text_area(
                "Game IDs or date",
                value=st.session_state.recon_game_ids,
                placeholder="401772984\n401772949\n2025-12-14",
                height=100,
                key="recon_input_box",
                label_visibility="collapsed",
            )
        elif _mode == "Single Day":
            st.caption("Load all games played on a specific date.")
            _day_date = st.date_input("Date", value=_now.date(), key="recon_day_date", label_visibility="collapsed")
            _recon_input = str(_day_date)
        elif _mode == "Full Week":
            st.caption("Load all games in a 7-day window starting from the selected date (covers Thu–Wed of an NFL week).")
            _week_start = st.date_input("Week starts", value=_now.date(), key="recon_week_start", label_visibility="collapsed")
            _recon_input = ",".join(
                str(_week_start + timedelta(days=i)) for i in range(7)
            )
        else:  # Full Month
            st.caption("Load all games in a calendar month (~64 games, ~90s first run).")
            _mc1, _mc2 = st.columns(2)
            with _mc1:
                _sel_year = st.selectbox("Year", options=[_now.year - 1, _now.year, _now.year + 1],
                                         index=1, key="recon_year", label_visibility="collapsed")
            with _mc2:
                _sel_month = st.selectbox("Month", options=list(range(1, 13)),
                                          format_func=lambda m: MONTH_NAMES[m - 1],
                                          index=_now.month - 1, key="recon_month",
                                          label_visibility="collapsed")
            _recon_input = f"MONTH:{_sel_year}:{_sel_month}"

    with _rc2:
        st.markdown("<div style='margin-top:4px'>", unsafe_allow_html=True)
        _run_recon = st.button("▶ Run", use_container_width=True, key="recon_run")
        _clear_btn = st.button("✕ Clear", use_container_width=True, key="recon_clear")
        if _clear_btn:
            st.session_state.recon_results = None
            st.session_state.recon_game_ids = ""
            st.rerun()

    if _run_recon and _recon_input:
        if _mode == "Paste IDs":
            st.session_state.recon_game_ids = _recon_input

        # ── Build game ID list from mode ──────────────────────────────────────
        _game_ids = []
        _date_re  = _re_rc.compile(r'^\d{4}-\d{2}-\d{2}$')

        if _recon_input.startswith("MONTH:"):
            # Full Month: fetch_games_for_month already exists
            _, _yr, _mo = _recon_input.split(":")
            with st.spinner(f"Loading {MONTH_NAMES[int(_mo)-1]} {_yr} schedule…"):
                _month_games = fetch_games_for_month(int(_yr), int(_mo))
            _game_ids = list(dict.fromkeys(g["id"] for g in _month_games))
            st.caption(f"Found **{len(_game_ids)} games** in {MONTH_NAMES[int(_mo)-1]} {_yr}")
        else:
            # Paste IDs or date-based modes — expand each token
            _raw_tokens = [t.strip() for t in _re_rc.split(r'[\n,]+', _recon_input) if t.strip()]
            for _tok in _raw_tokens:
                if _date_re.match(_tok):
                    try:
                        _d = date.fromisoformat(_tok)
                        _month_games = fetch_games_for_month(_d.year, _d.month)
                        _day_ids = [g["id"] for g in _month_games if et_date_str(g["date"]) == _tok]
                        _game_ids.extend(_day_ids)
                        if not _day_ids and _mode == "Single Day":
                            st.warning(f"No games found for {_tok}")
                    except Exception as _de:
                        st.warning(f"Could not expand date {_tok}: {_de}")
                elif _tok.isdigit():
                    _game_ids.append(_tok)

            _game_ids = list(dict.fromkeys(_game_ids))  # deduplicate, preserve order

        if not _game_ids:
            st.error("No valid game IDs found. Enter numeric IDs or YYYY-MM-DD dates.")
        else:
            _results = []
            _prog = st.progress(0, text=f"Processing 0 / {len(_game_ids)} games…")

            for _gi, _gid in enumerate(_game_ids):
                _prog.progress((_gi) / len(_game_ids),
                               text=f"Processing game {_gi+1} / {len(_game_ids)}: {_gid}")
                try:
                    _gdata = load_all_stats(_gid)
                    _recon = get_reconciliation_status(_gdata, _gid)

                    # Resolve game label (away @ home)
                    _ls  = _gdata.get("linescore", pd.DataFrame())
                    if _ls is not None and not _ls.empty and "Team" in _ls.columns and len(_ls) >= 2:
                        _label = f"{_ls.iloc[0]['Team']} @ {_ls.iloc[1]['Team']}"
                    else:
                        _label = _gid

                    if _recon["passed"]:
                        _results.append({
                            "game_id": _gid,
                            "label":   _label,
                            "passed":  True,
                            "rows":    [],
                        })
                    else:
                        _mrows = []
                        for _player, _cat, _col, _pbp, _official, _ in _recon["mismatches"]:
                            _mrows.append({
                                "Game":       _label,
                                "Player":     _player,
                                "Stat":       _cat.capitalize(),
                                "Col":        _col,
                                "Q/H Total":  _pbp,
                                "Official":   _official,
                                "Missing":    str(_pbp - _official),
                            })
                        _results.append({
                            "game_id": _gid,
                            "label":   _label,
                            "passed":  False,
                            "rows":    _mrows,
                        })
                except Exception as _ge:
                    _results.append({
                        "game_id": _gid,
                        "label":   _gid,
                        "passed":  None,
                        "rows":    [{"Game": _gid, "Player": f"Error: {str(_ge)[:60]}",
                                     "Stat":"","Col":"","Q/H Total":"","Official":"","Missing":""}],
                    })

            _prog.progress(1.0, text=f"Done — {len(_game_ids)} games processed.")
            st.session_state.recon_results = _results

    # ── Display results ───────────────────────────────────────────────────────
    if st.session_state.recon_results:
        _results = st.session_state.recon_results
        _n_total  = len(_results)
        _n_passed = sum(1 for r in _results if r["passed"] is True)
        _n_failed = sum(1 for r in _results if r["passed"] is False)
        _n_error  = sum(1 for r in _results if r["passed"] is None)
        _n_miss   = sum(len(r["rows"]) for r in _results if not r["passed"])

        # Summary banner
        if _n_failed == 0 and _n_error == 0:
            st.success(f"✅ All {_n_total} games passed reconciliation — stats match official totals.")
        else:
            st.error(
                f"❌ {_n_failed} / {_n_total} games have gaps · "
                f"{_n_miss} total mismatches · "
                f"✅ {_n_passed} passed"
                + (f" · ⚠️ {_n_error} errors" if _n_error else "")
            )

        # Per-game results
        for _r in _results:
            if _r["passed"] is True:
                st.success(f"✅ {_r['label']}  ({_r['game_id']})")
            elif _r["passed"] is None:
                st.warning(f"⚠️ {_r['label']}  ({_r['game_id']}) — {_r['rows'][0]['Player']}")
            else:
                with st.expander(
                    f"❌ {_r['label']}  ({_r['game_id']}) — {len(_r['rows'])} mismatch{'es' if len(_r['rows'])>1 else ''}",
                    expanded=True,
                ):
                    _mdf = pd.DataFrame(_r["rows"])
                    st.dataframe(
                        _mdf.style.map(
                            lambda v: "color:#f59e0b;font-weight:700"
                            if isinstance(v, str) and v.startswith("-") else "",
                            subset=["Missing"],
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        # Full flat table download
        _all_rows = []
        for _r in _results:
            if _r["rows"]:
                _all_rows.extend(_r["rows"])
            elif _r["passed"]:
                _all_rows.append({"Game": _r["label"], "Player": "✅ Passed",
                                  "Stat":"","Col":"","Q/H Total":"","Official":"","Missing":""})
        if _all_rows:
            st.divider()
            _flat_df = pd.DataFrame(_all_rows)
            st.download_button(
                "⬇ Download full results as CSV",
                data=_flat_df.to_csv(index=False),
                file_name="reconciliation_results.csv",
                mime="text/csv",
                key="recon_download",
            )
