"""
app.py  —  NFL Live Box Score Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date
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

    .nfl-header {
        background: #013369;
        color: white;
        padding: 1rem 1.6rem;
        border-radius: 12px;
        margin-bottom: 1.4rem;
        display: flex;
        align-items: center;
        gap: 1rem;
        border-left: 6px solid #D50A0A;
    }
    .nfl-header h1 {
        margin: 0;
        font-family: 'Oswald', sans-serif;
        font-size: 1.7rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    .nfl-header p { margin: 0; opacity: 0.7; font-size: 0.82rem; }

    .section-label {
        font-family: 'Oswald', sans-serif;
        font-size: 0.7rem;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #888;
        margin-bottom: 0.6rem;
        padding-bottom: 0.3rem;
        border-bottom: 1px solid rgba(128,128,128,0.15);
    }

    .score-banner {
        background: #0a0e1a;
        color: white;
        border-radius: 12px;
        padding: 1.4rem 2rem;
        margin-bottom: 1.2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border: 1px solid rgba(255,255,255,0.06);
    }
    .score-team-name { font-family:'Oswald',sans-serif; font-size:1.3rem; font-weight:600; letter-spacing:0.5px; }
    .score-record    { font-size:0.75rem; color:#888; margin-top:2px; }
    .score-num       { font-family:'Oswald',sans-serif; font-size:3rem; font-weight:700; }
    .score-sep       { font-size:1.4rem; color:#333; padding: 0 0.6rem; }
    .status-pill     { background:#D50A0A; color:white; font-size:0.68rem; font-weight:700;
                       padding:0.2rem 0.7rem; border-radius:20px; text-transform:uppercase;
                       letter-spacing:0.8px; display:inline-block; font-family:'Oswald',sans-serif; }
    .status-pill.final { background:#333; }
    .status-pill.pre   { background:#013369; }

    .stRadio > div { flex-direction:row; gap:6px; flex-wrap:wrap; }
    .stRadio > div > label {
        background: rgba(1,51,105,0.08);
        border: 1px solid rgba(1,51,105,0.2);
        border-radius: 20px;
        padding: 4px 16px;
        font-size: 0.8rem;
        cursor: pointer;
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
    }

    div[data-testid="stButton"] > button {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        border-radius: 8px;
        border: 1px solid rgba(1,51,105,0.3);
        background: transparent;
        color: #013369;
        font-size: 0.85rem;
        padding: 0.4rem 1rem;
    }
    div[data-testid="stButton"] > button:hover {
        background: #013369;
        color: white;
        border-color: #013369;
    }

    .stTabs [data-baseweb="tab"] {
        font-family: 'Oswald', sans-serif;
        letter-spacing: 0.5px;
        font-size: 0.85rem;
    }

    .period-note {
        background: rgba(213,10,10,0.06);
        border-left: 3px solid #D50A0A;
        border-radius: 0 6px 6px 0;
        padding: 0.4rem 0.8rem;
        font-size: 0.78rem;
        color: #888;
        margin-bottom: 0.6rem;
    }

    .empty-state {
        text-align:center;
        padding:3rem 1rem;
        color:#aaa;
        font-size:0.95rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

for key, default in {
    "view": "calendar",
    "selected_game_id": None,
    "selected_game": None,
    "cal_year": datetime.now().year,
    "cal_month": datetime.now().month,
    "cal_season_type": 2,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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
def load_games_for_week(week, season_type):
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

def fetch_games_for_month(year, month, season_type):
    all_games = []
    max_week = 18 if season_type == 2 else 4
    for week in range(1, max_week + 1):
        games = load_games_for_week(week, season_type)
        for g in games:
            try:
                gdate = datetime.fromisoformat(g["date"].replace("Z", "")).date()
                if gdate.year == year and gdate.month == month:
                    all_games.append(g)
            except Exception:
                pass
    return all_games

# ══════════════════════════════════════════════════════════════════════════════
#  CALENDAR VIEW
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.view == "calendar":

    import calendar

    MONTH_NAMES = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]

    # Season selector
    col_s, _ = st.columns([3, 9])
    with col_s:
        season_type = st.selectbox(
            "Season",
            options=[2, 3, 1],
            format_func=lambda x: {1:"Preseason", 2:"Regular Season", 3:"Playoffs"}[x],
            index=[2,3,1].index(st.session_state.cal_season_type),
        )
        st.session_state.cal_season_type = season_type

    year  = st.session_state.cal_year
    month = st.session_state.cal_month

    # Load games for this month
    with st.spinner(f"Loading {MONTH_NAMES[month-1]} {year}..."):
        month_games = fetch_games_for_month(year, month, season_type)

    # Group by date
    games_by_date = {}
    for g in month_games:
        try:
            gdate = datetime.fromisoformat(g["date"].replace("Z","")).date()
            ds = gdate.isoformat()
            games_by_date.setdefault(ds, []).append(g)
        except Exception:
            pass

    # ── Calendar navigation ───────────────────────────────────────────────────
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
            f"<div style='text-align:center;font-weight:700;padding-top:6px;font-family:Oswald,sans-serif;font-size:1.05rem'>"
            f"{MONTH_NAMES[month-1]} {year}</div>",
            unsafe_allow_html=True
        )
    with nav3:
        if st.button("Next →"):
            m = st.session_state.cal_month + 1
            y = st.session_state.cal_year
            if m > 12: m = 1; y += 1
            st.session_state.cal_month = m
            st.session_state.cal_year  = y
            st.rerun()

    # ── Calendar grid ─────────────────────────────────────────────────────────
    today_str = date.today().isoformat()
    games_json = json.dumps({
        ds: [
            {
                "id": g["id"],
                "away_abbr":   g["away"]["abbr"],
                "away_logo":   g["away"].get("logo",""),
                "away_score":  g["away"]["score"],
                "away_record": g["away"]["record"],
                "home_abbr":   g["home"]["abbr"],
                "home_logo":   g["home"].get("logo",""),
                "home_score":  g["home"]["score"],
                "home_record": g["home"]["record"],
                "state":       g["status_state"],
                "period":      g["period"],
                "status":      g["status"],
                "venue":       g.get("venue",""),
            }
            for g in games_by_date.get(ds, [])
        ]
        for ds in games_by_date
    })

    import calendar as cal_mod
    first_dow   = cal_mod.monthcalendar(year, month)[0].index(
        next(d for d in cal_mod.monthcalendar(year, month)[0] if d != 0)
    ) if any(d != 0 for row in cal_mod.monthcalendar(year, month) for d in row) else 0
    days_in_mon = cal_mod.monthrange(year, month)[1]
    first_dow   = date(year, month, 1).weekday()  # Monday=0
    # Convert to Sunday=0
    first_dow   = (first_dow + 1) % 7

    cal_html = f"""
<html><head><style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',system-ui,sans-serif}}
body{{background:transparent}}
.cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;margin-top:8px}}
.dow{{text-align:center;font-size:0.62rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#888;padding:4px 0}}
.day{{min-height:88px;border-radius:8px;border:1px solid rgba(128,128,128,0.1);padding:5px;background:rgba(255,255,255,0.01);position:relative}}
.day.empty{{border-color:transparent;background:transparent}}
.day.has-games{{border-color:rgba(1,51,105,0.3);background:rgba(1,51,105,0.04)}}
.day.today{{border-color:#D50A0A !important;background:rgba(213,10,10,0.03) !important}}
.day-num{{font-size:0.7rem;font-weight:600;color:#666;margin-bottom:3px}}
.day.has-games .day-num{{color:#013369;font-weight:700}}
.day.today .day-num{{color:#D50A0A}}
.chip{{display:flex;align-items:center;gap:2px;background:white;border:1px solid rgba(1,51,105,0.12);border-radius:4px;padding:2px 3px;margin-bottom:2px;cursor:pointer;font-size:0.58rem;font-weight:600;color:#013369;transition:all 0.1s;overflow:hidden}}
.chip:hover{{background:#013369;color:white;border-color:#013369}}
.chip.live{{border-color:#D50A0A;background:rgba(213,10,10,0.05);color:#D50A0A}}
.chip.live:hover{{background:#D50A0A;color:white}}
.chip img{{width:13px;height:13px;object-fit:contain;flex-shrink:0}}
.chip:hover img{{filter:brightness(10)}}
.chip.live img{{filter:none}}
.chip.live:hover img{{filter:brightness(10)}}
.dot{{width:5px;height:5px;background:#D50A0A;border-radius:50%;flex-shrink:0;animation:pulse 1.2s infinite}}
.chip:hover .dot{{background:white}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.more{{font-size:0.56rem;color:#013369;cursor:pointer;padding:1px 2px}}

/* Panel */
.panel{{display:none;margin-top:10px;border:1px solid rgba(1,51,105,0.2);border-radius:10px;overflow:hidden}}
.panel.open{{display:block}}
.ph{{background:#013369;color:white;padding:8px 14px;font-size:0.78rem;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center}}
.ph span{{cursor:pointer;opacity:.7;font-size:1rem}} .ph span:hover{{opacity:1}}
.grow{{display:flex;align-items:center;padding:10px 14px;border-bottom:1px solid rgba(128,128,128,0.1);gap:10px;cursor:pointer;transition:background .1s}}
.grow:last-child{{border-bottom:none}} .grow:hover{{background:rgba(1,51,105,0.04)}}
.tb{{display:flex;align-items:center;gap:7px;flex:1}}
.tl{{width:30px;height:30px;object-fit:contain}}
.tn{{font-weight:600;font-size:0.85rem;color:#013369}} .tr{{font-size:0.65rem;color:#aaa}}
.sc{{font-size:1.25rem;font-weight:800;font-family:monospace;color:#013369;min-width:64px;text-align:center}}
.sp{{background:#D50A0A;color:white;font-size:0.62rem;font-weight:700;padding:2px 8px;border-radius:10px;text-align:center;white-space:nowrap}}
.sp.f{{background:#444}} .sp.s{{background:rgba(1,51,105,0.12);color:#013369}}
.sbtn{{background:#013369;color:white;border:none;border-radius:6px;padding:5px 12px;font-size:0.72rem;font-weight:600;cursor:pointer;white-space:nowrap;transition:background .15s}}
.sbtn:hover{{background:#D50A0A}}
</style></head>
<body>
<div class="cal-grid">
  <div class="dow">Sun</div><div class="dow">Mon</div><div class="dow">Tue</div>
  <div class="dow">Wed</div><div class="dow">Thu</div><div class="dow">Fri</div><div class="dow">Sat</div>
</div>
<div class="cal-grid" id="grid"></div>
<div class="panel" id="panel">
  <div class="ph"><span id="plabel">Games</span><span onclick="closeP()">✕</span></div>
  <div id="pgames"></div>
</div>
<script>
const G={games_json};
const today='{today_str}';
let firstDow={first_dow};
let daysIn={days_in_mon};
let year={year}; let month={month};

function pad(n){{return String(n).padStart(2,'0')}}

const grid=document.getElementById('grid');
for(let i=0;i<firstDow;i++){{const e=document.createElement('div');e.className='day empty';grid.appendChild(e);}}
for(let d=1;d<=daysIn;d++){{
  const ds=year+'-'+pad(month)+'-'+pad(d);
  const games=G[ds]||[];
  const isToday=ds===today;
  const hasg=games.length>0;
  const el=document.createElement('div');
  el.className='day'+(hasg?' has-games':'')+(isToday?' today':'');
  let h=`<div class="day-num">${{d}}</div>`;
  const shown=games.slice(0,2);
  shown.forEach(g=>{{
    const live=g.state==='in';
    h+=`<div class="chip ${{live?'live':''}}" onclick="showG('${{ds}}',event)">
      ${{live?'<div class="dot"></div>':''}}
      ${{g.away_logo?`<img src="${{g.away_logo}}" onerror="this.style.display='none'">`:''}}
      <span>${{g.away_abbr}}</span><span style="color:#ccc;font-size:0.5rem">@</span>
      ${{g.home_logo?`<img src="${{g.home_logo}}" onerror="this.style.display='none'">`:''}}
      <span>${{g.home_abbr}}</span>
    </div>`;
  }});
  if(games.length>2) h+=`<div class="more" onclick="showG('${{ds}}',event)">+${{games.length-2}} more</div>`;
  el.innerHTML=h;
  grid.appendChild(el);
}}

function showG(ds,ev){{
  ev&&ev.stopPropagation();
  const games=G[ds]||[];
  const pg=document.getElementById('pgames');
  const pl=document.getElementById('plabel');
  const d=new Date(ds+'T12:00:00');
  pl.textContent=d.toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric'}});
  pg.innerHTML='';
  games.forEach(g=>{{
    const st=g.state;
    const scls=st==='in'?'':'(st==="post"?"f":"s")';
    const sc2=st==='in'?'':st==='post'?'f':'s';
    const stxt=st==='in'?'LIVE Q'+g.period:st==='post'?'Final':'Scheduled';
    const scoreHtml=st!=='pre'?g.away_score+' – '+g.home_score:'<span style="font-size:.8rem;color:#aaa">vs</span>';
    const row=document.createElement('div');
    row.className='grow';
    row.innerHTML=`
      <div class="tb">
        ${{g.away_logo?`<img class="tl" src="${{g.away_logo}}" onerror="this.style.display='none'">`:''}}
        <div><div class="tn">${{g.away_abbr}}</div><div class="tr">${{g.away_record}}</div></div>
      </div>
      <div class="sc">${{scoreHtml}}</div>
      <div class="tb" style="flex-direction:row-reverse;text-align:right">
        ${{g.home_logo?`<img class="tl" src="${{g.home_logo}}" onerror="this.style.display='none'">`:''}}
        <div><div class="tn">${{g.home_abbr}}</div><div class="tr">${{g.home_record}}</div></div>
      </div>
      <div class="sp ${{sc2}}">${{stxt}}</div>
      <button class="sbtn" onclick="selGame('${{g.id}}','${{ds}}')">Box Score</button>
    `;
    pg.appendChild(row);
  }});
  document.getElementById('panel').classList.add('open');
}}

function closeP(){{document.getElementById('panel').classList.remove('open');}}

function selGame(id, ds){{
  // Send to Streamlit via query param trick
  const url=new URL(window.location.href);
  // Use postMessage to parent
  window.parent.postMessage({{streamlitGameSelect: id}}, '*');
}}
</script>
</body></html>
"""
    components.html(cal_html, height=680, scrolling=True)

    # ── Legend ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="display:flex;gap:16px;align-items:center;margin:8px 0 16px;font-size:0.75rem;color:#888">
      <span><span style="display:inline-block;width:10px;height:10px;background:rgba(1,51,105,0.08);border:1px solid rgba(1,51,105,0.3);border-radius:2px;margin-right:4px;vertical-align:middle"></span>Has games</span>
      <span><span style="display:inline-block;width:10px;height:10px;background:rgba(213,10,10,0.06);border:1px solid #D50A0A;border-radius:2px;margin-right:4px;vertical-align:middle"></span>Today</span>
      <span><span style="display:inline-block;width:8px;height:8px;background:#D50A0A;border-radius:50%;margin-right:4px;vertical-align:middle"></span>Live game</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Game list below calendar ──────────────────────────────────────────────
    if games_by_date:
        st.markdown('<div class="section-label">All games this month</div>', unsafe_allow_html=True)
        for ds in sorted(games_by_date.keys()):
            day_games = games_by_date[ds]
            d = datetime.fromisoformat(ds)
            try:
                date_label = d.strftime("%A, %B %-d")
            except ValueError:
                date_label = d.strftime("%A, %B %d")

            with st.expander(f"📅 {date_label}  —  {len(day_games)} game{'s' if len(day_games)>1 else ''}", expanded=False):
                for g in day_games:
                    away = g["away"]; home = g["home"]
                    state = g["status_state"]

                    if state == "in":
                        badge = f'<span style="background:#D50A0A;color:white;font-size:0.65rem;font-weight:700;padding:2px 10px;border-radius:10px">🔴 LIVE Q{g["period"]}</span>'
                    elif state == "post":
                        badge = '<span style="background:#444;color:white;font-size:0.65rem;font-weight:700;padding:2px 10px;border-radius:10px">Final</span>'
                    else:
                        badge = '<span style="background:rgba(1,51,105,0.1);color:#013369;font-size:0.65rem;font-weight:700;padding:2px 10px;border-radius:10px">Scheduled</span>'

                    score_str = f"{away['score']} – {home['score']}" if state != "pre" else "vs"

                    away_logo = f'<img src="{away["logo"]}" style="width:26px;height:26px;object-fit:contain;vertical-align:middle;margin-right:5px">' if away.get("logo") else ""
                    home_logo = f'<img src="{home["logo"]}" style="width:26px;height:26px;object-fit:contain;vertical-align:middle;margin-right:5px">' if home.get("logo") else ""

                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"""
                        <div style="display:flex;align-items:center;gap:14px;padding:6px 0">
                          <div style="display:flex;align-items:center">{away_logo}<b>{away['abbr']}</b> <span style="color:#aaa;font-size:0.75rem;margin-left:4px">{away['record']}</span></div>
                          <div style="font-weight:700;color:#013369;font-size:1rem;min-width:50px;text-align:center">{score_str}</div>
                          <div style="display:flex;align-items:center">{home_logo}<b>{home['abbr']}</b> <span style="color:#aaa;font-size:0.75rem;margin-left:4px">{home['record']}</span></div>
                          {badge}
                        </div>
                        """, unsafe_allow_html=True)
                    with c2:
                        if st.button("Box Score", key=f"btn_{g['id']}"):
                            st.session_state.selected_game_id = g["id"]
                            st.session_state.selected_game    = g
                            st.session_state.view = "boxscore"
                            st.rerun()
    else:
        st.markdown('<div class="empty-state">No games this month. NFL season runs Sep – Feb. Try the regular season weeks.</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  BOX SCORE VIEW
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.view == "boxscore":

    game    = st.session_state.selected_game
    game_id = st.session_state.selected_game_id

    if not game or not game_id:
        st.session_state.view = "calendar"
        st.rerun()

    # Back + Refresh
    b1, b2, _ = st.columns([1.6, 1.2, 7])
    with b1:
        if st.button("← Back to Schedule"):
            st.session_state.view = "calendar"
            st.rerun()
    with b2:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()

    # Score banner with logos
    away = game["away"]; home = game["home"]
    sc = {"in":"","post":"final","pre":"pre"}.get(game["status_state"],"")
    clk = (f'<span style="color:#aaa;font-size:0.75rem;margin-left:8px">{game["clock"]} · Q{game["period"]}</span>'
           if game["status_state"]=="in" else "")
    al = f'<img src="{away["logo"]}" style="width:54px;height:54px;object-fit:contain">' if away.get("logo") else ""
    hl = f'<img src="{home["logo"]}" style="width:54px;height:54px;object-fit:contain">' if home.get("logo") else ""

    st.markdown(f"""
    <div class="score-banner">
      <div style="display:flex;align-items:center;gap:14px">
        {al}
        <div><div class="score-team-name">{away['team']}</div><div class="score-record">{away['record']}</div></div>
      </div>
      <div style="text-align:center">
        <div><span class="score-num">{away['score']}</span><span class="score-sep"> – </span><span class="score-num">{home['score']}</span></div>
        <div style="margin-top:6px"><span class="status-pill {sc}">{game['status']}</span>{clk}</div>
        <div style="color:#555;font-size:0.73rem;margin-top:4px">{game.get('venue','')}</div>
      </div>
      <div style="display:flex;align-items:center;gap:14px;flex-direction:row-reverse">
        {hl}
        <div style="text-align:right"><div class="score-team-name">{home['team']}</div><div class="score-record">{home['record']}</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Load stats
    with st.spinner("Loading box score..."):
        data = load_all_stats(game_id)
    pbp = data["pbp"]

    # Linescore
    st.markdown('<div class="section-label">Score by Quarter</div>', unsafe_allow_html=True)
    ls_df = data["linescore"]
    if ls_df is not None and not ls_df.empty:
        def hl_ls(df):
            s = pd.DataFrame("", index=df.index, columns=df.columns)
            for c in ["1H","2H"]:
                if c in df.columns: s[c] = "background:rgba(1,51,105,0.08);font-weight:600"
            if "Total" in df.columns: s["Total"] = "font-weight:800;background:rgba(1,51,105,0.13)"
            return s
        st.dataframe(ls_df.style.apply(hl_ls, axis=None), use_container_width=True, hide_index=True)
    else:
        st.info("Linescore not available yet.")

    # Period filter
    st.markdown('<div class="section-label" style="margin-top:1.4rem">Player Stats</div>', unsafe_allow_html=True)

    available = ["Full Game"]
    for pbp_key, label in [("1H","1st Half"),("2H","2nd Half"),("Q1","Q1"),("Q2","Q2"),("Q3","Q3"),("Q4","Q4")]:
        if pbp_key in pbp and not pbp[pbp_key].empty:
            available.append(label)
    for k in pbp:
        if k.startswith("OT") and not pbp[k].empty and k not in available:
            available.append(k)

    period_filter = st.radio("Period:", options=available, horizontal=True, label_visibility="collapsed")

    def pbp_key(pf):
        return {"1st Half":"1H","2nd Half":"2H"}.get(pf, pf)

    def filter_df(df, pf):
        if pf == "Full Game" or df is None or df.empty:
            return df
        k = pbp_key(pf)
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
            st.markdown('<div class="period-note">Showing players active in this period. ESPN provides cumulative game totals — see Play-by-Play for play-level detail.</div>', unsafe_allow_html=True)
        if sort and sort in out.columns:
            try:
                tmp = out.copy()
                tmp[sort] = pd.to_numeric(tmp[sort], errors="coerce")
                out = tmp.sort_values(sort, ascending=False)
            except Exception:
                pass
        st.dataframe(out, use_container_width=True, hide_index=True)

    # Stat tabs
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
    st.markdown('<div class="section-label" style="margin-top:1.4rem">Scoring Summary</div>', unsafe_allow_html=True)
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
                hdf = fsdf[fsdf["Half"]==half]
                st.markdown(f"**{half}**")
                st.dataframe(hdf.drop(columns=["Half"]), use_container_width=True, hide_index=True)
    else:
        st.info("No scoring plays yet.")

    # Play-by-play
    st.markdown('<div class="section-label" style="margin-top:1.4rem">Play-by-Play</div>', unsafe_allow_html=True)
    if pbp:
        pf = period_filter
        k  = pbp_key(pf)
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
                    df = show[key]
                    cols = [c for c in ["Clock","Team","Down & Distance","Description","Yards","Play Type"] if c in df.columns]
                    st.dataframe(df[cols], use_container_width=True, hide_index=True)
        else:
            st.info(f"No play-by-play for {pf}.")
    else:
        st.info("Play-by-play not yet available.")

    st.markdown("---")
    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}  ·  ESPN public API  ·  Not affiliated with ESPN or the NFL")
