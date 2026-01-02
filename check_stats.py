#!/usr/bin/env python3
"""
Check what stats are actually returned by Yahoo API
"""

import sys
from yahoo_client import YahooClient

# Common NHL stat IDs from Yahoo's documentation
STAT_ID_MAP = {
    "0": "Games Played (GP)",
    "1": "Goals (G)",
    "2": "Assists (A)",
    "3": "Plus/Minus (+/-)",
    "4": "Penalty Minutes (PIM)",
    "5": "Powerplay Goals (PPG)",
    "6": "Shorthanded Goals (SHG)",
    "7": "Game Winning Goals (GWG)",
    "8": "Shots on Goal (SOG)",
    "9": "Shooting Percentage (SH%)",
    "10": "Faceoffs Won (FOW)",
    "11": "Faceoffs Lost (FOL)",
    "12": "Hits (HIT)",
    "13": "Blocks (BLK)",
    "14": "Powerplay Points (PPP)",
    "15": "Shorthanded Points (SHP)",
    "16": "Wins (W)",
    "17": "Losses (L)",
    "18": "Goals Against (GA)",
    "19": "Goals Against Average (GAA)",
    "20": "Saves (SV)",
    "21": "Save Percentage (SV%)",
    "22": "Shutouts (SO)",
    "32": "Shots on Goal (SOG)",  # Sometimes duplicate
}

def main():
    # Initialize client
    client = YahooClient()

    print("=" * 80)
    print("CHECKING STATS RETURNED BY YAHOO API FOR FREE AGENTS")
    print("=" * 80)

    # Get top 5 free agents (league_id comes from config)
    players = client.fetch_available_players(count=5)

    for i, player in enumerate(players, 1):
        print(f"\n{'-' * 80}")
        print(f"#{i}: {player['name']} ({player['team']}) - {'/'.join(player['pos'])}")
        print(f"Overall Rank: {player.get('overall_rank', 'N/A')}")
        print(f"Fantasy Points Total: {player.get('fantasy_points_total', 0.0)}")
        print(f"{'-' * 80}")

        stats = player.get('stats', {})
        print(f"\nSTATS RETURNED (stat_id: value):")

        if not stats:
            print("  No stats found!")
        else:
            # Sort by stat_id for consistent display
            sorted_stats = sorted(stats.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999)

            for stat_id, value in sorted_stats:
                stat_name = STAT_ID_MAP.get(stat_id, f"Unknown stat")
                print(f"  {stat_id:>3}: {value:>6} - {stat_name}")

        # Check specifically for GP (stat_id "0")
        if "0" in stats:
            print(f"\n✓ GAMES PLAYED FOUND: {stats['0']}")
        else:
            print(f"\n✗ GAMES PLAYED (stat_id 0) NOT FOUND")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Check if ANY player has GP
    has_gp = any("0" in player.get('stats', {}) for player in players)

    if has_gp:
        print("✓ Games Played (GP) IS available from Yahoo API!")
    else:
        print("✗ Games Played (GP) is NOT available from Yahoo API for free agents")

    # Show what stats are consistently available
    if players:
        common_stats = set(players[0].get('stats', {}).keys())
        for player in players[1:]:
            common_stats &= set(player.get('stats', {}).keys())

        print(f"\nStats consistently available across all {len(players)} players:")
        for stat_id in sorted(common_stats, key=lambda x: int(x) if x.isdigit() else 999):
            stat_name = STAT_ID_MAP.get(stat_id, f"Unknown stat")
            print(f"  {stat_id}: {stat_name}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
