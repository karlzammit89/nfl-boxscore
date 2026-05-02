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

def _parse_play_athletes(play: dict) -> list[dict]:
    """
    Extract athlete stat contributions from a single play's participants.
    ESPN encodes per-play stats in play['participants'] as a list of
    { athlete: {...}, stats: [...] } entries.
    Returns list of dicts: { athlete_id, name, team, stat_key, value }
    """
    rows = []
    for participant in play.get("participants", []):
        athlete = participant.get("athlete", {})
        name    = athlete.get("displayName", "")
        team    = athlete.get("team", {}).get("abbreviation", "")
        a_id    = athlete.get("id", "")
        pos     = athlete.get("position", {}).get("abbreviation", "")
        for stat in participant.get("stats", []):
            rows.append({
                "athlete_id": a_id,
                "Player":     name,
                "Pos":        pos,
                "Team":       team,
                "stat_name":  stat.get("name", ""),
                "value":      _safe_float(stat.get("value", 0)),
                "display":    stat.get("displayValue", ""),
            })
    return rows


def get_player_stats_by_period(game_id: str) -> dict:
    """
    Build true per-quarter and per-half player stat tables by aggregating
    play-by-play participant data.

    Returns a dict keyed by period label (Q1, Q2, 1H, Q3, Q4, 2H, OT1, Full Game).
    Each value is a dict of stat-category DataFrames:
      { 'passing': df, 'rushing': df, 'receiving': df }

    Stat definitions (matching ESPN boxscore column names):
      Passing:   C/ATT, YDS, TD, INT
      Rushing:   CAR, YDS, TD
      Receiving: REC, YDS, TD
    """
    summary = get_game_summary(game_id)
    if not summary:
        return {}

    drives = summary.get("drives", {})
    if not drives:
        return {}

    previous_drives = drives.get("previous", [])
    current_drive   = drives.get("current")
    all_drives      = previous_drives + ([current_drive] if current_drive else [])

    # Collect per-play, per-athlete, per-period contributions
    # Structure: { period_int: { athlete_id: { Player, Pos, Team, stats... } } }
    from collections import defaultdict

    # We'll accumulate raw stat values per period per athlete
    # passing: completions, attempts, yards, td, int
    # rushing: carries, yards, td
    # receiving: receptions, yards, td

    def empty_pass():
        return {"comp": 0, "att": 0, "yds": 0, "td": 0, "int": 0}
    def empty_rush():
        return {"car": 0, "yds": 0, "td": 0}
    def empty_recv():
        return {"rec": 0, "yds": 0, "td": 0}

    # period → category → athlete_id → stats dict
    passing_data   = defaultdict(lambda: defaultdict(lambda: {"Player":"","Pos":"","Team":"",**empty_pass()}))
    rushing_data   = defaultdict(lambda: defaultdict(lambda: {"Player":"","Pos":"","Team":"",**empty_rush()}))
    receiving_data = defaultdict(lambda: defaultdict(lambda: {"Player":"","Pos":"","Team":"",**empty_recv()}))

    for drive in all_drives:
        if not drive:
            continue
        for play in drive.get("plays", []):
            period   = _safe_int(play.get("period", {}).get("number", 0))
            if period == 0:
                continue
            play_type = play.get("type", {}).get("text", "").lower()
            desc      = play.get("description", "").lower()

            for participant in play.get("participants", []):
                athlete = participant.get("athlete", {})
                a_id    = athlete.get("id", "")
                if not a_id:
                    continue
                name = athlete.get("displayName", "")
                pos  = athlete.get("position", {}).get("abbreviation", "")
                team = athlete.get("team", {}).get("abbreviation", "")
                role = participant.get("type", {}).get("name", "").lower()
                stats_list = participant.get("stats", [])

                stat_map = {s.get("name","").lower(): _safe_float(s.get("value",0))
                            for s in stats_list}

                # ── Passing
                if role in ("passer", "quarterback") or "passingyards" in stat_map or "passingTouchdowns".lower() in stat_map:
                    pd_  = passing_data[period][a_id]
                    pd_["Player"] = name; pd_["Pos"] = pos; pd_["Team"] = team
                    pd_["yds"]  += stat_map.get("passingyards", stat_map.get("yards", 0))
                    pd_["td"]   += stat_map.get("passingtouchdowns", 0)
                    pd_["int"]  += stat_map.get("interceptions", 0)
                    pd_["comp"] += stat_map.get("completions", 0)
                    pd_["att"]  += stat_map.get("passattempts", stat_map.get("attempts", 0))

                # ── Rushing
                if role in ("rusher", "ballcarrier") or "rushingyards" in stat_map:
                    rd_ = rushing_data[period][a_id]
                    rd_["Player"] = name; rd_["Pos"] = pos; rd_["Team"] = team
                    rd_["yds"] += stat_map.get("rushingyards", stat_map.get("yards", 0))
                    rd_["td"]  += stat_map.get("rushingtouchdowns", 0)
                    rd_["car"] += stat_map.get("rushingcarries", stat_map.get("carries", 1))

                # ── Receiving
                if role in ("receiver", "recipient") or "receivingyards" in stat_map:
                    rvd = receiving_data[period][a_id]
                    rvd["Player"] = name; rvd["Pos"] = pos; rvd["Team"] = team
                    rvd["yds"] += stat_map.get("receivingyards", stat_map.get("yards", 0))
                    rvd["td"]  += stat_map.get("receivingtouchdowns", 0)
                    rvd["rec"] += stat_map.get("receptions", 1)

    def pass_df(period_dict) -> pd.DataFrame:
        rows = []
        for a_id, d in period_dict.items():
            if d["comp"] == 0 and d["att"] == 0 and d["yds"] == 0:
                continue
            rows.append({
                "Player": d["Player"], "Pos": d["Pos"], "Team": d["Team"],
                "C/ATT": f"{int(d['comp'])}/{int(d['att'])}",
                "YDS":   int(d["yds"]), "TD": int(d["td"]), "INT": int(d["int"]),
            })
        return pd.DataFrame(rows).sort_values("YDS", ascending=False) if rows else pd.DataFrame()

    def rush_df(period_dict) -> pd.DataFrame:
        rows = []
        for a_id, d in period_dict.items():
            if d["car"] == 0 and d["yds"] == 0:
                continue
            rows.append({
                "Player": d["Player"], "Pos": d["Pos"], "Team": d["Team"],
                "CAR": int(d["car"]), "YDS": int(d["yds"]), "TD": int(d["td"]),
            })
        return pd.DataFrame(rows).sort_values("YDS", ascending=False) if rows else pd.DataFrame()

    def recv_df(period_dict) -> pd.DataFrame:
        rows = []
        for a_id, d in period_dict.items():
            if d["rec"] == 0 and d["yds"] == 0:
                continue
            rows.append({
                "Player": d["Player"], "Pos": d["Pos"], "Team": d["Team"],
                "REC": int(d["rec"]), "YDS": int(d["yds"]), "TD": int(d["td"]),
            })
        return pd.DataFrame(rows).sort_values("YDS", ascending=False) if rows else pd.DataFrame()

    # Build per-period results
    all_periods = sorted(set(list(passing_data.keys()) +
                             list(rushing_data.keys()) +
                             list(receiving_data.keys())))

    result = {}

    for period in all_periods:
        label = _quarter_label(period)
        result[label] = {
            "passing":   pass_df(passing_data[period]),
            "rushing":   rush_df(rushing_data[period]),
            "receiving": recv_df(receiving_data[period]),
        }

    # Half aggregations
    def merge_pass(periods):
        combined = defaultdict(lambda: {"Player":"","Pos":"","Team":"",**empty_pass()})
        for p in periods:
            for a_id, d in passing_data[p].items():
                combined[a_id]["Player"] = d["Player"]
                combined[a_id]["Pos"]    = d["Pos"]
                combined[a_id]["Team"]   = d["Team"]
                for k in ["comp","att","yds","td","int"]:
                    combined[a_id][k] += d[k]
        return combined

    def merge_rush(periods):
        combined = defaultdict(lambda: {"Player":"","Pos":"","Team":"",**empty_rush()})
        for p in periods:
            for a_id, d in rushing_data[p].items():
                combined[a_id]["Player"] = d["Player"]
                combined[a_id]["Pos"]    = d["Pos"]
                combined[a_id]["Team"]   = d["Team"]
                for k in ["car","yds","td"]:
                    combined[a_id][k] += d[k]
        return combined

    def merge_recv(periods):
        combined = defaultdict(lambda: {"Player":"","Pos":"","Team":"",**empty_recv()})
        for p in periods:
            for a_id, d in receiving_data[p].items():
                combined[a_id]["Player"] = d["Player"]
                combined[a_id]["Pos"]    = d["Pos"]
                combined[a_id]["Team"]   = d["Team"]
                for k in ["rec","yds","td"]:
                    combined[a_id][k] += d[k]
        return combined

    h1_periods = [p for p in all_periods if p in (1, 2)]
    h2_periods = [p for p in all_periods if p in (3, 4)]
    ot_periods = [p for p in all_periods if p > 4]

    if h1_periods:
        result["1H"] = {"passing": pass_df(merge_pass(h1_periods)),
                        "rushing": rush_df(merge_rush(h1_periods)),
                        "receiving": recv_df(merge_recv(h1_periods))}
    if h2_periods:
        result["2H"] = {"passing": pass_df(merge_pass(h2_periods)),
                        "rushing": rush_df(merge_rush(h2_periods)),
                        "receiving": recv_df(merge_recv(h2_periods))}

    # Full game from all periods
    fg_pass = merge_pass(all_periods)
    fg_rush = merge_rush(all_periods)
    fg_recv = merge_recv(all_periods)
    result["Full Game"] = {
        "passing":   pass_df(fg_pass),
        "rushing":   rush_df(fg_rush),
        "receiving": recv_df(fg_recv),
    }

    return result
