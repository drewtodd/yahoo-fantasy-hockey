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

# ---------- ANSI Color codes ----------
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


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
    """
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
        "--compare-team",
        type=str,
        metavar="TEAM_ID",
        help="Compare your roster efficiency against another team (forces single-week mode). Requires Yahoo API.",
    )
    args = ap.parse_args()

    # Normalize export aliases
    if args.export:
        if args.export == "md":
            args.export = "markdown"
        elif args.export == "cp":
            args.export = "clipboard"

    # Validate comparison mode
    if args.compare_team:
        if args.local:
            print("Error: --compare-team requires Yahoo API (cannot use with --local)", file=sys.stderr)
            return 2
        if args.day:
            print("Error: --compare-team only works with week mode (cannot use with --day)", file=sys.stderr)
            return 2
        # Force single-week analysis in comparison mode
        args.weeks = 1

    tz = gettz("America/Los_Angeles")
    today = dt.datetime.now(tz=tz).date()

    # Handle --sync mode (fetch and save, then exit)
    if args.sync:
        try:
            from yahoo_client import YahooClient

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

    if not use_local:
        # Try Yahoo first (default behavior)
        try:
            from yahoo_client import YahooClient

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

        # Print comparison summary
        print("\n=== Comparison Summary ===\n")

        # Calculate overall stats
        total_slots = len(SLOTS)
        your_total_filled = sum(your_filled_by_pos.values())
        opp_total_filled = sum(opp_filled_by_pos.values())
        your_overall_pct = (your_total_filled / (total_slots * 7) * 100) if total_slots > 0 else 0
        opp_overall_pct = (opp_total_filled / (total_slots * 7) * 100) if total_slots > 0 else 0

        # Daily fills
        your_daily_fills = []
        opp_daily_fills = []
        for day_i in range(7):
            your_day_filled = sum(1 for s_i in range(len(SLOTS)) if your_grid[s_i][1 + day_i] == "X")
            opp_day_filled = sum(1 for s_i in range(len(SLOTS)) if opp_grid[s_i][1 + day_i] == "X")
            your_daily_fills.append(your_day_filled)
            opp_daily_fills.append(opp_day_filled)

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