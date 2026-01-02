#!/usr/bin/env python3
"""
Test why certain players aren't being found in NHL API
"""

import nhl_api

# Problem players from the output
problem_players = [
    ("JJ Peterka", "UTA"),
    ("Thomas Chabot", "OTT"),
    ("Charlie McAvoy", "BOS"),
    ("Will Smith", "SJ"),
    ("Dylan Cozens", "OTT"),  # This might be wrong - Cozens plays for BUF
    ("Timo Meier", "NJ"),
    ("Juraj Slafkovský", "MTL"),
]

print("=" * 80)
print("TESTING PROBLEM PLAYERS")
print("=" * 80)

# Fetch stats (with debug)
stats_map = nhl_api.fetch_season_stats(debug=False)

print(f"\nTotal players in NHL API: {len([k for k in stats_map.keys() if k != '__name_only__'])}")

# Check name-only index
name_only = stats_map.get("__name_only__", {})
print(f"Name-only index size: {len(name_only)}")

print("\n" + "=" * 80)
print("CHECKING EACH PROBLEM PLAYER")
print("=" * 80)

for player_name, team in problem_players:
    print(f"\n{player_name} ({team}):")
    print("-" * 40)

    # Try to get GP with verbose mode
    gp = nhl_api.get_games_played(player_name, team, verbose=True)

    if gp is not None:
        print(f"  ✓ Found: {gp} GP")
    else:
        print(f"  ✗ Not found")

        # Try to find similar names
        norm_name = nhl_api._normalize_name(player_name)
        print(f"  Normalized search: '{norm_name}'")

        # Search for partial matches
        print(f"  Searching for similar names...")
        found_similar = False
        for key in stats_map.keys():
            if key == "__name_only__":
                continue
            if norm_name.split()[0] in key or (len(norm_name.split()) > 1 and norm_name.split()[1] in key):
                player_data = stats_map[key]
                print(f"    - {player_data['full_name']} ({player_data['team']}) - {player_data['games_played']} GP")
                found_similar = True

        if not found_similar:
            print(f"    No similar names found")

print("\n" + "=" * 80)
print("CHECKING SPECIFIC NHL API NAMES")
print("=" * 80)

# Let's check what the actual names are in the NHL API for some known players
test_names = ["peterka", "chabot", "mcavoy", "smith", "cozens", "meier", "slafkovsky"]

for search_term in test_names:
    print(f"\nSearching for '{search_term}':")
    found = []
    for key, player_data in stats_map.items():
        if key == "__name_only__":
            continue
        if search_term in player_data.get('full_name', '').lower():
            found.append(f"  - {player_data['full_name']} ({player_data['team']}) - {player_data['games_played']} GP")

    if found:
        for f in found[:5]:  # Limit to 5 results
            print(f)
    else:
        print("  No matches found")
