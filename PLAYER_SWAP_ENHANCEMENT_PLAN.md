# Player Swap Feature Enhancement Plan

## Current State

The `--player-swap` feature currently provides basic schedule density comparison:
- Shows efficiency (filled slots) difference between current roster and roster with swap
- Shows daily slot fills for each day of the week
- Uses **unweighted optimizer** (treats all players equally, only maximizes filled slots)
- **Does NOT consider** player quality (FPTS/G)
- **Does NOT show** expected fantasy points impact

### Current Output Example
```
=== Swap Impact Summary (Drop Carter Verhaeghe, Add Thomas Chabot) ===

                          CURRENT     WITH SWAP      DIFF
──────────────────── ────────────  ────────────  ────────
EFF                     47/84         49/84            +2
PCT                         56.0%         58.3%     +2.4%
M (01/05)                       4             5        +1
T (01/06)                      11            11        +0
W (01/07)                       2             3        +1
Th (01/08)                     12            12        +0
F (01/09)                       2             2        +0
Sa (01/10)                     11            11        +0
Su (01/11)                      5             5        +0
```

## Problems with Current Implementation

1. **No Player Quality Consideration**: Swapping Nathan MacKinnon (17.27 FPTS/G) for a 3rd-line player would show the same +2 EFF if they have the same schedule
2. **Misleading Recommendations**: A swap could show positive EFF but actually reduce expected weekly points
3. **Inconsistent with Other Features**: Drop candidates and FA recommendations now use weighted optimizer and expected FPTS
4. **Missing Critical Metric**: Users can't see the actual fantasy points impact of the swap

## Planned Enhancements

### 1. Weighted Optimizer Integration

**Current**:
```python
assignment = solve_daily_assignment(active_players, SLOTS)  # Unweighted
```

**Enhanced**:
```python
# Build FPTS/G map for all players
player_fpts_g_map = {}
for p in players:
    p_data = roster_stats_map.get(p.name, {"rank": 999, "fpts": 0.0})
    p_fpts = p_data["fpts"]
    p_gp = nhl_api.get_games_played(p.name, p.team)
    if p_gp and p_gp > 0:
        player_fpts_g_map[p.name] = p_fpts / p_gp
    else:
        player_fpts_g_map[p.name] = 0.0

# Use weighted optimizer
player_values = [player_fpts_g_map.get(p.name, 0.0) for p in active_players]
assignment = solve_daily_assignment(active_players, SLOTS, player_values)
```

### 2. Expected FPTS Calculation

**Add to Swap Impact Summary**:
```
=== Swap Impact Summary (Drop Carter Verhaeghe, Add Thomas Chabot) ===

                          CURRENT     WITH SWAP      DIFF
──────────────────── ────────────  ────────────  ────────
EFF                     47/84         49/84            +2
PCT                         56.0%         58.3%     +2.4%
Expected FPTS               284.3         289.7      +5.4  ← NEW
M (01/05)                       4             5        +1
T (01/06)                      11            11        +0
W (01/07)                       2             3        +1
Th (01/08)                     12            12        +0
F (01/09)                       2             2        +0
Sa (01/10)                     11            11        +0
Su (01/11)                      5             5        +0
```

**Color Coding**:
- **Green (+)**: Expected FPTS increase (good swap)
- **Red (-)**: Expected FPTS decrease (bad swap)
- **Yellow (0)**: Neutral swap

### 3. Player Details Section

**Add after Swap Impact Summary**:
```
Drop: Carter Verhaeghe (FLA, LW) - 6.09 FPTS/G
  Games this week: 4
  Expected slots: 4
  Expected contribution: 24.4 FPTS

Add: Thomas Chabot (OTT, D) - 7.45 FPTS/G
  Games this week: 4
  Expected slots: 3
  Expected contribution: 22.4 FPTS

Net Impact: -2.0 FPTS (worse despite +2 efficiency)
```

### 4. Multi-Position Warning

**If drop player has multi-position eligibility**:
```
⚠ WARNING: Carter Verhaeghe is multi-position (LW/RW)
  Dropping may reduce lineup flexibility
```

### 5. Position Depth Warning

**If dropping from a thin position**:
```
⚠ THIN: Only 2 LW on roster for 2 LW slots
  Dropping Verhaeghe may limit future lineup options
```

## Implementation Tasks

### Phase 1: Core Weighted Optimizer Integration
- [ ] Fetch roster stats (FPTS, GP) using `client.fetch_player_ranks()`
- [ ] Fetch NHL stats for GP using `nhl_api.get_games_played()`
- [ ] Build `player_fpts_g_map` for all roster players
- [ ] Include swap-add player in FPTS/G map
- [ ] Update both optimizer calls to use weighted version:
  - Current roster optimizer
  - Modified roster (with swap) optimizer

### Phase 2: Expected FPTS Calculation
- [ ] Calculate expected FPTS for current roster:
  ```python
  current_expected_fpts = 0.0
  for day in week_dates:
      for s_i, p_i in assignment.items():
          player = active_players[p_i]
          fpts_g = player_fpts_g_map.get(player.name, 0.0)
          current_expected_fpts += fpts_g
  ```
- [ ] Calculate expected FPTS for modified roster (same logic)
- [ ] Calculate delta: `modified_expected_fpts - current_expected_fpts`

### Phase 3: Enhanced Display
- [ ] Add "Expected FPTS" row to Swap Impact Summary table
- [ ] Color code the FPTS difference (green/red/yellow)
- [ ] Add player details section with:
  - Drop player: name, team, pos, FPTS/G, games, expected slots, expected contribution
  - Add player: same details
  - Net impact summary
- [ ] Add multi-position warning if applicable
- [ ] Add position depth warning if applicable

### Phase 4: Testing
- [ ] Test with beneficial swap (higher FPTS/G player, same schedule)
- [ ] Test with detrimental swap (lower FPTS/G player, more games)
- [ ] Test with multi-position player drop
- [ ] Test with thin position drop
- [ ] Verify weighted optimizer is being used (elite players get priority)

## Technical Details

### Affected Functions
- `main()` in `create_bodies_table.py` (around line 1300-1400)
- `solve_daily_assignment()` - already supports weighted optimization

### Data Requirements
- Yahoo API: `fetch_player_ranks(include_stats=True)` for roster players
- Yahoo API: `fetch_player_details()` for swap-add player (if not on roster)
- NHL API: `get_games_played()` for all players
- NHL Schedule API: Game schedules (already fetched)

### New Variables Needed
```python
# Player stats and FPTS/G
roster_stats_map = client.fetch_player_ranks(player_names, include_stats=True)
player_fpts_g_map = {}  # name -> FPTS/G

# Expected FPTS tracking
current_expected_fpts = 0.0
modified_expected_fpts = 0.0
fpts_delta = modified_expected_fpts - current_expected_fpts

# Drop player analysis
drop_player_fpts_g = player_fpts_g_map.get(drop_player.name, 0.0)
drop_player_slots = sum(1 for s_i, p_i in current_assignment.items() if active[p_i].name == drop_player.name)
drop_player_contribution = drop_player_slots * drop_player_fpts_g

# Add player analysis (similar)
```

## Benefits

1. **Accurate Impact Assessment**: See actual fantasy points impact, not just schedule density
2. **Prevents Bad Swaps**: Avoid swapping elite players for streamers just because they have more games
3. **Consistency**: Aligns with drop candidates and FA recommendations methodology
4. **Better Decision Making**: Users can make informed decisions based on expected points

## Example Scenarios

### Scenario 1: Good Swap (Higher FPTS/G, Same Schedule)
```
Drop: Dylan Strome (7.07 FPTS/G, 4 games, 1 slot)
Add: Elias Pettersson (8.50 FPTS/G, 4 games, 4 slots)

Expected FPTS: +27.0 FPTS ← GOOD SWAP
```

### Scenario 2: Bad Swap (Lower FPTS/G, More Games)
```
Drop: Nathan MacKinnon (17.27 FPTS/G, 3 games, 3 slots)
Add: Generic Player (5.00 FPTS/G, 5 games, 5 slots)

Expected FPTS: -26.8 FPTS ← BAD SWAP (despite +2 EFF)
```

### Scenario 3: Thin Position Warning
```
Drop: Carter Verhaeghe (6.09 FPTS/G, LW, 4 games)
Add: Thomas Chabot (7.45 FPTS/G, D, 4 games)

⚠ THIN: Only 2 LW on roster for 2 LW slots
Expected FPTS: -2.0 FPTS (Chabot gets fewer slots due to position depth)
```

## Risks & Considerations

1. **Performance**: Additional API calls for stats/ranks (mitigated by caching)
2. **Complexity**: More calculations and display logic
3. **User Confusion**: Need clear explanation of expected FPTS calculation
4. **Edge Cases**: Handle players with 0 GP or missing stats

## Documentation Updates

### README.md - Player Swap Section
Update example output to show expected FPTS and add explanation:
```markdown
**Output includes:**
- Current roster efficiency vs. projected efficiency after swap
- **Expected fantasy points impact** (NEW)
- Games played comparison (drop vs. add)
- Weekly slot fill differential
- **Player contribution analysis** (NEW)
- Color-coded impact summary (green = good, red = bad)
```

### Add to Legend
```
Expected FPTS = Sum of (Slots Filled × Player FPTS/G) across all days
                Calculated using weighted lineup optimizer
                Green (+) = Good swap, Red (-) = Bad swap
```

## Future Enhancements (Out of Scope)

1. **Multi-Swap Support**: Compare dropping Player A vs Player B for Player C
2. **Season-Long Impact**: Project impact across multiple weeks
3. **Category Impact**: Show impact on specific stat categories (G, A, SOG, etc.)
4. **Roster Balance**: Analyze position balance before/after swap

## Dependencies

- ✅ Weighted optimizer (`solve_daily_assignment` with `player_values`)
- ✅ Yahoo API stats endpoint (`fetch_player_ranks(include_stats=True)`)
- ✅ NHL stats API (`nhl_api.get_games_played()`)
- ✅ Position depth calculation (already implemented)
- ✅ Multi-position detection (already implemented)

## Estimated Implementation Time

- Phase 1 (Weighted Optimizer): 30 minutes
- Phase 2 (Expected FPTS): 20 minutes
- Phase 3 (Enhanced Display): 40 minutes
- Phase 4 (Testing): 30 minutes
- **Total**: ~2 hours

## Priority

**HIGH** - This feature is inconsistent with recent improvements and could lead to bad swap decisions.

## Status

📋 **PLANNED** - Roadmap documented, ready for implementation
