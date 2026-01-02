# Streaming Pickups Feature Implementation Plan

## Overview
Implement `--stream-date` feature to recommend best available free agents playing on a specific date (for same-day streaming pickups), with intelligent drop candidate suggestions.

## User Requirements
1. Find best available FA playing on specified date
2. Rank by **FPTS/G first, then OR#**
3. Show drop candidates:
   - Players NOT playing on that date
   - Prioritize lowest FPTS/G
   - Show position flexibility indicator
4. Display estimated FPTS +/- for recommended swaps
5. Date format: `YYYY-MM-DD`

## Implementation Strategy

### 1. Command-Line Argument
**File:** `create_bodies_table.py`

Add new argument:
```python
ap.add_argument(
    "--stream-date",
    type=str,
    metavar="YYYY-MM-DD",
    help="Find best streaming pickups for a specific date. Shows available players "
         "with games on that date ranked by FPTS/G, and suggests drop candidates "
         "from your roster who aren't playing. Requires Yahoo API.",
)
```

**Validation:**
- Requires Yahoo API (incompatible with `--local`)
- Parse date string to validate format
- Cannot be combined with `--recommend-add`, `--compare-team`, or `--player-swap`
- Forces single-day mode

### 2. Core Logic Flow

```
1. Parse and validate date
2. Fetch roster from Yahoo API
3. Fetch top 100 available FAs (filter goalies/injured)
4. Build game matrix for target date ONLY
5. Filter available players: keep only those playing on target date
6. Calculate FPTS/G for all available players
7. Sort by FPTS/G (desc), then OR# (asc)
8. Identify drop candidates from roster (not playing on target date)
9. Calculate drop candidate metrics (FPTS/G, position flexibility)
10. Sort drop candidates by FPTS/G (asc)
11. Show top N streaming options with estimated single-game impact
12. Show drop candidates with position info
```

### 3. Key Data Structures

#### Available Player Metrics
```python
{
    "player": Player(...),
    "fpts_per_game": float,        # FPTS ÷ GP (primary sort)
    "overall_rank": int,            # Season rank (secondary sort)
    "fpts": float,                  # Season fantasy points
    "gp": int,                      # Games played
    "est_single_game": float,       # FPTS/G (same as fpts_per_game)
    "ownership_pct": float,         # Ownership %
    "positions": List[str]          # Eligible positions
}
```

#### Drop Candidate Metrics
```python
{
    "player": Player(...),
    "fpts_per_game": float,        # FPTS ÷ GP (ascending sort)
    "gp": int,                      # Games played
    "fpts": float,                  # Season fantasy points
    "position_count": int,          # Number of eligible positions (flexibility)
    "positions": List[str]          # Eligible positions list
}
```

### 4. Position Flexibility Scoring

Calculate for each roster player:
```python
position_count = len([p for p in player.pos if p not in ('Util', 'BN', 'IR', 'IR+', 'NA')])
```

Display in drop candidates table:
- 1 position: Show position only (e.g., "C")
- 2+ positions: Show all + count indicator (e.g., "C/LW/RW (3)")

### 5. Functions to Reuse from --recommend-add

| Function | Purpose | Usage |
|----------|---------|-------|
| `build_player_game_matrix()` | Get game schedule | Call for single target date |
| `nhl_api.fetch_season_stats()` | Pre-fetch NHL stats cache | Calculate FPTS/G |
| `nhl_api.get_games_played()` | Get player GP | Calculate FPTS/G |
| `fetch_team_week_games()` | NHL schedule API | Get single-date games |
| `pad_colored()` / `strip_ansi()` | ANSI color handling | Colored output |

### 6. New Helper Functions Needed

#### `build_single_date_game_matrix()`
```python
def build_single_date_game_matrix(players: List[Player], target_date: dt.date) -> Dict[str, bool]:
    """
    Map player.name -> bool (playing on target_date).
    Optimized for single-date lookup.
    """
    team_games = {}  # Cache team schedules
    result = {}

    for p in players:
        tri = yahoo_team_to_nhl_tri(p.team)
        if tri not in team_games:
            # Fetch week containing target_date, extract just that date
            week_start = week_start_monday(target_date)
            week_games = fetch_team_week_games(tri, week_start)
            team_games[tri] = target_date in week_games
        result[p.name] = team_games[tri]

    return result
```

#### `calculate_position_flexibility()`
```python
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
```

### 7. Output Format

#### Header
```
=== Streaming Pickups for Thursday, Jan 2, 2026 ===
```

#### Available Players Table
```
TOP STREAMING OPTIONS (players with games today):

RANK   PLAYER                TEAM  POS        GP   OR#   FPTS  FPTS/G  Est Game   OWN%
─────  ───────────────────── ────  ────────  ───  ────  ────  ──────  ────────  ─────
1      Dylan Strome          WSH   C          39   71   274    7.03      7.03    81%
2      Timo Meier            NJ    LW/RW      35  123   247    7.05      7.05    83%
3      JJ Peterka            UTA   LW/RW      41   99   252    6.16      6.16    63%
```

**Columns:**
- RANK: Recommendation order
- PLAYER: Name
- TEAM: Team abbr
- POS: Eligible positions
- GP: Games played (from NHL API)
- OR#: Season rank (from Yahoo)
- FPTS: Season total fantasy points
- FPTS/G: Fantasy points per game (**PRIMARY SORT**)
- Est Game: Expected points for this game (same as FPTS/G)
- OWN%: Ownership percentage

#### Drop Candidates Table
```
YOUR DROP CANDIDATES (not playing today, sorted by worst FPTS/G):

RANK   PLAYER                TEAM  POS            GP  FPTS  FPTS/G  Est Δ
─────  ───────────────────── ────  ────────────  ───  ────  ──────  ──────
1      Jordan Kyrou          STL   RW             31  154    4.95   +2.08
2      John Tavares          TOR   C              40  283    7.08   -0.05
3      Connor McDavid        EDM   C/LW/RW (3)    38  312    8.21   -1.18
```

**Columns:**
- RANK: Sort by FPTS/G ascending
- PLAYER: Name
- TEAM: Team abbr
- POS: Positions with flexibility indicator
- GP: Games played
- FPTS: Season fantasy points
- FPTS/G: Points per game
- Est Δ: Expected point differential if swapping #1 pickup for this drop
  - Calculation: `best_pickup_fpts_g - drop_player_fpts_g`
  - Green if positive, red if negative

#### Legend
```
Legend:
  GP        = Games played this season (from NHL API)
  OR#       = Season rank (Yahoo's 2025 season performance rank, lower = better)
  FPTS      = Total fantasy points this season
  FPTS/G    = Fantasy points per game (FPTS ÷ GP)
  Est Game  = Estimated points for this single game (same as FPTS/G)
  Est Δ     = Expected point differential (Best Pickup FPTS/G - Drop Player FPTS/G)
  OWN%      = Ownership percentage
  POS (N)   = Position flexibility indicator (number of eligible positions)
```

### 8. Sorting Logic

#### Available Players (Streaming Options)
```python
streaming_options.sort(key=lambda x: (-x["fpts_per_game"], x["overall_rank"]))
```
1. FPTS/G descending (highest performers first)
2. OR# ascending (tie-breaker: better rank)

#### Drop Candidates
```python
drop_candidates.sort(key=lambda x: (x["fpts_per_game"], -x["position_count"]))
```
1. FPTS/G ascending (worst performers first)
2. Position count descending (tie-breaker: most flexible)

### 9. Implementation Checklist

**Phase 1: Argument & Validation**
- [ ] Add `--stream-date` argument
- [ ] Add date parsing and validation
- [ ] Add incompatibility checks
- [ ] Force single-day mode

**Phase 2: Core Logic**
- [ ] Implement `build_single_date_game_matrix()`
- [ ] Implement `calculate_position_flexibility()`
- [ ] Filter available players by target date
- [ ] Calculate FPTS/G for all players
- [ ] Identify drop candidates (roster players not playing)

**Phase 3: Metrics & Sorting**
- [ ] Calculate streaming option metrics
- [ ] Calculate drop candidate metrics
- [ ] Implement sorting (FPTS/G first, then OR#/position)
- [ ] Calculate Est Δ for drop candidates

**Phase 4: Output**
- [ ] Format streaming options table
- [ ] Format drop candidates table
- [ ] Add color coding (green/red for Est Δ)
- [ ] Add legend

**Phase 5: Testing**
- [ ] Test with various dates (weekday, weekend, off-day)
- [ ] Test edge cases (no games on date, all roster playing)
- [ ] Verify FPTS/G calculations match NHL GP data
- [ ] Test color alignment with `pad_colored()`

### 10. Code Location

**File:** `/Users/drew/Projects/yahoo-fantasy-hockey/create_bodies_table.py`

**Insert location:** After `--recommend-add` feature block (around line 1520+)

**Integration points:**
- Argument parsing: ~line 533 (after `--top`)
- Validation: ~line 582 (after `--recommend-add` validation)
- Main execution: ~line 1520 (after `--recommend-add` output)

### 11. Edge Cases to Handle

1. **No games on target date:** Show message "No games scheduled for [date]"
2. **All roster playing:** Show message "All your players are already playing on [date]"
3. **No roster players idle:** Show message "No drop candidates available"
4. **Missing GP data:** Skip player or show "N/A" for FPTS/G
5. **Future date validation:** Allow any date, but warn if too far in future

### 12. Future Enhancements (Not in Initial Version)

- `--stream-today` shortcut for current date
- `--stream-position C` to filter by position need
- Multi-day streaming (e.g., `--stream-date 2026-01-02 --days 3`)
- Historical streaming analysis (track past recommendations)

---

## Summary

This feature provides a **focused, single-day optimization** for streaming pickups:

**Key Differentiators from --recommend-add:**
- Single date instead of full week
- Sort by FPTS/G (performance) not efficiency gain
- Smart drop suggestions based on schedule + performance
- Position flexibility scoring for drop decisions

**Reuses existing architecture:**
- NHL schedule caching
- Yahoo FA fetching with IR filtering
- FPTS/G calculations via NHL API
- ANSI color handling

**User workflow:**
```bash
$ python create_bodies_table.py --stream-date 2026-01-05

# Output shows:
# 1. Best FAs playing that day (by FPTS/G)
# 2. Worst roster players not playing (drop candidates)
# 3. Expected point swing for each swap
```

This enables quick, data-driven streaming decisions during the fantasy week.
