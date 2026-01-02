#!/usr/bin/env python3
"""
NHL API client for fetching Games Played and other stats
"""

import requests
from typing import Dict, Optional
import time
import json
import os
from pathlib import Path

# Cache file location
_cache_dir = Path(".cache")
_nhl_cache_file = _cache_dir / "nhl_stats.json"

# In-memory cache for NHL player stats to avoid repeated API calls
_nhl_stats_cache: Dict[str, Dict] = {}
_cache_timestamp: Optional[float] = None
_cache_ttl: int = 86400  # 24 hours cache (86400 seconds)


def _normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    # Remove common suffixes and normalize spacing
    name = name.lower().strip()

    # Remove accents and special characters
    import unicodedata
    name = unicodedata.normalize('NFKD', name)
    name = ''.join([c for c in name if not unicodedata.combining(c)])

    # Remove periods, apostrophes, hyphens, convert to spaces
    name = name.replace(".", "").replace("'", "").replace("-", " ")

    # Collapse multiple spaces
    return " ".join(name.split())


def _normalize_team(team: str) -> str:
    """Normalize team abbreviation for matching."""
    # Handle team abbreviation differences between Yahoo and NHL
    team_map = {
        "UTA": "UTA",  # Utah Hockey Club
        "ARI": "UTA",  # Arizona moved to Utah
        "PHX": "UTA",  # Phoenix moved to Utah
        "SJ": "SJS",   # San Jose Sharks
        "TB": "TBL",   # Tampa Bay Lightning
        "LA": "LAK",   # Los Angeles Kings
        "NJ": "NJD",   # New Jersey Devils
        "MON": "MTL",  # Montreal Canadiens
    }

    return team_map.get(team.upper(), team.upper())


def _load_cache_from_disk() -> Optional[Dict]:
    """Load NHL stats cache from disk if it exists and is fresh."""
    if not _nhl_cache_file.exists():
        return None

    try:
        # Check file modification time
        file_mtime = os.path.getmtime(_nhl_cache_file)
        current_time = time.time()
        age = current_time - file_mtime

        # If cache is older than TTL, don't use it
        if age > _cache_ttl:
            print(f"  Cache is {age / 3600:.1f} hours old (stale), fetching fresh data...")
            return None

        # Load cache from file
        with open(_nhl_cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        print(f"  ✓ Loaded NHL stats from cache ({age / 3600:.1f} hours old)")
        return cache_data

    except Exception as e:
        print(f"  Warning: Failed to load cache from disk: {e}")
        return None


def _save_cache_to_disk(stats_map: Dict) -> None:
    """Save NHL stats cache to disk."""
    try:
        # Create cache directory if it doesn't exist
        _cache_dir.mkdir(exist_ok=True)

        # Save to temp file first, then rename (atomic operation)
        temp_file = _nhl_cache_file.with_suffix('.tmp')

        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(stats_map, f)

        # Atomic rename
        temp_file.replace(_nhl_cache_file)

    except Exception as e:
        print(f"  Warning: Failed to save cache to disk: {e}")


def fetch_season_stats(season: str = "20252026", debug: bool = False, force_refresh: bool = False) -> Dict[str, Dict]:
    """
    Fetch all skater stats for the current season from NHL API.

    Args:
        season: Season ID (default 20252026 for 2025-26)
        debug: Print debug info about fetched players
        force_refresh: Force fetch from API even if cache is fresh

    Returns:
        Dictionary mapping normalized "name|team" to stats dict
    """
    global _nhl_stats_cache, _cache_timestamp

    current_time = time.time()

    # Check in-memory cache first
    if not force_refresh:
        if _nhl_stats_cache and _cache_timestamp and (current_time - _cache_timestamp) < _cache_ttl:
            if debug:
                age = current_time - _cache_timestamp
                print(f"  ✓ Using in-memory cache ({age / 3600:.1f} hours old)")
            return _nhl_stats_cache

        # Check disk cache
        disk_cache = _load_cache_from_disk()
        if disk_cache:
            _nhl_stats_cache.clear()
            _nhl_stats_cache.update(disk_cache)
            _cache_timestamp = time.time()
            return _nhl_stats_cache

    print("Fetching NHL season stats from NHL API...")

    try:
        stats_map = {}
        # Also create a name-only index for fuzzy matching
        name_only_map = {}

        # NHL API has a hard limit of 100 per request, need to paginate
        start = 0
        limit = 100
        total_fetched = 0

        while True:
            url = f"https://api.nhle.com/stats/rest/en/skater/summary?cayenneExp=seasonId={season}&limit={limit}&start={start}"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()

            if "data" not in data or len(data["data"]) == 0:
                break

            for player in data["data"]:
                name = player.get("skaterFullName", "")
                team = player.get("teamAbbrevs", "")
                gp = player.get("gamesPlayed", 0)

                if name and team:
                    # Normalize name and team for matching
                    norm_name = _normalize_name(name)
                    norm_team = _normalize_team(team)

                    key = f"{norm_name}|{norm_team}"

                    player_stats = {
                        "full_name": name,
                        "team": team,
                        "games_played": gp,
                        "goals": player.get("goals", 0),
                        "assists": player.get("assists", 0),
                        "points": player.get("points", 0),
                        "ppg": player.get("pointsPerGame", 0.0),
                    }

                    stats_map[key] = player_stats

                    # Also index by name only for fallback matching
                    if norm_name not in name_only_map:
                        name_only_map[norm_name] = []
                    name_only_map[norm_name].append(player_stats)

            total_fetched += len(data["data"])

            # Check if we've fetched all available players
            total_available = data.get("total", 0)
            if total_fetched >= total_available:
                break

            # Move to next page
            start += limit

        # Update in-memory cache
        _nhl_stats_cache = stats_map
        _cache_timestamp = current_time

        # Store name-only map for fuzzy matching
        _nhl_stats_cache["__name_only__"] = name_only_map

        # Save to disk for future runs
        _save_cache_to_disk(_nhl_stats_cache)

        print(f"✓ Fetched stats for {len(stats_map)} NHL players from API")

        if debug:
            print("\nSample of fetched players:")
            for i, (key, player) in enumerate(list(stats_map.items())[:10]):
                if key != "__name_only__":
                    print(f"  {player['full_name']} ({player['team']}) - {player['games_played']} GP")

        return stats_map

    except Exception as e:
        print(f"Warning: Failed to fetch NHL stats: {e}")
        return {}


def get_games_played(player_name: str, team_abbr: str, season: str = "20252026", verbose: bool = False) -> Optional[int]:
    """
    Get games played for a specific player.

    Args:
        player_name: Player's full name (e.g., "Jordan Kyrou")
        team_abbr: Team abbreviation (e.g., "STL")
        season: Season ID (default 20252026)
        verbose: Print debug info when player not found

    Returns:
        Games played as integer, or None if not found
    """
    stats_map = fetch_season_stats(season)

    # Normalize for lookup
    norm_name = _normalize_name(player_name)
    norm_team = _normalize_team(team_abbr)

    key = f"{norm_name}|{norm_team}"

    # Try exact match first
    player_stats = stats_map.get(key)

    if player_stats and isinstance(player_stats, dict) and "games_played" in player_stats:
        return player_stats["games_played"]

    # Try without team if exact match not found (player may have been traded)
    for k, v in stats_map.items():
        if k == "__name_only__":
            continue
        if isinstance(v, dict) and k.startswith(f"{norm_name}|"):
            if verbose:
                print(f"  Note: Found {player_name} on {v['team']} (not {team_abbr})")
            return v["games_played"]

    # Try fuzzy match by name only (ignoring team)
    name_only_map = stats_map.get("__name_only__", {})
    if norm_name in name_only_map:
        candidates = name_only_map[norm_name]
        if len(candidates) == 1:
            # Only one player with this name, use it
            if verbose:
                print(f"  Note: Matched {player_name} by name only to {candidates[0]['full_name']} ({candidates[0]['team']})")
            return candidates[0]["games_played"]
        else:
            # Multiple players with same name, prefer the one on the right team
            for candidate in candidates:
                if _normalize_team(candidate["team"]) == norm_team:
                    return candidate["games_played"]
            # No team match, just use the first one
            if verbose:
                print(f"  Note: Multiple matches for {player_name}, using {candidates[0]['full_name']} ({candidates[0]['team']})")
            return candidates[0]["games_played"]

    if verbose:
        print(f"  Warning: Could not find {player_name} ({team_abbr}) in NHL stats")

    return None


def get_player_stats(player_name: str, team_abbr: str, season: str = "20252026") -> Optional[Dict]:
    """
    Get full stats for a specific player.

    Args:
        player_name: Player's full name
        team_abbr: Team abbreviation
        season: Season ID

    Returns:
        Stats dictionary or None if not found
    """
    stats_map = fetch_season_stats(season)

    norm_name = _normalize_name(player_name)
    norm_team = _normalize_team(team_abbr)

    key = f"{norm_name}|{norm_team}"

    return stats_map.get(key)
