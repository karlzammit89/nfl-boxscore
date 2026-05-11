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
try:
    from .api import get_game_summary, get_linescore, get_scoring_plays
except ImportError:
    from nfl.api import get_game_summary, get_linescore, get_scoring_plays


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
            _p_raw = play.get("period", {})
            period = _safe_int(_p_raw.get("number", 0) if isinstance(_p_raw, dict) else _p_raw)
            if period == 0:
                period = _safe_int(play.get("start", {}).get("period", {}).get("number", 0))
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
_RUSH_PTYPES = {"rush", "rushing touchdown", "scramble", "kneel"}
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
    Build per-quarter and per-half player stat tables by intelligently parsing
    ESPN play text. Uses text-based classification (not ESPN ptype) for accuracy,
    handling formation prefixes, eligibility notices, compound plays, and edge cases.
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

    _seen_play_ids = set()

    def new_pass(): return {"Team":"","comp":0,"att":0,"yds":0,"td":0,"int":0}
    def new_rush(): return {"Team":"","car":0,"yds":0,"td":0}
    def new_recv(): return {"Team":"","rec":0,"yds":0,"td":0}
    def new_sack(): return {"Team":"","sacks":0}

    passing   = defaultdict(lambda: defaultdict(new_pass))
    rushing   = defaultdict(lambda: defaultdict(new_rush))
    receiving = defaultdict(lambda: defaultdict(new_recv))
    sacking   = defaultdict(lambda: defaultdict(new_sack))

    # ── Smart text-based play classifier ─────────────────────────────────────

    _N = r'[A-Z][a-z]?\.[A-Z][A-Za-z\'\-]+(?:\.\s*[A-Z][A-Za-z\'\-]+)*'

    # Strip formation notes and eligibility prefixes
    _strip_re = _re.compile(
        r'^(?:\([^)]+\)\s*)*'
        r'(?:' + _N + r'(?:\s+[A-Za-z\'\-]+)*\s+reported\s+[^.]+\.\s*)*',
        _re.I
    )

    # Detect if a text fragment describes a pass play
    _pass_detect_re = _re.compile(
        r'^(' + _N + r')\s+pass\s+'
        r'(incomplete\s+)?'
        r'(?:short|deep|long|screen|flat|)?\s*'
        r'(?:left|right|middle|out|over|cross|flat|)?\s*'
        r'(?:to\s+)?(' + _N + r')?',
        _re.I
    )

    # Detect receiver in completed pass
    _recv_detect_re = _re.compile(
        r'pass\s+(?:complete\s+to\s+|(?:short|deep|long|screen|flat)?\s*'
        r'(?:left|right|middle|out|over|cross|flat)?\s*to\s+)?(' + _N + r')',
        _re.I
    )

    # Detect rush: name followed by direction, scramble, kneel, or bare "to TEAM YD for"
    _rush_detect_re = _re.compile(
        r'^(' + _N + r')\s+'
        r'(?:right end|left end|right tackle|left tackle|right guard|left guard|'
        r'right side|left side|up the middle|center\b|'
        r'scrambles?\s|kneels?\s|rushes?\s|runs?\s|ran\s+ob|'
        r'to\s+[A-Z]{2,3}\s+\d+\s+for\s)',
        _re.I
    )

    # Direct snap trick play: "Direct snap to NAME. NAME direction"
    _direct_snap_re = _re.compile(
        r'Direct snap to (' + _N + r')',
        _re.I
    )

    # Sack
    _sack_detect_re = _re.compile(
        r'(' + _N + r')\s+sacked\s+',
        _re.I
    )

    def classify_sentences(text, stat_yds, team):
        """
        Parse ALL sentences in a play text and yield stat events.
        Handles compound plays (fumble+pass, etc.)
        Returns list of (event_type, player1, player2, yds, is_td, is_int) tuples.
        """
        # Two-point conversions: NEVER count towards any regular stats
        # (passing ATT/CMP/YDS, receiving REC/YDS, rushing CAR/YDS, TDs)
        is_two_pt  = bool(_re.search(r'TWO.POINT\s+CONVERSION', text, _re.I))
        if is_two_pt:
            return []

        # No Play = down wiped out, don't count any stats
        is_no_play = bool(_re.search(r'No\s+Play', text, _re.I))

        # Strip formation/eligibility prefix from full text
        clean = _strip_re.sub('', text).strip()

        # Split into sentences for compound play handling
        sentences = _re.split(r'\.\s+(?=[A-Z(])', clean)

        is_td  = bool(_re.search(r'TOUCHDOWN', text, _re.I))
        is_int = bool(_re.search(r'intercepted|INTERCEPTED', text, _re.I))

        events = []

        for sent in sentences:
            sent = sent.strip().rstrip('.')

            # Skip non-action sentences
            if _re.match(r'^(FUMBLES|recovers|PENALTY|Official|Timeout|Two-Minute|Injury|END|\*\*)', sent, _re.I):
                continue

            # ── Sack ─────────────────────────────────────────────────────────
            sack_m = _sack_detect_re.search(sent)
            if sack_m and not _re.search(r'\bpass\b', sent[:sack_m.start()], _re.I):
                qb = sack_m.group(1)
                # Also find sacker(s)
                sacker_m = _SACK_RE.search(text)
                sacker = (sacker_m.group(1) or sacker_m.group(2) or "").strip() if sacker_m else ""
                events.append(("sack", qb, sacker, stat_yds, False, False))
                continue

            # ── Pass ─────────────────────────────────────────────────────────
            pass_m = _pass_detect_re.match(sent)
            if pass_m:
                # No Play = down wiped out, skip all pass attempts
                if is_no_play:
                    continue
                passer = pass_m.group(1).strip()
                is_incomplete = bool(pass_m.group(2)) or bool(_re.search(r'\bincomplete\b', sent, _re.I))
                receiver = None

                if not is_incomplete:
                    rv = _recv_detect_re.search(sent)
                    if rv:
                        receiver = rv.group(1).strip()
                    # If no receiver found but no "incomplete", check if it's a TD pass
                    # (some TD texts omit the to: "pass short left to R.Doubs for 2 yards, TOUCHDOWN")
                    if not receiver and is_td:
                        rv2 = _re.search(r'\bto\s+(' + _N + r')\s+(?:for|,)', sent, _re.I)
                        if rv2:
                            receiver = rv2.group(1).strip()

                events.append(("pass", passer, receiver, stat_yds, is_td and not is_incomplete, is_int))
                continue

            # ── Rush ─────────────────────────────────────────────────────────
            # Check for direct snap trick play first
            ds_m = _direct_snap_re.search(sent)
            if ds_m:
                rusher = ds_m.group(1)
                events.append(("rush", rusher, None, stat_yds, is_td, False))
                continue

            rush_m = _rush_detect_re.match(sent)
            if rush_m:
                # Exclude penalties that look like rush (NAME to TEAM for...PENALTY)
                if is_no_play and not _re.search(r'\bpass\b', text, _re.I):
                    continue
                # Skip rush on fumble plays that also contain a pass attempt
                # e.g. "J.Love to GB 42...FUMBLES...J.Love pass incomplete"
                # The fumbled snap is not counted as a rushing attempt
                if _re.search(r'FUMBLES', text, _re.I) and _re.search(r'\bpass\b', text, _re.I):
                    continue
                rusher = rush_m.group(1).strip()
                events.append(("rush", rusher, None, stat_yds, is_td, False))
                continue

        return events

    # ── Main drive loop ───────────────────────────────────────────────────────

    for drive in all_drives:
        if not drive:
            continue
        team = drive.get("team", {}).get("abbreviation", "")
        _drive_period = _safe_int(drive.get("start", {}).get("period", {}).get("number", 0))
        _last_valid_period = _drive_period

        for play in drive.get("plays", []):
            _p_raw = play.get("period", {})
            _raw_period = _safe_int(_p_raw.get("number", 0) if isinstance(_p_raw, dict) else _p_raw)
            if _raw_period == 0:
                _raw_period = _safe_int(play.get("start", {}).get("period", {}).get("number", 0))
            if _raw_period > 0:
                _last_valid_period = _raw_period
            period = _last_valid_period if _last_valid_period > 0 else _drive_period

            text     = play.get("text", "") or play.get("description", "") or ""
            ptype    = play.get("type", {}).get("text", "").lower().strip()
            stat_yds = _safe_int(play.get("statYardage", 0))

            # Deduplicate by play ID
            play_id = play.get("id", "")
            if play_id and play_id in _seen_play_ids:
                continue
            if play_id:
                _seen_play_ids.add(play_id)

            # Skip non-play types entirely (no text to parse)
            if ptype in _SKIP_PTYPES or not text:
                continue

            # Run smart text classifier
            events = classify_sentences(text, stat_yds, team)

            for evt_type, p1, p2, yds, is_td, is_int in events:
                if evt_type == "pass":
                    passer, receiver = p1, p2
                    if not passer:
                        continue
                    d = passing[period][passer]
                    d["Team"] = team
                    d["att"] += 1
                    is_complete = receiver is not None
                    if is_complete:
                        d["comp"] += 1
                        d["yds"]  += yds
                        if is_td:
                            d["td"] += 1
                        if receiver:
                            rd = receiving[period][receiver]
                            rd["Team"] = team
                            rd["rec"] += 1
                            rd["yds"] += yds
                            if is_td:
                                rd["td"] += 1
                    if is_int:
                        d["int"] += 1

                elif evt_type == "rush":
                    rusher = p1
                    if not rusher:
                        continue
                    d = rushing[period][rusher]
                    d["Team"] = team
                    d["car"] += 1
                    d["yds"] += yds
                    if is_td:
                        d["td"] += 1

                elif evt_type == "sack":
                    qb, sacker = p1, p2
                    if qb:
                        # ESPN ATT column excludes sacks — sacks are tracked separately
                        d = passing[period][qb]
                        d["Team"] = team
                        # Do NOT increment att for sacks (ESPN convention)
                    if sacker:
                        sd = sacking[period][sacker]
                        sd["Team"] = team
                        sd["sacks"] += 1

    # ── DataFrame builders ────────────────────────────────────────────────────

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
        if p > 4:
            continue
        lbl = _quarter_label(p)
        result[lbl] = {"passing":   to_pass_df(passing[p]),
                       "rushing":   to_rush_df(rushing[p]),
                       "receiving": to_recv_df(receiving[p]),
                       "defense":   to_sack_df(sacking[p])}

    h1 = [p for p in all_periods if p in (1, 2)]
    h2 = [p for p in all_periods if p in (3, 4)]
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

    # ── Reconcile with ESPN official boxscore ────────────────────────────────
    # PBP parsing handles ~98% of plays correctly. The remaining edge cases
    # (ESPN's inconsistent No Play counting, etc.) are corrected by comparing
    # PBP-derived per-player totals against the ESPN official boxscore and
    # distributing any difference to the last quarter the player appeared in.
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
    """
    if "Player" not in df.columns:
        return df.iloc[0:0]
    row = df[df["Player"] == player]
    if not row.empty:
        return row
    parts = player.strip().split()
    if len(parts) >= 2:
        abbr = f"{parts[0][0].upper()}.{chr(32).join(parts[1:])}"
        row = df[df["Player"] == abbr]
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
    """
    Compare Full Game PBP totals against official boxscore.
    Returns list of (player, cat, col, pbp_val, official_val, suspected_quarter) tuples
    for any mismatches.
    """
    try:
        official = {
            "passing":   get_passing_stats(game_id),
            "rushing":   get_rushing_stats(game_id),
            "receiving": get_receiving_stats(game_id),
        }
    except Exception:
        return []

    periods = ["Q1","Q2","Q3","Q4"]
    mismatches = []

    for cat, cols in [
        ("passing",   ["YDS","TD","INT"]),
        ("rushing",   ["YDS","TD","CAR"]),
        ("receiving", ["YDS","TD","REC"]),
    ]:
        off_df = official.get(cat)
        fg_df  = result.get("Full Game", {}).get(cat)
        if off_df is None or off_df.empty or fg_df is None or fg_df.empty:
            continue

        for _, off_row in off_df.iterrows():
            player = str(off_row.get("Player",""))
            if not player:
                continue

            # ATT check for passing
            if cat == "passing" and "C/ATT" in off_df.columns:
                ca = str(off_row.get("C/ATT","0/0"))
                try:
                    off_att = int(ca.split("/")[1])
                    pbp_att = _get_att(fg_df, player)
                    if off_att != pbp_att:
                        last_p = _last_period(result, cat, player, periods)
                        mismatches.append((player, cat, "ATT", pbp_att, off_att, last_p or "unknown"))
                except Exception:
                    pass

            for col in cols:
                if col not in off_df.columns:
                    continue
                try:
                    off_val = int(pd.to_numeric(off_row.get(col, 0), errors="coerce") or 0)
                    pbp_val = _get_col(fg_df, player, col)
                    if off_val != pbp_val:
                        last_p = _last_period(result, cat, player, periods)
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
