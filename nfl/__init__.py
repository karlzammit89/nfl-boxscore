"""
nfl_boxscore
============
Live NFL box score fetcher using ESPN's unofficial API.
"""

from .api import get_live_games, get_game_summary, get_linescore, get_scoring_plays
from .stats import (
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

__all__ = [
    "get_live_games", "get_game_summary", "get_linescore", "get_scoring_plays",
    "build_linescore_df", "get_passing_stats", "get_rushing_stats",
    "get_receiving_stats", "get_defensive_stats", "get_kicking_stats",
    "get_returning_stats", "get_team_stats", "get_scoring_summary",
    "get_pbp_by_quarter",
]
