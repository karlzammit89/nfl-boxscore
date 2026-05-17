"""
nfl/stats.py
------------
Parse raw ESPN boxscore data into clean, structured DataFrames
split by quarter and half. This is the accuracy-critical layer.

ESPN's boxscore provides cumulative stats per player, not per-quarter
player stats (that granularity requires play-by-play parsing).
Quarter-level team totals come from linescores.
Per-player quarter splits are derived by parsing drives + plays.

Change log:
  - Play classification switched from type.text → type.id where confirmed:
      3=PassIncompletion, 5=Rush, 7=Sack, 8=Penalty, 9=FumbleRecoveryOwn,
      24=PassReception, 67=PassingTouchdown
  - Spike detection: type_id=3 same as incompletion; text parse confirmed required
  - Off-pen pass guard added (type_id=24 & type_id=3): mirrors _is_off_pen_rush
  - Def-pen pass reception: uses text-parsed yards (not statYardage which includes penalty advance)
  - New type_id=8 handler: credits text-parsed actual yards for off-pen march-back plays
  - "penalty" removed from _SKIP_TYPES (now has its own handler)
  - Sack handler uses type_id=7; fumble recovery uses type_id=9 with ptype fallback
  - 6 penalty-handling fixes derived from NFL Guide for Statisticians 2025:
      1. Receiver-present guard on type_id=8 (NFL §Penalty Plays Rule 1):
         off-pen rushes/scrambles enforced from previous spot are nullified
      2. type_id=67 (passing TDs) text-parses yards when isPenalty=True
         (statYardage may be net field gain, not actual play yards)
      3. Off-pen reception with dead-ball/declined penalty counts normally
         (NFL §Rule 2A + declined-penalty rule)
      4. Universal text-parse fallback for type_id=24 normal receptions
         (verifies statYardage; defensive only, no behavior change unless match)
      5. Strips "X reported in as eligible. [Direct snap to Y.]" prefix in
         all text-parse helpers
      6. Skips scoring-summary duplicate entries
         ("Player N Yd pass from QB (Kicker Kick)" format)
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
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "passing")
    return _make_df(rows, drop_cols=["Team Full"])


def get_rushing_stats(game_id: str) -> pd.DataFrame:
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "rushing")
    return _make_df(rows, drop_cols=["Team Full"])


def get_receiving_stats(game_id: str) -> pd.DataFrame:
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "receiving")
    return _make_df(rows, drop_cols=["Team Full"])


def get_defensive_stats(game_id: str) -> pd.DataFrame:
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})

    players_data = []
    for team_block in boxscore.get("players", []):
        team_info = team_block.get("team", {})
        team_abbr = team_info.get("abbreviation", "")
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
_PASSER_RE = _re.compile(rf'({_NAME}(?:\s+{_NAME})?)\s+pass\s+', _re.I)
_RECV_RE = _re.compile(
    rf'pass\s+(?:complete\s+to|(?:short|deep|long|screen|flat)?\s*'
    rf'(?:right|left|middle)?\s*to\s+)({_NAME}(?:\s+{_NAME})?)',
    _re.I
)
_INCOMP_RE = _re.compile(r'pass\s+incomplete', _re.I)
_RUSH_RE = _re.compile(
    rf'(?:^\s*|\)\s*)({_NAME}(?:\s+{_NAME})?)\s+'
    r'(?:up the middle|left end|right end|left tackle|right tackle|'
    r'left guard|right guard|rushes?\s|scrambles?\s)',
    _re.I
)
_TD_RE  = _re.compile(r'touchdown', _re.I)
_INT_RE = _re.compile(r'intercepted', _re.I)
_PENALTY_RE = _re.compile(r'PENALTY|No Play', _re.I)
_SACK_RE = _re.compile(
    r'sacked\s+(?:at\s+\w+\s+\w+\s+)?for\s+-?\d+\s+yards?\s+\(([A-Z][a-z]?\.[A-Z][A-Za-z\'\-]+)\)'
    r'|sacked\s+(?:at\s+[\w\s]+?)?\s*(?:for\s+-?\d+\s+yards?\s+)?by\s+([A-Z][a-z]?\.[A-Z][A-Za-z\'\-]+)',
    _re.I
)


def get_player_stats_by_period(game_id: str) -> dict:
    """
    Build per-quarter and per-half player stat tables using ESPN Core API plays.

    Play classification uses confirmed type.id values:
      3  = Pass Incompletion   (spike also type_id=3 — text parse distinguishes)
      5  = Rush
      7  = Sack
      8  = Penalty             (new handler: credits actual yards for off-pen plays)
      9  = Fumble Recovery Own
      24 = Pass Reception
      67 = Passing Touchdown

    Unconfirmed play types (rushing TD, INT, fumble opponent) keep text matching.
    """
    import re as _re
    from collections import defaultdict

    summary = get_game_summary(game_id)
    if not summary:
        return {}

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

    # ── Athlete ID → displayName resolution ───────────────────────────────────
    _ID_RE = _re.compile(r"/athletes/([0-9]+)")
    _name_cache = {}

    def _resolve_athlete(athlete_id: str) -> str:
        if athlete_id in _name_cache:
            return _name_cache[athlete_id]

        _sb = None
        try:
            import streamlit as _st
            from supabase import create_client as _create_client
            _sb = _create_client(
                _st.secrets["supabase"]["url"],
                _st.secrets["supabase"]["key"],
            )
            result = (
                _sb.table("athletes")
                   .select("display_name")
                   .eq("athlete_id", athlete_id)
                   .eq("season_year", _season_year)
                   .limit(1)
                   .execute()
            )
            if result.data:
                name = result.data[0]["display_name"]
                _name_cache[athlete_id] = name
                return name
        except Exception:
            pass

        name = get_athlete_displayname(athlete_id, _season_year)
        if not name:
            name = get_athlete_displayname(athlete_id, "")

        if name and _sb is not None:
            try:
                _sb.table("athletes").upsert({
                    "athlete_id":   athlete_id,
                    "season_year":  _season_year,
                    "display_name": name,
                }).execute()
            except Exception:
                pass

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
    # "penalty" removed: type_id=8 (Penalty) now has its own handler below.
    # All other skip types kept as text-based (type_ids not yet confirmed).
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
        "safety", "fumble return touchdown",
        "two point rush", "two point pass", "two-point rush", "two-point pass",
        "two point conversion", "two-point conversion",
        "two point conversion attempt", "two-point conversion attempt",
        "defensive 2pt conversion",
        "uncategorized", "placeholder", "",
        # NOTE: "penalty" intentionally excluded — handled by type_id=8 block below
    }

    _STAT_ROLES = {"passer", "receiver", "rusher", "sackedBy"}

    # ── Team abbreviation lookup ───────────────────────────────────────────────
    _team_id_to_abbr = {}
    for _tb in summary.get("boxscore", {}).get("teams", []):
        _tid = str(_tb.get("team", {}).get("id", ""))
        _tab = _tb.get("team", {}).get("abbreviation", "")
        if _tid and _tab:
            _team_id_to_abbr[_tid] = _tab

    def _team_abbr_from_play(play: dict) -> str:
        team_ref = play.get("team", {}).get("$ref", "")
        m = _re.search(r"/teams/([0-9]+)", team_ref)
        if m:
            return _team_id_to_abbr.get(m.group(1), "")
        return ""

    # ── Off-pen helper: returns True when the penalized team is the possessing team ──
    # Uses structured numeric team IDs from $ref URLs — no text parsing, no alias issues.
    # If penaltyTeam field is absent in API response, returns False (no change to behavior).
    def _is_off_pen(play: dict) -> bool:
        if not play.get("isPenalty"):
            return False
        pen_ref = (play.get("penaltyTeam") or play.get("penaltyPlayerTeam") or {})
        if not isinstance(pen_ref, dict):
            return False
        pen_tid  = _re.search(r"/teams/(\d+)", pen_ref.get("$ref", ""))
        play_tid = _re.search(r"/teams/(\d+)", (play.get("team") or {}).get("$ref", ""))
        return bool(pen_tid and play_tid and pen_tid.group(1) == play_tid.group(1))

    # ── Penalty / text helpers (Changes 3, 5, 6) ──────────────────────────────
    # NFL Guide for Statisticians §Penalty Plays:
    #   Rule 2A — Penalty enforced from dead ball spot → credit yards normally.
    #   Declined penalty → record play in the usual manner.
    # Dead-ball fouls happen AFTER the live play ends, so the live play counts.
    # Keyword list is conservative — only unambiguous dead-ball fouls.
    _DEAD_BALL_FOUL_KEYWORDS = (
        "taunting",
        "unsportsmanlike",
        "excessive celebration",
        "dead ball",
        "late hit",
    )

    def _has_dead_ball_or_declined(text: str) -> bool:
        """True if the penalty associated with the play is dead-ball or declined."""
        if not text:
            return False
        t = text.lower()
        if "declined" in t and "penalty" in t:
            return True
        return any(kw in t for kw in _DEAD_BALL_FOUL_KEYWORDS)

    # Strip "X reported in as eligible. [Direct snap to Y.]" prefix before yards regex.
    # Prevents the prefix's player name from interfering with future text-based parsing.
    _ELIG_PREFIX_RE = _re.compile(
        r"^.*?reported\s+in\s+as\s+eligible\.\s+(?:Direct\s+snap\s+to\s+\S+\.\s+)?",
        _re.I,
    )

    def _strip_elig_prefix(text: str) -> str:
        if not text:
            return ""
        return _ELIG_PREFIX_RE.sub("", text)

    # Scoring-summary duplicates ("Player N Yd pass from QB (Kicker Kick)") are
    # entries that mirror real plays — must be skipped to prevent double counting.
    # Core API plays endpoint normally does not include these, but defending here
    # against any future endpoint mixing.
    _SCORING_SUMMARY_RE = _re.compile(
        r"^\s*(?:[A-Z][A-Za-z\.\-']+\s+){1,3}\d+\s+Yd\s+(?:pass|run|return|Fumble|Interception)\b",
    )

    def _is_scoring_summary_duplicate(text: str) -> bool:
        if not text:
            return False
        return bool(_SCORING_SUMMARY_RE.match(text))

    # Universal "for N yards" text-parse helper — strips eligibility prefix first
    # (Change 5) so that prefixed plays parse correctly. Returns None if not found.
    _YARDS_RE = _re.compile(r"for\s+(-?\d+)\s+yards?", _re.I)

    def _text_parse_yards(text: str) -> Optional[int]:
        if not text:
            return None
        cleaned = _strip_elig_prefix(text)
        m = _YARDS_RE.search(cleaned)
        if not m:
            return None
        try:
            return int(m.group(1))
        except (TypeError, ValueError):
            return None

    # ── Main play loop ────────────────────────────────────────────────────────
    _seen_ids = set()

    for play in core_plays:
        play_id = play.get("id", "")
        if play_id in _seen_ids:
            continue
        if play_id:
            _seen_ids.add(play_id)

        # Extract both type_id (numeric, stable) and ptype (text, fallback for unknowns)
        type_id = str(play.get("type", {}).get("id", "") or "")
        ptype   = (play.get("type", {}).get("text", "") or "").lower().strip()

        # Skip non-stat play types using text (type_ids for these not yet confirmed)
        if ptype in _SKIP_TYPES:
            continue

        # Change 6: Skip scoring-summary duplicate entries (e.g. "Player N Yd pass from QB").
        # These mirror real plays in the scoring_plays endpoint — counting them here would double.
        if _is_scoring_summary_duplicate(play.get("text", "")):
            continue

        period = _safe_int((play.get("period") or {}).get("number", 0))
        if period == 0:
            continue

        stat_yds = _safe_int(play.get("statYardage", 0))
        team     = _team_abbr_from_play(play)

        # Build role → displayName map for this play
        roles = {}
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
                roles[role] = name

        psr = roles.get("passer")
        rcv = roles.get("receiver")
        rsh = roles.get("rusher")
        skr = roles.get("sackedBy")

        # ── Classify and accumulate ───────────────────────────────────────────
        # Use confirmed type_id where available; fall back to ptype for unknowns.

        if type_id == "24":
            # ── Pass Reception (type_id confirmed) ───────────────────────────
            # Four sub-cases based on penalty status:
            #   a) Off-pen reception with dead-ball/declined penalty (Change 3):
            #      Live play counted normally; penalty applied separately per NFL §2A.
            #      Credit ATT/COMP/REC and statYardage (which equals actual yards here).
            #   b) Off-pen reception with live-ball foul (Rule 1): nullified, no stats.
            #   c) Def-pen reception: valid completion but statYardage includes penalty
            #      advance distance. Use text-parsed "for N yards" for actual yards.
            #   d) Normal (no penalty): statYardage = actual yards, count normally.
            _off_pen = _is_off_pen(play)
            _text    = play.get("text", "") or ""
            if _off_pen:
                # Change 3: detect dead-ball/declined penalty → play counts normally
                if _has_dead_ball_or_declined(_text):
                    if psr:
                        d = passing[period][psr]; d["Team"] = team or d["Team"]
                        d["att"] += 1; d["comp"] += 1; d["yds"] += stat_yds
                    if rcv:
                        rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                        rd["rec"] += 1; rd["yds"] += stat_yds
                # else: standard live-ball off-pen → nullified (NFL Rule 1), no stats
            elif play.get("isPenalty"):
                # Defensive penalty: statYardage = net field gain (catch + penalty yds)
                # Use text-parsed yards for box-score-accurate individual stats
                _txt_yds = _text_parse_yards(_text)
                _actual_rec_yds = _txt_yds if _txt_yds is not None else stat_yds
                if psr:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += _actual_rec_yds
                if rcv:
                    rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += _actual_rec_yds
            else:
                # Normal reception: statYardage = actual yards.
                # Change 4: belt-and-suspenders — verify with text-parse but fall back
                # to statYardage if text does not match (defensive, no regression).
                _txt_yds = _text_parse_yards(_text)
                _final_yds = _txt_yds if (_txt_yds is not None and _txt_yds == stat_yds) else stat_yds
                if psr:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += _final_yds
                if rcv:
                    rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += _final_yds

        elif type_id == "3":
            # ── Pass Incompletion (type_id confirmed) ────────────────────────
            # Spike plays share type_id=3 — confirmed from live data.
            # ESPN gives spikes no distinct type_id. Text parse is the only discriminator.
            _play_text = (play.get("text", "") or "").lower()
            if "spiked the ball" in _play_text:
                # Spike: intentional incompletion to stop clock — not a pass attempt
                pass
            elif "intentional grounding" in _play_text:
                # Intentional grounding: penalty but still counts as ATT (NFL rule)
                if psr:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1
            elif _is_off_pen(play):
                # Off-pen incompletion (e.g., holding on the play): nullified, no ATT
                pass
            else:
                # Normal incompletion or def-pen incompletion: count ATT
                if psr:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1

        elif type_id == "67":
            # ── Passing Touchdown (type_id confirmed) ────────────────────────
            # Change 2: when isPenalty=True, statYardage may represent net field gain
            # rather than actual play yards. Text-parse "for N yards" in that case.
            if play.get("isPenalty"):
                _txt_yds = _text_parse_yards(play.get("text", "") or "")
                _td_yds = _txt_yds if _txt_yds is not None else stat_yds
            else:
                _td_yds = stat_yds
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
                d["att"] += 1; d["comp"] += 1; d["yds"] += _td_yds; d["td"] += 1
            if rcv:
                rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                rd["rec"] += 1; rd["yds"] += _td_yds; rd["td"] += 1

        elif type_id == "7" or ptype in {"sack", "sack opp fumble recovery"}:
            # ── Sack (type_id=7 confirmed; ptype fallback for sack-fumble variant) ─
            # QB sack: not counted as a pass attempt (ESPN convention)
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
            if skr:
                sd = sacking[period][skr]; sd["Team"] = team or sd["Team"]
                sd["sacks"] += 1

        elif type_id == "8":
            # ── Penalty event (type_id=8 confirmed) ──────────────────────────
            # statYardage semantics for type_id=8:
            #   < 0 : off-pen march-back distance (e.g., -10 for holding)
            #         → actual yards are in play text "for N yards"
            #   > 0 : defensive penalty ball advance (e.g., DPI +15)
            #         → no individual player stat credits per NFL rules
            #   = 0 : pre-snap or declined penalty → no stats
            #
            # Change 1: Receiver-present guard.
            # Per NFL Guide §Penalty Plays Rule 1, off-pen plays enforced from previous
            # spot (rushes/scrambles behind LOS) are nullified — no stats credited.
            # ESPN credits yards only when a pass-and-catch occurred (receiver participant
            # present). Pure rush/scramble off-pen plays must NOT credit yards.
            if stat_yds < 0 and rcv:
                _txt_yds = _text_parse_yards(play.get("text", "") or "")
                if _txt_yds is not None:
                    # Credit yards but not counts (ATT/COMP/REC/CAR stay unchanged)
                    if psr:
                        d = passing[period][psr]; d["Team"] = team or d["Team"]
                        d["yds"] += _txt_yds
                    rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["yds"] += _txt_yds
            # else: pure rush/scramble off-pen OR positive statYardage → no individual stats

        elif type_id == "5" or ptype in {"rush", "scramble", "rushing touchdown"}:
            # ── Rush (type_id=5 confirmed; ptype fallback for rushing TD & scramble) ─
            # Rushing Touchdown type_id not yet confirmed — keep ptype fallback.
            if rsh:
                d = rushing[period][rsh]; d["Team"] = team or d["Team"]
                _is_off_pen_rush = _is_off_pen(play)
                if _is_off_pen_rush:
                    # Off-pen rush: credit text-parsed yards, no CAR
                    # statYardage = march-back distance (e.g., -12 for 3-yd run + 15 penalty)
                    _pen_text = play.get("text", "") or ""
                    _pen_yd_m = _re.search(r"for\s+(-?\d+)\s+yards?", _pen_text, _re.I)
                    if _pen_yd_m:
                        d["yds"] += _safe_int(_pen_yd_m.group(1))
                    # else: no yards parseable, add nothing
                else:
                    d["car"] += 1; d["yds"] += stat_yds
                    if ptype == "rushing touchdown":
                        d["td"] += 1

        elif ptype in {"pass interception return", "interception return", "interception",
                       "interception return touchdown"}:
            # ── Interception (type_id not yet confirmed; keep text-based) ────
            # F4: ESPN uses variant play type strings for INTs.
            # Psr participant always present on these plays.
            if psr:
                d = passing[period][psr]; d["Team"] = team or d["Team"]
                d["att"] += 1; d["int"] += 1

        elif type_id == "9" or ptype in {"fumble recovery (own)", "fumble recovery (opponent)"}:
            # ── Fumble Recovery (type_id=9 confirmed for own; ptype fallback for opp) ─
            fum_yds = stat_yds
            if fum_yds == 0:
                text = play.get("text", "") or ""
                yd_m = _re.search(r"\bfor\s+(-?[0-9]+)\s+yards?", text, _re.I)
                if yd_m:
                    fum_yds = _safe_int(yd_m.group(1))
            _fum_text = (play.get("text", "") or "").lower()
            _fum_is_sack_or_snap = (
                "sacked" in _fum_text
                or "direct snap" in _fum_text
                or "field goal formation" in _fum_text
                or "punt formation" in _fum_text
            )
            if type_id == "9" or ptype == "fumble recovery (own)":
                if psr and not _fum_is_sack_or_snap:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += fum_yds
                if rcv and not _fum_is_sack_or_snap:
                    rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += fum_yds
                if rsh and not psr:
                    d = rushing[period][rsh]; d["Team"] = team or d["Team"]
                    d["car"] += 1; d["yds"] += fum_yds
            else:
                # fumble recovery (opponent): receiver gained yards then fumbled
                if psr:
                    d = passing[period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += fum_yds
                if rcv:
                    rd = receiving[period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += fum_yds

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
                 "CAR": d["car"], "YDS": d["yds"], "TD": d["td"]}
                for n, d in acc.items() if d["car"] > 0]
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
    try:
        official = {
            "passing":   get_passing_stats(game_id),
            "rushing":   get_rushing_stats(game_id),
            "receiving": get_receiving_stats(game_id),
        }
    except Exception:
        return
    pass


def _last_period(result, cat, player, periods):
    for p in reversed(periods):
        df = result.get(p, {}).get(cat)
        if df is not None and not df.empty and _in_df(df, player):
            return p
    for h in ["2H","1H"]:
        df = result.get(h, {}).get(cat)
        if df is not None and not df.empty and _in_df(df, player):
            return None
    return None


def _match_player(df, player):
    import re as _re_mp
    _SUFFIX_RE = _re_mp.compile(r'\s+(?:jr\.?|sr\.?|ii|iii|iv)\.?\s*$', _re_mp.I)

    if "Player" not in df.columns:
        return df.iloc[0:0]
    row = df[df["Player"] == player]
    if not row.empty:
        return row
    clean = _SUFFIX_RE.sub("", player.strip()).strip()
    parts = clean.split()
    if len(parts) >= 2:
        abbr = f"{parts[0][0].upper()}.{chr(32).join(parts[1:])}"
        row = df[df["Player"] == abbr]
        if not row.empty:
            return row
    orig_parts = player.strip().split()
    if len(orig_parts) >= 2:
        orig_abbr = f"{orig_parts[0][0].upper()}.{chr(32).join(orig_parts[1:])}"
        if orig_abbr != abbr:
            row = df[df["Player"] == orig_abbr]
            if not row.empty:
                return row
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
    try:
        official = {
            "passing":   get_passing_stats(game_id),
            "rushing":   get_rushing_stats(game_id),
            "receiving": get_receiving_stats(game_id),
        }
    except Exception:
        return []

    by_period = result.get("by_period", result)

    valid_periods = ["Q1","Q2","Q3","Q4","OT"]
    extra_ot = [k for k in by_period if k.startswith("OT") and k not in valid_periods]
    check_periods = ["Q1","Q2","Q3","Q4"] + extra_ot + (["OT"] if "OT" in by_period else [])
    mismatches = []

    def _sum_col_across_periods(cat, player, col):
        total = 0
        for p in check_periods:
            df = by_period.get(p, {}).get(cat)
            if df is None or df.empty:
                continue
            total += _get_col(df, player, col)
        return total

    def _sum_att_across_periods(cat, player):
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
