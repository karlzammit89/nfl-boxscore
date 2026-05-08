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

_PASS_PTYPES = {"pass reception", "pass incompletion", "passing touchdown",
                "receiving touchdown",
                "interception", "interception return", "pass", "sack"}
_RUSH_PTYPES = {"rush", "rushing touchdown", "scramble"}
_SKIP_PTYPES = {"kickoff", "punt", "field goal", "extra point", "penalty",
                "timeout", "end period", "end of half", "two-point conversion",
                "two point conversion", "kick off", "no play", "",
                "extra point good", "field goal good", "field goal missed",
                "punt downed", "punt out of bounds", "kickoff return touchdown",
                "kickoff return", "two-point conversion attempt",
                "two point conversion attempt"}

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
    Build per-quarter and per-half player stat tables by parsing ESPN play text.
    ESPN stores play text in 'text' field using abbreviated names (T.Tagovailoa).
    Play type comes from play['type']['text'] e.g. 'Pass Reception', 'Rush'.
    Yardage comes from play['statYardage'] (always accurate).
    """
    from collections import defaultdict

    summary = get_game_summary(game_id)
    if not summary:
        return {}

    drives = summary.get("drives", {})
    if not drives:
        return {}

    prev_drives   = drives.get("previous", [])
    current_drive = drives.get("current")
    all_drives    = prev_drives + ([current_drive] if current_drive else [])
    if not all_drives:
        return {}

    # Deduplicate plays by play ID to avoid double-counting
    _seen_play_ids = set()

    def new_pass(): return {"Team":"","comp":0,"att":0,"yds":0,"td":0,"int":0}
    def new_rush(): return {"Team":"","car":0,"yds":0,"td":0}
    def new_recv(): return {"Team":"","rec":0,"yds":0,"td":0}
    def new_sack(): return {"Team":"","sacks":0}

    passing   = defaultdict(lambda: defaultdict(new_pass))
    rushing   = defaultdict(lambda: defaultdict(new_rush))
    receiving = defaultdict(lambda: defaultdict(new_recv))
    sacking   = defaultdict(lambda: defaultdict(new_sack))

    for drive in all_drives:
        if not drive:
            continue
        team = drive.get("team", {}).get("abbreviation", "")
        # Derive drive's primary period from its start period as fallback
        _drive_period = _safe_int(drive.get("start", {}).get("period", {}).get("number", 0))
        _last_valid_period = _drive_period  # track last known valid period within drive
        for play in drive.get("plays", []):
            _raw_period = _safe_int(play.get("period", {}).get("number", 0))
            if _raw_period > 0:
                _last_valid_period = _raw_period
            period = _last_valid_period if _last_valid_period > 0 else _drive_period
            ptype    = play.get("type", {}).get("text", "").lower().strip()
            text     = play.get("text", "") or ""
            stat_yds = _safe_int(play.get("statYardage", 0))

            # Deduplicate by play ID
            play_id = play.get("id", "")
            if play_id and play_id in _seen_play_ids:
                continue
            if play_id:
                _seen_play_ids.add(play_id)

            # Skip play types we don't care about
            if ptype in _SKIP_PTYPES or not text:
                continue

            # Skip only ENFORCED penalties (those with "No Play" marker).
            # Declined penalties keep their stats — the play still counts.
            if _re.search(r'No Play', text, _re.I):
                continue

            # TD: use ESPN's scoringPlay flag first, fallback to play type
            is_scoring = play.get("scoringPlay", False)
            is_td = is_scoring or ptype in ("passing touchdown", "rushing touchdown",
                                             "receiving touchdown", "touchdown")
            is_int = "interception" in ptype

            # ── Sack plays — ptype-gated first, text fallback second ──────────
            if ptype == "sack" or "sacked" in text.lower():
                sm = _SACK_RE.search(text)
                if sm:
                    sacker = (sm.group(1) or sm.group(2) or "").strip()
                    if sacker:
                        sacking[period][sacker]["sacks"] += 1
                # Fall through to pass block to count QB pass attempt

            # ── Pass plays ─────────────────────────────────────────────────────
            if ptype in _PASS_PTYPES:
                pm = _PASSER_RE.search(text)
                if not pm:
                    continue
                passer = pm.group(1).strip()
                d = passing[period][passer]
                d["Team"] = team
                d["att"] += 1
                is_complete = ptype in ("pass reception", "passing touchdown", "receiving touchdown")
                if is_complete:
                    d["comp"] += 1
                    d["yds"]  += stat_yds
                    if is_td:
                        d["td"] += 1
                    rv = _RECV_RE.search(text)
                    if rv:
                        receiver = rv.group(1).strip()
                        rd = receiving[period][receiver]
                        rd["Team"] = team
                        rd["rec"] += 1
                        rd["yds"] += stat_yds
                        if is_td:
                            rd["td"] += 1
                if is_int:
                    d["int"] += 1
                continue

            # ── Rush plays ─────────────────────────────────────────────────────
            if ptype in _RUSH_PTYPES:
                rm = _RUSH_RE.search(text)
                if rm:
                    rusher = rm.group(1).strip()
                    d = rushing[period][rusher]
                    d["Team"] = team
                    d["car"] += 1
                    d["yds"] += stat_yds
                    if is_td:
                        d["td"] += 1
                continue

    # ── DataFrame builders ────────────────────────────────────────────────

    def to_sack_df(acc):
        rows = [{"Player": n, "Team": d["Team"], "SACKS": d["sacks"]}
                for n, d in acc.items() if d["sacks"] > 0]
        return (pd.DataFrame(rows).sort_values("SACKS", ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def to_pass_df(acc):
        rows = [{"Player":n,"Team":d["Team"],
                 "C/ATT":f"{d['comp']}/{d['att']}",
                 "YDS":d["yds"],"TD":d["td"],"INT":d["int"]}
                for n,d in acc.items() if d["att"]>0]
        return (pd.DataFrame(rows).sort_values("YDS",ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def to_rush_df(acc):
        rows = [{"Player":n,"Team":d["Team"],
                 "CAR":d["car"],"YDS":d["yds"],"TD":d["td"]}
                for n,d in acc.items() if d["car"]>0]
        return (pd.DataFrame(rows).sort_values("YDS",ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def to_recv_df(acc):
        rows = [{"Player":n,"Team":d["Team"],
                 "REC":d["rec"],"YDS":d["yds"],"TD":d["td"]}
                for n,d in acc.items() if d["rec"]>0]
        return (pd.DataFrame(rows).sort_values("YDS",ascending=False)
                .reset_index(drop=True)) if rows else pd.DataFrame()

    def merge(base, periods, factory):
        from collections import defaultdict
        merged = defaultdict(factory)
        for p in periods:
            for name, d in base[p].items():
                m = merged[name]
                m["Team"] = d["Team"]
                for k in d:
                    if k != "Team":
                        m[k] = m.get(k, 0) + d[k]
        return merged

    all_periods = sorted(set(
        list(passing.keys()) + list(rushing.keys()) +
        list(receiving.keys()) + list(sacking.keys())))

    result = {}
    for p in all_periods:
        if p > 4:   # skip OT
            continue
        lbl = _quarter_label(p)
        result[lbl] = {"passing":   to_pass_df(passing[p]),
                       "rushing":   to_rush_df(rushing[p]),
                       "receiving": to_recv_df(receiving[p]),
                       "defense":   to_sack_df(sacking[p])}

    h1 = [p for p in all_periods if p in (1, 2)]
    h2 = [p for p in all_periods if p in (3, 4)]
    # OT excluded — only Q1-Q4 and halves
    if h1:
        result["1H"] = {"passing":   to_pass_df(merge(passing,  h1, new_pass)),
                        "rushing":   to_rush_df(merge(rushing,  h1, new_rush)),
                        "receiving": to_recv_df(merge(receiving,h1, new_recv)),
                        "defense":   to_sack_df(merge(sacking,  h1, new_sack))}
    if h2:
        result["2H"] = {"passing":   to_pass_df(merge(passing,  h2, new_pass)),
                        "rushing":   to_rush_df(merge(rushing,  h2, new_rush)),
                        "receiving": to_recv_df(merge(receiving,h2, new_recv)),
                        "defense":   to_sack_df(merge(sacking,  h2, new_sack))}

    result["Full Game"] = {
        "passing":   to_pass_df(merge(passing,   all_periods, new_pass)),
        "rushing":   to_rush_df(merge(rushing,   all_periods, new_rush)),
        "receiving": to_recv_df(merge(receiving, all_periods, new_recv)),
        "defense":   to_sack_df(merge(sacking,   all_periods, new_sack)),
    }
    return result
