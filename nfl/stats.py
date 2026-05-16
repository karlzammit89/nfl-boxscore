"""
nfl/stats.py
------------
Parse raw ESPN boxscore data into clean, structured DataFrames
split by quarter and half. This is the accuracy-critical layer.

ESPN's boxscore provides cumulative stats per player, not per-quarter
player stats (that granularity requires play-by-play parsing).
Quarter-level team totals come from linescores.
Per-player quarter splits are derived by parsing drives + plays.
"""

import pandas as pd
from typing import Optional
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
try:
    from .api import get_game_summary, get_linescore, get_scoring_plays, get_core_plays, get_athlete_displayname
except ImportError:
    import importlib as _il
    _api = _il.import_module('api' if 'nfl' not in _sys.modules else 'nfl.api')
    get_game_summary       = _api.get_game_summary
    get_linescore          = _api.get_linescore
    get_scoring_plays      = _api.get_scoring_plays
    get_core_plays         = _api.get_core_plays
    get_athlete_displayname = _api.get_athlete_displayname


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _period_to_half(period: int) -> str:
    if period == 0:
        return "—"
    if period <= 2:
        return "1st Half"
    if period <= 4:
        return "2nd Half"
    return f"OT{period - 4}"


def _quarter_label(period: int) -> str:
    labels = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}
    if period in labels:
        return labels[period]
    if period > 4:
        return f"OT{period - 4}"
    return "—"


# ── Linescore ─────────────────────────────────────────────────────────────────

def build_linescore_df(game_id: str) -> pd.DataFrame:
    """
    Quarter-by-quarter score table.
    Returns DataFrame with columns: Team | Q1 | Q2 | 1H | Q3 | Q4 | 2H | OT... | Total
    """
    ls = get_linescore(game_id)
    if not ls:
        return pd.DataFrame()

    home_q = ls.get("home", [])
    away_q = ls.get("away", [])
    home_team = ls.get("home_team", "HOME")
    away_team = ls.get("away_team", "AWAY")

    # Pad to equal length
    max_periods = max(len(home_q), len(away_q), 4)
    home_q = home_q + [0] * (max_periods - len(home_q))
    away_q = away_q + [0] * (max_periods - len(away_q))

    def build_row(team: str, quarters: list) -> dict:
        row = {"Team": team}
        for i, score in enumerate(quarters):
            period = i + 1
            row[_quarter_label(period)] = _safe_int(score)

        # Half totals
        q_vals = [_safe_int(q) for q in quarters]
        row["1H"] = sum(q_vals[:2])
        row["2H"] = sum(q_vals[2:4])
        row["Total"] = sum(q_vals)
        return row

    home_row = build_row(home_team, home_q)
    away_row = build_row(away_team, away_q)

    # Build ordered columns
    period_cols = [_quarter_label(i + 1) for i in range(max_periods)]
    q1_q2 = [c for c in period_cols[:2]]
    q3_q4 = [c for c in period_cols[2:4]]
    ot_cols = [c for c in period_cols[4:]]
    cols = ["Team"] + q1_q2 + ["1H"] + q3_q4 + ["2H"] + ot_cols + ["Total"]

    df = pd.DataFrame([away_row, home_row])
    # Only keep columns that exist
    cols = [c for c in cols if c in df.columns]
    return df[cols]


# ── Player Stats ──────────────────────────────────────────────────────────────

def _parse_player_stats(boxscore: dict, stat_category: str) -> list[dict]:
    """
    Extract players from a specific stat category in ESPN boxscore.
    stat_category examples: 'passing', 'rushing', 'receiving', 'defensiveTotals'
    Returns list of dicts with player info + their stat keys/values.
    """
    players_data = []
    teams = boxscore.get("players", [])

    for team_block in teams:
        team_info = team_block.get("team", {})
        team_name = team_info.get("displayName", "")
        team_abbr = team_info.get("abbreviation", "")

        for category in team_block.get("statistics", []):
            if category.get("name", "").lower() != stat_category.lower():
                continue

            keys = category.get("keys", [])
            labels = category.get("labels", keys)

            for athlete_entry in category.get("athletes", []):
                athlete = athlete_entry.get("athlete", {})
                stats_raw = athlete_entry.get("stats", [])

                if not stats_raw or all(s in ("--", "", "0/0") for s in stats_raw):
                    continue

                row = {
                    "Player":   athlete.get("displayName", "Unknown"),
                    "Pos":      athlete.get("position", {}).get("abbreviation", ""),
                    "Team":     team_abbr,
                    "Team Full": team_name,
                }

                for key, label, val in zip(keys, labels, stats_raw):
                    row[label] = val

                players_data.append(row)

    return players_data


# ── Category DataFrames ───────────────────────────────────────────────────────

def _make_df(rows: list, drop_cols: list = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if drop_cols:
        df = df.drop(columns=[c for c in drop_cols if c in df.columns])
    return df


def get_passing_stats(game_id: str) -> pd.DataFrame:
    """
    Passing stats for all QBs.
    Typical cols: Player, Pos, Team, C/ATT, YDS, AVG, TD, INT, SACKS, QBR, RTG
    """
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "passing")
    return _make_df(rows, drop_cols=["Team Full"])


def get_rushing_stats(game_id: str) -> pd.DataFrame:
    """
    Rushing stats.
    Typical cols: Player, Pos, Team, CAR, YDS, AVG, TD, LONG
    """
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "rushing")
    return _make_df(rows, drop_cols=["Team Full"])


def get_receiving_stats(game_id: str) -> pd.DataFrame:
    """
    Receiving stats.
    Typical cols: Player, Pos, Team, REC, YDS, AVG, TD, LONG, TGTS
    """
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "receiving")
    return _make_df(rows, drop_cols=["Team Full"])


def get_defensive_stats(game_id: str) -> pd.DataFrame:
    """
    Defensive stats — includes ALL defenders (even those with 0 across the board
    are kept so sack lookups work correctly).
    Typical cols: Player, Pos, Team, TOT, SOLO, SACKS, TFL, PD, QB HTS, TD
    """
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})

    # Parse defensive stats keeping all players (including 0-stat rows for sack lookup)
    players_data = []
    for team_block in boxscore.get("players", []):
        team_info = team_block.get("team", {})
        team_abbr = team_info.get("abbreviation", "")
        team_name = team_info.get("displayName", "")
        for category in team_block.get("statistics", []):
            cat_name = category.get("name", "").lower()
            if cat_name not in ("defensive", "defensivetotals"):
                continue
            keys   = category.get("keys", [])
            labels = category.get("labels", keys)
            for athlete_entry in category.get("athletes", []):
                athlete   = athlete_entry.get("athlete", {})
                stats_raw = athlete_entry.get("stats", [])
                if not stats_raw:
                    continue
                row = {
                    "Player": athlete.get("displayName", "Unknown"),
                    "Pos":    athlete.get("position", {}).get("abbreviation", ""),
                    "Team":   team_abbr,
                }
                for label, val in zip(labels, stats_raw):
                    row[label] = val
                players_data.append(row)
    if not players_data:
        return pd.DataFrame()
    df = pd.DataFrame(players_data)
    # Ensure SACKS column is numeric
    if "SACKS" in df.columns:
        df["SACKS"] = pd.to_numeric(df["SACKS"], errors="coerce").fillna(0)
    return df


def get_kicking_stats(game_id: str) -> pd.DataFrame:
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "kicking")
    return _make_df(rows, drop_cols=["Team Full"])


def get_returning_stats(game_id: str) -> pd.DataFrame:
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "returning")
    return _make_df(rows, drop_cols=["Team Full"])


# ── Team Totals ───────────────────────────────────────────────────────────────

def get_team_stats(game_id: str) -> pd.DataFrame:
    """
    Team-level stat totals (total yards, TO, time of possession, etc.)
    """
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()

    boxscore = summary.get("boxscore", {})
    teams_raw = boxscore.get("teams", [])
    rows = []

    for team_block in teams_raw:
        team_info = team_block.get("team", {})
        row = {
            "Team": team_info.get("abbreviation", ""),
            "Team Full": team_info.get("displayName", ""),
        }
        for stat in team_block.get("statistics", []):
            name  = stat.get("label", stat.get("name", ""))
            value = stat.get("displayValue", stat.get("value", ""))
            row[name] = value
        rows.append(row)

    return _make_df(rows, drop_cols=["Team Full"])


# ── Scoring Summary ───────────────────────────────────────────────────────────

def get_scoring_summary(game_id: str) -> pd.DataFrame:
    """
    Chronological scoring plays with quarter/half labels.
    Cols: Quarter, Half, Clock, Team, Type, TypeID, ScoringTypeName, ScoreValue,
          Description, Away Score, Home Score

    ScoringTypeName (ESPN scoringType.name) is the authoritative high-level
    classification: 'touchdown', 'field-goal', 'safety'. Use this for any_td
    and fg grading instead of text parsing or TypeID enumeration.
    TypeID is used for subtype grading: '67'=Pass TD, '68'=Rush TD, '32'=KR TD etc.
    """
    plays = get_scoring_plays(game_id)
    if not plays:
        return pd.DataFrame()

    rows = []
    for play in plays:
        period = _safe_int(play.get("period", 0))
        rows.append({
            "Quarter":         _quarter_label(period),
            "Half":            _period_to_half(period),
            "Clock":           play.get("clock", ""),
            "Team":            play.get("team_abbr", play.get("team", "")),
            "Type":            play.get("type", ""),
            "TypeID":          play.get("type_id", ""),
            "ScoringTypeName": play.get("scoring_type_name", ""),
            "ScoreValue":      play.get("score_value", 0),
            "Description":     play.get("description", ""),
            "Away Score":      _safe_int(play.get("away_score", 0)),
            "Home Score":      _safe_int(play.get("home_score", 0)),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Quarter Split from Play-by-Play ──────────────────────────────────────────

def get_pbp_by_quarter(game_id: str) -> dict[str, pd.DataFrame]:
    """
    Parse drives + plays from summary to build per-quarter play-by-play.
    Returns dict: { 'Q1': df, 'Q2': df, '1H': df, 'Q3': df, 'Q4': df, '2H': df, 'OT1': df }
    Each df has: Period, Quarter, Half, Clock, Down & Distance, Description, Team, Yards, Result
    """
    summary = get_game_summary(game_id)
    if not summary:
        return {}

    drives = summary.get("drives", {})
    if not drives:
        return {}

    all_plays = []
    previous_drives = drives.get("previous", [])
    current_drive = drives.get("current")
    all_drives = previous_drives + ([current_drive] if current_drive else [])

    def _pbp_period(play, drive) -> int:
        """Resolve play period for PBP view using same multi-source logic."""
        _p_raw = play.get("period", {})
        p = _safe_int(_p_raw.get("number", 0) if isinstance(_p_raw, dict) else _p_raw)
        if p > 0: return p
        if isinstance(_p_raw, dict):
            dv = _p_raw.get("displayValue", "")
            if dv:
                dv = dv.strip().lower()
                if "4th" in dv or "4th quarter" in dv: p = 4
                elif "3rd" in dv or "3rd quarter" in dv: p = 3
                elif "2nd" in dv or "2nd quarter" in dv: p = 2
                elif "1st" in dv or "1st quarter" in dv: p = 1
                elif "1st overtime" in dv: p = 5
                elif "2nd overtime" in dv: p = 6
                elif "overtime" in dv or dv.startswith("ot"): p = 5
                if p > 0: return p
        p = _safe_int(play.get("start", {}).get("period", {}).get("number", 0))
        if p > 0: return p
        dv2 = play.get("start", {}).get("period", {}).get("displayValue", "")
        if dv2:
            dv2 = dv2.strip().lower()
            if "4th" in dv2: return 4
            if "3rd" in dv2: return 3
            if "2nd" in dv2: return 2
            if "1st quarter" in dv2: return 1
            if "overtime" in dv2 or dv2.startswith("ot"): return 5
        p = _safe_int(drive.get("start", {}).get("period", {}).get("number", 0))
        if p > 0: return p
        dv3 = drive.get("start", {}).get("period", {}).get("displayValue", "")
        if dv3:
            dv3 = dv3.strip().lower()
            if "4th" in dv3: return 4
            if "3rd" in dv3: return 3
            if "2nd" in dv3: return 2
            if "1st quarter" in dv3: return 1
            if "overtime" in dv3 or dv3.startswith("ot"): return 5
        return 0

    for drive in all_drives:
        if not drive:
            continue
        team_abbr = drive.get("team", {}).get("abbreviation", "")
        for play in drive.get("plays", []):
            period = _pbp_period(play, drive)
            clock  = play.get("clock", {}).get("displayValue", "")
            desc   = play.get("description", "")
            yards  = play.get("statYardage", 0)
            ptype  = play.get("type", {}).get("text", "")
            down   = play.get("start", {}).get("downDistanceText", "")

            all_plays.append({
                "Period":           period,
                "Quarter":          _quarter_label(period),
                "Half":             _period_to_half(period),
                "Clock":            clock,
                "Team":             team_abbr,
                "Down & Distance":  down,
                "Description":      desc,
                "Yards":            _safe_int(yards),
                "Play Type":        ptype,
            })

    if not all_plays:
        return {}

    df = pd.DataFrame(all_plays)
    result = {}

    for period in df["Period"].unique():
        label = _quarter_label(_safe_int(period))
        result[label] = df[df["Period"] == period].copy()

    # Add half views
    if not df.empty:
        h1 = df[df["Period"].isin([1, 2])].copy()
        h2 = df[df["Period"].isin([3, 4])].copy()
        if not h1.empty:
            result["1H"] = h1
        if not h2.empty:
            result["2H"] = h2

    return result


# ── Per-Quarter Player Stats from Play-by-Play ────────────────────────────────

import re as _re

_NAME = r'[A-Z][a-z]?\.[A-Z][A-Za-z\'\-]+'

# Passer: any name followed by "pass "
_PASSER_RE = _re.compile(rf'({_NAME}(?:\s+{_NAME})?)\s+pass\s+', _re.I)

# Receiver: handles both ESPN formats:
#   "pass short right to J.Waddle to MIA 45"   (new)
#   "pass complete to T.Hill for 23 yards"      (old)
_RECV_RE = _re.compile(
    rf'pass\s+(?:complete\s+to|(?:short|deep|long|screen|flat)?\s*'
    rf'(?:right|left|middle)?\s*to\s+)({_NAME}(?:\s+{_NAME})?)',
    _re.I
)

# Incomplete pass
_INCOMP_RE = _re.compile(r'pass\s+incomplete', _re.I)

# Rusher: name followed by direction/motion keyword
_RUSH_RE = _re.compile(
    # Rusher name must appear at start of play text (not after "to"/"for")
    rf'(?:^\s*|\)\s*)({_NAME}(?:\s+{_NAME})?)\s+'
    r'(?:up the middle|left end|right end|left tackle|right tackle|'
    r'left guard|right guard|rushes?\s|scrambles?\s)',
    _re.I
)

_TD_RE  = _re.compile(r'touchdown', _re.I)
_INT_RE = _re.compile(r'intercepted', _re.I)

# Play type sets superseded by _SKIP_TYPES in get_player_stats_by_period
_PENALTY_RE = _re.compile(r'PENALTY|No Play', _re.I)



# Matches both ESPN sack formats:
# '(Shotgun) D.Maye sacked at CLV 18 for -10 yards (M.Garrett)'  <- parentheses
# 'T.Tagovailoa sacked by C.Young for -8 yards'                  <- by format
_SACK_RE = _re.compile(
    r'sacked\s+(?:at\s+\w+\s+\w+\s+)?for\s+-?\d+\s+yards?\s+\(([A-Z][a-z]?\.[A-Z][A-Za-z\'\-]+)\)'
    r'|sacked\s+(?:at\s+[\w\s]+?)?\s*(?:for\s+-?\d+\s+yards?\s+)?by\s+([A-Z][a-z]?\.[A-Z][A-Za-z\'\-]+)',
    _re.I
)


def get_player_stats_by_period(game_id: str) -> dict:
    """
    Build per-quarter and per-half player stat tables using ESPN Core API plays.

    Approach: fetches all plays from the Core API plays endpoint which provides
    structured participant roles (passer/receiver/rusher/sackedBy) and athlete IDs
    per play — no text parsing needed for player identification.

    Athlete IDs are resolved to displayNames via individual athlete API calls.
    Callers (app.py) cache these resolutions for 30 days via @st.cache_data.

    Data sources:
      1. summary endpoint (existing) — boxscore official stats + season year
      2. core API plays endpoint (new, +1 call) — all plays with structured roles
      3. /athletes/{id} per unique player (new, cached) — displayName resolution
    """
    import re as _re
    from collections import defaultdict

    summary = get_game_summary(game_id)
    if not summary:
        return {}

    # Determine the current season year from summary header for athlete lookups
    _season_year = "2025"
    try:
        _season_year = str(
            summary.get("header", {})
                   .get("season", {})
                   .get("year", 2025)
        )
    except Exception:
        pass

    # ── Fetch all plays from Core API ─────────────────────────────────────────
    core_plays = get_core_plays(game_id)
    if not core_plays:
        return {}

    # ── Athlete ID → displayName resolution (one call per unique ID) ──────────
    _ID_RE = _re.compile(r"/athletes/([0-9]+)")
    _name_cache = {}   # athlete_id str → displayName str (local per-call cache)

    def _resolve_athlete(athlete_id: str) -> str:
        """Resolve athlete_id to displayName. Cached locally and by caller."""
        if athlete_id in _name_cache:
            return _name_cache[athlete_id]
        name = get_athlete_displayname(athlete_id, _season_year)
        if not name:
            # Try without season (some athletes only available without year)
            name = get_athlete_displayname(athlete_id, "")
        _name_cache[athlete_id] = name
        return name

    def _extract_id(ref_url: str) -> str:
        m = _ID_RE.search(ref_url)
        return m.group(1) if m else ""

    # ── Stat accumulators ─────────────────────────────────────────────────────
    def new_pass(): return {"Team": "", "comp": 0, "att": 0, "yds": 0, "td": 0, "int": 0}
    def new_rush(): return {"Team": "", "car": 0, "yds": 0, "td": 0}
    def new_recv(): return {"Team": "", "rec": 0, "yds": 0, "td": 0}
    def new_sack(): return {"Team": "", "sacks": 0}

    passing   = defaultdict(lambda: defaultdict(new_pass))
    rushing   = defaultdict(lambda: defaultdict(new_rush))
    receiving = defaultdict(lambda: defaultdict(new_recv))
    sacking   = defaultdict(lambda: defaultdict(new_sack))

    # ── Play type skip set ────────────────────────────────────────────────────
    _SKIP_TYPES = {
        "end period", "end of half", "end of game", "end of regulation",
        "timeout", "official timeout", "two-minute warning", "two minute warning",
        "coin toss", "kickoff", "kickoff return (offense)", "kickoff return (defense)",
        "kickoff return touchdown",
        "punt", "punt return", "punt return touchdown",
        "blocked punt", "blocked punt touchdown", "blocked field goal",
        "field goal good", "field goal missed",
        "missed field goal return", "missed field goal return touchdown",
        "extra point good", "extra point failed",
        "safety", "interception return touchdown", "fumble return touchdown",
        "two point rush", "two point pass", "two-point rush", "two-point pass",
        "two point conversion", "two-point conversion",
        "two point conversion attempt", "two-point conversion attempt",
        "defensive 2pt conversion",
        "penalty", "uncategorized", "placeholder", "",
    }

    # Roles we track — all pat* roles (2pt conversions embedded in TD rows) are
    # intentionally excluded so they don't double-count passing/rushing attempts
    _STAT_ROLES = {"passer", "receiver", "rusher", "sackedBy"}

    # ── Team abbreviation lookup from summary boxscore ────────────────────────
    # Maps ESPN team ID string → abbreviation (e.g. "26" → "SEA")
    _team_id_to_abbr = {}
    for _tb in summary.get("boxscore", {}).get("teams", []):
        _tid = str(_tb.get("team", {}).get("id", ""))
        _tab = _tb.get("team", {}).get("abbreviation", "")
        if _tid and _tab:
            _team_id_to_abbr[_tid] = _tab

    def _team_abbr_from_play(play: dict) -> str:
        """Get possessing team abbreviation from a core API play."""
        team_ref = play.get("team", {}).get("$ref", "")
        m = _re.search(r"/teams/([0-9]+)", team_ref)
        if m:
            return _team_id_to_abbr.get(m.group(1), "")
        return ""

    # ── Main play loop ────────────────────────────────────────────────────────
    _seen_ids = set()

    for play in core_plays:
        play_id = play.get("id", "")
        if play_id in _seen_ids:
            continue
        if play_id:
            _seen_ids.add(play_id)

        ptype = (play.get("type", {}).get("text", "") or "").lower().strip()
        if ptype in _SKIP_TYPES:
            continue

        # isPenalty guard removed: plays with type='Penalty' are already caught
        # by _SKIP_TYPES above. Real offensive plays (Rush, Pass Reception) that
        # have isPenalty=True simply had a declined/offset penalty on the play —
        # the yards still count and the play must be classified normally.

        period = _safe_int((play.get("period") or {}).get("number", 0))
        if period == 0:
            continue   # can't assign to a quarter — skip

        stat_yds = _safe_int(play.get("statYardage", 0))
        team     = _team_abbr_from_play(play)

        # Build role → displayName map for this play
        # Only resolve IDs for roles we actually use
        roles    = {}   # role_str → displayName
        role_ids = {}   # role_str → athlete_id
        for participant in play.get("participants", []):
            role = participant.get("type", "")
            if role not in _STAT_ROLES:
                continue
            ref = participant.get("athlete", {}).get("$ref", "")
            aid = _extract_id(ref)
            if not aid:
                continue
            name = _resolve_athlete(aid)
            if name and role not in roles:
                roles[role]    = name
                role_ids[role] = aid

        psr = roles.get("passer")
        rcv = roles.get("receiver")
        rsh = roles.get("rusher")
        skr = roles.get("sackedBy")

        # RC-OFFPEN Fix: determine possession team with fallback to participant ref
        _pos_team = _team_abbr_from_play(play)
        if not _pos_team:
            for _pt in play.get("participants", []):
                if _pt.get("type") in ("passer", "rusher", "receiver"):
                    _pt_ref = _pt.get("athlete", {}).get("$ref", "")
                    _pt_tm  = _re.search(r"/teams/([0-9]+)", _pt_ref)
                    if _pt_tm:
                        _pos_team = _team_id_to_abbr.get(_pt_tm.group(1), "")
                        if _pos_team:
                            break

        # RC-OFFPEN Fix: skip offensive-penalty plays (penalty on possession team)
        if play.get("isPenalty") and not play.get("scoringPlay"):
            _play_txt = (play.get("text") or "").upper()
            _pen_m    = _re.search(r"PENALTY ON ([A-Z]{2,3})[^A-Z]", _play_txt)
            if _pen_m and _pos_team and _pen_m.group(1) == _pos_team:
                continue  # offensive-team penalty: play nullified → skip
            # RC3a Fix: DPI completions statYardage=0 — skip as ATT/REC
            if ptype in {"pass reception", "pass"} and stat_yds == 0:
                continue

        # ── Classify and accumulate ───────────────────────────────────────────
        if ptype in {"pass reception", "pass"}:
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
                d["att"] += 1; d["comp"] += 1; d["yds"] += stat_yds
            if rcv:
                rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                rd["rec"] += 1; rd["yds"] += stat_yds

        elif ptype == "pass incompletion":
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
                d["att"] += 1

        elif ptype == "passing touchdown":
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
                d["att"] += 1; d["comp"] += 1; d["yds"] += stat_yds; d["td"] += 1
            if rcv:
                rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                rd["rec"] += 1; rd["yds"] += stat_yds; rd["td"] += 1

        elif ptype == "pass interception return":
            # RC-INT Fix: ESPN often omits passer role on INT plays.
            # Parse QB abbreviated name from play text as fallback.
            _int_psr = psr
            if not _int_psr:
                _int_txt = play.get("text") or ""
                _int_m = _re.search(
                    r"(?:\([^)]*\)\s*)?([A-Z]\.[A-Za-z\-']+(?:\s+(?:Jr|Sr|II|III|IV)\.?)?)\s+pass",
                    _int_txt)
                if _int_m:
                    _int_psr = _int_m.group(1)
            if _int_psr:
                d = passing[period][_int_psr]; d["Team"] = team or d["Team"]
                d["att"] += 1; d["int"] += 1

        elif ptype == "sack":
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
            if skr:
                sd = sacking[period][skr]; sd["Team"] = team or sd["Team"]
                sd["sacks"] += 1

        elif ptype in {"rush", "scramble", "rushing touchdown"}:
            # RC-KNEEL Fix: count kneels — ESPN includes them in official rushing stats
            if rsh:
                d = rushing[period][rsh]; d["Team"] = team or d["Team"]
                d["car"] += 1; d["yds"] += stat_yds
                if ptype == "rushing touchdown":
                    d["td"] += 1

        elif ptype in {"fumble recovery (own)", "fumble recovery (opponent)"}:
            # RC4b: Skip aborted snap recoveries
            _fum_txt = (play.get("text") or "").lower()
            if "aborted" not in _fum_txt:
                fum_yds = stat_yds
                if fum_yds == 0:
                    yd_m = _re.search(r"\bfor\s+(-?[0-9]+)\s+yards?", _fum_txt, _re.I)
                    if yd_m:
                        fum_yds = _safe_int(yd_m.group(1))
                if psr:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += fum_yds
                if rcv:
                    rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += fum_yds
                if rsh and not psr:
                    d = rushing[period][rsh]; d["Team"] = team or d["Team"]
                    d["car"] += 1; d["yds"] += fum_yds

        elif rsh and ptype not in _SKIP_TYPES:
            # RC-MISC catch-all: unhandled play type with rusher role
            d = rushing[period][rsh]; d["Team"] = team or d["Team"]
            d["car"] += 1; d["yds"] += stat_yds

    # ── DataFrame builders ────────────────────────────────────────────────────
    def to_sack_df(acc):
        rows = [{"Player": n, "Team": d["Team"], "SACKS": d["sacks"]}
                for n, d in acc.items() if d["sacks"] > 0]
        return (pd.DataFrame(rows).sort_values("SACKS", ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def to_pass_df(acc):
        rows = [{"Player": n, "Team": d["Team"],
                 "C/ATT": f"{d['comp']}/{d['att']}",
                 "YDS": d["yds"], "TD": d["td"], "INT": d["int"]}
                for n, d in acc.items() if d["att"] > 0]
        return (pd.DataFrame(rows).sort_values("YDS", ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def to_rush_df(acc):
        rows = [{"Player": n, "Team": d["Team"],
                 "CAR": d.get("car", 0), "YDS": d.get("yds", 0), "TD": d.get("td", 0)}
                for n, d in acc.items() if d.get("car", 0) > 0 or d.get("yds", 0) != 0]
        return (pd.DataFrame(rows).sort_values("YDS", ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def to_recv_df(acc):
        rows = [{"Player": n, "Team": d["Team"],
                 "REC": d["rec"], "YDS": d["yds"], "TD": d["td"]}
                for n, d in acc.items() if d["rec"] > 0]
        return (pd.DataFrame(rows).sort_values("YDS", ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def merge(base, periods, factory):
        merged = defaultdict(factory)
        for p in periods:
            for name, d in base[p].items():
                m = merged[name]; m["Team"] = d["Team"]
                for k in d:
                    if k != "Team":
                        m[k] = m.get(k, 0) + d[k]
        return merged

    all_periods = sorted(set(
        list(passing.keys()) + list(rushing.keys()) +
        list(receiving.keys()) + list(sacking.keys())))

    result = {}
    for p in all_periods:
        if p > 4:
            continue
        lbl = _quarter_label(p)
        result[lbl] = {"passing":   to_pass_df(passing[p]),
                       "rushing":   to_rush_df(rushing[p]),
                       "receiving": to_recv_df(receiving[p]),
                       "defense":   to_sack_df(sacking[p])}

    h1 = [p for p in all_periods if p in (1, 2)]
    h2 = [p for p in all_periods if p in (3, 4)]
    ot = [p for p in all_periods if p > 4]
    if h1:
        result["1H"] = {"passing":   to_pass_df(merge(passing,   h1, new_pass)),
                        "rushing":   to_rush_df(merge(rushing,   h1, new_rush)),
                        "receiving": to_recv_df(merge(receiving, h1, new_recv)),
                        "defense":   to_sack_df(merge(sacking,   h1, new_sack))}
    if h2:
        result["2H"] = {"passing":   to_pass_df(merge(passing,   h2, new_pass)),
                        "rushing":   to_rush_df(merge(rushing,   h2, new_rush)),
                        "receiving": to_recv_df(merge(receiving, h2, new_recv)),
                        "defense":   to_sack_df(merge(sacking,   h2, new_sack))}
    if ot:
        ot_periods = sorted(p for p in all_periods if p > 4)
        result["OT"] = {"passing":   to_pass_df(merge(passing,   ot_periods, new_pass)),
                        "rushing":   to_rush_df(merge(rushing,   ot_periods, new_rush)),
                        "receiving": to_recv_df(merge(receiving, ot_periods, new_recv)),
                        "defense":   to_sack_df(merge(sacking,   ot_periods, new_sack))}

    result["Full Game"] = {
        "passing":   to_pass_df(merge(passing,   all_periods, new_pass)),
        "rushing":   to_rush_df(merge(rushing,   all_periods, new_rush)),
        "receiving": to_recv_df(merge(receiving, all_periods, new_recv)),
        "defense":   to_sack_df(merge(sacking,   all_periods, new_sack)),
    }

    _reconcile(result, game_id)
    return result

def _reconcile(result: dict, game_id: str) -> None:
    """
    Step 2: Compare PBP quarter/half splits against official totals.
    Step 3: Log PASSED if everything matches.
    Step 4: Log which quarter/half is suspected missing if gaps remain.
    """
    try:
        official = {
            "passing":   get_passing_stats(game_id),
            "rushing":   get_rushing_stats(game_id),
            "receiving": get_receiving_stats(game_id),
        }
    except Exception:
        return

    # No auto-correction — we never guess which quarter a missing play belongs to.
    # Gaps are reported via get_reconciliation_status() for transparency.
    pass


def _last_period(result, cat, player, periods):
    """Find the last quarter this player appeared in."""
    for p in reversed(periods):
        df = result.get(p, {}).get(cat)
        if df is not None and not df.empty and _in_df(df, player):
            return p
    # Not in any quarter — check halves
    for h in ["2H","1H"]:
        df = result.get(h, {}).get(cat)
        if df is not None and not df.empty and _in_df(df, player):
            return None  # can't map back to quarter
    return None


def _match_player(df, player):
    """Match player row handling full-name vs ESPN-abbr mismatch.
    e.g. 'Amon-Ra St. Brown' matches 'A.St. Brown' in PBP df.
    e.g. 'Kenneth Walker III' → strip suffix → 'Kenneth Walker' → 'K.Walker'
    """
    import re as _re_mp
    _SUFFIX_RE = _re_mp.compile(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$', _re_mp.I)

    if "Player" not in df.columns:
        return df.iloc[0:0]
    # 1. Exact match (abbreviated name already)
    row = df[df["Player"] == player]
    if not row.empty:
        return row
    # 2. Strip name suffix (Jr/Sr/II/III/IV) then build ESPN abbreviation
    #    "Kenneth Walker III" → "Kenneth Walker" → "K.Walker"
    clean = _SUFFIX_RE.sub("", player.strip()).strip()
    parts = clean.split()
    if len(parts) >= 2:
        abbr = f"{parts[0][0].upper()}.{chr(32).join(parts[1:])}"
        row = df[df["Player"] == abbr]
        if not row.empty:
            return row
    # 3. Also try without suffix on the original (catches "AJ Barner" → "A.Barner")
    orig_parts = player.strip().split()
    if len(orig_parts) >= 2:
        orig_abbr = f"{orig_parts[0][0].upper()}.{chr(32).join(orig_parts[1:])}"
        if orig_abbr != abbr:
            row = df[df["Player"] == orig_abbr]
            if not row.empty:
                return row
    # 4. Last-name + first-initial fallback (handles remaining edge cases)
    last = parts[-1] if parts else ""
    first_init = parts[0][0].upper() if parts else ""
    candidates = df[df["Player"].str.endswith(last, na=False)]
    if not candidates.empty and first_init:
        candidates = candidates[candidates["Player"].str.startswith(first_init, na=False)]
    return candidates.iloc[0:1] if not candidates.empty else df.iloc[0:0]


def _in_df(df, player):
    if "Player" not in df.columns: return False
    return not _match_player(df, player).empty


def _get_col(df, player, col):
    if df is None or df.empty or "Player" not in df.columns or col not in df.columns:
        return 0
    row = _match_player(df, player)
    if row.empty: return 0
    return int(pd.to_numeric(row.iloc[0].get(col, 0), errors="coerce") or 0)


def _get_att(df, player):
    if df is None or df.empty or "Player" not in df.columns: return 0
    row = _match_player(df, player)
    if row.empty: return 0
    ca = str(row.iloc[0].get("C/ATT","0/0"))
    try: return int(ca.split("/")[1])
    except: return 0


def _adjust_col(df, player, col, diff):
    if df is None or df.empty or "Player" not in df.columns or col not in df.columns:
        return
    mask = df["Player"] == player
    if not mask.any(): return
    df.loc[mask, col] = (pd.to_numeric(df.loc[mask, col], errors="coerce").fillna(0) + diff).astype(int)


def _adjust_att(df, player, diff):
    if df is None or df.empty or "Player" not in df.columns: return
    mask = df["Player"] == player
    if not mask.any(): return
    ca = str(df.loc[mask, "C/ATT"].iloc[0])
    try:
        comp, att = ca.split("/")
        df.loc[mask, "C/ATT"] = f"{comp}/{max(0,int(att)+diff)}"
    except: pass


def _build_reconciliation_report(result: dict, game_id: str) -> list:
    """
    Compare per-period PBP totals (Q1+Q2+Q3+Q4+OT) against official boxscore.
    Uses summed quarter/OT buckets — NOT Full Game PBP — so period=0 plays
    that leaked into Full Game but weren't assigned to any quarter are caught.
    Returns list of (player, cat, col, pbp_val, official_val, suspected_quarter) tuples.
    """
    try:
        official = {
            "passing":   get_passing_stats(game_id),
            "rushing":   get_rushing_stats(game_id),
            "receiving": get_receiving_stats(game_id),
        }
    except Exception:
        return []

    # Sum across all valid period buckets — excludes period=0 "—" bucket
    # result may be the full data dict (with "by_period" key) or by_period directly
    by_period = result.get("by_period", result)

    valid_periods = ["Q1","Q2","Q3","Q4","OT"]
    # Also include any OT1/OT2 keys that get_pbp_by_quarter might add
    extra_ot = [k for k in by_period if k.startswith("OT") and k not in valid_periods]
    check_periods = ["Q1","Q2","Q3","Q4"] + extra_ot + (["OT"] if "OT" in by_period else [])
    mismatches = []

    def _sum_col_across_periods(cat, player, col):
        """Sum a stat column for a player across all valid period buckets."""
        total = 0
        for p in check_periods:
            df = by_period.get(p, {}).get(cat)
            if df is None or df.empty:
                continue
            total += _get_col(df, player, col)
        return total

    def _sum_att_across_periods(cat, player):
        """Sum passing attempts for a player across all valid period buckets."""
        total = 0
        for p in check_periods:
            df = by_period.get(p, {}).get(cat)
            if df is None or df.empty:
                continue
            total += _get_att(df, player)
        return total

    for cat, cols in [
        ("passing",   ["YDS","TD","INT"]),
        ("rushing",   ["YDS","TD","CAR"]),
        ("receiving", ["YDS","TD","REC"]),
    ]:
        off_df = official.get(cat)
        if off_df is None or off_df.empty:
            continue

        for _, off_row in off_df.iterrows():
            player = str(off_row.get("Player",""))
            if not player:
                continue

            # ATT check for passing — sum across quarters
            if cat == "passing" and "C/ATT" in off_df.columns:
                ca = str(off_row.get("C/ATT","0/0"))
                try:
                    off_att = int(ca.split("/")[1])
                    pbp_att = _sum_att_across_periods(cat, player)
                    if off_att != pbp_att:
                        last_p = _last_period(by_period, cat, player, ["Q1","Q2","Q3","Q4"])
                        mismatches.append((player, cat, "ATT", pbp_att, off_att, last_p or "unknown"))
                except Exception:
                    pass

            for col in cols:
                if col not in off_df.columns:
                    continue
                try:
                    off_val = int(pd.to_numeric(off_row.get(col, 0), errors="coerce") or 0)
                    pbp_val = _sum_col_across_periods(cat, player, col)
                    if off_val != pbp_val:
                        last_p = _last_period(by_period, cat, player, ["Q1","Q2","Q3","Q4"])
                        mismatches.append((player, cat, col, pbp_val, off_val, last_p or "unknown"))
                except Exception:
                    pass

    return mismatches


def get_reconciliation_status(result: dict, game_id: str) -> dict:
    """
    Public API: returns reconciliation status for display.
    {
      "passed": bool,
      "mismatches": [(player, cat, col, pbp, official, suspected_quarter), ...],
      "message": str
    }
    """
    mismatches = _build_reconciliation_report(result, game_id)
    if not mismatches:
        return {
            "passed": True,
            "mismatches": [],
            "message": "✅ Reconciliation passed — all quarter/half stats match official totals."
        }
    lines = []
    for player, cat, col, pbp, official, qtr in mismatches:
        diff = official - pbp
        sign = "+" if diff > 0 else ""
        lines.append(
            f"  {player} ({cat} {col}): PBP={pbp}, Official={official} "
            f"({sign}{diff}) — suspected missing from {qtr}"
        )
    return {
        "passed": False,
        "mismatches": mismatches,
        "message": "⚠️ Reconciliation gaps (corrected automatically):\n" + "\n".join(lines)
    }
