#!/usr/bin/env python3
"""
Debug script to thoroughly investigate Games Played availability in Yahoo API
"""

import sys
import json
from yahoo_client import YahooClient

def main():
    league_id = "161107"

    # Initialize client
    client = YahooClient()

    print("=" * 80)
    print("INVESTIGATING GAMES PLAYED (GP) IN YAHOO API")
    print("=" * 80)

    # Fetch a few free agents with all possible data
    print("\n1. FETCHING FREE AGENT DATA...")
    print("-" * 80)

    try:
        # Try to get raw response with as much data as possible
        endpoint = (
            f"league/nhl.l.{league_id}/players;"
            f"status=FA;"
            f"sort=OR;"
            f"count=3;"
            f"out=percent_owned,stats,ranks"
        )

        response = client._api_request(endpoint)

        # Pretty print the entire response
        print("\nFULL API RESPONSE:")
        print(json.dumps(response, indent=2))

        # Extract players and examine stats structure
        if "fantasy_content" in response and "league" in response["fantasy_content"]:
            league_data = response["fantasy_content"]["league"]
            if isinstance(league_data, list):
                league_data = league_data[0]

            players_data = league_data.get("players", {})
            player_count = players_data.get("count", 0)

            print("\n" + "=" * 80)
            print(f"FOUND {player_count} PLAYERS - EXAMINING STATS STRUCTURE")
            print("=" * 80)

            for i in range(player_count):
                player_key = str(i)
                if player_key not in players_data:
                    continue

                player_wrapper = players_data[player_key].get("player", [])
                if not isinstance(player_wrapper, list) or len(player_wrapper) < 3:
                    continue

                # Get player name
                name = "Unknown"
                player_info = player_wrapper[0]
                if isinstance(player_info, list):
                    for item in player_info:
                        if isinstance(item, dict) and "name" in item:
                            name = item["name"].get("full", "Unknown")
                            break

                print(f"\n{'-' * 80}")
                print(f"PLAYER: {name}")
                print(f"{'-' * 80}")

                # Examine the stats object (3rd element)
                if len(player_wrapper) > 2:
                    stats_obj = player_wrapper[2]
                    print("\nSTATS OBJECT (player_wrapper[2]):")
                    print(json.dumps(stats_obj, indent=2))

                    # Check for player_stats
                    if isinstance(stats_obj, dict) and "player_stats" in stats_obj:
                        player_stats = stats_obj["player_stats"]
                        print("\nPLAYER_STATS SECTION:")
                        print(json.dumps(player_stats, indent=2))

                        # Look for stats array
                        if "stats" in player_stats:
                            stats_array = player_stats["stats"]
                            print("\nSTATS ARRAY:")
                            print(json.dumps(stats_array, indent=2))

                            # Parse each stat
                            if isinstance(stats_array, list):
                                print("\nPARSED STATS:")
                                for stat in stats_array:
                                    if isinstance(stat, dict) and "stat" in stat:
                                        stat_obj = stat["stat"]
                                        stat_id = stat_obj.get("stat_id", "?")
                                        value = stat_obj.get("value", "?")
                                        print(f"  stat_id {stat_id}: {value}")

                # Also check player_points
                if len(player_wrapper) > 2:
                    stats_obj = player_wrapper[2]
                    if isinstance(stats_obj, dict) and "player_points" in stats_obj:
                        player_points = stats_obj["player_points"]
                        print("\nPLAYER_POINTS SECTION:")
                        print(json.dumps(player_points, indent=2))

        print("\n" + "=" * 80)
        print("2. TESTING WITH ROSTERED PLAYER (INSTEAD OF FREE AGENT)")
        print("=" * 80)

        # Try fetching a rostered player to compare
        roster_endpoint = f"team/nhl.l.{league_id}.t.1/roster/players;out=stats"
        roster_response = client._api_request(roster_endpoint)

        print("\nROSTER PLAYER RESPONSE (FIRST PLAYER):")
        if "fantasy_content" in roster_response and "team" in roster_response["fantasy_content"]:
            team_data = roster_response["fantasy_content"]["team"]
            if isinstance(team_data, list):
                team_data = team_data[0]

            roster_data = team_data.get("roster", {})
            if isinstance(roster_data, list):
                roster_data = roster_data[0]

            players_data = roster_data.get("players", {})

            # Get first player
            if "0" in players_data:
                first_player = players_data["0"].get("player", [])

                # Get name
                name = "Unknown"
                if isinstance(first_player, list) and len(first_player) > 0:
                    player_info = first_player[0]
                    if isinstance(player_info, list):
                        for item in player_info:
                            if isinstance(item, dict) and "name" in item:
                                name = item["name"].get("full", "Unknown")
                                break

                print(f"\nROSTERED PLAYER: {name}")
                print(json.dumps(first_player, indent=2))

                # Check their stats
                if len(first_player) > 1:
                    for elem in first_player:
                        if isinstance(elem, dict) and "player_stats" in elem:
                            print("\nROSTERED PLAYER STATS:")
                            print(json.dumps(elem["player_stats"], indent=2))

                            stats_array = elem["player_stats"].get("stats", [])
                            if isinstance(stats_array, list):
                                print("\nROSTERED PLAYER PARSED STATS:")
                                for stat in stats_array:
                                    if isinstance(stat, dict) and "stat" in stat:
                                        stat_obj = stat["stat"]
                                        stat_id = stat_obj.get("stat_id", "?")
                                        value = stat_obj.get("value", "?")
                                        print(f"  stat_id {stat_id}: {value}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
