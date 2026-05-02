"""
nfl/api.py
----------
All ESPN unofficial API calls for live NFL game data.
Endpoints are stable but undocumented — handle gracefully.
"""

import requests
from typing import Optional
import logging

logger = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
CDN  = "https://cdn.espn.com/core/nfl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NFLBoxScore/1.0)",
    "Accept": "application/json",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[dict]:
    """Safe GET with error logging."""
    try:
        r = SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error(f"ESPN API error [{url}]: {e}")
        return None


# ── Scoreboard ────────────────────────────────────────────────────────────────

def get_scoreboard(week: int = None, season_type: int = 2) -> Optional[dict]:
    """
    Fetch current NFL scoreboard.
    season_type: 1=preseason, 2=regular, 3=playoffs
    Returns raw ESPN scoreboard response.
    """
    params = {"limit": 100}
    if week:
        params["week"] = week
    params["seasontype"] = season_type
    return _get(f"{BASE}/scoreboard", params=params)


def get_live_games(week: int = None) -> list[dict]:
    """
    Return a flat list of all games (live, scheduled, final) from scoreboard.
    Each dict has: id, name, short_name, status, clock, period, home, away, venue.
    """
    data = get_scoreboard(week=week)
    if not data:
        return []

    games = []
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {})
        competitors = {c["homeAway"]: c for c in comp.get("competitors", [])}

        home = competitors.get("home", {})
        away = competitors.get("away", {})

        games.append({
            "id":         event["id"],
            "name":       event.get("name", ""),
            "short_name": event.get("shortName", ""),
            "date":       event.get("date", ""),
            "status":     status.get("type", {}).get("description", "Scheduled"),
            "status_state": status.get("type", {}).get("state", "pre"),
            "clock":      status.get("displayClock", "0:00"),
            "period":     status.get("period", 0),
            "home": {
                "team":   home.get("team", {}).get("displayName", ""),
                "abbr":   home.get("team", {}).get("abbreviation", ""),
                "logo":   home.get("team", {}).get("logo", ""),
                "score":  home.get("score", "0"),
                "record": home.get("records", [{}])[0].get("summary", "") if home.get("records") else "",
            },
            "away": {
                "team":   away.get("team", {}).get("displayName", ""),
                "abbr":   away.get("team", {}).get("abbreviation", ""),
                "logo":   away.get("team", {}).get("logo", ""),
                "score":  away.get("score", "0"),
                "record": away.get("records", [{}])[0].get("summary", "") if away.get("records") else "",
            },
            "venue": comp.get("venue", {}).get("fullName", ""),
        })
    return games


# ── Game Summary (box score + play-by-play) ───────────────────────────────────

def get_game_summary(game_id: str) -> Optional[dict]:
    """
    Full game summary from ESPN summary endpoint.
    Contains: boxscore, scoring plays, leaders, drives, header.
    """
    return _get(f"{BASE}/summary", params={"event": game_id})


def get_game_boxscore(game_id: str) -> Optional[dict]:
    """
    Raw boxscore node from the summary.
    Contains per-player and per-team stats with quarter-level data.
    """
    summary = get_game_summary(game_id)
    if not summary:
        return None
    return summary.get("boxscore")


def get_scoring_plays(game_id: str) -> list[dict]:
    """
    Return list of scoring plays in chronological order.
    Each entry: period, clock, team, type, description, home_score, away_score.
    """
    summary = get_game_summary(game_id)
    if not summary:
        return []

    plays = []
    for sp in summary.get("scoringPlays", []):
        plays.append({
            "period":      sp.get("period", {}).get("number", 0),
            "clock":       sp.get("clock", {}).get("displayValue", ""),
            "team":        sp.get("team", {}).get("displayName", ""),
            "team_abbr":   sp.get("team", {}).get("abbreviation", ""),
            "type":        sp.get("type", {}).get("text", ""),
            "description": sp.get("text", ""),
            "away_score":  sp.get("awayScore", 0),
            "home_score":  sp.get("homeScore", 0),
        })
    return plays


def get_linescore(game_id: str) -> dict:
    """
    Return quarter-by-quarter scores for both teams.
    Structure: { 'home': [Q1, Q2, Q3, Q4, OT...], 'away': [...], 'home_team': str, 'away_team': str }
    """
    summary = get_game_summary(game_id)
    if not summary:
        return {}

    header = summary.get("header", {})
    competitions = header.get("competitions", [{}])
    if not competitions:
        return {}

    comp = competitions[0]
    result = {"home": [], "away": [], "home_team": "", "away_team": ""}

    for competitor in comp.get("competitors", []):
        side = competitor.get("homeAway", "")
        team_name = competitor.get("team", {}).get("abbreviation", side)
        result[f"{side}_team"] = team_name
        linescores = competitor.get("linescores", [])
        result[side] = [ls.get("value", 0) for ls in linescores]

    return result
