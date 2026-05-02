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

# ── CSS — structural only, zero color overrides ───────────────────────────────

st.markdown("""
<style>
[data-testid="stSidebar"]        { display: none; }
[data-testid="collapsedControl"] { display: none; }
.block-container { padding-top: 1.2rem !important; max-width: 1100px; }

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

    # ── Month navigation — pure HTML links, immune to st.button CSS ─────────
    # Using st.button for Prev/Next causes them to be caught by the invisible-
    # overlay CSS applied to calendar cells. HTML anchor buttons avoid this
    # entirely — they communicate via query params which Streamlit reads below.
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    st.markdown(f"""
    <style>
    .nav-btn {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        padding: 8px 16px;
        border-radius: 8px;
        border: 1px solid rgba(128,128,128,0.4);
        background: transparent;
        font-size: 0.85rem;
        font-weight: 600;
        cursor: pointer;
        text-decoration: none;
        color: inherit;
        box-sizing: border-box;
        transition: border-color .15s, background .15s;
    }}
    .nav-btn:hover {{
        border-color: rgba(128,128,128,0.7);
        background: rgba(128,128,128,0.08);
        color: inherit;
        text-decoration: none;
    }}
    </style>
    <div style="display:grid;grid-template-columns:1fr 3fr 1fr;gap:8px;align-items:center;margin-bottom:4px">
      <div>
        <a class="nav-btn" href="?nav=prev&py={prev_y}&pm={prev_m}" target="_self">← Prev</a>
      </div>
      <div style="text-align:center;font-weight:700;font-size:1.05rem">
        {MONTH_NAMES[month-1]} {year}
      </div>
      <div>
        <a class="nav-btn" href="?nav=next&py={next_y}&pm={next_m}" target="_self">Next →</a>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Handle nav query params
    _qp = st.query_params
    if "nav" in _qp:
        try:
            st.session_state.cal_month = int(_qp["pm"])
            st.session_state.cal_year  = int(_qp["py"])
        except Exception:
            pass
        st.query_params.clear()
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
    /* Invisible overlay — scoped to vertical blocks containing a .cal-day */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.cal-day) button[data-testid="stBaseButton-secondary"],
    div[data-testid="stVerticalBlock"]:has(.cal-day) button[data-testid="stBaseButton-secondary"] {
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
    pbp = data["pbp"]

    # Linescore
    st.markdown("<div class='sec-div'>Score by Quarter</div>", unsafe_allow_html=True)
    ls_df = data["linescore"]
    if ls_df is not None and not ls_df.empty:
        def style_ls(df):
            s = pd.DataFrame("", index=df.index, columns=df.columns)
            for c in ["1H","2H"]:
                if c in df.columns:
                    s[c] = "font-weight:700"
            if "Total" in df.columns:
                s["Total"] = "font-weight:800"
            return s
        st.dataframe(ls_df.style.apply(style_ls, axis=None),
                     use_container_width=True, hide_index=True)
    else:
        st.info("Linescore not yet available.")

    # Period filter
    st.markdown("<div class='sec-div' style='margin-top:18px'>Player Stats</div>",
                unsafe_allow_html=True)

    available = ["Full Game"]
    for pk, lbl in [("1H","1st Half"),("2H","2nd Half"),
                    ("Q1","Q1"),("Q2","Q2"),("Q3","Q3"),("Q4","Q4")]:
        if pk in pbp and not pbp[pk].empty:
            available.append(lbl)
    for k in pbp:
        if k.startswith("OT") and not pbp[k].empty and k not in available:
            available.append(k)

    period_filter = st.radio("Period:", options=available,
                             horizontal=True, label_visibility="collapsed")

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
                'ESPN provides cumulative game totals — see Play-by-Play for '
                'play-level detail.</div>',
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

    # Scoring summary
    st.markdown("<div class='sec-div' style='margin-top:18px'>Scoring Summary</div>",
                unsafe_allow_html=True)
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
                st.dataframe(hdf.drop(columns=["Half"]),
                             use_container_width=True, hide_index=True)
    else:
        st.info("No scoring plays yet.")

    # Play-by-play
    st.markdown("<div class='sec-div' style='margin-top:18px'>Play-by-Play</div>",
                unsafe_allow_html=True)
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
                    cols = [c for c in ["Clock","Team","Down & Distance",
                                        "Description","Yards","Play Type"]
                            if c in df.columns]
                    st.dataframe(df[cols], use_container_width=True, hide_index=True)
        else:
            st.info(f"No play-by-play for {pf}.")
    else:
        st.info("Play-by-play not yet available.")

    st.divider()
    st.caption(
        f"Updated {et_now().strftime('%-I:%M %p')} ET  ·  "
        "ESPN public API  ·  Not affiliated with ESPN or the NFL"
    )
