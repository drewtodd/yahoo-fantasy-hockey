#!/usr/bin/env python3
"""
Test NHL API limits and pagination
"""

import requests
import json

season = "20252026"

# Test different limits
for limit in [10, 50, 100, 500, 1000]:
    print(f"\nTesting limit={limit}")
    print("-" * 40)

    url = f"https://api.nhle.com/stats/rest/en/skater/summary?cayenneExp=seasonId={season}&limit={limit}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "data" in data:
            actual_count = len(data["data"])
            print(f"  Requested: {limit}")
            print(f"  Received: {actual_count}")

            # Check if there's pagination info
            if "total" in data:
                print(f"  Total available: {data['total']}")

            # Check all top-level keys
            print(f"  Response keys: {list(data.keys())}")

            if limit == 100:
                # Show full response structure for limit=100
                print("\nFull response structure:")
                print(json.dumps(data, indent=2)[:1000])

    except Exception as e:
        print(f"  Error: {e}")

# Try with start parameter (pagination)
print("\n" + "=" * 80)
print("TESTING PAGINATION")
print("=" * 80)

all_players = []

for start in range(0, 500, 100):
    url = f"https://api.nhle.com/stats/rest/en/skater/summary?cayenneExp=seasonId={season}&limit=100&start={start}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "data" in data:
            count = len(data["data"])
            all_players.extend(data["data"])
            print(f"Start={start}: Got {count} players (total so far: {len(all_players)})")

            if count == 0:
                print("  No more players, stopping")
                break

    except Exception as e:
        print(f"Start={start}: Error - {e}")
        break

print(f"\nTotal players fetched with pagination: {len(all_players)}")

if all_players:
    print("\nSample of players fetched:")
    for player in all_players[:5]:
        print(f"  - {player.get('skaterFullName', 'Unknown')} ({player.get('teamAbbrevs', '?')}) - {player.get('gamesPlayed', 0)} GP")

    # Check if we have the problem players
    problem_names = ["peterka", "chabot", "mcavoy", "meier", "cozens", "slafkovsky"]

    print("\nSearching for problem players:")
    for search in problem_names:
        found = [p for p in all_players if search in p.get('skaterFullName', '').lower()]
        if found:
            for p in found[:3]:
                print(f"  ✓ {p['skaterFullName']} ({p['teamAbbrevs']}) - {p['gamesPlayed']} GP")
        else:
            print(f"  ✗ '{search}' not found")
