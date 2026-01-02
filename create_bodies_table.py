#!/usr/bin/env python3
"""
yahoo_bodies_table.py

Build a weekly "bodies table" (X's per roster slot/day) by:
- fetching NHL schedules for each player's team
- assigning players to Yahoo lineup slots per day to maximize filled slots

Data source:
- NHL public web API endpoints, e.g. /v1/club-schedule/{team}/week/{date}  [oai_citation:2‡GitHub](https://github.com/Zmalski/NHL-API-Reference?utm_source=chatgpt.com)
Optimization:
- OR-Tools CP-SAT  [oai_citation:3‡Google for Developers](https://developers.google.com/optimization/cp/cp_solver?utm_source=chatgpt.com)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import requests
import yaml
from dateutil.tz import gettz
from ortools.sat.python import cp_model

import nhl_api

# ---------- Config: Yahoo active slots (based on your table) ----------
SLOTS: List[str] = ["C", "C", "LW", "LW", "RW", "RW", "D", "D", "D", "D", "G", "G"]
DAYS = ["M", "T", "W", "Th", "F", "Sa", "Su"]

# ---------- NHL team code mapping ----------
# NHL "club-schedule" endpoint uses 3-letter "triCode" in lowercase for most teams.
# Yahoo uses "NJ" whereas NHL uses "njd", etc. Include common exceptions.
YAHOO_TO_NHL_TRI = {
    "NJ": "njd",
    "LA": "lak",
    "SJ": "sjs",
    "TB": "tbl",
    "VGK": "vgk",
    # Most others are the same letters, just lowercased (COL -> col)
}

NHL_BASE = "https://api-web.nhle.com/v1"

# ---------- NHL Schedule Cache ----------
# Cache team schedules to avoid redundant API calls during bulk simulations
# Key: (team_tri, week_start_isoformat), Value: Set[dt.date]
_nhl_schedule_cache: Dict[Tuple[str, str], Set[dt.date]] = {}

# ---------- ANSI Color codes ----------
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from text."""
    import re
    ansi_escape = re.compile(r'\033\[[0-9;]+m')
    return ansi_escape.sub('', text)


def pad_colored(text: str, width: int, align: str = '>') -> str:
    """Pad a string that may contain ANSI color codes.

    Args:
        text: The text to pad (may contain ANSI codes)
        width: The desired visible width
        align: Alignment ('<', '>', '^')

    Returns:
        Padded string with color codes preserved
    """
    visible_len = len(strip_ansi(text))
    padding_needed = width - visible_len

    if padding_needed <= 0:
        return text

    if align == '<':
        return text + ' ' * padding_needed
    elif align == '>':
        return ' ' * padding_needed + text
    else:  # center
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return ' ' * left_pad + text + ' ' * right_pad


@dataclass(frozen=True)
class Player:
    name: str
    team: str
    pos: Tuple[str, ...]  # eligible positions


def week_start_monday(today: dt.date) -> dt.date:
    # Monday = 0
    return today - dt.timedelta(days=today.weekday())


def daterange(start: dt.date, days: int) -> List[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(days)]


def yahoo_team_to_nhl_tri(team: str) -> str:
    team = team.strip().upper()
    return YAHOO_TO_NHL_TRI.get(team, team.lower())


def fetch_team_week_games(team_tri: str, week_start: dt.date) -> Set[dt.date]:
    """
    Returns set of game dates (local date as provided by schedule; we only care about date).
    Endpoint example: /v1/club-schedule/ari/week/2023-09-30  [oai_citation:4‡Home Assistant Community](https://community.home-assistant.io/t/nhl-api-custom-component-track-your-favorite-hockey-team-in-home-assistant/140428?page=9&utm_source=chatgpt.com)

    Uses global cache to avoid redundant API calls during bulk simulations.
    """
    # Check cache first
    cache_key = (team_tri, week_start.isoformat())
    if cache_key in _nhl_schedule_cache:
        return _nhl_schedule_cache[cache_key]

    # Fetch from API if not cached
    url = f"{NHL_BASE}/club-schedule/{team_tri}/week/{week_start.isoformat()}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()

    # The response structure can include games in a list; keys may vary slightly across seasons.
    # We'll defensively look for a list of games under common keys.
    games = []
    for key in ("games", "gameWeek", "weekGames"):
        if key in data and isinstance(data[key], list):
            games = data[key]
            break

    if not games and "games" in data and isinstance(data["games"], dict):
        # Some variants nest differently; ignore if not list
        pass

    game_dates: Set[dt.date] = set()
    for g in games:
        # Common field: "gameDate" as YYYY-MM-DD
        gd = g.get("gameDate")
        if isinstance(gd, str) and len(gd) >= 10:
            try:
                game_dates.add(dt.date.fromisoformat(gd[:10]))
            except ValueError:
                continue

    # Cache the result before returning
    _nhl_schedule_cache[cache_key] = game_dates
    return game_dates


def build_player_game_matrix(players: List[Player], week_start: dt.date) -> Dict[str, Set[dt.date]]:
    """
    Map player.name -> set of dates they play in that matchup week.
    We fetch per-team once and reuse.
    """
    team_to_dates: Dict[str, Set[dt.date]] = {}
    for p in players:
        tri = yahoo_team_to_nhl_tri(p.team)
        if tri not in team_to_dates:
            team_to_dates[tri] = fetch_team_week_games(tri, week_start)
    return {p.name: team_to_dates[yahoo_team_to_nhl_tri(p.team)] for p in players}


def build_single_date_game_matrix(players: List[Player], target_date: dt.date) -> Dict[str, bool]:
    """
    Map player.name -> bool (playing on target_date).
    Optimized for single-date lookup.
    """
    team_games: Dict[str, bool] = {}  # Cache team schedules
    result: Dict[str, bool] = {}

    for p in players:
        tri = yahoo_team_to_nhl_tri(p.team)
        if tri not in team_games:
            # Fetch week containing target_date, check if that date has games
            week_start = week_start_monday(target_date)
            week_games = fetch_team_week_games(tri, week_start)
            team_games[tri] = target_date in week_games
        result[p.name] = team_games[tri]

    return result


def calculate_position_flexibility(player: Player) -> Tuple[int, str]:
    """
    Returns (position_count, display_string).

    Examples:
      ("C",) -> (1, "C")
      ("C", "LW") -> (2, "C/LW (2)")
      ("C", "LW", "RW") -> (3, "C/LW/RW (3)")
    """
    valid_pos = [p for p in player.pos if p not in ('Util', 'BN', 'IR', 'IR+', 'NA')]
    count = len(valid_pos)
    display = '/'.join(valid_pos)
    if count > 1:
        display += f" ({count})"
    return count, display


def solve_daily_assignment(
    active_players: List[Player],
    slots: List[str],
) -> Dict[int, int]:
    """
    Returns mapping: slot_index -> player_index assigned (within active_players),
    maximizing number of filled slots.
    """
    model = cp_model.CpModel()

    # x[s, p] = 1 if slot s assigned to player p
    x: Dict[Tuple[int, int], cp_model.IntVar] = {}
    for s_i, slot in enumerate(slots):
        for p_i, pl in enumerate(active_players):
            if slot in pl.pos:
                x[(s_i, p_i)] = model.NewBoolVar(f"x_s{s_i}_p{p_i}")

    # Each slot: at most 1 player
    for s_i in range(len(slots)):
        vars_in_slot = [x[(s_i, p_i)] for p_i in range(len(active_players)) if (s_i, p_i) in x]
        if vars_in_slot:
            model.Add(sum(vars_in_slot) <= 1)

    # Each player: at most 1 slot
    for p_i in range(len(active_players)):
        vars_for_player = [x[(s_i, p_i)] for s_i in range(len(slots)) if (s_i, p_i) in x]
        if vars_for_player:
            model.Add(sum(vars_for_player) <= 1)

    # Objective: maximize filled slots
    model.Maximize(sum(x.values()) if x else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0  # plenty for this size
    status = solver.Solve(model)

    assignment: Dict[int, int] = {}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (s_i, p_i), var in x.items():
            if solver.Value(var) == 1:
                assignment[s_i] = p_i

    return assignment


def print_bodies_table(grid: List[List[str]]) -> None:
    # Simple aligned print (no extra deps)
    col_w = 4
    pos_w = max(len(row[0]) for row in grid)
    header = ["POS"] + DAYS
    print(f"{header[0]:<{pos_w}}  " + "  ".join(f"{h:>{col_w}}" for h in header[1:]))
    for row in grid:
        pos = row[0]
        cells = row[1:]
        print(f"{pos:<{pos_w}}  " + "  ".join(f"{c:>{col_w}}" for c in cells))


def get_slot_names(slots: List[str]) -> List[str]:
    """
    Generate numbered slot names from slot list.

    Args:
        slots: List of roster slots (e.g., ['C', 'C', 'LW', 'LW', 'D', 'D', 'D', 'D'])

    Returns:
        List of slot names with numbers (e.g., ['C1', 'C2', 'LW1', 'LW2', 'D1', 'D2', 'D3', 'D4'])
    """
    pos_counts = {}
    slot_names = []
    for slot in slots:
        pos_counts[slot] = pos_counts.get(slot, 0) + 1
        slot_names.append(f"{slot}{pos_counts[slot]}")
    return slot_names


def sort_slots_by_efficiency(slots: List[str], grid: List[List[str]], total_days: int) -> List[int]:
    """
    Sort slots by position type, then by efficiency (PCT) descending.

    Within each position group (C, LW, RW, D, G), slots are sorted so that
    the highest performing slot becomes #1, second highest becomes #2, etc.

    Args:
        slots: List of roster slots
        grid: Grid data with slot performance
        total_days: Total number of days in the analysis period

    Returns:
        List of indices representing the sorted order
    """
    # Calculate efficiency for each slot
    slot_data = []
    for s_i, slot in enumerate(slots):
        cells = grid[s_i][1:]  # Skip position column
        filled = sum(1 for cell in cells if cell == "X")
        pct = (filled / total_days * 100) if total_days > 0 else 0
        slot_data.append((s_i, slot, pct))

    # Group by position type
    from collections import defaultdict
    pos_groups = defaultdict(list)
    for s_i, slot, pct in slot_data:
        pos_groups[slot].append((s_i, pct))

    # Sort each group by PCT descending and build sorted order
    sorted_indices = []
    for pos in ["C", "LW", "RW", "D", "G"]:
        if pos in pos_groups:
            # Sort by PCT descending
            sorted_group = sorted(pos_groups[pos], key=lambda x: x[1], reverse=True)
            sorted_indices.extend([s_i for s_i, pct in sorted_group])

    return sorted_indices


def calculate_idle_players(players: List[Player], slots: List[str]) -> Dict[str, int]:
    """
    Calculate idle/surplus players by position.

    An idle player is one who is eligible for a position but there aren't enough
    roster slots to utilize all eligible players optimally.

    Args:
        players: List of Player objects with position eligibility
        slots: List of roster slots (e.g., ['C', 'C', 'LW', 'LW', ...])

    Returns:
        Dictionary mapping position to count of idle players
    """
    # Count roster slots by position
    slots_by_pos = {}
    for slot in slots:
        slots_by_pos[slot] = slots_by_pos.get(slot, 0) + 1

    # Count eligible players by position
    eligible_by_pos = {}
    for player in players:
        for pos in player.pos:
            eligible_by_pos[pos] = eligible_by_pos.get(pos, 0) + 1

    # Calculate idle players (surplus)
    idle_by_pos = {}
    for pos in eligible_by_pos:
        slot_count = slots_by_pos.get(pos, 0)
        eligible_count = eligible_by_pos[pos]
        idle = max(0, eligible_count - slot_count)
        if idle > 0:
            idle_by_pos[pos] = idle

    return idle_by_pos


def colorize_cell(cell: str) -> str:
    """
    Apply color and symbols to cells.
    - Filled: Green checkmark (✓)
    - Empty: Red X
    """
    if cell == "X":
        return f"{Colors.GREEN}✓{Colors.RESET}"
    else:
        return f"{Colors.RED}✗{Colors.RESET}"


def colorize_percentage(pct: float) -> str:
    """
    Apply color to percentage values based on performance thresholds.
    - Green (good): >= 70%
    - Yellow (warning): 40-69%
    - Red (bad): < 40%
    """
    if pct >= 70:
        return Colors.GREEN
    elif pct >= 40:
        return Colors.YELLOW
    else:
        return Colors.RED


def pad_colored_cell(colored_cell: str, width: int) -> str:
    """
    Pad a colored cell string to a specific width.

    Since the colored cell contains ANSI escape codes, we need to account for
    the visual width vs the string length (which includes invisible ANSI codes).
    """
    # Remove ANSI codes to calculate visual width
    import re
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    visual_text = ansi_pattern.sub('', colored_cell)
    visual_width = len(visual_text)

    padding = width - visual_width
    if padding > 0:
        # Center the content by adding spaces
        left_pad = padding // 2
        right_pad = padding - left_pad
        return " " * left_pad + colored_cell + " " * right_pad
    return colored_cell


def export_to_csv(grid: List[List[str]], header: List[str], output_file: Optional[str] = None) -> str:
    """Export grid to CSV format. Returns CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(grid)
    csv_content = output.getvalue()

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(csv_content)

    return csv_content


def export_to_markdown(grid: List[List[str]], header: List[str], output_file: Optional[str] = None) -> str:
    """Export grid to Markdown table format. Returns Markdown string."""
    lines = []

    # Header row
    lines.append("| " + " | ".join(header) + " |")

    # Separator row
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    # Data rows
    for row in grid:
        lines.append("| " + " | ".join(row) + " |")

    md_content = "\n".join(lines)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_content)

    return md_content


def copy_to_clipboard(text: str) -> bool:
    """Attempt to copy text to clipboard using pbcopy (macOS) or xclip (Linux)."""
    try:
        import subprocess
        # Try macOS pbcopy first
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            # Try Linux xclip
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False


def generate_export_filename(export_format: str) -> str:
    """Generate timestamped filename for export."""
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    extension = "csv" if export_format == "csv" else "md"
    return f"yfh-export-{timestamp}.{extension}"


def prompt_user_yes_no(question: str) -> bool:
    """Prompt user with yes/no question."""
    while True:
        response = input(f"{question} (y/n): ").strip().lower()
        if response in ("y", "yes"):
            return True
        elif response in ("n", "no"):
            return False
        else:
            print("Please answer 'y' or 'n'")


def main() -> int:
    global SLOTS

    ap = argparse.ArgumentParser()
    ap.add_argument("-r", "--roster", default="roster.yml", help="Path to roster YAML")
    ap.add_argument(
        "-d",
        "--date",
        default=None,
        help="Any date (YYYY-MM-DD) to determine which Mon-Sun week to analyze. If omitted, uses current week (America/Los_Angeles).",
    )
    ap.add_argument(
        "-w",
        "--weeks",
        type=int,
        default=1,
        help="Number of consecutive weeks to project (default: 1).",
    )
    ap.add_argument(
        "-D",
        "--day",
        action="store_true",
        help="Analyze a single day instead of a week. Uses --date if provided, otherwise current date.",
    )
    ap.add_argument(
        "--compact",
        action="store_true",
        help="Use compact day headers (M, T, W, Th, F, Sa, Su) instead of full date format.",
    )
    ap.add_argument(
        "-e",
        "--export",
        choices=["csv", "md", "markdown", "cp", "clipboard"],
        help="Export format: csv, md/markdown, or cp/clipboard.",
    )
    ap.add_argument(
        "-o",
        "--export-file",
        help="Output file for export (optional, auto-generates timestamped filename if omitted). Not used with clipboard.",
    )
    ap.add_argument(
        "-s",
        "--separate-weeks",
        action="store_true",
        help="Display each week in a separate table instead of one unified table (only affects multi-week mode).",
    )
    ap.add_argument(
        "-l",
        "--local",
        action="store_true",
        help="Use local roster.yml instead of fetching from Yahoo Fantasy API.",
    )
    ap.add_argument(
        "--sync",
        action="store_true",
        help="Fetch roster from Yahoo and save to roster.yml, then exit.",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Force refresh all caches (NHL stats, free agents, schedules). Ignores cache TTL.",
    )
    ap.add_argument(
        "--compare-team",
        type=str,
        metavar="TEAM_ID",
        help="Compare your roster efficiency against another team (forces single-week mode). Requires Yahoo API.",
    )
    ap.add_argument(
        "--player-swap",
        nargs=2,
        metavar=("DROP_PLAYER_ID", "ADD_PLAYER_ID"),
        help="Simulate swapping players (forces single-week mode). First ID is player to drop, second is player to add. Requires Yahoo API.",
    )
    ap.add_argument(
        "--recommend-add",
        type=str,
        metavar="DROP_PLAYER_NAME",
        help="Recommend free agent additions by simulating swaps with available players (forces single-week mode). Specify player by name. Requires Yahoo API.",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of recommendations to display when using --recommend-add (default: 10).",
    )
    ap.add_argument(
        "--available-fas",
        type=str,
        metavar="YYYY-MM-DD",
        help="Find best streaming pickups for a specific date. Shows available players "
             "with games on that date ranked by FPTS/G, and suggests drop candidates "
             "from your roster who aren't playing. Requires Yahoo API.",
    )
    args = ap.parse_args()

    # Normalize export aliases
    if args.export:
        if args.export == "md":
            args.export = "markdown"
        elif args.export == "cp":
            args.export = "clipboard"

    # Clear caches if --force is set
    if args.force:
        global _nhl_schedule_cache
        _nhl_schedule_cache.clear()
        print("✓ Force refresh enabled - clearing all caches")

    # Validate comparison mode
    if args.compare_team:
        if args.local:
            print("Error: --compare-team requires Yahoo API (cannot use with --local)", file=sys.stderr)
            return 2
        if args.day:
            print("Error: --compare-team only works with week mode (cannot use with --day)", file=sys.stderr)
            return 2
        if args.player_swap:
            print("Error: Cannot use --compare-team and --player-swap together", file=sys.stderr)
            return 2
        # Force single-week analysis in comparison mode
        args.weeks = 1

    # Validate player swap mode
    if args.player_swap:
        if args.local:
            print("Error: --player-swap requires Yahoo API (cannot use with --local)", file=sys.stderr)
            return 2
        if args.day:
            print("Error: --player-swap only works with week mode (cannot use with --day)", file=sys.stderr)
            return 2
        if args.recommend_add:
            print("Error: Cannot use --player-swap and --recommend-add together", file=sys.stderr)
            return 2
        # Force single-week analysis in swap mode
        args.weeks = 1

    # Validate recommend add mode
    if args.recommend_add:
        if args.local:
            print("Error: --recommend-add requires Yahoo API (cannot use with --local)", file=sys.stderr)
            return 2
        if args.day:
            print("Error: --recommend-add only works with week mode (cannot use with --day)", file=sys.stderr)
            return 2
        if args.compare_team:
            print("Error: Cannot use --recommend-add and --compare-team together", file=sys.stderr)
            return 2
        # Force single-week analysis in recommendation mode
        args.weeks = 1

    # Validate available FAs mode
    if args.available_fas:
        if args.local:
            print("Error: --available-fas requires Yahoo API (cannot use with --local)", file=sys.stderr)
            return 2
        if args.recommend_add:
            print("Error: Cannot use --available-fas and --recommend-add together", file=sys.stderr)
            return 2
        if args.compare_team:
            print("Error: Cannot use --available-fas and --compare-team together", file=sys.stderr)
            return 2
        if args.player_swap:
            print("Error: Cannot use --available-fas and --player-swap together", file=sys.stderr)
            return 2

        # Parse and validate date format
        try:
            target_date = dt.datetime.strptime(args.available_fas, "%Y-%m-%d").date()
            args.available_fas_date = target_date
        except ValueError:
            print(f"Error: Invalid date format '{args.available_fas}'. Use YYYY-MM-DD format.", file=sys.stderr)
            return 2

    tz = gettz("America/Los_Angeles")
    today = dt.datetime.now(tz=tz).date()

    # Handle --sync mode (fetch and save, then exit)
    if args.sync:
        try:
            from yahoo_client import YahooClient
            from config import config

            print("Fetching roster from Yahoo Fantasy API...")
            client = YahooClient()
            client.authorize()

            roster_data = client.fetch_team_roster()
            league_settings = client.fetch_league_settings()

            # Build YAML structure
            roster_yaml = {"players": roster_data}
            if league_settings.get("slots"):
                roster_yaml["slots"] = league_settings["slots"]

            # Save to file
            with open(args.roster, "w", encoding="utf-8") as f:
                yaml.dump(roster_yaml, f, default_flow_style=False, sort_keys=False)

            print(f"✓ Saved {len(roster_data)} players to {args.roster}")
            if league_settings.get("slots"):
                print(f"✓ Saved roster slots: {league_settings['slots']}")
            return 0

        except ImportError:
            print("Error: Yahoo client not available. Install required dependencies.", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Error fetching from Yahoo API: {e}", file=sys.stderr)
            return 2

    # Fetch roster (Yahoo by default, local if --local flag)
    use_local = args.local
    yahoo_failed = False
    opponent_players: Optional[List[Player]] = None
    swap_add_player: Optional[Player] = None
    available_players: Optional[List[Dict]] = None

    if not use_local:
        # Try Yahoo first (default behavior)
        try:
            from yahoo_client import YahooClient
            from config import config

            print("Fetching roster from Yahoo Fantasy API...")
            client = YahooClient()
            client.authorize()

            # Fetch roster and league settings
            roster_data = client.fetch_team_roster()
            league_settings = client.fetch_league_settings()

            # Use league settings for SLOTS if available
            if league_settings.get("slots"):
                SLOTS = league_settings["slots"]
                print(f"✓ Using league roster configuration: {SLOTS}")

            players: List[Player] = [
                Player(name=p["name"], team=p["team"], pos=tuple(p["pos"]))
                for p in roster_data
            ]

            print(f"✓ Fetched {len(players)} players from Yahoo")

            # Fetch opponent roster if comparison mode is active
            if args.compare_team:
                print(f"Fetching opponent team {args.compare_team} roster...")
                try:
                    opponent_roster_data = client.fetch_team_roster(team_id=args.compare_team)
                    opponent_players = [
                        Player(name=p["name"], team=p["team"], pos=tuple(p["pos"]))
                        for p in opponent_roster_data
                    ]
                    print(f"✓ Fetched {len(opponent_players)} players from opponent team")
                except Exception as e:
                    print(f"Error fetching opponent roster: {e}", file=sys.stderr)
                    return 2

            # Fetch player details if swap mode is active
            if args.player_swap:
                drop_player_id, add_player_id = args.player_swap
                print(f"Fetching player details for swap (drop: {drop_player_id}, add: {add_player_id})...")
                try:
                    add_player_data = client.fetch_player_details(add_player_id)
                    swap_add_player = Player(
                        name=add_player_data["name"],
                        team=add_player_data["team"],
                        pos=tuple(add_player_data["pos"])
                    )
                    print(f"✓ Fetched player to add: {swap_add_player.name} ({swap_add_player.team}, {'/'.join(swap_add_player.pos)})")
                except Exception as e:
                    print(f"Error fetching player {add_player_id}: {e}", file=sys.stderr)
                    return 2

            # Fetch available players if recommendation mode is active
            if args.recommend_add:
                print("Fetching top 100 available free agents...")
                try:
                    available_players = client.fetch_available_players(count=100, use_cache=not args.force)
                    # Filter out goalies
                    available_players = [p for p in available_players if 'G' not in p['pos']]
                    # Filter out injured players (IR, Out, Day-to-Day)
                    injured_count = sum(1 for p in available_players if p.get('is_injured', False))
                    available_players = [p for p in available_players if not p.get('is_injured', False)]
                    print(f"✓ Fetched {len(available_players)} available skaters (goalies and {injured_count} injured players filtered out)")
                except Exception as e:
                    print(f"Error fetching available players: {e}", file=sys.stderr)
                    return 2

        except ImportError:
            print("\n⚠ Yahoo client not available. Install required dependencies.", file=sys.stderr)
            yahoo_failed = True
        except Exception as e:
            print(f"\n⚠ Error fetching from Yahoo API: {e}", file=sys.stderr)
            yahoo_failed = True

        # If Yahoo failed, prompt for fallback
        if yahoo_failed:
            if prompt_user_yes_no(f"Would you like to use local roster file ({args.roster})?"):
                use_local = True
            else:
                print("Exiting. Please fix Yahoo API configuration or use --local flag.", file=sys.stderr)
                return 2

    if use_local:
        # Load from local YAML file
        try:
            with open(args.roster, "r", encoding="utf-8") as f:
                roster = yaml.safe_load(f)

            players: List[Player] = [
                Player(name=p["name"], team=p["team"], pos=tuple(p["pos"]))
                for p in roster.get("players", [])
            ]

            print(f"✓ Loaded {len(players)} players from {args.roster}")

            # Use roster slots if defined in YAML
            if roster.get("slots"):
                SLOTS = roster["slots"]

        except FileNotFoundError:
            print(f"Error: Roster file '{args.roster}' not found.", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"Error loading roster file: {e}", file=sys.stderr)
            return 2

    if not players:
        print("No players found", file=sys.stderr)
        return 2

    # Handle single-day mode
    if args.day:
        target_date = dt.date.fromisoformat(args.date) if args.date else today
        week_start = week_start_monday(target_date)

        # Build games-per-player for the week (API works week-by-week)
        p_games = build_player_game_matrix(players, week_start)

        # Get active players for the target date
        active = [p for p in players if target_date in p_games.get(p.name, set())]

        # Solve the assignment
        assignment = solve_daily_assignment(active, SLOTS)

        # Display results
        day_name = target_date.strftime("%A")
        print(f"\n{day_name}, {target_date.isoformat()}\n")

        # Build single-column grid
        grid: List[List[str]] = [[slot, ""] for slot in SLOTS]
        filled_by_pos = {k: 0 for k in set(SLOTS)}
        empties_by_pos = {k: 0 for k in set(SLOTS)}

        for s_i, slot in enumerate(SLOTS):
            if s_i in assignment:
                grid[s_i][1] = "X"
                filled_by_pos[slot] += 1
            else:
                empties_by_pos[slot] += 1

        # Handle export
        header = ["POS", day_name[:3]]
        if args.export:
            if args.export == "csv":
                export_file = args.export_file or generate_export_filename("csv")
                output = export_to_csv(grid, header, export_file)
                print(f"✓ Exported to {export_file}")
            elif args.export == "markdown":
                export_file = args.export_file or generate_export_filename("markdown")
                output = export_to_markdown(grid, header, export_file)
                print(f"✓ Exported to {export_file}")
            elif args.export == "clipboard":
                output = export_to_csv(grid, header)
                if copy_to_clipboard(output):
                    print("✓ Copied to clipboard")
                else:
                    print("✗ Failed to copy to clipboard (pbcopy/xclip not available)", file=sys.stderr)
            return 0

        # Print single-day grid with EFF and PCT columns, sorted by efficiency
        sorted_indices = sort_slots_by_efficiency(SLOTS, grid, 1)

        col_w = 4
        pos_w = 3  # "LW1", "RW2", etc.
        eff_w = 3  # "1/1"
        pct_w = 6  # "100.0%"

        print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  {day_name[:3]:>{col_w}}")

        # Renumber slots after sorting
        pos_counts = {}
        for s_i in sorted_indices:
            row = grid[s_i]
            slot = SLOTS[s_i]
            pos_counts[slot] = pos_counts.get(slot, 0) + 1
            slot_name = f"{slot}{pos_counts[slot]}"

            # Calculate efficiency for this slot
            filled = 1 if row[1] else 0
            total = 1
            pct = (filled / total * 100) if total > 0 else 0

            # Format the row with colors
            cell = colorize_cell(row[1])
            pct_color = colorize_percentage(pct)
            eff_str = f"{pct_color}{filled}/{total}{Colors.RESET}"
            pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
            print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  {cell}")

        # Add summary row
        total_slots = len(SLOTS)
        filled_count = sum(1 for s_i in range(len(SLOTS)) if grid[s_i][1])
        daily_pct = (filled_count / total_slots * 100) if total_slots > 0 else 0
        daily_color = colorize_percentage(daily_pct)
        daily_eff_str = f"{daily_color}{filled_count}/{total_slots}{Colors.RESET}"
        daily_pct_str = f"{daily_color}{daily_pct:5.1f}%{Colors.RESET}"
        daily_count_str = f"{daily_color}{filled_count}{Colors.RESET}"
        print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  {'─' * col_w}")
        print(f"{'TOT':<{pos_w}}  {daily_eff_str}  {daily_pct_str}  {daily_count_str}")

        print("\nEmpty slots by position:")
        for pos in ["C", "LW", "RW", "D", "G"]:
            print(f"  {pos}: {empties_by_pos.get(pos, 0)}")

        # Calculate and show idle players
        idle_by_pos = calculate_idle_players(players, SLOTS)
        if idle_by_pos:
            print("\nIdle players by position (surplus over roster slots):")
            for pos in ["C", "LW", "RW", "D", "G"]:
                if pos in idle_by_pos:
                    print(f"  {pos}: {idle_by_pos[pos]}")

        return 0

    # Handle comparison mode (must be before regular week mode)
    if args.compare_team and opponent_players:
        # Determine the week to analyze
        if args.date:
            provided_date = dt.date.fromisoformat(args.date)
            week_start = week_start_monday(provided_date)
        else:
            week_start = week_start_monday(today)

        week_end = week_start + dt.timedelta(days=6)
        week_dates = daterange(week_start, 7)

        # Build games-per-player for both teams
        your_p_games = build_player_game_matrix(players, week_start)
        opp_p_games = build_player_game_matrix(opponent_players, week_start)

        # Generate grids for both teams
        your_grid: List[List[str]] = [[slot] + [""] * 7 for slot in SLOTS]
        opp_grid: List[List[str]] = [[slot] + [""] * 7 for slot in SLOTS]

        your_filled_by_pos = {k: 0 for k in set(SLOTS)}
        opp_filled_by_pos = {k: 0 for k in set(SLOTS)}

        # Process each day for both teams
        for day_i, day_date in enumerate(week_dates):
            # Your team
            your_active = [p for p in players if day_date in your_p_games.get(p.name, set())]
            your_assignment = solve_daily_assignment(your_active, SLOTS)
            for s_i, slot in enumerate(SLOTS):
                if s_i in your_assignment:
                    your_grid[s_i][1 + day_i] = "X"
                    your_filled_by_pos[slot] += 1

            # Opponent team
            opp_active = [p for p in opponent_players if day_date in opp_p_games.get(p.name, set())]
            opp_assignment = solve_daily_assignment(opp_active, SLOTS)
            for s_i, slot in enumerate(SLOTS):
                if s_i in opp_assignment:
                    opp_grid[s_i][1 + day_i] = "X"
                    opp_filled_by_pos[slot] += 1

        # Display both grids
        day_abbrevs = ["M", "T", "W", "Th", "F", "Sa", "Su"]
        if args.compact:
            header = ["POS"] + day_abbrevs
        else:
            header = ["POS"] + [f"{abbr}({d.strftime('%m/%d')})" for abbr, d in zip(day_abbrevs, week_dates)]

        # Column widths
        pos_w = 3
        eff_w = 5
        pct_w = 6
        col_w = 3 if args.compact else 8
        header_align = '^' if args.compact else '>'
        total_slots = len(SLOTS)

        # Calculate daily fills for both teams (needed for summary rows)
        your_daily_fills = []
        opp_daily_fills = []
        for day_i in range(7):
            your_day_filled = sum(1 for s_i in range(len(SLOTS)) if your_grid[s_i][1 + day_i] == "X")
            opp_day_filled = sum(1 for s_i in range(len(SLOTS)) if opp_grid[s_i][1 + day_i] == "X")
            your_daily_fills.append(your_day_filled)
            opp_daily_fills.append(opp_day_filled)

        # Print YOUR TEAM grid
        print(f"\n=== YOUR TEAM: {week_start.isoformat()} → {week_end.isoformat()} ===\n")
        sorted_indices = sort_slots_by_efficiency(SLOTS, your_grid, 7)
        print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  " + "  ".join(f"{h:{header_align}{col_w}}" for h in header[1:]))

        pos_counts = {}
        for s_i in sorted_indices:
            row = your_grid[s_i]
            slot = SLOTS[s_i]
            pos_counts[slot] = pos_counts.get(slot, 0) + 1
            slot_name = f"{slot}{pos_counts[slot]}"

            cells = row[1:]
            filled = sum(1 for cell in cells if cell == "X")
            pct = (filled / 7 * 100) if 7 > 0 else 0

            colored_cells = [pad_colored_cell(colorize_cell(cell), col_w) for cell in cells]
            pct_color = colorize_percentage(pct)
            eff_str = f"{pct_color}{filled:>2}/{7:<2}{Colors.RESET}"
            pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
            print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  " + "  ".join(colored_cells))

        # Add summary row for YOUR TEAM
        your_week_total_filled = sum(your_daily_fills)
        your_week_total_slots = total_slots * 7
        your_week_pct = (your_week_total_filled / your_week_total_slots * 100) if your_week_total_slots > 0 else 0
        your_week_color = colorize_percentage(your_week_pct)
        your_week_eff_str = f"{your_week_color}{your_week_total_filled:>2}/{your_week_total_slots:<2}{Colors.RESET}"
        your_week_pct_str = f"{your_week_color}{your_week_pct:5.1f}%{Colors.RESET}"

        your_daily_cells = []
        for day_filled in your_daily_fills:
            day_pct = (day_filled / total_slots * 100) if total_slots > 0 else 0
            day_color = colorize_percentage(day_pct)
            day_str = f"{day_color}{day_filled}{Colors.RESET}"
            your_daily_cells.append(pad_colored_cell(day_str, col_w))

        print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  " + "  ".join(['─' * col_w for _ in range(7)]))
        print(f"{'TOT':<{pos_w}}  {your_week_eff_str}  {your_week_pct_str}  " + "  ".join(your_daily_cells))

        # Print OPPONENT grid
        print(f"\n=== OPPONENT (Team {args.compare_team}): {week_start.isoformat()} → {week_end.isoformat()} ===\n")
        sorted_indices = sort_slots_by_efficiency(SLOTS, opp_grid, 7)
        print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  " + "  ".join(f"{h:{header_align}{col_w}}" for h in header[1:]))

        pos_counts = {}
        for s_i in sorted_indices:
            row = opp_grid[s_i]
            slot = SLOTS[s_i]
            pos_counts[slot] = pos_counts.get(slot, 0) + 1
            slot_name = f"{slot}{pos_counts[slot]}"

            cells = row[1:]
            filled = sum(1 for cell in cells if cell == "X")
            pct = (filled / 7 * 100) if 7 > 0 else 0

            colored_cells = [pad_colored_cell(colorize_cell(cell), col_w) for cell in cells]
            pct_color = colorize_percentage(pct)
            eff_str = f"{pct_color}{filled:>2}/{7:<2}{Colors.RESET}"
            pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
            print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  " + "  ".join(colored_cells))

        # Add summary row for OPPONENT
        opp_week_total_filled = sum(opp_daily_fills)
        opp_week_total_slots = total_slots * 7
        opp_week_pct = (opp_week_total_filled / opp_week_total_slots * 100) if opp_week_total_slots > 0 else 0
        opp_week_color = colorize_percentage(opp_week_pct)
        opp_week_eff_str = f"{opp_week_color}{opp_week_total_filled:>2}/{opp_week_total_slots:<2}{Colors.RESET}"
        opp_week_pct_str = f"{opp_week_color}{opp_week_pct:5.1f}%{Colors.RESET}"

        opp_daily_cells = []
        for day_filled in opp_daily_fills:
            day_pct = (day_filled / total_slots * 100) if total_slots > 0 else 0
            day_color = colorize_percentage(day_pct)
            day_str = f"{day_color}{day_filled}{Colors.RESET}"
            opp_daily_cells.append(pad_colored_cell(day_str, col_w))

        print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  " + "  ".join(['─' * col_w for _ in range(7)]))
        print(f"{'TOT':<{pos_w}}  {opp_week_eff_str}  {opp_week_pct_str}  " + "  ".join(opp_daily_cells))

        # Print comparison summary
        print("\n=== Comparison Summary ===\n")

        # Calculate overall stats
        total_slots = len(SLOTS)
        your_total_filled = sum(your_filled_by_pos.values())
        opp_total_filled = sum(opp_filled_by_pos.values())
        your_overall_pct = (your_total_filled / (total_slots * 7) * 100) if total_slots > 0 else 0
        opp_overall_pct = (opp_total_filled / (total_slots * 7) * 100) if total_slots > 0 else 0

        # Print comparison table
        print(f"{'':20} {'YOUR TEAM':>12}  {'OPPONENT':>12}  {'DIFF':>8}")
        print(f"{'─' * 20} {'─' * 12}  {'─' * 12}  {'─' * 8}")

        # Overall stats
        eff_diff = your_total_filled - opp_total_filled
        eff_diff_str = f"{'+' if eff_diff >= 0 else ''}{eff_diff}"
        eff_diff_color = Colors.GREEN if eff_diff > 0 else (Colors.RED if eff_diff < 0 else Colors.YELLOW)
        print(f"{'EFF':20} {your_total_filled:>5}/{total_slots * 7:<6}  {opp_total_filled:>5}/{total_slots * 7:<6}  {eff_diff_color}{eff_diff_str:>8}{Colors.RESET}")

        pct_diff = your_overall_pct - opp_overall_pct
        pct_diff_str = f"{'+' if pct_diff >= 0 else ''}{pct_diff:.1f}%"
        pct_diff_color = Colors.GREEN if pct_diff > 0 else (Colors.RED if pct_diff < 0 else Colors.YELLOW)
        print(f"{'PCT':20} {your_overall_pct:>11.1f}%  {opp_overall_pct:>11.1f}%  {pct_diff_color}{pct_diff_str:>8}{Colors.RESET}")

        # Daily breakdown
        for day_i, abbr in enumerate(day_abbrevs):
            day_date = week_dates[day_i]
            day_label = f"{abbr} ({day_date.strftime('%m/%d')})"
            your_filled = your_daily_fills[day_i]
            opp_filled = opp_daily_fills[day_i]
            diff = your_filled - opp_filled
            diff_str = f"{'+' if diff >= 0 else ''}{diff}"
            diff_color = Colors.GREEN if diff > 0 else (Colors.RED if diff < 0 else Colors.YELLOW)
            print(f"{day_label:20} {your_filled:>12}  {opp_filled:>12}  {diff_color}{diff_str:>8}{Colors.RESET}")

        return 0

    # Handle player swap mode (must be before regular week mode)
    if args.player_swap and swap_add_player:
        drop_player_id, add_player_id = args.player_swap

        # Find the player to drop by matching Yahoo player ID from roster
        # Note: Yahoo roster data doesn't include player IDs, so we'll match by name search
        # For now, we'll use a simpler approach: let the user know which player to identify
        print("\nCurrent roster players:")
        for i, p in enumerate(players, 1):
            print(f"  {i}. {p.name} ({p.team}, {'/'.join(p.pos)})")

        # Try to fetch the drop player details to get their name
        try:
            drop_player_data = client.fetch_player_details(drop_player_id)
            drop_player_name = drop_player_data["name"]
        except Exception as e:
            print(f"Error fetching player {drop_player_id} details: {e}", file=sys.stderr)
            return 2

        # Find and remove the drop player from roster
        drop_player = None
        for p in players:
            if p.name == drop_player_name:
                drop_player = p
                break

        if not drop_player:
            print(f"Error: Player '{drop_player_name}' not found in your roster", file=sys.stderr)
            return 2

        print(f"→ Dropping: {drop_player.name} ({drop_player.team}, {'/'.join(drop_player.pos)})")
        print(f"→ Adding: {swap_add_player.name} ({swap_add_player.team}, {'/'.join(swap_add_player.pos)})")

        # Create modified roster
        modified_players = [p for p in players if p.name != drop_player_name]
        modified_players.append(swap_add_player)

        # Determine the week to analyze
        if args.date:
            provided_date = dt.date.fromisoformat(args.date)
            week_start = week_start_monday(provided_date)
        else:
            week_start = week_start_monday(today)

        week_end = week_start + dt.timedelta(days=6)
        week_dates = daterange(week_start, 7)

        # Build games-per-player for both rosters
        current_p_games = build_player_game_matrix(players, week_start)
        modified_p_games = build_player_game_matrix(modified_players, week_start)

        # Generate grids for both rosters
        current_grid: List[List[str]] = [[slot] + [""] * 7 for slot in SLOTS]
        modified_grid: List[List[str]] = [[slot] + [""] * 7 for slot in SLOTS]

        current_filled_by_pos = {k: 0 for k in set(SLOTS)}
        modified_filled_by_pos = {k: 0 for k in set(SLOTS)}

        # Process each day for both rosters
        for day_i, day_date in enumerate(week_dates):
            # Current roster
            current_active = [p for p in players if day_date in current_p_games.get(p.name, set())]
            current_assignment = solve_daily_assignment(current_active, SLOTS)
            for s_i, slot in enumerate(SLOTS):
                if s_i in current_assignment:
                    current_grid[s_i][1 + day_i] = "X"
                    current_filled_by_pos[slot] += 1

            # Modified roster
            modified_active = [p for p in modified_players if day_date in modified_p_games.get(p.name, set())]
            modified_assignment = solve_daily_assignment(modified_active, SLOTS)
            for s_i, slot in enumerate(SLOTS):
                if s_i in modified_assignment:
                    modified_grid[s_i][1 + day_i] = "X"
                    modified_filled_by_pos[slot] += 1

        # Display both grids
        day_abbrevs = ["M", "T", "W", "Th", "F", "Sa", "Su"]
        if args.compact:
            header = ["POS"] + day_abbrevs
        else:
            header = ["POS"] + [f"{abbr}({d.strftime('%m/%d')})" for abbr, d in zip(day_abbrevs, week_dates)]

        # Column widths
        pos_w = 3
        eff_w = 5
        pct_w = 6
        col_w = 3 if args.compact else 8
        header_align = '^' if args.compact else '>'
        total_slots = len(SLOTS)

        # Calculate daily fills for both rosters (needed for summary rows)
        current_daily_fills = []
        modified_daily_fills = []
        for day_i in range(7):
            current_day_filled = sum(1 for s_i in range(len(SLOTS)) if current_grid[s_i][1 + day_i] == "X")
            modified_day_filled = sum(1 for s_i in range(len(SLOTS)) if modified_grid[s_i][1 + day_i] == "X")
            current_daily_fills.append(current_day_filled)
            modified_daily_fills.append(modified_day_filled)

        # Print CURRENT ROSTER grid
        print(f"\n=== CURRENT ROSTER: {week_start.isoformat()} → {week_end.isoformat()} ===\n")
        sorted_indices = sort_slots_by_efficiency(SLOTS, current_grid, 7)
        print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  " + "  ".join(f"{h:{header_align}{col_w}}" for h in header[1:]))

        pos_counts = {}
        for s_i in sorted_indices:
            row = current_grid[s_i]
            slot = SLOTS[s_i]
            pos_counts[slot] = pos_counts.get(slot, 0) + 1
            slot_name = f"{slot}{pos_counts[slot]}"

            cells = row[1:]
            filled = sum(1 for cell in cells if cell == "X")
            pct = (filled / 7 * 100) if 7 > 0 else 0

            colored_cells = [pad_colored_cell(colorize_cell(cell), col_w) for cell in cells]
            pct_color = colorize_percentage(pct)
            eff_str = f"{pct_color}{filled:>2}/{7:<2}{Colors.RESET}"
            pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
            print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  " + "  ".join(colored_cells))

        # Add summary row for CURRENT ROSTER
        current_week_total_filled = sum(current_daily_fills)
        current_week_total_slots = total_slots * 7
        current_week_pct = (current_week_total_filled / current_week_total_slots * 100) if current_week_total_slots > 0 else 0
        current_week_color = colorize_percentage(current_week_pct)
        current_week_eff_str = f"{current_week_color}{current_week_total_filled:>2}/{current_week_total_slots:<2}{Colors.RESET}"
        current_week_pct_str = f"{current_week_color}{current_week_pct:5.1f}%{Colors.RESET}"

        current_daily_cells = []
        for day_filled in current_daily_fills:
            day_pct = (day_filled / total_slots * 100) if total_slots > 0 else 0
            day_color = colorize_percentage(day_pct)
            day_str = f"{day_color}{day_filled}{Colors.RESET}"
            current_daily_cells.append(pad_colored_cell(day_str, col_w))

        print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  " + "  ".join(['─' * col_w for _ in range(7)]))
        print(f"{'TOT':<{pos_w}}  {current_week_eff_str}  {current_week_pct_str}  " + "  ".join(current_daily_cells))

        # Print WITH SWAP grid
        print(f"\n=== WITH SWAP: {week_start.isoformat()} → {week_end.isoformat()} ===\n")
        sorted_indices = sort_slots_by_efficiency(SLOTS, modified_grid, 7)
        print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  " + "  ".join(f"{h:{header_align}{col_w}}" for h in header[1:]))

        pos_counts = {}
        for s_i in sorted_indices:
            row = modified_grid[s_i]
            slot = SLOTS[s_i]
            pos_counts[slot] = pos_counts.get(slot, 0) + 1
            slot_name = f"{slot}{pos_counts[slot]}"

            cells = row[1:]
            filled = sum(1 for cell in cells if cell == "X")
            pct = (filled / 7 * 100) if 7 > 0 else 0

            colored_cells = [pad_colored_cell(colorize_cell(cell), col_w) for cell in cells]
            pct_color = colorize_percentage(pct)
            eff_str = f"{pct_color}{filled:>2}/{7:<2}{Colors.RESET}"
            pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
            print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  " + "  ".join(colored_cells))

        # Add summary row for WITH SWAP
        modified_week_total_filled = sum(modified_daily_fills)
        modified_week_total_slots = total_slots * 7
        modified_week_pct = (modified_week_total_filled / modified_week_total_slots * 100) if modified_week_total_slots > 0 else 0
        modified_week_color = colorize_percentage(modified_week_pct)
        modified_week_eff_str = f"{modified_week_color}{modified_week_total_filled:>2}/{modified_week_total_slots:<2}{Colors.RESET}"
        modified_week_pct_str = f"{modified_week_color}{modified_week_pct:5.1f}%{Colors.RESET}"

        modified_daily_cells = []
        for day_filled in modified_daily_fills:
            day_pct = (day_filled / total_slots * 100) if total_slots > 0 else 0
            day_color = colorize_percentage(day_pct)
            day_str = f"{day_color}{day_filled}{Colors.RESET}"
            modified_daily_cells.append(pad_colored_cell(day_str, col_w))

        print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  " + "  ".join(['─' * col_w for _ in range(7)]))
        print(f"{'TOT':<{pos_w}}  {modified_week_eff_str}  {modified_week_pct_str}  " + "  ".join(modified_daily_cells))

        # Print comparison summary
        print(f"\n=== Swap Impact Summary (Drop {drop_player.name}, Add {swap_add_player.name}) ===\n")

        # Calculate overall stats
        total_slots = len(SLOTS)
        current_total_filled = sum(current_filled_by_pos.values())
        modified_total_filled = sum(modified_filled_by_pos.values())
        current_overall_pct = (current_total_filled / (total_slots * 7) * 100) if total_slots > 0 else 0
        modified_overall_pct = (modified_total_filled / (total_slots * 7) * 100) if total_slots > 0 else 0

        # Print comparison table
        print(f"{'':20} {'CURRENT':>12}  {'WITH SWAP':>12}  {'DIFF':>8}")
        print(f"{'─' * 20} {'─' * 12}  {'─' * 12}  {'─' * 8}")

        # Overall stats
        eff_diff = modified_total_filled - current_total_filled
        eff_diff_str = f"{'+' if eff_diff >= 0 else ''}{eff_diff}"
        eff_diff_color = Colors.GREEN if eff_diff > 0 else (Colors.RED if eff_diff < 0 else Colors.YELLOW)
        print(f"{'EFF':20} {current_total_filled:>5}/{total_slots * 7:<6}  {modified_total_filled:>5}/{total_slots * 7:<6}  {eff_diff_color}{eff_diff_str:>8}{Colors.RESET}")

        pct_diff = modified_overall_pct - current_overall_pct
        pct_diff_str = f"{'+' if pct_diff >= 0 else ''}{pct_diff:.1f}%"
        pct_diff_color = Colors.GREEN if pct_diff > 0 else (Colors.RED if pct_diff < 0 else Colors.YELLOW)
        print(f"{'PCT':20} {current_overall_pct:>11.1f}%  {modified_overall_pct:>11.1f}%  {pct_diff_color}{pct_diff_str:>8}{Colors.RESET}")

        # Daily breakdown
        for day_i, abbr in enumerate(day_abbrevs):
            day_date = week_dates[day_i]
            day_label = f"{abbr} ({day_date.strftime('%m/%d')})"
            current_filled = current_daily_fills[day_i]
            modified_filled = modified_daily_fills[day_i]
            diff = modified_filled - current_filled
            diff_str = f"{'+' if diff >= 0 else ''}{diff}"
            diff_color = Colors.GREEN if diff > 0 else (Colors.RED if diff < 0 else Colors.YELLOW)
            print(f"{day_label:20} {current_filled:>12}  {modified_filled:>12}  {diff_color}{diff_str:>8}{Colors.RESET}")

        return 0

    # Handle recommend add mode (must be before regular week mode)
    if args.recommend_add and available_players:
        drop_player_name = args.recommend_add

        # Find the drop player from roster by name
        drop_player = None
        for p in players:
            if p.name.lower() == drop_player_name.lower():
                drop_player = p
                break

        if not drop_player:
            print(f"Error: Player '{drop_player_name}' not found in your roster", file=sys.stderr)
            print("\nAvailable roster players:", file=sys.stderr)
            for p in sorted(players, key=lambda x: x.name):
                print(f"  - {p.name}", file=sys.stderr)
            return 2

        print(f"\nAnalyzing recommendations to replace: {drop_player.name} ({drop_player.team}, {'/'.join(drop_player.pos)})")

        # Determine the week to analyze
        if args.date:
            provided_date = dt.date.fromisoformat(args.date)
            week_start = week_start_monday(provided_date)
        else:
            week_start = week_start_monday(today)

        week_end = week_start + dt.timedelta(days=6)
        week_dates = daterange(week_start, 7)

        print(f"Week: {week_start.isoformat()} → {week_end.isoformat()}\n")

        # Build current roster game matrix
        current_p_games = build_player_game_matrix(players, week_start)

        # Calculate current roster efficiency
        current_total_filled = 0
        for day_date in week_dates:
            current_active = [p for p in players if day_date in current_p_games.get(p.name, set())]
            current_assignment = solve_daily_assignment(current_active, SLOTS)
            current_total_filled += len(current_assignment)

        # Get NHL stats for calculating PPG and weekly estimates
        print("Fetching NHL stats for PPG calculations...")
        nhl_api.fetch_season_stats(force_refresh=args.force)  # Pre-fetch and cache NHL stats

        # Get games next week for drop player
        drop_p_games = build_player_game_matrix([drop_player], week_start)
        drop_games_next_week = len(drop_p_games.get(drop_player.name, set()))

        # Calculate drop player's estimated weekly points
        drop_player_gp = nhl_api.get_games_played(drop_player.name, drop_player.team)
        drop_player_est_pts = 0.0  # Default
        drop_player_fpts = 0.0
        drop_player_ppg = 0.0

        # Fetch drop player's stats from Yahoo API using league player search
        try:
            # Search for player by last name using league players endpoint
            last_name = drop_player.name.split()[-1]
            search_endpoint = (
                f"league/nhl.l.{config.league_id}/players;"
                f"search={last_name};"
                f"count=25;"
                f"out=stats"
            )
            search_data = client._api_request(search_endpoint)

            # Parse search results to find matching player
            found_player = False
            if "fantasy_content" in search_data and "league" in search_data["fantasy_content"]:
                league_data = search_data["fantasy_content"]["league"]
                for item in league_data:
                    if isinstance(item, dict) and "players" in item:
                        players_data = item["players"]
                        for key, player_wrapper_data in players_data.items():
                            if key == "count":
                                continue

                            player_wrapper = player_wrapper_data["player"]
                            player = player_wrapper[0]

                            # Get player name
                            name_obj = next((p for p in player if isinstance(p, dict) and "name" in p), None)
                            if name_obj and name_obj["name"]["full"].lower() == drop_player.name.lower():
                                # Found the player, extract fantasy points
                                found_player = True
                                for elem in player_wrapper[1:]:
                                    if isinstance(elem, dict) and "player_points" in elem:
                                        player_points = elem["player_points"]
                                        if "total" in player_points:
                                            try:
                                                drop_player_fpts = float(player_points["total"])
                                                print(f"  ✓ Found drop player in Yahoo API: {drop_player_fpts:.1f} FPTS")
                                            except (ValueError, TypeError):
                                                drop_player_fpts = 0.0
                                            break
                                break
                        if found_player:
                            break

            if not found_player:
                print(f"  Note: Could not find {drop_player.name} in Yahoo search results")
        except Exception as e:
            print(f"  Warning: Could not fetch drop player stats from Yahoo API: {e}")

        # Calculate estimated weekly points for drop player
        if drop_player_gp and drop_player_gp > 0 and drop_player_fpts > 0:
            drop_player_ppg = drop_player_fpts / drop_player_gp
            drop_player_est_pts = drop_player_ppg * drop_games_next_week
            print(f"  Drop player info: {drop_player_fpts:.1f} FPTS, {drop_player_gp} GP, {drop_player_ppg:.2f} FPTS/G, {drop_games_next_week} G@ next week → Est {drop_player_est_pts:.1f} pts")
        else:
            print(f"  Drop player info: {drop_games_next_week} G@ next week (stats unavailable)")

        # Run simulations for each available player
        print(f"Simulating swaps with {len(available_players)} available players...")
        recommendations = []

        for i, avail_player_data in enumerate(available_players):
            # Create Player object
            avail_player = Player(
                name=avail_player_data["name"],
                team=avail_player_data["team"],
                pos=tuple(avail_player_data["pos"])
            )

            # Create modified roster
            modified_players = [p for p in players if p.name != drop_player_name]
            modified_players.append(avail_player)

            # Build modified roster game matrix
            modified_p_games = build_player_game_matrix(modified_players, week_start)

            # Calculate modified roster efficiency
            modified_total_filled = 0
            for day_date in week_dates:
                modified_active = [p for p in modified_players if day_date in modified_p_games.get(p.name, set())]
                modified_assignment = solve_daily_assignment(modified_active, SLOTS)
                modified_total_filled += len(modified_assignment)

            # Calculate efficiency gain
            eff_gain = modified_total_filled - current_total_filled

            # Get overall rank (OR) from Yahoo API - lower is better
            overall_rank = avail_player_data.get("overall_rank", i + 1)  # Fallback to index if not available

            # Get total fantasy points (Yahoo provides this directly)
            fantasy_points_total = avail_player_data.get("fantasy_points_total", 0.0)

            # Get games next week for this player
            avail_games_next_week = len(modified_p_games.get(avail_player.name, set()))

            # Get games played from NHL API to calculate PPG
            gp = nhl_api.get_games_played(avail_player.name, avail_player.team)

            # Calculate estimated weekly point differential
            weekly_pt_diff = None
            ppg = None
            avail_estimated_pts = None

            if gp and gp > 0:
                # Calculate PPG (fantasy points per game)
                ppg = fantasy_points_total / gp

                # Estimate weekly points for new player
                avail_estimated_pts = ppg * avail_games_next_week

                # Calculate differential if we have drop player's estimated points
                if drop_player_est_pts is not None:
                    weekly_pt_diff = avail_estimated_pts - drop_player_est_pts
                else:
                    # If we can't get drop player stats, just show add player estimate
                    weekly_pt_diff = avail_estimated_pts

            recommendations.append({
                "player": avail_player,
                "eff_gain": eff_gain,
                "overall_rank": overall_rank,
                "fpts": fantasy_points_total,
                "ownership_pct": avail_player_data.get("ownership_pct", 0.0),
                "stats": avail_player_data.get("stats", {}),
                "games_played": gp,
                "games_next_week": avail_games_next_week,
                "ppg": ppg,
                "est_week_pts": avail_estimated_pts,
                "weekly_pt_diff": weekly_pt_diff
            })

            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"  Simulated {i + 1}/{len(available_players)} players...")

        print(f"✓ Completed {len(available_players)} simulations\n")

        # Sort recommendations by:
        # 1. Efficiency gain (descending)
        # 2. Overall rank (ascending - lower is better)
        # 3. Total fantasy points (descending)
        recommendations.sort(key=lambda r: (-r["eff_gain"], r["overall_rank"], -r["fpts"]))

        # Display top N recommendations
        top_n = min(args.top, len(recommendations))

        # Show drop player info
        if drop_player_ppg > 0:
            drop_info = f"Drop: {drop_player.name} ({drop_player.team}, {'/'.join(drop_player.pos)}), {drop_games_next_week} G@ next week, {drop_player_ppg:.2f} FPTS/G"
        else:
            drop_info = f"Drop: {drop_player.name} ({drop_player.team}, {'/'.join(drop_player.pos)}), {drop_games_next_week} G@ next week"
        print(f"=== Top {top_n} Free Agent Recommendations ({drop_info}) ===\n")

        # Table header with new columns
        print(f"{'RANK':<6} {'PLAYER':<25} {'TEAM':<5} {'POS':<10} {'EFF':>5} {'GP':>4} {'G@':>4} {'OR#':>5} {'FPTS':>6} {'FPTS/G':>7} {'Est Week':>9} {'Est Δ':>7} {'OWN%':>6}")
        print(f"{'─' * 6} {'─' * 25} {'─' * 5} {'─' * 10} {'─' * 5} {'─' * 4} {'─' * 4} {'─' * 5} {'─' * 6} {'─' * 7} {'─' * 9} {'─' * 7} {'─' * 6}")

        for rank, rec in enumerate(recommendations[:top_n], 1):
            player = rec["player"]
            eff_gain = rec["eff_gain"]
            overall_rank = rec["overall_rank"]
            fpts = rec["fpts"]
            own_pct = rec["ownership_pct"]
            gp = rec.get("games_played")
            games_next_week = rec.get("games_next_week", 0)
            ppg = rec.get("ppg")
            est_week_pts = rec.get("est_week_pts")
            weekly_pt_diff = rec.get("weekly_pt_diff")

            # Color code efficiency gain
            if eff_gain > 0:
                eff_str = f"{Colors.GREEN}+{eff_gain}{Colors.RESET}"
            elif eff_gain < 0:
                eff_str = f"{Colors.RED}{eff_gain}{Colors.RESET}"
            else:
                eff_str = f"{Colors.YELLOW}{eff_gain}{Colors.RESET}"

            # Format GP
            gp_str = str(gp) if gp is not None else "?"

            # Format games next week
            g_at_str = str(games_next_week)

            # Format FPTS/G
            ppg_str = f"{ppg:.2f}" if ppg is not None else "N/A"

            # Format estimated weekly points
            est_week_str = f"{est_week_pts:.1f}" if est_week_pts is not None else "N/A"

            # Color code weekly point differential
            if weekly_pt_diff is not None:
                if weekly_pt_diff > 0:
                    est_diff_str = f"{Colors.GREEN}+{weekly_pt_diff:.1f}{Colors.RESET}"
                elif weekly_pt_diff < 0:
                    est_diff_str = f"{Colors.RED}{weekly_pt_diff:.1f}{Colors.RESET}"
                else:
                    est_diff_str = f"{Colors.YELLOW}{weekly_pt_diff:.1f}{Colors.RESET}"
            else:
                est_diff_str = "N/A"

            pos_str = '/'.join(player.pos)
            # Use pad_colored for columns with ANSI color codes
            eff_padded = pad_colored(eff_str, 5, '>')
            est_diff_padded = pad_colored(est_diff_str, 7, '>')
            print(f"{rank:<6} {player.name:<25} {player.team:<5} {pos_str:<10} {eff_padded} {gp_str:>4} {g_at_str:>4} {overall_rank:>5} {fpts:>6.1f} {ppg_str:>7} {est_week_str:>9} {est_diff_padded} {own_pct:>5.1f}%")

        # Print legend
        print("\nLegend:")
        print("  EFF      = Efficiency gain (additional games in lineup for the week)")
        print("  GP       = Games played this season (from NHL API)")
        print("  G@       = Games next week (for this player)")
        print("  OR#      = Season rank (Yahoo's 2025 season performance rank, lower = better)")
        print("  FPTS     = Total fantasy points this season")
        print("  FPTS/G   = Fantasy points per game (FPTS ÷ GP)")
        print("  Est Week = Estimated fantasy points for this week (FPTS/G × G@)")
        print("  Est Δ    = Estimated weekly point differential (New Player Est Week - Drop Player Est Week)")
        print("  OWN%     = Ownership percentage")

        return 0

    # Handle --available-fas mode (streaming pickups for specific date)
    if args.available_fas:
        from yahoo_client import YahooClient
        from config import config

        target_date = args.available_fas_date

        # Initialize Yahoo client
        client = YahooClient()
        client.authorize()

        # Fetch roster
        print("Fetching roster from Yahoo API...")
        roster_data = client.fetch_team_roster()
        players = [
            Player(name=p["name"], team=p["team"], pos=tuple(p["pos"]))
            for p in roster_data
        ]

        # Fetch available players (limit to top 100)
        print("Fetching available free agents...")
        available_players = client.fetch_available_players(count=100, use_cache=not args.force)

        # Filter out goalies
        available_players = [p for p in available_players if 'G' not in p['pos']]

        # Filter out injured players
        injured_count = sum(1 for p in available_players if p.get('is_injured', False))
        if injured_count > 0:
            print(f"  Filtered out {injured_count} injured players")
        available_players = [p for p in available_players if not p.get('is_injured', False)]

        print(f"  Found {len(available_players)} available skaters")

        # Pre-fetch NHL stats for GP calculations
        print("Fetching NHL stats for FPTS/G calculations...")
        nhl_api.fetch_season_stats(force_refresh=args.force)

        # Build single-date game matrix for available players
        available_player_objs = [
            Player(name=p["name"], team=p["team"], pos=tuple(p["pos"]))
            for p in available_players
        ]
        available_games = build_single_date_game_matrix(available_player_objs, target_date)

        # Filter available players to those playing on target date
        streaming_candidates = []
        for i, avail_data in enumerate(available_players):
            player_name = avail_data["name"]
            if available_games.get(player_name, False):
                # Get NHL stats for FPTS/G calculation
                gp = nhl_api.get_games_played(player_name, avail_data["team"])
                fpts = avail_data.get("fantasy_points_total", 0.0)

                if gp and gp > 0 and fpts > 0:
                    fpts_per_game = fpts / gp
                    streaming_candidates.append({
                        "player": Player(name=player_name, team=avail_data["team"], pos=tuple(avail_data["pos"])),
                        "fpts_per_game": fpts_per_game,
                        "overall_rank": avail_data.get("overall_rank", 999),
                        "fpts": fpts,
                        "gp": gp,
                        "ownership_pct": avail_data.get("ownership_pct", 0.0),
                        "positions": avail_data["pos"]
                    })

        if len(streaming_candidates) == 0:
            print(f"\nNo available players found with games on {target_date.strftime('%A, %b %d, %Y')}")
            return 0

        # Sort by FPTS/G (desc), then OR# (asc)
        streaming_candidates.sort(key=lambda x: (-x["fpts_per_game"], x["overall_rank"]))

        # Build single-date game matrix for roster players
        roster_games = build_single_date_game_matrix(players, target_date)

        # Identify drop candidates (roster players NOT playing on target date)
        drop_candidates = []
        for p in players:
            if not roster_games.get(p.name, False):
                # Get NHL stats for FPTS/G calculation
                gp = nhl_api.get_games_played(p.name, p.team)
                fpts = p.fpts if hasattr(p, 'fpts') else 0.0
                overall_rank = 999  # Default fallback

                # Fetch FPTS and OR# from Yahoo API
                try:
                    last_name = p.name.split()[-1]
                    search_endpoint = (
                        f"league/nhl.l.{config.league_id}/players;"
                        f"search={last_name};"
                        f"count=25;"
                        f"out=stats,ranks"
                    )
                    search_data = client._api_request(search_endpoint)

                    if "fantasy_content" in search_data and "league" in search_data["fantasy_content"]:
                        league_data = search_data["fantasy_content"]["league"]
                        for item in league_data:
                            if isinstance(item, dict) and "players" in item:
                                players_data = item["players"]
                                for key, player_wrapper_data in players_data.items():
                                    if key == "count":
                                        continue

                                    player_wrapper = player_wrapper_data["player"]
                                    player_info = player_wrapper[0]

                                    name_obj = next((obj for obj in player_info if isinstance(obj, dict) and "name" in obj), None)
                                    if name_obj and name_obj["name"]["full"].lower() == p.name.lower():
                                        # Extract FPTS by iterating through all wrapper elements
                                        if fpts == 0.0:
                                            for elem in player_wrapper[1:]:
                                                if isinstance(elem, dict) and "player_points" in elem:
                                                    player_points = elem["player_points"]
                                                    if "total" in player_points:
                                                        try:
                                                            fpts = float(player_points["total"])
                                                        except (ValueError, TypeError):
                                                            fpts = 0.0
                                                        break

                                        # Extract overall rank by iterating through all wrapper elements
                                        for elem in player_wrapper[1:]:
                                            if isinstance(elem, dict) and "player_stats" in elem:
                                                stats_obj = elem["player_stats"]
                                                if "stats" in stats_obj:
                                                    for stat_item in stats_obj["stats"]:
                                                        if isinstance(stat_item, dict) and "stat" in stat_item:
                                                            stat = stat_item["stat"]
                                                            if "rank" in stat:
                                                                rank_obj = stat["rank"]
                                                                # Prefer current season rank (S with season 2025)
                                                                if rank_obj.get("rank_type") == "S" and rank_obj.get("rank_season") == "2025":
                                                                    try:
                                                                        overall_rank = int(rank_obj.get("rank_value", 999))
                                                                    except (ValueError, TypeError):
                                                                        overall_rank = 999
                                                                    break
                                                                # Fallback to OR (preseason rank)
                                                                elif rank_obj.get("rank_type") == "OR" and overall_rank == 999:
                                                                    try:
                                                                        overall_rank = int(rank_obj.get("rank_value", 999))
                                                                    except (ValueError, TypeError):
                                                                        overall_rank = 999
                                        break
                except Exception:
                    pass  # Use defaults if we can't fetch

                if gp and gp > 0 and fpts > 0:
                    fpts_per_game = fpts / gp
                    pos_count, pos_display = calculate_position_flexibility(p)

                    drop_candidates.append({
                        "player": p,
                        "fpts_per_game": fpts_per_game,
                        "gp": gp,
                        "fpts": fpts,
                        "overall_rank": overall_rank,
                        "position_count": pos_count,
                        "position_display": pos_display
                    })

        # Sort drop candidates by FPTS/G (asc), then position count (desc for flexibility)
        drop_candidates.sort(key=lambda x: (x["fpts_per_game"], -x["position_count"]))

        # Display results
        date_str = target_date.strftime("%A, %b %d, %Y")
        print(f"\n=== Streaming Pickups for {date_str} ===\n")

        # Show top streaming options
        top_n = min(args.top, len(streaming_candidates))
        print(f"TOP STREAMING OPTIONS (players with games on {date_str}):\n")
        print("RANK   PLAYER                    TEAM  POS           GP  OR#   FPTS  FPTS/G  Est Game   OWN%")
        print("────── ───────────────────────── ───── ──────────── ──── ───── ────── ─────── ───────── ──────")

        for rank, candidate in enumerate(streaming_candidates[:top_n], 1):
            player = candidate["player"]
            pos_str = '/'.join(player.pos)
            print(f"{rank:<6} {player.name:<25} {player.team:<5} {pos_str:<12} {candidate['gp']:>4} {candidate['overall_rank']:>5} {candidate['fpts']:>6.1f} {candidate['fpts_per_game']:>7.2f} {candidate['fpts_per_game']:>9.2f} {candidate['ownership_pct']:>5.1f}%")

        # Show drop candidates if any
        if len(drop_candidates) > 0:
            best_pickup_fpts_g = streaming_candidates[0]["fpts_per_game"]

            print(f"\nYOUR DROP CANDIDATES (not playing on {date_str}, sorted by worst FPTS/G):\n")
            print("RANK   PLAYER                    TEAM  POS              GP  OR#   FPTS  FPTS/G  Est Δ")
            print("────── ───────────────────────── ───── ─────────────── ──── ───── ────── ─────── ───────")

            for rank, candidate in enumerate(drop_candidates[:top_n], 1):
                player = candidate["player"]
                est_delta = best_pickup_fpts_g - candidate["fpts_per_game"]

                # Color code Est Δ
                if est_delta > 0:
                    est_delta_str = f"{Colors.GREEN}+{est_delta:.2f}{Colors.RESET}"
                elif est_delta < 0:
                    est_delta_str = f"{Colors.RED}{est_delta:.2f}{Colors.RESET}"
                else:
                    est_delta_str = f"{Colors.YELLOW}{est_delta:.2f}{Colors.RESET}"

                est_delta_padded = pad_colored(est_delta_str, 7, '>')

                print(f"{rank:<6} {player.name:<25} {player.team:<5} {candidate['position_display']:<15} {candidate['gp']:>4} {candidate['overall_rank']:>5} {candidate['fpts']:>6.1f} {candidate['fpts_per_game']:>7.2f} {est_delta_padded}")
        else:
            print(f"\nAll your players are already playing on {date_str}")

        # Print legend
        print("\nLegend:")
        print("  GP        = Games played this season (from NHL API)")
        print("  OR#       = Season rank (Yahoo's 2025 season performance rank, lower = better)")
        print("  FPTS      = Total fantasy points this season")
        print("  FPTS/G    = Fantasy points per game (FPTS ÷ GP)")
        print("  Est Game  = Estimated points for this single game (same as FPTS/G)")
        print("  Est Δ     = Expected point differential (Best Pickup FPTS/G - Drop Player FPTS/G)")
        print("  OWN%      = Ownership percentage")
        print("  POS (N)   = Position flexibility indicator (number of eligible positions)")

        return 0

    # Handle week/multi-week mode
    if args.date:
        # Parse the provided date and find the Monday of that week
        provided_date = dt.date.fromisoformat(args.date)
        initial_week_start = week_start_monday(provided_date)
    else:
        initial_week_start = week_start_monday(today)

    # Calculate total days across all weeks
    total_days = args.weeks * 7
    all_dates = daterange(initial_week_start, total_days)

    # Prepare grid: first column is POS label, then one column per day
    grid: List[List[str]] = [[slot] + [""] * total_days for slot in SLOTS]

    # Track empties/filled by slot type
    empties_by_pos = {k: 0 for k in set(SLOTS)}
    filled_by_pos = {k: 0 for k in set(SLOTS)}

    # Process each week to fetch games
    for week_num in range(args.weeks):
        week_start = initial_week_start + dt.timedelta(weeks=week_num)
        week_days = daterange(week_start, 7)

        # Build games-per-player for this week
        p_games = build_player_game_matrix(players, week_start)

        # Fill in the grid for this week's days
        for day_i, day_date in enumerate(week_days):
            active = [p for p in players if day_date in p_games.get(p.name, set())]
            assignment = solve_daily_assignment(active, SLOTS)

            # Calculate the column index in the full grid
            col_i = week_num * 7 + day_i

            # Mark X where a slot is filled
            for s_i, slot in enumerate(SLOTS):
                if s_i in assignment:
                    grid[s_i][1 + col_i] = "X"
                    filled_by_pos[slot] += 1
                else:
                    grid[s_i][1 + col_i] = ""
                    empties_by_pos[slot] += 1

    # Handle separate weeks mode
    if args.separate_weeks and args.weeks > 1:
        # Display each week as a separate table
        for week_num in range(args.weeks):
            week_start = initial_week_start + dt.timedelta(weeks=week_num)
            week_end = week_start + dt.timedelta(days=6)
            week_dates = daterange(week_start, 7)

            # Extract this week's data from the grid
            week_grid = []
            for s_i, slot in enumerate(SLOTS):
                row_data = [slot]
                for day_i in range(7):
                    col_i = week_num * 7 + day_i
                    row_data.append(grid[s_i][1 + col_i])
                week_grid.append(row_data)

            # Build header for this week
            day_abbrevs = ["M", "T", "W", "Th", "F", "Sa", "Su"]
            if args.compact:
                header = ["POS"] + day_abbrevs
            else:
                header = ["POS"] + [f"{abbr}({d.strftime('%m/%d')})" for abbr, d in zip(day_abbrevs, week_dates)]

            # Handle export for this week
            if args.export:
                if args.export == "csv":
                    export_file = args.export_file or generate_export_filename("csv")
                    export_to_csv(week_grid, header, export_file)
                    if week_num == 0:
                        print(f"✓ Exported to {export_file}")
                elif args.export == "markdown":
                    export_file = args.export_file or generate_export_filename("markdown")
                    export_to_markdown(week_grid, header, export_file)
                    if week_num == 0:
                        print(f"✓ Exported to {export_file}")
                elif args.export == "clipboard" and week_num == 0:
                    output = export_to_csv(week_grid, header)
                    if copy_to_clipboard(output):
                        print("✓ Copied first week to clipboard")
                    else:
                        print("✗ Failed to copy to clipboard", file=sys.stderr)
            else:
                # Print this week with EFF and PCT columns, sorted by efficiency
                print(f"\n=== Week {week_num + 1}: {week_start.isoformat()} → {week_end.isoformat()} ===\n")

                sorted_indices = sort_slots_by_efficiency(SLOTS, week_grid, 7)

                # Column widths
                pos_w = 3  # "LW1", "RW2", etc.
                eff_w = 5  # "11/14"
                pct_w = 6  # "100.0%"
                col_w = 3 if args.compact else 8  # Compact: "M", Full: "M(12/29)"

                # Print header (center-align in compact mode for better visual balance)
                header_align = '^' if args.compact else '>'
                print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  " + "  ".join(f"{h:{header_align}{col_w}}" for h in header[1:]))

                # Print rows with EFF, PCT, and optional colors, in sorted order
                pos_counts = {}
                for s_i in sorted_indices:
                    row = week_grid[s_i]
                    slot = SLOTS[s_i]
                    pos_counts[slot] = pos_counts.get(slot, 0) + 1
                    slot_name = f"{slot}{pos_counts[slot]}"

                    # Calculate efficiency for this slot across this week (7 days)
                    cells = row[1:]
                    filled = sum(1 for cell in cells if cell == "X")
                    total = 7
                    pct = (filled / total * 100) if total > 0 else 0

                    # Format with colors
                    colored_cells = [pad_colored_cell(colorize_cell(cell), col_w) for cell in cells]
                    pct_color = colorize_percentage(pct)
                    eff_str = f"{pct_color}{filled:>2}/{total:<2}{Colors.RESET}"
                    pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
                    print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  " + "  ".join(colored_cells))

                # Add summary row for this week
                total_slots = len(SLOTS)
                daily_fills = []
                for day_i in range(7):
                    day_filled = sum(1 for s_i in range(len(SLOTS)) if week_grid[s_i][1 + day_i] == "X")
                    daily_fills.append(day_filled)

                # Overall week stats
                week_total_filled = sum(daily_fills)
                week_total_slots = total_slots * 7
                week_pct = (week_total_filled / week_total_slots * 100) if week_total_slots > 0 else 0
                week_color = colorize_percentage(week_pct)
                week_eff_str = f"{week_color}{week_total_filled:>2}/{week_total_slots:<2}{Colors.RESET}"
                week_pct_str = f"{week_color}{week_pct:5.1f}%{Colors.RESET}"

                # Daily summaries
                daily_cells = []
                for day_filled in daily_fills:
                    day_pct = (day_filled / total_slots * 100) if total_slots > 0 else 0
                    day_color = colorize_percentage(day_pct)
                    day_str = f"{day_color}{day_filled}{Colors.RESET}"
                    daily_cells.append(pad_colored_cell(day_str, col_w))

                print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  " + "  ".join(['─' * col_w for _ in range(7)]))
                print(f"{'TOT':<{pos_w}}  {week_eff_str}  {week_pct_str}  " + "  ".join(daily_cells))

        # Print aggregate stats
        if not args.export:
            print("\n=== Aggregate Stats ===")
            print("\nEmpty slots by position (lower is better):")
            for pos in ["C", "LW", "RW", "D", "G"]:
                print(f"  {pos}: {empties_by_pos.get(pos, 0)}")

            # Calculate and show idle players
            idle_by_pos = calculate_idle_players(players, SLOTS)
            if idle_by_pos:
                print("\nIdle players by position (surplus over roster slots):")
                for pos in ["C", "LW", "RW", "D", "G"]:
                    if pos in idle_by_pos:
                        print(f"  {pos}: {idle_by_pos[pos]}")

        return 0

    # Unified table mode (default)
    end_date = all_dates[-1]
    day_abbrevs = ["M", "T", "W", "Th", "F", "Sa", "Su"]

    # Build header with day abbreviations and dates
    header = ["POS"]
    if args.compact:
        for day_date in all_dates:
            day_idx = day_date.weekday()  # 0=Monday
            day_abbrev = day_abbrevs[day_idx]
            header.append(day_abbrev)
    else:
        for day_date in all_dates:
            day_idx = day_date.weekday()  # 0=Monday
            day_abbrev = day_abbrevs[day_idx]
            date_str = day_date.strftime("%m/%d")
            header.append(f"{day_abbrev}({date_str})")

    # Handle export
    if args.export:
        if args.export == "csv":
            export_file = args.export_file or generate_export_filename("csv")
            export_to_csv(grid, header, export_file)
            print(f"✓ Exported to {export_file}")
        elif args.export == "markdown":
            export_file = args.export_file or generate_export_filename("markdown")
            export_to_markdown(grid, header, export_file)
            print(f"✓ Exported to {export_file}")
        elif args.export == "clipboard":
            output = export_to_csv(grid, header)
            if copy_to_clipboard(output):
                print("✓ Copied to clipboard")
            else:
                print("✗ Failed to copy to clipboard (pbcopy/xclip not available)", file=sys.stderr)
        return 0

    # Print unified table with EFF and PCT columns, sorted by efficiency
    print(f"\n{initial_week_start.isoformat()} → {end_date.isoformat()}\n")

    sorted_indices = sort_slots_by_efficiency(SLOTS, grid, total_days)

    # Column widths
    pos_w = 3  # "LW1", "RW2", etc.
    eff_w = 5  # "11/14"
    pct_w = 6  # "100.0%"
    col_w = 3 if args.compact else 8  # Compact: "M", Full: "M(12/29)"

    # Print header (center-align in compact mode for better visual balance)
    header_align = '^' if args.compact else '>'
    print(f"{'POS':<{pos_w}}  {'EFF':>{eff_w}}  {'PCT':>{pct_w}}  " + "  ".join(f"{h:{header_align}{col_w}}" for h in header[1:]))

    # Print each row with EFF, PCT, and optional colors, in sorted order
    pos_counts = {}
    for s_i in sorted_indices:
        row = grid[s_i]
        slot = SLOTS[s_i]
        pos_counts[slot] = pos_counts.get(slot, 0) + 1
        slot_name = f"{slot}{pos_counts[slot]}"

        cells = row[1:]
        # Calculate efficiency for this slot across all days
        filled = sum(1 for cell in cells if cell == "X")
        total = total_days
        pct = (filled / total * 100) if total > 0 else 0

        # Format with colors
        colored_cells = [pad_colored_cell(colorize_cell(cell), col_w) for cell in cells]
        pct_color = colorize_percentage(pct)
        eff_str = f"{pct_color}{filled:>2}/{total:<2}{Colors.RESET}"
        pct_str = f"{pct_color}{pct:5.1f}%{Colors.RESET}"
        print(f"{slot_name:<{pos_w}}  {eff_str}  {pct_str}  " + "  ".join(colored_cells))

    # Add summary row for all days
    total_slots = len(SLOTS)
    daily_fills = []
    for day_i in range(total_days):
        day_filled = sum(1 for s_i in range(len(SLOTS)) if grid[s_i][1 + day_i] == "X")
        daily_fills.append(day_filled)

    # Overall stats
    overall_total_filled = sum(daily_fills)
    overall_total_slots = total_slots * total_days
    overall_pct = (overall_total_filled / overall_total_slots * 100) if overall_total_slots > 0 else 0
    overall_color = colorize_percentage(overall_pct)
    overall_eff_str = f"{overall_color}{overall_total_filled:>2}/{overall_total_slots:<2}{Colors.RESET}"
    overall_pct_str = f"{overall_color}{overall_pct:5.1f}%{Colors.RESET}"

    # Daily summaries
    daily_cells = []
    for day_filled in daily_fills:
        day_pct = (day_filled / total_slots * 100) if total_slots > 0 else 0
        day_color = colorize_percentage(day_pct)
        day_str = f"{day_color}{day_filled}{Colors.RESET}"
        daily_cells.append(pad_colored_cell(day_str, col_w))

    print(f"{'─' * pos_w}  {'─' * eff_w}  {'─' * pct_w}  " + "  ".join(['─' * col_w for _ in range(total_days)]))
    print(f"{'TOT':<{pos_w}}  {overall_eff_str}  {overall_pct_str}  " + "  ".join(daily_cells))

    print("\nEmpty slots by position (lower is better):")
    for pos in ["C", "LW", "RW", "D", "G"]:
        print(f"  {pos}: {empties_by_pos.get(pos, 0)}")

    # Calculate and show idle players
    idle_by_pos = calculate_idle_players(players, SLOTS)
    if idle_by_pos:
        print("\nIdle players by position (surplus over roster slots):")
        for pos in ["C", "LW", "RW", "D", "G"]:
            if pos in idle_by_pos:
                print(f"  {pos}: {idle_by_pos[pos]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())