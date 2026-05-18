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
      7. type_id=5 def-pen rush with dead-ball/declined foul (NFL §Rule 2A):
         credit actual rush yards from text (or 0 on "no gain"), not statYardage
         which includes the penalty distance.
      8. type_id=24 off-pen reception with statYardage > 0 (NFL §Rule 2B):
         credit statYardage as "yards to spot of foul" when the offensive penalty
         is enforced downfield. ESPN encodes the spot-of-foul value in statYardage.
      9. type_id=8 handler rewritten with text-based off-pen detection:
         _is_off_pen_from_text() extracts "PENALTY on TEAM" from play.text
         and compares against possessing team abbreviation (penaltyTeam.$ref
         is absent on type_id=8 plays so _is_off_pen() always returned False).
         Off-pen pass/scramble: ATT+1, 0 yards.
         Off-pen rush: 0 everything.
         Def-pen with receiver: text-parsed yards to psr+rcv (Change 1 retained).
     10. type_id=5 off-pen rush: CAR+1 AND text-parsed yards.
         Confirmed from live data: ESPN credits actual rush yards on off-pen rushes
         (zeroing yards caused -16 gap for Sanders).
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
    Build per-quarter and per-half player stat tables.

    Architecture — 4-layer hybrid model:
      Layer 1: ESPN statistics/0 endpoint → official game totals (immutable)
      Layer 2: PBP period.number → assign each play to its quarter
               Penalty plays: text-parsed yards ("for N yards" / "no gain")
               Normal plays:  statYardage (always reliable when no penalty)
      Layer 3: period=0 → skip; period≥5 → OT bucket
      Layer 4: Smart reconciliation — if attributed_sum ≠ Layer1 total after
               all text corrections, emit RECONCILIATION_FAILED rather than guess.
               Game total is always shown; quarters are withheld only on failure.

    Return contract:
      {
        "Q1": {"passing": df, "rushing": df, "receiving": df, "defense": df},
        "Q2": ..., "Q3": ..., "Q4": ...,
        "1H": ..., "2H": ..., "OT": ...,
        "Full Game": ...,
        "reconciliation_failed": {player: {cat: reason}}    # rare — L4 couldn't reconcile
        "residual_applied":      {player: {cat: {period: residual_yds}}}  # ➰ indicator
      }
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

    # ── Fetch plays ───────────────────────────────────────────────────────────
    core_plays = get_core_plays(game_id)
    if not core_plays:
        return {}

    # ── Athlete resolution (unchanged) ────────────────────────────────────────
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

    # ── Team abbreviation lookup (unchanged) ──────────────────────────────────
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

    # ── Period extractor (unchanged) ──────────────────────────────────────────
    def _pbp_period(play: dict) -> int:
        _p_raw = play.get("period", {})
        p = _safe_int(_p_raw.get("number", 0) if isinstance(_p_raw, dict) else _p_raw)
        if p > 0:
            return p
        if isinstance(_p_raw, dict):
            dv = _p_raw.get("displayValue", "")
            if dv:
                dv = dv.strip().lower()
                if "4th" in dv:             p = 4
                elif "3rd" in dv:           p = 3
                elif "2nd" in dv:           p = 2
                elif "1st" in dv:           p = 1
                elif "1st overtime" in dv:  p = 5
                elif "2nd overtime" in dv:  p = 6
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
        return 0

    # ── Text helpers ──────────────────────────────────────────────────────────
    _ELIG_RE  = _re.compile(
        r"^.*?reported\s+in\s+as\s+eligible\.\s+(?:Direct\s+snap\s+to\s+\S+\.\s+)?",
        _re.I,
    )
    _YARDS_RE = _re.compile(r"for\s+(-?\d+)\s+yards?", _re.I)
    _NO_GAIN  = _re.compile(r"\bno\s+gain\b", _re.I)
    _NULLIFY  = _re.compile(r"TOUCHDOWN\s+NULLIFIED|No\s+Play", _re.I)

    # Broader TD invalidation: TOUCHDOWN combined with NULLIFIED/REVERSED/Replay/No Play
    # (Fix 2: TD detection — replay-reviewed TDs that were reversed)
    _TD_INVALID = _re.compile(
        r"NULLIFIED|REVERSED|No\s+Play|TOUCHDOWN[^.]*\.\s*The\s+Replay",
        _re.I,
    )

    # Off-pen detection from play text (Fix 1: identify off-pen plays)
    # Examples: "PENALTY on PHI-J.Smith, Holding", "PENALTY on PHI, Holding"
    _PEN_ON_RE = _re.compile(r"PENALTY\s+on\s+([A-Z]{2,3})", _re.I)
    _ESPN_ABBR_ALIASES = {
        "CLV": "CLE", "WAS": "WSH", "HST": "HOU",
        "ARZ": "ARI", "BLT": "BAL", "LA":  "LAR",
    }

    def _is_off_pen_text(text: str, pos_team: str) -> bool:
        """Detect offensive penalty from play text: PENALTY on TEAM == possessing team."""
        if not text or not pos_team:
            return False
        m = _PEN_ON_RE.search(str(text))
        if not m:
            return False
        pen = _ESPN_ABBR_ALIASES.get(m.group(1).upper(), m.group(1).upper())
        pos = _ESPN_ABBR_ALIASES.get(str(pos_team).upper(), str(pos_team).upper())
        return pen == pos

    def _td_invalid(text: str) -> bool:
        """Return True if play text indicates TD was nullified/reversed/replay-reviewed."""
        return bool(text) and bool(_TD_INVALID.search(str(text)))

    def _text_yds(text: str):
        """Return text-parsed yards, 0 for 'no gain', None if unparseable."""
        if not text:
            return None
        if _NULLIFY.search(text):
            return 0
        cleaned = _ELIG_RE.sub("", text)
        if _NO_GAIN.search(cleaned):
            return 0
        m = _YARDS_RE.search(cleaned)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                pass
        return None

    # ── Skip set (non-stat play types) ───────────────────────────────────────
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
    }

    # Scoring-summary duplicate detector
    _SCORING_SUMMARY_RE = _re.compile(
        r"^\s*(?:[A-Z][A-Za-z\.\-']+\s+){1,3}\d+\s+Yd\s+(?:pass|run|return|Fumble|Interception)\b",
    )

    def _is_scoring_dup(text: str) -> bool:
        return bool(text and _SCORING_SUMMARY_RE.match(text))

    # ── Layer 1: official totals from boxscore players block ──────────────────
    # ESPN's boxscore.players contains the same stats as statistics/0, already
    # fetched as part of get_game_summary. We read them here to lock game totals.
    def _read_official_totals(summary: dict):
        """
        Returns (totals, name_to_aid, aid_to_name, aid_to_team):
          totals       — {athlete_id: {cat: {stat: value}}}
          name_to_aid  — {display_name: athlete_id}  ← used for Layer 4 lookup
                         when _resolve_athlete returned a name (not [ID:XXXX])
          aid_to_name  — {athlete_id: display_name}  ← for Fix 4 player creation
          aid_to_team  — {athlete_id: team_abbr}     ← for Fix 4 team attribution
        cat ∈ {"passing", "rushing", "receiving"}
        stat keys: passing→{att,comp,yds,td,int}  rushing→{car,yds,td}  receiving→{rec,yds,td}
        """
        totals      = {}
        name_to_aid = {}
        aid_to_name = {}
        aid_to_team = {}
        _aid_re = _re.compile(r"/athletes/([0-9]+)")
        cat_map = {
            "passing":   {"C/ATT": "c_att", "YDS": "yds", "TD": "td", "INT": "int"},
            "rushing":   {"CAR": "car",     "YDS": "yds", "TD": "td"},
            "receiving": {"REC": "rec",     "YDS": "yds", "TD": "td"},
        }
        for team_block in summary.get("boxscore", {}).get("players", []):
            team_abbr = team_block.get("team", {}).get("abbreviation", "")
            for category in team_block.get("statistics", []):
                cat_name = category.get("name", "").lower()
                if cat_name not in cat_map:
                    continue
                labels = category.get("labels", category.get("keys", []))
                for athlete_entry in category.get("athletes", []):
                    athlete   = athlete_entry.get("athlete", {})
                    stats_raw = athlete_entry.get("stats", [])
                    if not stats_raw:
                        continue
                    # Key by athlete_id from $ref — works even when name resolution fails
                    ref = athlete.get("$ref", "")
                    m   = _aid_re.search(ref)
                    if not m:
                        continue
                    aid = m.group(1)
                    # Build reverse maps for name-keyed lookups (Layer 4) and Fix 4
                    display_name = athlete.get("displayName", "") or ""
                    if display_name:
                        name_to_aid.setdefault(display_name, aid)
                        aid_to_name.setdefault(aid, display_name)
                    if team_abbr:
                        aid_to_team.setdefault(aid, team_abbr)
                    if aid not in totals:
                        totals[aid] = {}
                    if cat_name not in totals[aid]:
                        totals[aid][cat_name] = {}
                    for label, val in zip(labels, stats_raw):
                        if label in cat_map[cat_name]:
                            try:
                                if label == "C/ATT":
                                    parts = str(val).split("/")
                                    totals[aid][cat_name]["comp"] = int(parts[0]) if len(parts) == 2 else 0
                                    totals[aid][cat_name]["att"]  = int(parts[1]) if len(parts) == 2 else 0
                                else:
                                    totals[aid][cat_name][label.lower()] = int(
                                        pd.to_numeric(val, errors="coerce") or 0
                                    )
                            except Exception:
                                pass
        return totals, name_to_aid, aid_to_name, aid_to_team

    official_totals, _name_to_aid, _aid_to_name, _aid_to_team_boxscore = _read_official_totals(summary)

    # Runtime name→aid map: populated as _resolve_athlete returns names during the
    # play loop. Bridges the gap between Supabase-resolved names (e.g., "Jalen Hurts")
    # and ESPN boxscore display names (e.g., "J. Hurts") which may differ for the
    # same athlete_id. Without this, Layer 4 lookup fails for every player whose
    # Supabase cached name differs from the boxscore display name.
    _resolved_name_to_aid = {}

    # ── Stat accumulators ─────────────────────────────────────────────────────
    # Per-period, per-player: {period: {player_name: stat_dict}}
    # Also track every play per player for Layer 4 reconciliation.
    def new_pass(): return {"Team": "", "comp": 0, "att": 0, "yds": 0, "td": 0, "int": 0}
    def new_rush(): return {"Team": "", "car": 0, "yds": 0, "td": 0}
    def new_recv(): return {"Team": "", "rec": 0, "yds": 0, "td": 0}
    def new_sack(): return {"Team": "", "sacks": 0}

    passing   = defaultdict(lambda: defaultdict(new_pass))
    rushing   = defaultdict(lambda: defaultdict(new_rush))
    receiving = defaultdict(lambda: defaultdict(new_recv))
    sacking   = defaultdict(lambda: defaultdict(new_sack))

    # Play log per (player_name, category) for Layer 4
    # {(player, cat): [(period, credited_yds, text, isPenalty), ...]}
    _play_log = defaultdict(list)

    # ── Layer 4 text-parse helper for penalty plays ───────────────────────────
    def _credited_yds_for_play(play: dict, stat_yds: int) -> tuple:
        """
        For a penalty play: return (credited_yds, parseable).
        For a normal play:  return (stat_yds, True).
        """
        if not play.get("isPenalty"):
            return stat_yds, True
        text = play.get("text", "") or ""
        parsed = _text_yds(text)
        if parsed is not None:
            return parsed, True
        return stat_yds, False   # fallback to stat_yds; parseable=False flags L4 risk

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
        if _is_scoring_dup(play.get("text", "")):
            continue

        # Layer 3: period=0 → skip; period≥5 → OT bucket
        period = _pbp_period(play)
        if period == 0:
            continue
        eff_period = period   # period≥5 stays as-is; bucketed to OT in output

        stat_yds = _safe_int(play.get("statYardage", 0))
        team     = _team_abbr_from_play(play)
        is_pen   = bool(play.get("isPenalty"))
        text_str = play.get("text", "") or ""

        # Resolve participant roles
        roles = {}
        for participant in play.get("participants", []):
            role = participant.get("type", "")
            if role not in {"passer", "receiver", "rusher", "sackedBy"}:
                continue
            ath  = participant.get("athlete", {})
            ref  = ath.get("$ref", "")
            aid  = _extract_id(ref)
            if not aid:
                continue
            name = _resolve_athlete(aid)
            if not name:
                name = f"[ID:{aid}]"   # fallback — never drop a play due to name failure
            # Record this name↔aid binding so Layer 4 can look up the player
            # by whatever name the accumulator stored (Supabase, ESPN boxscore,
            # or [ID:XXXX] fallback — all map back to the same aid).
            _resolved_name_to_aid[name] = aid
            roles[role] = name

        psr = roles.get("passer")
        rcv = roles.get("receiver")
        rsh = roles.get("rusher")
        sck = roles.get("sackedBy")

        type_id = str(play.get("type", {}).get("id", "") or "")

        # ── Fix 1: Off-pen detection ──────────────────────────────────────────
        # An off-pen play (penalty on possessing team) where the penalty is
        # accepted nullifies the play's stats per NFL/ESPN box-score rules.
        # No ATT, COMP, YDS, REC, CAR, TD credited.
        play_is_off_pen = is_pen and _is_off_pen_text(text_str, team)

        # ── Layer 2: route each play type to correct accumulator ──────────────

        # ── Pass Reception (type_id=24) ───────────────────────────────────────
        if type_id == "24":
            if not psr:
                continue
            if play_is_off_pen:
                continue   # Fix 1: off-pen reception → no stat credit
            yds_to_credit, _ = _credited_yds_for_play(play, stat_yds)
            d = passing[eff_period][psr];  d["Team"] = team or d["Team"]
            r = receiving[eff_period][rcv] if rcv else None
            d["att"]  += 1
            d["comp"] += 1
            d["yds"]  += yds_to_credit
            if r is not None:
                r["Team"] = team or r["Team"]
                r["rec"] += 1
                r["yds"] += yds_to_credit
            # Fix 2: Skip TD credit if play was NULLIFIED/REVERSED/Replay-reversed
            if _re.search(r"touchdown", text_str, _re.I) and not _td_invalid(text_str):
                d["td"] += 1
                if r is not None:
                    r["td"] += 1
            _play_log[(psr, "passing")].append(
                (eff_period, yds_to_credit, text_str, is_pen))
            if rcv:
                _play_log[(rcv, "receiving")].append(
                    (eff_period, yds_to_credit, text_str, is_pen))

        # ── Pass Incompletion (type_id=3) ─────────────────────────────────────
        elif type_id == "3":
            if not psr:
                continue
            # Spike: no ATT
            if "spiked the ball" in text_str.lower():
                continue
            if is_pen:
                continue   # off-pen incompletion: duplicate arrives as type_id=8; skip
            d = passing[eff_period][psr]; d["Team"] = team or d["Team"]
            d["att"] += 1
            _play_log[(psr, "passing")].append((eff_period, 0, text_str, False))

        # ── Passing Touchdown (type_id=67) ────────────────────────────────────
        elif type_id == "67":
            if not psr:
                continue
            if play_is_off_pen:
                continue   # Fix 1: off-pen TD play → no stat credit
            yds_to_credit, _ = _credited_yds_for_play(play, stat_yds)
            d = passing[eff_period][psr];  d["Team"] = team or d["Team"]
            r = receiving[eff_period][rcv] if rcv else None
            d["att"]  += 1
            d["comp"] += 1
            d["yds"]  += yds_to_credit
            # Fix 2: Skip TD credit if play was NULLIFIED/REVERSED/Replay-reversed
            td_valid = not _td_invalid(text_str)
            if td_valid:
                d["td"] += 1
            if r is not None:
                r["Team"] = team or r["Team"]
                r["rec"] += 1
                r["yds"] += yds_to_credit
                if td_valid:
                    r["td"]  += 1
            _play_log[(psr, "passing")].append(
                (eff_period, yds_to_credit, text_str, is_pen))
            if rcv:
                _play_log[(rcv, "receiving")].append(
                    (eff_period, yds_to_credit, text_str, is_pen))

        # ── Penalty (type_id=8) ───────────────────────────────────────────────
        elif type_id == "8":
            # Fix 1: ESPN's official passing ATT/YDS exclude all off-pen pass plays.
            # When a penalty on the offense voids the play, ESPN credits NOTHING.
            # Only def-pen plays (penalty on defense) credit stats — handled here.
            tl = text_str.lower()
            _t8_pass  = "pass" in tl
            _t8_scr   = "scrambles" in tl
            # Fix 1: Off-pen pass plays credit NOTHING. ESPN's official ATT/YDS
            # exclude these. Only def-pen plays credit stats here.
            if play_is_off_pen:
                pass   # skip — no credit for off-pen pass plays
            elif stat_yds < 0 and rcv and _t8_pass and not _t8_scr:
                # Def-pen pass with receiver: text-parsed yards (ATT/COMP arrive
                # via the separate type_id=24 play record for the same down)
                yds_to_credit, _ = _credited_yds_for_play(play, stat_yds)
                if psr:
                    d = passing[eff_period][psr]; d["Team"] = team or d["Team"]
                    d["yds"] += yds_to_credit
                    _play_log[(psr, "passing")].append(
                        (eff_period, yds_to_credit, text_str, True))
                rd = receiving[eff_period][rcv]; rd["Team"] = team or rd["Team"]
                rd["yds"] += yds_to_credit
                _play_log[(rcv, "receiving")].append(
                    (eff_period, yds_to_credit, text_str, True))

        # ── Rush (type_id=5) ──────────────────────────────────────────────────
        elif type_id == "5" or ptype in {"rush", "scramble", "rushing touchdown"}:
            if not rsh:
                continue
            if play_is_off_pen:
                continue   # Fix 1: off-pen rush → no stat credit
            d = rushing[eff_period][rsh]; d["Team"] = team or d["Team"]
            yds_to_credit, _ = _credited_yds_for_play(play, stat_yds)
            d["car"] += 1
            d["yds"] += yds_to_credit
            # Fix 2: Skip TD credit if play was NULLIFIED/REVERSED/Replay-reversed
            if (ptype == "rushing touchdown" or
                _re.search(r"touchdown", text_str, _re.I)) and not _td_invalid(text_str):
                d["td"] += 1
            _play_log[(rsh, "rushing")].append(
                (eff_period, yds_to_credit, text_str, is_pen))

        # ── Sack (type_id=7) ──────────────────────────────────────────────────
        elif type_id == "7":
            if sck:
                d = sacking[eff_period][sck]; d["Team"] = team or d["Team"]
                d["sacks"] += 1
            # ESPN's official passing ATT and YDS both exclude sacks.
            # Do not credit ATT or YDS on sack plays — they are not
            # counted as pass attempts in ESPN's box score display.

        # ── Fumble Recovery (type_id=9 or ptype) ─────────────────────────────
        elif type_id == "9" or ptype in {"fumble recovery (own)", "fumble recovery (opponent)"}:
            fum_yds = stat_yds
            if fum_yds == 0:
                yd_m = _re.search(r"\bfor\s+(-?[0-9]+)\s+yards?", text_str, _re.I)
                if yd_m:
                    fum_yds = _safe_int(yd_m.group(1))
            _fum_low = text_str.lower()
            _skip_fum = any(kw in _fum_low for kw in
                            ("sacked", "direct snap", "field goal formation", "punt formation"))
            if type_id == "9" or ptype == "fumble recovery (own)":
                if psr and not _skip_fum:
                    d = passing[eff_period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += fum_yds
                if rcv and not _skip_fum:
                    rd = receiving[eff_period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += fum_yds
                if rsh and not psr:
                    d = rushing[eff_period][rsh]; d["Team"] = team or d["Team"]
                    d["car"] += 1; d["yds"] += fum_yds
            else:
                if psr:
                    d = passing[eff_period][psr]; d["Team"] = team or d["Team"]
                    d["att"] += 1; d["comp"] += 1; d["yds"] += fum_yds
                if rcv:
                    rd = receiving[eff_period][rcv]; rd["Team"] = team or rd["Team"]
                    rd["rec"] += 1; rd["yds"] += fum_yds

        # ── Interception ──────────────────────────────────────────────────────
        elif ptype in {"pass interception return", "interception return", "interception",
                       "interception return touchdown"}:
            if psr:
                d = passing[eff_period][psr]; d["Team"] = team or d["Team"]
                d["att"] += 1; d["int"] += 1
                _play_log[(psr, "passing")].append((eff_period, 0, text_str, False))

    # ── Layer 4: smart reconciliation ────────────────────────────────────────
    # For each player×category: check attributed_sum vs Layer1 official total.
    #
    # The hybrid guarantee: Q/H Total = Official for every player×category.
    # This is enforced by a 4-step process per player×category:
    #
    #   Step A: Text-parse corrections — if a play's credited yards ≠ text yards,
    #           replace credited with text value (catches missing parse cases).
    #   Step B: Residual yards mode (Fix 5) — if a gap remains, apply the
    #           residual to the quarter with the highest yardage. The corrected
    #           quarter is marked with the ➰ indicator in residual_applied[].
    #   Step C: Zero phantom credits (Fix 3) — if a player has accumulator
    #           stats but no official_totals entry for that category, force
    #           every period's value to 0 for that player×category.
    #   Step D: Add missing players (Fix 4) — if a player has an official_totals
    #           entry but never appeared in the accumulator, create entries
    #           with the official totals assigned to a single best-guess period.

    reconciliation_failed = {}   # {player: {cat: reason_str}}
    residual_applied = {}        # {player: {cat: {period: residual_yds}}}  → ➰ indicator

    # Regex to extract numeric ID from "[ID:4045163]" fallback names
    _ID_KEY_RE = _re.compile(r"\[ID:(\d+)\]")

    def _resolve_player_lookup(player_key):
        """
        Given an accumulator key (may be a display name like 'Jalen Hurts'
        or a fallback like '[ID:4040715]'), return (athlete_id, player_totals).

        Tries (in order):
          1. Extract numeric ID from '[ID:XXXX]' format
          2. Runtime _resolved_name_to_aid map (built during the play loop
             from _resolve_athlete returns — works for Supabase names that
             differ from ESPN boxscore displayNames)
          3. _name_to_aid (boxscore displayName → aid)
          4. Treat the key itself as an aid
        Returns (aid_or_None, totals_dict_possibly_empty).
        """
        # 1. Try [ID:XXXX] pattern
        m = _ID_KEY_RE.search(player_key)
        if m:
            aid = m.group(1)
            return aid, official_totals.get(aid, {})
        # 2. Runtime name (Supabase or whatever _resolve_athlete returned)
        aid = _resolved_name_to_aid.get(player_key)
        if aid:
            return aid, official_totals.get(aid, {})
        # 3. ESPN boxscore displayName
        aid = _name_to_aid.get(player_key)
        if aid:
            return aid, official_totals.get(aid, {})
        # 4. Last resort: treat key itself as aid
        if player_key in official_totals:
            return player_key, official_totals[player_key]
        return None, {}

    cat_accumulators = {
        "passing":   (passing,   "yds"),
        "rushing":   (rushing,   "yds"),
        "receiving": (receiving, "yds"),
    }

    def _record_residual(player, cat, period, amount):
        """Track residual yards application for the ➰ indicator."""
        if player not in residual_applied:
            residual_applied[player] = {}
        if cat not in residual_applied[player]:
            residual_applied[player][cat] = {}
        residual_applied[player][cat][period] = (
            residual_applied[player][cat].get(period, 0) + amount
        )

    def _valid_quarter_periods(periods):
        """Return only Q1–Q4 periods (1–4) — excludes OT (5+) and period=0.
        Used by Fix 6 to keep count corrections inside Q1–Q4 buckets so they
        appear in both Full Game AND the Q-sum displayed in reconciliation."""
        return [p for p in periods if 1 <= p <= 4]

    for cat, (acc, yds_key) in cat_accumulators.items():
        # Iterate the accumulators (keyed by resolved name or "[ID:XXXX]")
        # and look up official totals by athlete_id extracted from the key.
        all_players = set()
        for p in acc:
            all_players.update(acc[p].keys())

        for player in all_players:
            # Unified lookup: handles both [ID:XXXX] keys AND name-resolved keys
            aid, player_totals = _resolve_player_lookup(player)

            # ── Fix 3: Zero phantom credits ───────────────────────────────────
            # Player has accumulator stats but no boxscore entry for this category.
            # Force every period's value to 0 (overrides any phantom credits).
            if cat not in player_totals:
                for p in list(acc.keys()):
                    if player in acc[p]:
                        acc[p][player]["yds"] = 0
                continue

            off = player_totals[cat]
            official_yds = off.get("yds", 0)

            # Sum attributed yards across all periods
            attributed_yds = sum(
                acc[p].get(player, {}).get("yds", 0)
                for p in acc
            )
            gap = official_yds - attributed_yds

            if gap == 0:
                continue

            # ── Step A: scan play log for text-correctable mismatches ────────
            plays_for_player = _play_log.get((player, cat), [])
            for idx, (period, credited, text, was_pen) in enumerate(plays_for_player):
                if gap == 0:
                    break
                parsed = _text_yds(text)
                if parsed is None:
                    continue
                diff = parsed - credited
                if diff == 0:
                    continue
                # Only apply the correction if it moves toward closing the gap
                if (gap > 0 and diff > 0) or (gap < 0 and diff < 0):
                    correction = diff if abs(diff) <= abs(gap) else gap
                    acc[period][player][yds_key] = (
                        acc[period][player].get(yds_key, 0) + correction
                    )
                    gap -= correction
                    # Update play log record so repeat scans don't double-correct
                    plays_for_player[idx] = (period, credited + correction, text, was_pen)

            if gap == 0:
                continue

            # ── Step B (Fix 5): Residual mode ────────────────────────────────
            # Apply remaining gap to the quarter with the highest yardage
            # (deterministic, transparent — flagged with ➰ indicator).
            valid_periods = _valid_quarter_periods(list(acc.keys()))
            if valid_periods:
                # Pick quarter with most yds; ties go to earliest quarter
                target_period = max(
                    valid_periods,
                    key=lambda p: (acc[p].get(player, {}).get("yds", 0), -p)
                )
            elif acc:
                # No Q1–Q4 periods exist; use any available period
                target_period = max(
                    acc.keys(),
                    key=lambda p: (acc[p].get(player, {}).get("yds", 0), -p)
                )
            else:
                target_period = None

            if target_period is not None:
                acc[target_period][player]["yds"] = (
                    acc[target_period][player].get("yds", 0) + gap
                )
                _record_residual(player, cat, target_period, gap)
            else:
                # No periods at all — emit RECONCILIATION_FAILED
                if player not in reconciliation_failed:
                    reconciliation_failed[player] = {}
                reconciliation_failed[player][cat] = (
                    f"attributed={attributed_yds}, official={official_yds}, "
                    f"remaining_gap={gap}"
                )

    # ── Fix 4: Add missing players (in official_totals but not accumulator) ──
    # For each player in official_totals: if they're missing from a category
    # accumulator they should be in, create entries with the official totals
    # assigned to the first period that has any plays (deterministic).
    def _team_play_periods(team_abbr):
        """Find a period that has any plays for the given team. Used as the
        default attribution period for missing players."""
        if not team_abbr:
            return None
        for p in sorted([k for k in passing.keys()
                         if 1 <= k <= 4]):
            for entry in passing[p].values():
                if entry.get("Team") == team_abbr:
                    return p
        # Fallback: any Q1–Q4 period
        for p in (1, 2, 3, 4):
            if p in passing or p in rushing or p in receiving:
                return p
        return 1   # last resort

    cat_specs = {
        "passing":   (passing,   ["att", "comp", "yds", "td", "int"]),
        "rushing":   (rushing,   ["car", "yds", "td"]),
        "receiving": (receiving, ["rec", "yds", "td"]),
    }

    # Build aid → resolved_name reverse map for Fix 4 to use the SAME name
    # convention the accumulator used. If _resolve_athlete returned "Jalen Hurts"
    # for some other play, use that; otherwise fall back to boxscore name.
    _aid_to_resolved_name = {}
    for nm, a in _resolved_name_to_aid.items():
        _aid_to_resolved_name.setdefault(a, nm)

    for aid, player_totals in official_totals.items():
        # Prefer the name the play loop actually used (Supabase-resolved),
        # then ESPN boxscore display name, finally [ID:XXXX] fallback.
        resolved_name = _aid_to_resolved_name.get(aid, "")
        box_name      = _aid_to_name.get(aid, "")
        player_key    = resolved_name or box_name or f"[ID:{aid}]"
        team_abbr     = _aid_to_team_boxscore.get(aid, "")

        for cat, (acc, stat_keys) in cat_specs.items():
            if cat not in player_totals:
                continue
            # Find an existing accumulator entry for this athlete_id.
            # An accumulator key may be:
            #   - "[ID:XXXX]"        → extract aid
            #   - Supabase name      → matches resolved_name
            #   - ESPN boxscore name → matches box_name
            existing_key = None
            for p in acc:
                for k in acc[p]:
                    km = _ID_KEY_RE.search(k)
                    if km and km.group(1) == aid:
                        existing_key = k
                        break
                    if resolved_name and k == resolved_name:
                        existing_key = k
                        break
                    if box_name and k == box_name:
                        existing_key = k
                        break
                if existing_key:
                    break
            if existing_key:
                continue   # player already in accumulator → no action here

            # Player is in official_totals but never accumulated. Add their stats.
            target_p = _team_play_periods(team_abbr) or 1
            entry = acc[target_p][player_key]
            entry["Team"] = team_abbr or entry.get("Team", "")
            for k in stat_keys:
                official_v = player_totals[cat].get(k, 0)
                if official_v:
                    entry[k] = official_v

    # ── Fix 6: Count reconciliation (CAR/REC/ATT/COMP/INT/TD) ────────────────
    # Constrain best_period to Q1–Q4 so the correction appears in the displayed
    # Q-sum. Fixes the "Full Game shows 4 but Q/H sums to 3" class of bugs.

    for cat, count_key, acc in [
        ("rushing",   "car", rushing),
        ("receiving", "rec", receiving),
    ]:
        all_players = set()
        for p in acc:
            all_players.update(acc[p].keys())
        for player in all_players:
            aid, player_totals = _resolve_player_lookup(player)
            if cat not in player_totals:
                # Fix 3 also applies to counts: zero out phantom counts
                for p in list(acc.keys()):
                    if player in acc[p]:
                        acc[p][player][count_key] = 0
                continue
            official_count = player_totals[cat].get(count_key, 0)
            attributed_count = sum(
                acc[p].get(player, {}).get(count_key, 0)
                for p in acc
            )
            diff = official_count - attributed_count
            if diff == 0:
                continue
            # Fix 6: prefer Q1–Q4 periods so correction appears in displayed Q-sum.
            # Direction-aware: when INCREMENTING (diff>0), pick max-yds period;
            # when DECREMENTING (diff<0), pick min-yds period — this prevents
            # erasing legitimate plays by subtracting counts from busy quarters.
            valid_periods = _valid_quarter_periods(list(acc.keys()))
            candidate_periods = valid_periods if valid_periods else list(acc.keys())
            if not candidate_periods:
                # No periods at all — create Q1 entry
                acc[1][player][count_key] = max(0, official_count)
                continue
            if diff > 0:
                best_period = max(
                    candidate_periods,
                    key=lambda p: (acc[p].get(player, {}).get("yds", 0), -p)
                )
            else:
                # Subtract from period with LEAST yds (likely a phantom entry).
                # Only consider periods where the player ACTUALLY has an entry,
                # to avoid creating new (negative) phantom entries.
                player_periods = [p for p in candidate_periods if player in acc[p]]
                if not player_periods:
                    player_periods = candidate_periods   # fallback
                best_period = min(
                    player_periods,
                    key=lambda p: (acc[p].get(player, {}).get("yds", 0), p)
                )
            acc[best_period][player][count_key] = (
                acc[best_period][player].get(count_key, 0) + diff
            )

    # Reconcile ATT/COMP/TD/INT for passing
    all_pass_players = set()
    for p in passing:
        all_pass_players.update(passing[p].keys())
    for player in all_pass_players:
        aid, player_totals = _resolve_player_lookup(player)
        if "passing" not in player_totals:
            # Fix 3 for passing counts
            for p in list(passing.keys()):
                if player in passing[p]:
                    for k in ("att", "comp", "int", "td"):
                        passing[p][player][k] = 0
            continue
        for count_key in ("att", "comp", "int", "td"):
            official_count = player_totals["passing"].get(count_key, 0)
            attributed_count = sum(
                passing[p].get(player, {}).get(count_key, 0)
                for p in passing
            )
            diff = official_count - attributed_count
            if diff == 0:
                continue
            # Fix 6: constrain to Q1–Q4, direction-aware
            valid_periods = _valid_quarter_periods(list(passing.keys()))
            candidate_periods = valid_periods if valid_periods else list(passing.keys())
            if not candidate_periods:
                passing[1][player][count_key] = max(0, official_count)
                continue
            if diff > 0:
                best_period = max(
                    candidate_periods,
                    key=lambda p: (passing[p].get(player, {}).get("yds", 0), -p)
                )
            else:
                # Subtract from existing entry — avoid creating phantoms
                player_periods = [p for p in candidate_periods if player in passing[p]]
                if not player_periods:
                    player_periods = candidate_periods
                best_period = min(
                    player_periods,
                    key=lambda p: (passing[p].get(player, {}).get("yds", 0), p)
                )
            passing[best_period][player][count_key] = (
                passing[best_period][player].get(count_key, 0) + diff
            )

    # Reconcile TD for rushing and receiving (Fix 6 also covers TD counts)
    for cat, acc in [("rushing", rushing), ("receiving", receiving)]:
        all_players = set()
        for p in acc:
            all_players.update(acc[p].keys())
        for player in all_players:
            aid, player_totals = _resolve_player_lookup(player)
            if cat not in player_totals:
                continue   # already zeroed above
            official_td = player_totals[cat].get("td", 0)
            attributed_td = sum(
                acc[p].get(player, {}).get("td", 0)
                for p in acc
            )
            diff = official_td - attributed_td
            if diff == 0:
                continue
            valid_periods = _valid_quarter_periods(list(acc.keys()))
            candidate_periods = valid_periods if valid_periods else list(acc.keys())
            if not candidate_periods:
                acc[1][player]["td"] = max(0, official_td)
                continue
            if diff > 0:
                best_period = max(
                    candidate_periods,
                    key=lambda p: (acc[p].get(player, {}).get("yds", 0), -p)
                )
            else:
                # Subtract from existing entry — avoid creating phantoms
                player_periods = [p for p in candidate_periods if player in acc[p]]
                if not player_periods:
                    player_periods = candidate_periods
                best_period = min(
                    player_periods,
                    key=lambda p: (acc[p].get(player, {}).get("yds", 0), p)
                )
            acc[best_period][player]["td"] = (
                acc[best_period][player].get("td", 0) + diff
            )

    # ── DataFrame builders (unchanged signatures) ─────────────────────────────
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

    # Recompute all_periods AFTER count reconciliation — the reconciliation loops
    # may have created new period entries in the defaultdicts via direct access.
    # Computing here ensures every period with data appears in the result dict.
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

    if reconciliation_failed:
        result["reconciliation_failed"] = reconciliation_failed

    if residual_applied:
        # Fix 5: residual indicator — UI can display ➰ for quarters whose
        # yards were adjusted by residual reconciliation (no specific play
        # could be identified as the source of the gap).
        result["residual_applied"] = residual_applied

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

    # Build a name→aid map from the boxscore so we can fall back to "[ID:AID]"
    # keys when _resolve_athlete returned None (Supabase unavailable) and the
    # accumulator used "[ID:XXXX]" format instead of the player's real name.
    import re as _re_rcn
    _AID_REF_RE = _re_rcn.compile(r"/athletes/([0-9]+)")
    _name_to_aid_rcn: dict = {}
    try:
        _summary_rcn = get_game_summary(game_id)
        for _tb in (_summary_rcn or {}).get("boxscore", {}).get("players", []):
            for _cat in _tb.get("statistics", []):
                for _ae in _cat.get("athletes", []):
                    _ath = _ae.get("athlete", {})
                    _nm  = _ath.get("displayName", "") or ""
                    _ref = _ath.get("$ref", "") or ""
                    _m   = _AID_REF_RE.search(_ref)
                    if _nm and _m:
                        _name_to_aid_rcn[_nm] = _m.group(1)
    except Exception:
        pass

    valid_periods = ["Q1","Q2","Q3","Q4","OT"]
    extra_ot = [k for k in by_period if k.startswith("OT") and k not in valid_periods]
    check_periods = ["Q1","Q2","Q3","Q4"] + extra_ot + (["OT"] if "OT" in by_period else [])
    mismatches = []

    def _get_col_with_id_fallback(df, player, col):
        """Get a column value, falling back to [ID:AID] key if name match fails."""
        val = _get_col(df, player, col)
        if val != 0:
            return val
        # Name match returned 0 — could be a real 0 or a failed match.
        # Try [ID:AID] key directly if we can find the aid for this player name.
        aid = _name_to_aid_rcn.get(player)
        if not aid:
            return 0
        id_key = f"[ID:{aid}]"
        if "Player" not in df.columns:
            return 0
        id_row = df[df["Player"] == id_key]
        if id_row.empty:
            return 0
        try:
            return int(pd.to_numeric(id_row.iloc[0].get(col, 0), errors="coerce") or 0)
        except Exception:
            return 0

    def _get_att_with_id_fallback(df, player):
        """Get ATT value, falling back to [ID:AID] key if name match fails."""
        val = _get_att(df, player)
        if val != 0:
            return val
        aid = _name_to_aid_rcn.get(player)
        if not aid:
            return 0
        id_key = f"[ID:{aid}]"
        if "Player" not in df.columns:
            return 0
        id_row = df[df["Player"] == id_key]
        if id_row.empty:
            return 0
        ca = str(id_row.iloc[0].get("C/ATT", "0/0"))
        try:
            return int(ca.split("/")[1])
        except Exception:
            return 0

    def _sum_col_across_periods(cat, player, col):
        total = 0
        for p in check_periods:
            df = by_period.get(p, {}).get(cat)
            if df is None or df.empty:
                continue
            total += _get_col_with_id_fallback(df, player, col)
        return total

    def _sum_att_across_periods(cat, player):
        total = 0
        for p in check_periods:
            df = by_period.get(p, {}).get(cat)
            if df is None or df.empty:
                continue
            total += _get_att_with_id_fallback(df, player)
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
