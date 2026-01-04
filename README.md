# Yahoo Fantasy Hockey Bodies Table Generator

A tool to optimize your Yahoo Fantasy Hockey lineup by visualizing roster slot coverage across the week and projecting multi-week schedules.

## Features

### Core Analysis
- **Weekly bodies table** - Visualize filled roster slots (Mon-Sun) with position-aware optimization
- **Single-day analysis** - Check lineup coverage for any specific date
- **Multi-week projections** - Forecast coverage for multiple consecutive weeks
- **Yahoo API integration** - Automatically fetch roster and league settings from Yahoo Fantasy
- **Color-coded output** - Green for filled, yellow for moderate gaps, red for critical issues
- **Export options** - CSV, Markdown, or clipboard for easy sharing
- **Flexible date selection** - Analyze any week by providing any date within it

### Advanced Features
- **Weekly summary report (`--weekly-summary`)** - Comprehensive Monday morning report with roster saturation, drop candidates, and top FAs
- **Automated email reports** - Schedule Sunday morning email delivery of weekly summary (see [QUICKSTART_AUTOMATION.md](QUICKSTART_AUTOMATION.md))
- **Drop candidates (`--drop-candidates`)** - Identify underutilized roster players with wasted bench games
- **Streaming pickups (`--available-fas`)** - Find best available free agents playing on a specific date with smart drop recommendations
- **Free agent recommendations (`--recommend-add`)** - Discover top weekly efficiency gains from available players
- **Team comparisons (`--compare-team`)** - Benchmark your roster efficiency against league opponents
- **Player swap simulation (`--player-swap`)** - Preview the impact of add/drop transactions before making them
- **Force refresh (`--force`)** - Override caches to get the latest stats and schedules

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Using YAML roster (no Yahoo API required)

```bash
# Analyze current week
python create_bodies_table.py

# Analyze specific week (provide any date in that week)
python create_bodies_table.py --date 2025-01-06

# Project next 4 weeks
python create_bodies_table.py --weeks 4 --color
```

### Using Yahoo Fantasy API

1. **Set up Yahoo Developer App** (one-time setup):
   - Go to https://developer.yahoo.com/apps/
   - Create a new app as a **Public Client** (mobile/native apps)
   - Set redirect URI: `https://localhost:8000`
   - Copy your Client ID (no Client Secret needed for Public Client)

2. **Configure credentials**:
   ```bash
   # Copy example file
   cp .env.example .env

   # Edit .env with your credentials
   nano .env
   ```

3. **Run with Yahoo integration**:
   ```bash
   # First run will open browser for authorization
   python create_bodies_table.py

   # Browser will show a security warning (self-signed certificate)
   # Click 'Advanced' or 'Show Details' and then 'Proceed to localhost'
   # This is safe - it's your own local HTTPS server

   # Subsequent runs use cached tokens automatically
   python create_bodies_table.py -w 4 -c
   ```

## Usage

```bash
# Basic usage
python create_bodies_table.py [OPTIONS]

# Short form aliases
python create_bodies_table.py -y -w 4 -c -s
```

### Command-line Options

#### Core Options
| Option | Short | Description |
|--------|-------|-------------|
| `--roster FILE` | `-r` | Path to roster YAML (default: roster.yml) |
| `--date YYYY-MM-DD` | `-d` | Any date to determine which week to analyze |
| `--weeks N` | `-w` | Number of consecutive weeks to project (default: 1) |
| `--day` | `-D` | Analyze single day instead of week |
| `--color` | `-c` | Enable color-coded output |
| `--export FORMAT` | `-e` | Export as csv, markdown, or clipboard |
| `--export-file FILE` | `-o` | Output file for export (optional) |
| `--separate-weeks` | `-s` | Show each week in separate table |
| `--local` | `-l` | Use local roster.yml instead of Yahoo API |
| `--sync` | | Fetch roster from Yahoo and save to roster.yml |

#### Advanced Options (Require Yahoo API)
| Option | Description |
|--------|-------------|
| `--weekly-summary` | Comprehensive Monday morning report (bodies table + drop candidates + top FAs) |
| `--drop-candidates` | Show underutilized roster players with low slot utilization for the week |
| `--available-fas YYYY-MM-DD` | Find best available free agents playing on specific date with drop recommendations |
| `--recommend-add` | Show top free agent recommendations ranked by weekly efficiency gain |
| `--compare-team TEAM_ID` | Compare your roster efficiency against another team |
| `--player-swap DROP_ID ADD_ID` | Simulate the impact of swapping two players |
| `--force` | Force refresh all caches (NHL stats, free agents, schedules) |

### Examples

#### Basic Usage
```bash
# Current week with colors
python create_bodies_table.py -c

# Specific date with 4-week projection
python create_bodies_table.py -d 2025-01-15 -w 4

# Today's lineup only
python create_bodies_table.py -D

# Export to Markdown
python create_bodies_table.py -e markdown -o week.md
```

#### Advanced Features
```bash
# Monday morning workflow report (RECOMMENDED!)
python create_bodies_table.py --weekly-summary
# Shows: Complete weekly report with roster saturation, drop candidates, and top FAs

# Identify underutilized players on your roster
python create_bodies_table.py --drop-candidates
# Shows: Players benched despite having games (wasted bench games)

# Find streaming pickups for a specific date
python create_bodies_table.py --available-fas 2026-01-05
# Shows: Best FAs playing that day + which rostered players to drop

# Get weekly free agent recommendations
python create_bodies_table.py --recommend-add
# Shows: Top FAs ranked by efficiency gain with weekly projections

# Compare efficiency against another team
python create_bodies_table.py --compare-team 2
# Shows: Side-by-side roster efficiency comparison

# Simulate a player swap before executing
python create_bodies_table.py --player-swap 12345 67890
# Shows: Projected impact of dropping player 12345 and adding 67890

# Force refresh all data (ignore caches)
python create_bodies_table.py --available-fas 2026-01-05 --force
# Useful when you need the latest stats/rankings
```

## Advanced Features Explained

### Weekly Summary (`--weekly-summary`)

Complete Monday morning workflow report combining three essential sections into one comprehensive view.

**Sections included:**
1. **Roster Saturation** - Bodies table showing lineup coverage for the week with efficiency percentages
2. **Drop Candidates** - Top 5 underutilized players with wasted bench games
3. **Top Free Agent Targets** - Top 5 available FAs ranked by efficiency gain potential

**Perfect for:**
- Monday morning waiver decisions
- Quick weekly roster assessment
- Identifying optimization opportunities

**Output highlights:**
- Color-coded efficiency metrics (green = good, yellow = moderate, red = critical)
- Utilization percentages (Slots ÷ Games)
- Wasted games counter for drop candidates
- Efficiency gain projections for free agents

**Example workflow:**
```bash
# Sunday night or Monday morning
python create_bodies_table.py --weekly-summary

# Review the three sections:
# 1. Check roster saturation - where are the gaps?
# 2. Identify drop candidates - who's sitting on the bench?
# 3. Evaluate top FAs - what's the best add for maximum impact?
```

### Drop Candidates (`--drop-candidates`)

Identify roster players with low slot utilization for the upcoming week.

**How it works:**
1. Runs the lineup optimizer for each day of the week
2. Counts actual slot assignments for each player
3. Compares slot fills vs. games played
4. Calculates utilization percentage and wasted bench games

**Output columns:**
- **PLAYER** - Player name
- **TEAM** - Team abbreviation
- **POS** - Position eligibility (shows flexibility, e.g., "C/LW (2)")
- **FPTS/G** - Fantasy points per game (season average)
- **Games** - Total games scheduled this week
- **Slots** - Actual roster slot fills (from optimizer)
- **Util%** - Utilization percentage (Slots ÷ Games × 100)
- **Wasted** - Bench games (Games - Slots)

**Sorting:**
- Primary: Wasted games (descending) - players with most bench time first
- Secondary: FPTS/G (ascending) - worst performers among ties

**Use cases:**
- Identify candidates for drops when picking up streamers
- Find roster inefficiencies before making waiver claims
- Optimize roster composition for better weekly coverage

### Streaming Pickups (`--available-fas`)

Find the best available free agents playing on a specific date for same-day streaming pickups.

**Output includes:**
- **Top streaming options**: Available FAs ranked by FPTS/G (fantasy points per game), then OR# (overall rank)
- **Drop candidates**: Your rostered players NOT playing that date, sorted by worst FPTS/G
- **Position flexibility**: Shows multi-position eligibility (e.g., "C/LW/RW (3)")
- **Est Δ**: Expected point differential for each recommended swap (color-coded: green = positive, red = negative)

**Example output:**
```
TOP STREAMING OPTIONS (players with games on Sunday, Jan 04, 2026):
RANK  PLAYER           TEAM  POS     GP  OR#  FPTS  FPTS/G  Est Game  OWN%
1     Brock Nelson     COL   C       39   67  294.4   7.55     7.55   59%
2     Juraj Slafkovský MTL   LW/RW   40   64  299.0   7.47     7.47   85%

YOUR DROP CANDIDATES (not playing on Sunday, Jan 04, 2026):
RANK  PLAYER           TEAM  POS       GP  OR#  FPTS  FPTS/G  Est Δ
1     Roman Josi       NSH   D         28  999  183.7   6.56   +0.99
2     Elias Pettersson VAN   C/LW (2)  31  999  212.9   6.87   +0.68
```

### Free Agent Recommendations (`--recommend-add`)

Discover the best available free agents based on weekly efficiency gain potential.

**How it works:**
1. Analyzes your roster's schedule for the upcoming week
2. Fetches top 100 available FAs (excludes goalies and injured players)
3. Calculates each FA's projected weekly efficiency gain
4. Ranks by: (1) Efficiency gain, (2) Games next week, (3) Fantasy points per game

**Efficiency gain formula:**
```
Gain = (FA Games Next Week × FA FPTS/G) - (Average Roster Player Games × FPTS/G)
```

### Team Comparison (`--compare-team`)

Benchmark your roster's efficiency against any league opponent.

**Shows:**
- Side-by-side bodies tables for both teams
- Total filled slots comparison
- Efficiency percentage for each team
- Identifies scheduling advantages

### Player Swap Simulation (`--player-swap`)

Preview the exact impact of an add/drop transaction before executing it.

**Output includes:**
- Current roster efficiency vs. projected efficiency after swap
- Games played comparison (drop vs. add)
- Weekly slot fill differential
- Color-coded impact summary

## Roster YAML Format

If not using Yahoo API, create a `roster.yml` file:

```yaml
players:
  - name: "Connor McDavid"
    team: "EDM"
    pos: ["C", "LW"]

  - name: "Cale Makar"
    team: "COL"
    pos: ["D"]

  - name: "Igor Shesterkin"
    team: "NYR"
    pos: ["G"]
```

## How It Works

### Core Algorithm
1. **Fetch NHL schedules** - Uses NHL public API to get game schedules per team
2. **Position-aware optimization** - OR-Tools CP-SAT solver assigns players to maximize filled slots
3. **Constraint satisfaction** - Ensures each slot gets at most one player, each player fills at most one slot
4. **Multi-week projection** - Repeats process across consecutive weeks

### Advanced Features Integration
- **NHL Stats API** - Fetches games played (GP) for accurate FPTS/G calculations
- **Yahoo Free Agents API** - Retrieves top 100 FAs with ownership %, ranks, and fantasy points
- **Single-date game matrix** - Optimized lookup for streaming pickup schedule detection
- **Position flexibility scoring** - Identifies multi-position players for drop candidate evaluation

## Caching

To minimize API calls and improve performance, the tool caches data:

- **NHL Stats Cache**: `.cache/nhl_stats.json` - 24-hour TTL (825 NHL players)
- **Yahoo FA Cache**: `.cache/yahoo_free_agents.json` - 30-minute TTL (top 100 FAs)
- **In-memory schedule cache**: Team game schedules cached per week
- **Force refresh**: Use `--force` to bypass all caches and fetch fresh data

## Color Coding

When using `--color`:
- **Green (X)** - Filled slot
- **Yellow (empty)** - 2-3 empty slots for this position (moderate concern)
- **Red (empty)** - 4+ empty slots for this position (critical gap)

In streaming pickups and recommendations:
- **Green Est Δ** - Positive point differential (good swap)
- **Red Est Δ** - Negative point differential (bad swap)

## Automation

Schedule automated weekly reports delivered via email every Sunday morning.

**Quick Setup:**
```bash
# 1. Configure email in send_weekly_email.py
# 2. Set up Gmail App Password (see QUICKSTART_AUTOMATION.md)
# 3. Schedule with launchd
cp com.fantasyhockey.weeklyreport.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
```

**What you get:**
- Weekly summary report delivered every Sunday morning
- HTML email with color-coded output preserved
- Roster saturation, drop candidates, and top FA recommendations
- Perfect for Monday morning waiver decisions

**Full guides:**
- **Quick Start**: [QUICKSTART_AUTOMATION.md](QUICKSTART_AUTOMATION.md) - 5-minute setup
- **Detailed Guide**: [AUTOMATION_GUIDE.md](AUTOMATION_GUIDE.md) - All options and troubleshooting

## OAuth & Security

- OAuth tokens stored in `.yahoo_tokens.json` (gitignored, user-only permissions)
- Tokens auto-refresh - only authorize once
- Credentials never logged or exposed
- `.env` file gitignored for safety

## Files

### Core Files
- `create_bodies_table.py` - Main script with all features
- `yahoo_client.py` - Yahoo OAuth and API wrapper
- `nhl_api.py` - NHL stats API client with caching
- `config.py` - Configuration management
- `roster.yml` - Manual roster input (optional)

### Configuration (gitignored)
- `.env` - Yahoo API credentials
- `.yahoo_tokens.json` - OAuth tokens
- `.cache/` - NHL stats and free agent caches

### Automation Files
- `send_weekly_email.py` - Email sender with HTML formatting (recommended)
- `send_weekly_report.sh` - Shell script for basic email via mail command
- `com.fantasyhockey.weeklyreport.plist` - launchd configuration for macOS scheduling

### Documentation
- `README.md` - This file
- `QUICKSTART_AUTOMATION.md` - 5-minute automation setup guide
- `AUTOMATION_GUIDE.md` - Comprehensive automation and troubleshooting guide
- `STREAMING_FEATURE_PLAN.md` - Detailed implementation plan for --available-fas

## License

MIT
