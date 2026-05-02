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
from .api import get_game_summary, get_linescore, get_scoring_plays


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
    Defensive stats.
    Typical cols: Player, Pos, Team, TOT, SOLO, SACKS, TFL, PD, QB HTS, TD
    """
    summary = get_game_summary(game_id)
    if not summary:
        return pd.DataFrame()
    boxscore = summary.get("boxscore", {})
    rows = _parse_player_stats(boxscore, "defensive")
    if not rows:
        rows = _parse_player_stats(boxscore, "defensiveTotals")
    return _make_df(rows, drop_cols=["Team Full"])


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
    Cols: Quarter, Half, Clock, Team, Type, Description, Away Score, Home Score
    """
    plays = get_scoring_plays(game_id)
    if not plays:
        return pd.DataFrame()

    rows = []
    for play in plays:
        period = _safe_int(play.get("period", 0))
        rows.append({
            "Quarter":     _quarter_label(period),
            "Half":        _period_to_half(period),
            "Clock":       play.get("clock", ""),
            "Team":        play.get("team_abbr", play.get("team", "")),
            "Type":        play.get("type", ""),
            "Description": play.get("description", ""),
            "Away Score":  _safe_int(play.get("away_score", 0)),
            "Home Score":  _safe_int(play.get("home_score", 0)),
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

    for drive in all_drives:
        if not drive:
            continue
        team_abbr = drive.get("team", {}).get("abbreviation", "")
        for play in drive.get("plays", []):
            period = _safe_int(play.get("period", {}).get("number", 0))
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

_PASS_RE = _re.compile(
    r'^(.+?)\s+pass\s+(complete|incomplete)\s+(?:to\s+(.+?)\s+for\s+(-?\d+)\s+yards?)?',
    _re.I
)
_PASS_YDS_RE = _re.compile(r'for\s+(-?\d+)\s+yards?', _re.I)
_RUSH_RE = _re.compile(
    r'^(.+?)\s+(?:rush(?:es)?|scrambles?|runs?|up the middle|left end|right end|left tackle|right tackle)\s*(?:to\s+\S+\s+)?for\s+(-?\d+)\s+yards?',
    _re.I
)
_RECV_RE  = _re.compile(r'pass complete to\s+(.+?)\s+for\s+(-?\d+)\s+yards?', _re.I)
_TD_RE    = _re.compile(r'touchdown', _re.I)
_INT_RE   = _re.compile(r'(?:is\s+)?intercepted(?:\s+by\s+\S+)?', _re.I)
_SACK_RE  = _re.compile(r'sacked', _re.I)


def get_player_stats_by_period(game_id: str) -> dict:
    """
    Build true per-quarter and per-half player stat tables by parsing
    play description text from ESPN's drives/plays data.

    Returns dict keyed by period label (Q1, Q2, 1H, Q3, Q4, 2H, OT1, Full Game).
    Each value: { 'passing': df, 'rushing': df, 'receiving': df }
    """
    from collections import defaultdict

    summary = get_game_summary(game_id)
    if not summary:
        return {}

    drives = summary.get("drives", {})
    if not drives:
        return {}

    prev_drives    = drives.get("previous", [])
    current_drive  = drives.get("current")
    all_drives     = prev_drives + ([current_drive] if current_drive else [])

    # Accumulators: period (int) → player_name → stat dict
    def new_pass(): return {"Team":"","comp":0,"att":0,"yds":0,"td":0,"int":0}
    def new_rush(): return {"Team":"","car":0,"yds":0,"td":0}
    def new_recv(): return {"Team":"","rec":0,"yds":0,"td":0}

    passing   = defaultdict(lambda: defaultdict(new_pass))   # [period][name]
    rushing   = defaultdict(lambda: defaultdict(new_rush))
    receiving = defaultdict(lambda: defaultdict(new_recv))

    for drive in all_drives:
        if not drive:
            continue
        team = drive.get("team", {}).get("abbreviation", "")
        for play in drive.get("plays", []):
            period = _safe_int(play.get("period", {}).get("number", 0))
            if period == 0:
                continue
            desc = play.get("description", "")
            if not desc:
                continue

            is_td   = bool(_TD_RE.search(desc))
            is_int  = bool(_INT_RE.search(desc))

            # ── Passing ──────────────────────────────────────────────────────
            pm = _PASS_RE.match(desc)
            if pm:
                passer = pm.group(1).strip()
                complete = pm.group(2).lower() == "complete"
                d = passing[period][passer]
                d["Team"] = team
                d["att"]  += 1
                if complete:
                    d["comp"] += 1
                    ym = _PASS_YDS_RE.search(desc)
                    d["yds"] += _safe_int(ym.group(1)) if ym else 0
                if is_td and complete:
                    d["td"] += 1
                if is_int:
                    d["int"] += 1

                # ── Receiving (from same play) ────────────────────────────
                rvm = _RECV_RE.search(desc)
                if rvm and complete:
                    receiver = rvm.group(1).strip()
                    # Remove trailing possessive/comma artifacts
                    receiver = receiver.split(",")[0].strip()
                    rd = receiving[period][receiver]
                    rd["Team"] = team
                    rd["rec"] += 1
                    rd["yds"] += _safe_int(rvm.group(2))
                    if is_td:
                        rd["td"] += 1
                continue

            # ── Rushing ──────────────────────────────────────────────────────
            rm = _RUSH_RE.match(desc)
            if rm:
                rusher = rm.group(1).strip()
                yards  = _safe_int(rm.group(2))
                d = rushing[period][rusher]
                d["Team"] = team
                d["car"] += 1
                d["yds"] += yards
                if is_td:
                    d["td"] += 1

    # ── Build DataFrames ──────────────────────────────────────────────────────

    def to_pass_df(acc: dict) -> pd.DataFrame:
        rows = []
        for name, d in acc.items():
            if d["att"] == 0:
                continue
            rows.append({
                "Player": name, "Team": d["Team"],
                "C/ATT": f"{d['comp']}/{d['att']}",
                "YDS":   d["yds"], "TD": d["td"], "INT": d["int"],
            })
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values("YDS", ascending=False).reset_index(drop=True)

    def to_rush_df(acc: dict) -> pd.DataFrame:
        rows = []
        for name, d in acc.items():
            if d["car"] == 0:
                continue
            rows.append({
                "Player": name, "Team": d["Team"],
                "CAR": d["car"], "YDS": d["yds"], "TD": d["td"],
            })
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values("YDS", ascending=False).reset_index(drop=True)

    def to_recv_df(acc: dict) -> pd.DataFrame:
        rows = []
        for name, d in acc.items():
            if d["rec"] == 0:
                continue
            rows.append({
                "Player": name, "Team": d["Team"],
                "REC": d["rec"], "YDS": d["yds"], "TD": d["td"],
            })
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values("YDS", ascending=False).reset_index(drop=True)

    def merge(acc_dict, periods):
        """Merge multiple period accumulators into one."""
        merged = defaultdict(lambda: {"Team":"","comp":0,"att":0,"yds":0,"td":0,"int":0,
                                       "car":0,"rec":0})
        for p in periods:
            for name, d in acc_dict[p].items():
                for k, v in d.items():
                    if k == "Team":
                        merged[name]["Team"] = v
                    else:
                        merged[name][k] = merged[name].get(k, 0) + v
        return merged

    all_periods = sorted(set(
        list(passing.keys()) + list(rushing.keys()) + list(receiving.keys())
    ))

    result = {}

    # Per-quarter
    for p in all_periods:
        label = _quarter_label(p)
        result[label] = {
            "passing":   to_pass_df(passing[p]),
            "rushing":   to_rush_df(rushing[p]),
            "receiving": to_recv_df(receiving[p]),
        }

    # Halves
    h1 = [p for p in all_periods if p in (1, 2)]
    h2 = [p for p in all_periods if p in (3, 4)]
    ot = [p for p in all_periods if p > 4]

    if h1:
        mp = merge(passing, h1); mr = merge(rushing, h1); mrv = merge(receiving, h1)
        result["1H"] = {"passing": to_pass_df(mp), "rushing": to_rush_df(mr),
                         "receiving": to_recv_df(mrv)}
    if h2:
        mp = merge(passing, h2); mr = merge(rushing, h2); mrv = merge(receiving, h2)
        result["2H"] = {"passing": to_pass_df(mp), "rushing": to_rush_df(mr),
                         "receiving": to_recv_df(mrv)}
    for ot_p in ot:
        label = _quarter_label(ot_p)
        if label not in result:
            result[label] = {"passing": to_pass_df(passing[ot_p]),
                              "rushing": to_rush_df(rushing[ot_p]),
                              "receiving": to_recv_df(receiving[ot_p])}

    # Full game
    mp  = merge(passing,   all_periods)
    mr  = merge(rushing,   all_periods)
    mrv = merge(receiving, all_periods)
    result["Full Game"] = {
        "passing":   to_pass_df(mp),
        "rushing":   to_rush_df(mr),
        "receiving": to_recv_df(mrv),
    }

    return result
