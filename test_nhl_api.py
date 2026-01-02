#!/usr/bin/env python3
"""
Test if NHL API provides Games Played data
"""

import requests
import json

def main():
    print("=" * 80)
    print("TESTING NHL API FOR GAMES PLAYED DATA")
    print("=" * 80)

    # Test with a known player - Jordan Kyrou (we know he's available)
    # First, let's search for him in the NHL API

    print("\n1. Searching for 'Jordan Kyrou' in NHL API...")
    print("-" * 80)

    # NHL API endpoint for searching players
    search_url = "https://api-web.nhle.com/v1/search/player?culture=en-us&limit=5&q=jordan%20kyrou"

    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        print(f"\nSearch Results:")
        print(json.dumps(data, indent=2)[:500])  # First 500 chars

        # Try to find Kyrou's player ID
        if isinstance(data, list) and len(data) > 0:
            player = data[0]
            player_id = player.get("playerId")
            print(f"\nFound player ID: {player_id}")

            if player_id:
                # Get player stats
                print(f"\n2. Fetching stats for player ID {player_id}...")
                print("-" * 80)

                # Try the player stats endpoint
                stats_url = f"https://api-web.nhle.com/v1/player/{player_id}/landing"

                stats_response = requests.get(stats_url, timeout=10)
                stats_response.raise_for_status()
                stats_data = stats_response.json()

                print(f"\nPlayer Stats Response (first 2000 chars):")
                print(json.dumps(stats_data, indent=2)[:2000])

                # Look for games played in the response
                if "featuredStats" in stats_data:
                    featured = stats_data["featuredStats"]
                    if "regularSeason" in featured:
                        reg_season = featured["regularSeason"]
                        if "subSeason" in reg_season:
                            current_season = reg_season["subSeason"]
                            gp = current_season.get("gamesPlayed")
                            print(f"\n✓ FOUND GAMES PLAYED: {gp}")

                            # Show all available stats
                            print(f"\nAvailable stats for {current_season.get('season', 'unknown season')}:")
                            for key, value in current_season.items():
                                print(f"  {key}: {value}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("3. Testing alternative NHL API endpoints...")
    print("=" * 80)

    # Try the stats API directly
    try:
        # Current season stats
        season = "20252026"  # 2025-26 season
        stats_url = f"https://api.nhle.com/stats/rest/en/skater/summary?cayenneExp=seasonId={season}"

        print(f"\nTrying season stats endpoint for {season}...")
        response = requests.get(stats_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "data" in data and len(data["data"]) > 0:
            # Show first player as example
            first_player = data["data"][0]
            print(f"\nExample player stats:")
            print(json.dumps(first_player, indent=2)[:1000])

            # Check if GP is in there
            if "gamesPlayed" in first_player or "GP" in first_player:
                print(f"\n✓ NHL API provides Games Played data!")

    except Exception as e:
        print(f"\nERROR with alternative endpoint: {e}")

if __name__ == "__main__":
    main()
