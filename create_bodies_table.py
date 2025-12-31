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
import datetime as dt
import sys
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", default="roster.yml", help="Path to roster YAML")
    ap.add_argument(
        "--date",
        default=None,
        help="Any date (YYYY-MM-DD) to determine which Mon-Sun week to analyze. If omitted, uses current week (America/Los_Angeles).",
    )
    ap.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of consecutive weeks to project (default: 1).",
    )
    ap.add_argument(
        "--day",
        action="store_true",
        help="Analyze a single day instead of a week. Uses --date if provided, otherwise current date.",
    )
    args = ap.parse_args()

    tz = gettz("America/Los_Angeles")
    today = dt.datetime.now(tz=tz).date()

    with open(args.roster, "r", encoding="utf-8") as f:
        roster = yaml.safe_load(f)

    players: List[Player] = [
        Player(name=p["name"], team=p["team"], pos=tuple(p["pos"]))
        for p in roster.get("players", [])
    ]

    if not players:
        print("No players found in roster.yml", file=sys.stderr)
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

        # Print single-day grid
        col_w = 4
        pos_w = max(len(row[0]) for row in grid)
        print(f"{'POS':<{pos_w}}  {day_name[:3]:>{col_w}}")
        for row in grid:
            print(f"{row[0]:<{pos_w}}  {row[1]:>{col_w}}")

        print("\nEmpty slots by position:")
        for pos in ["C", "LW", "RW", "D", "G"]:
            print(f"  {pos}: {empties_by_pos.get(pos, 0)}")

        print("\nFilled slots by position:")
        for pos in ["C", "LW", "RW", "D", "G"]:
            print(f"  {pos}: {filled_by_pos.get(pos, 0)}")

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

    # Print header with dates
    end_date = all_dates[-1]
    print(f"\n{initial_week_start.isoformat()} → {end_date.isoformat()}\n")

    # Build header with day abbreviations and dates
    col_w = 8  # Width for date columns like "M(12/29)"
    pos_w = max(len(slot) for slot in SLOTS)
    day_abbrevs = ["M", "T", "W", "Th", "F", "Sa", "Su"]

    header_parts = [f"{'POS':<{pos_w}}"]
    for day_date in all_dates:
        day_idx = day_date.weekday()  # 0=Monday
        day_abbrev = day_abbrevs[day_idx]
        date_str = day_date.strftime("%m/%d")
        day_label = f"{day_abbrev}({date_str})"
        header_parts.append(f"{day_label:>{col_w}}")

    print("  ".join(header_parts))

    # Print each row
    for row in grid:
        pos = row[0]
        cells = row[1:]
        row_parts = [f"{pos:<{pos_w}}"]
        for cell in cells:
            row_parts.append(f"{cell:>{col_w}}")
        print("  ".join(row_parts))

    print("\nEmpty slots by position (lower is better):")
    for pos in ["C", "LW", "RW", "D", "G"]:
        print(f"  {pos}: {empties_by_pos.get(pos, 0)}")

    print("\nFilled starts by position:")
    for pos in ["C", "LW", "RW", "D", "G"]:
        print(f"  {pos}: {filled_by_pos.get(pos, 0)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())