# Yahoo Fantasy Hockey — Roadmap

This document outlines planned enhancements for the Yahoo Fantasy Hockey Bodies Table project.

The goal is to incrementally evolve the tool from a roster-aware schedule visualizer into a flexible decision-support utility for weekly lineup planning and streaming strategy.

## Current State (Baseline)

The project has already moved beyond a simple proof of concept. As of now, the script supports:

✅ Core Functionality
	•	Weekly bodies table generation (Mon–Sun)
	•	Single-day analysis mode
	•	Multi-week projections
	•	Position-aware lineup assignment
	•	Constraint-based optimization to maximize filled slots
	•	Command-line interface with flags:
	•	--date
	•	--weeks
	•	--day
	•	--roster
	•	Manual roster input via YAML
	•	NHL schedule ingestion via public NHL API
	•	Deterministic, repeatable output suitable for weekly planning

This baseline is considered stable.

## Phase 1 — Yahoo! API Integration ✅ COMPLETED

🎯 Goal

Eliminate manual roster maintenance and ensure lineup rules exactly match league configuration.

Features
	✅	Authenticate with Yahoo Fantasy Sports API using OAuth 2.0 with PKCE
	✅	HTTPS support with self-signed certificates for OAuth callback
	✅	Automatically fetch:
		✅	Team roster with player names, teams, and position eligibility
		✅	League roster configuration (slots, positions)
	✅	Replace or augment roster.yml with live data
	✅	Allow fallback to YAML for offline or testing use
	✅	--sync flag to update local roster.yml from Yahoo API

Implementation Notes
	•	OAuth setup isolated in yahoo_client.py module
	•	Access tokens cached in .yahoo_tokens.json with automatic refresh
	•	JSON format explicitly requested from Yahoo API (defaults to XML)
	•	Yahoo Public Client OAuth requires HTTPS redirect URIs
	•	Self-signed certificates auto-generated using openssl
	•	Read-only API access (no roster modifications)

## Additional UX/Utility Enhancements
1. [x] Argument allowing users to export results to:
  - [x] CSV (--export csv)
  - [x] Markdown (--export markdown)
  - [x] Clipboard (--export clipboard, uses pbcopy/xclip)
2. [x] Allow user to toggle single/multi-table output in an argument (--separate-weeks)
3. [x] Implement color (--color flag: green for filled slots, yellow for moderate empties, red for critical empties)
4. [x] Update export to use default targets if none specified
   - CSV: yfh-export-{{date}}{{time}}.csv
   - MD: yfh-export-{{date}}{{time}}.md
5. [x] Update export signifiers to also accept
   - [x] `md` for Markdown output
   - [x] `cp` for clipboard
6. [x] Add argument to fetch data and create/update `roster.yml` file (--sync)
7. [x] Default to Yahoo API with --local/-l flag for local roster fallback
8. [x] Prompt user for local fallback when Yahoo API fails
9. [x] Update the calculation to include an "Idle players by position" summary - helps identify roster surpluses where you have more eligible players than roster slots
10. [x] Add denominator and percentage to filled starts report (e.g., "12/14 (85.7%)")
11. [x] Break down filled starts by individual slot (C1, C2, LW1, etc.) instead of aggregated position
12. [x] Integrate EFF and PCT columns into main position grid table
13. [x] Sort slots by efficiency (PCT) descending within each position group
14. [x] Remove --color flag and make colored output default with symbols (✓/✗)
15. [x] Fix grid alignment with proper ANSI code handling via pad_colored_cell()
16. [x] Add --compact flag for condensed day headers (M, T, W vs M(12/29), T(12/30))
17. [x] Add daily roster fill summary row (TOT) showing overall EFF/PCT and per-day counts
18. [x] Center-align headers in compact mode for better visual balance
19. [x] Widen compact mode columns (2→3 chars) for proper footer alignment

## Phase 2 — Competitive Team Comparison

🎯 Goal

Enable head-to-head roster efficiency comparison to identify competitive advantages and gaps that need immediate attention versus league-common weaknesses.

Features
	•	[x] Compare your roster efficiency against a specific opponent for the upcoming matchup week
	•	[x] Team specification via team ID: --compare-team <team_id>
	•	[x] Force single-week analysis when comparison mode is active (ignore --weeks)
	•	[x] Display separate grids for both teams (similar to --separate-weeks mode)
	•	[x] Side-by-side comparison in Aggregate Stats section showing:
		•	[x] Overall EFF (filled/total) for both teams
		•	[x] Overall PCT for both teams
		•	[x] Daily breakdown (M, T, W, Th, F, Sa, Su) comparing filled slots per day
		•	[x] Visual indicators: green when ahead, red when behind, yellow when tied
		•	[x] Differential values (e.g., "+5" or "-3") showing your advantage/deficit
	•	[x] Fetch opponent roster via Yahoo API using team ID
	•	[ ] Support comparison with local roster files for testing/offline use (not needed - requires Yahoo API)

Implementation Notes
	•	Reuse existing grid generation and optimization logic for opponent's roster
	•	Assume both teams use same SLOTS configuration (league-wide setting)
	•	Color-code comparison metrics for quick visual identification of strengths/weaknesses
	•	Add comparison summary showing position-group efficiency gaps (C vs C, D vs D, G vs G)

Example Output:
```
=== YOUR TEAM: 2025-12-29 → 2026-01-04 ===
[Full grid display]

=== OPPONENT (Team 3): 2025-12-29 → 2026-01-04 ===
[Full grid display]

=== Aggregate Stats ===

Comparison Summary:
                    YOUR TEAM    OPPONENT     DIFF
EFF                 57/84        63/84        -6
PCT                 67.9%        75.0%        -7.1%
M (12/29)           11           10           +1
T (12/30)           8            11           -3
W (12/31)           9            10           -1
Th (01/01)          6            8            -2
F (01/02)           6            9            -3
Sa (01/03)          10           9            +1
Su (01/04)          7            6            +1

Position Group Efficiency:
C:  71.4% vs 78.6% (-7.2%)
LW: 85.7% vs 71.4% (+14.3%) ✓ ADVANTAGE
RW: 78.6% vs 85.7% (-7.1%)
D:  53.6% vs 67.9% (-14.3%) ⚠ CRITICAL GAP
G:  50.0% vs 64.3% (-14.3%) ⚠ CRITICAL GAP
```

## Phase 3 — "What-If" Roster Scenarios ✅ COMPLETED

🎯 Goal

Test hypothetical roster moves (adds/drops) to quantify their impact on lineup efficiency before making actual transactions.

Features
	•	[x] Simulate adding/dropping players to see efficiency impact
	•	[x] Input method: --player-swap command-line argument with two Yahoo player IDs
	•	[x] Player data source: Yahoo API lookup using player IDs
	•	[x] Output format: Side-by-side comparison showing current roster vs. roster with swap
	•	[x] Force single-week analysis when swap mode is active
	•	[x] Display separate grids for both scenarios (similar to --compare-team mode)
	•	[x] Swap impact summary showing:
		•	[x] Overall EFF (filled/total) for both scenarios
		•	[x] Overall PCT for both scenarios
		•	[x] Daily breakdown (M, T, W, Th, F, Sa, Su) comparing filled slots per day
		•	[x] Visual indicators: green when swap improves, red when it worsens, yellow when neutral
		•	[x] Differential values (e.g., "+5" or "-3") showing improvement/regression
	•	[ ] Support multiple scenarios in one run (future enhancement)
	•	[ ] Validate against league roster constraints (future enhancement)

Implementation Notes
	•	Reuses existing comparison infrastructure from Phase 2
	•	Yahoo player IDs obtained from Yahoo Fantasy interface/app
	•	Drop player identified by fetching player details via Yahoo API and matching by name
	•	Automatic NHL schedule lookup (no manual caching needed)
	•	Cannot be used with --local flag (requires Yahoo API)
	•	Cannot be combined with --compare-team (mutually exclusive)

Example Usage:
```bash
# Swap player 3981 for player 5479 for current week
python create_bodies_table.py --player-swap 3981 5479

# Swap for a future week
python create_bodies_table.py --player-swap 3981 5479 --date 2026-01-06

# Compact output mode
python create_bodies_table.py --player-swap 3981 5479 --compact
```

Example Output:
```
=== CURRENT ROSTER: 2025-12-29 → 2026-01-04 ===
[Full grid display]

=== WITH SWAP: 2025-12-29 → 2026-01-04 ===
[Full grid display]

=== Swap Impact Summary ===

                    CURRENT      WITH SWAP    DIFF
EFF                 57/84        63/84        +6
PCT                 67.9%        75.0%        +7.1%
M (12/29)           11           12           +1
T (12/30)           8            10           +2
W (12/31)           9            10           +1
Th (01/01)          6            8            +2
F (01/02)           6            9            +3
Sa (01/03)          10           9            -1
Su (01/04)          7            5            -2
```

## Phase 4 — Web Interface

🎯 Goal

Create a web-based interface for mobile and remote access to the bodies table tool, eliminating the need to run Python scripts locally.

Features (To Be Specified)
	•	[ ] Web-based UI accessible from any device (desktop, tablet, mobile)
	•	[ ] Yahoo OAuth authentication flow
	•	[ ] Interactive mode selection (Week View, Compare Teams, Player Swap)
	•	[ ] Date picker for week selection
	•	[ ] Visual grid display with color-coded efficiency indicators
	•	[ ] Responsive design for mobile devices
	•	[ ] Session management for authenticated users
	•	[ ] Export functionality (CSV, Markdown)

## Implementation Options

### Option 1: Streamlit (Recommended)
**Best for:** Rapid deployment, Python developers, data-focused apps

**Pros:**
- Pure Python (no HTML/CSS/JS needed)
- Built-in UI components (tables, charts, date pickers, buttons)
- Native support for dataframes and grids
- Easy OAuth integration with session state
- Simple deployment to Streamlit Cloud (free tier available)
- OR-Tools works perfectly
- Auto-refresh and reactive UI
- Can reuse existing Python codebase directly

**Cons:**
- Less control over UI/UX customization
- Streamlit-specific paradigm (session state, reruns)
- Limited to Streamlit's widget library

**Hosting Options:**
- Streamlit Cloud (free, recommended for start)
- Railway
- Render
- Heroku
- Google Cloud Run

**Estimated Development Time:** 4-8 hours for MVP

### Option 2: Flask + Bootstrap
**Best for:** Full control, traditional web application

**Pros:**
- Lightweight Python web framework
- Complete control over UI/UX
- Can reuse existing Python logic
- Easy to add REST API endpoints
- Bootstrap for responsive mobile design
- Standard web development patterns

**Cons:**
- Need to write HTML templates, CSS, JavaScript
- More setup and boilerplate than Streamlit
- Need to handle session management manually
- OAuth flow requires more configuration

**Hosting Options:**
- Render (free tier, recommended)
- Railway
- PythonAnywhere
- Heroku
- AWS Elastic Beanstalk

**Estimated Development Time:** 12-20 hours for MVP

### Option 3: FastAPI + React
**Best for:** API-first approach, modern tech stack, mobile app future

**Pros:**
- Fast, modern async API framework
- Auto-generated API documentation (Swagger/OpenAPI)
- Can build native mobile app later using same API
- TypeScript frontend for type safety
- Modern development experience
- Separation of concerns (backend/frontend)

**Cons:**
- Most complex setup
- Two separate codebases to maintain
- Requires JavaScript/TypeScript knowledge
- More deployment complexity

**Hosting Options:**
- Vercel (frontend) + Railway/Render (API)
- Netlify (frontend) + AWS Lambda (API)
- Railway (full stack)
- Google Cloud Run

**Estimated Development Time:** 20-30 hours for MVP

## Recommended Approach: Streamlit

Start with Streamlit for these reasons:
1. **Fastest time to market** - Working MVP in hours, not days
2. **Pure Python** - Reuse existing codebase directly
3. **Built-in components** - Tables, date pickers, forms, session state
4. **Free hosting** - Streamlit Cloud free tier is generous
5. **OAuth integration** - Straightforward with session state
6. **Easy migration** - Can always move to Flask/FastAPI later

## Streamlit Implementation Plan

### Core Structure
```python
import streamlit as st
from yahoo_client import YahooClient
from create_bodies_table import (
    build_player_game_matrix,
    solve_daily_assignment,
    SLOTS
)

# Page configuration
st.set_page_config(
    page_title="Yahoo Fantasy Hockey - Bodies Table",
    page_icon="🏒",
    layout="wide"
)

# Session state for authentication
if 'yahoo_client' not in st.session_state:
    st.session_state.yahoo_client = None
if 'players' not in st.session_state:
    st.session_state.players = None

# Authentication
if st.session_state.yahoo_client is None:
    st.title("Yahoo Fantasy Hockey - Bodies Table")
    if st.button("Login with Yahoo"):
        # OAuth flow
        client = YahooClient()
        client.authorize()
        st.session_state.yahoo_client = client
        st.rerun()
else:
    # Main application
    st.sidebar.title("Options")

    mode = st.sidebar.radio(
        "Mode",
        ["Week View", "Compare Teams", "Player Swap"]
    )

    week_date = st.sidebar.date_input("Week Start")
    compact = st.sidebar.checkbox("Compact View")

    if mode == "Compare Teams":
        team_id = st.sidebar.text_input("Opponent Team ID")
    elif mode == "Player Swap":
        drop_id = st.sidebar.text_input("Drop Player ID")
        add_id = st.sidebar.text_input("Add Player ID")

    if st.sidebar.button("Generate"):
        # Run analysis and display results
        # Use st.dataframe() for grids
        # Use st.metric() for summary stats
        pass
```

### Key Features
- **Authentication:** Session-based OAuth with Yahoo
- **UI Components:**
  - Radio buttons for mode selection
  - Date picker for week selection
  - Text inputs for team/player IDs
  - Dataframes for grid display
  - Metrics for EFF/PCT summary
  - Download buttons for CSV/MD export
- **Display:**
  - Color-coded cells using Streamlit's styling API
  - Side-by-side dataframes for comparisons
  - Expandable sections for aggregate stats

### Deployment Steps
1. Create `streamlit_app.py` with web interface
2. Create `requirements.txt` with dependencies
3. Create Streamlit Cloud account
4. Connect GitHub repository
5. Configure secrets (Yahoo API credentials)
6. Deploy

### Future Enhancements
- [ ] Save favorite comparisons/scenarios
- [ ] Historical trend analysis
- [ ] Multi-week planning view
- [ ] Team league standings integration
- [ ] Push notifications for optimal roster changes
- [ ] Player search/autocomplete
- [ ] Free agent browse and analysis

## Mobile Considerations

### iOS/Android Access
- Streamlit apps are fully responsive and mobile-friendly
- Progressive Web App (PWA) capabilities can be added
- Native app wrapper possible with Capacitor/Cordova if needed

### Native App (Future)
If Streamlit proves limiting for mobile UX:
- Build FastAPI backend (reuse Python logic)
- Create React Native or Flutter frontend
- Use same API for web and mobile
- Full offline support with local caching

## Notes on OR-Tools Compatibility

All web deployment options support OR-Tools:
- ✅ Streamlit Cloud: Full support
- ✅ Render/Railway: Full support
- ✅ Heroku: Full support (may need buildpack)
- ✅ Cloud Run: Full support

No iOS Pythonista limitations in cloud-hosted environments.

## Phase 5 — Free Agent Recommendations

🎯 Goal

Automatically analyze available free agents and recommend the best waiver wire pickups based on schedule impact and player value, eliminating manual "what-if" testing.

### Features
- [ ] Fetch top available free agents from Yahoo API
- [ ] Simulate swapping drop candidate with each available player
- [ ] Rank recommendations by schedule impact (games added) and player value
- [ ] Display top 10 recommendations with detailed metrics
- [ ] Support custom number of recommendations via --top argument
- [ ] Filter out goalies (only recommend C, LW, RW, D)
- [ ] Show all available players regardless of position eligibility
- [ ] Single drop candidate per run (can run multiple times for multiple drops)

### Player Value Metrics (in priority order)
1. **Primary Sort**: Efficiency gain (number of games added to weekly schedule)
2. **Secondary Sort**: Overall Rank (OR#) - Yahoo's **current** overall rank (lower is better)
   - Extracted from Yahoo API `player_ranks` with `rank_type="OR"`
   - This is the live, current-season ranking, not preseason
3. **Tertiary Sort**: Total fantasy points (FPTS) - Season total fantasy points

### Implementation Notes
- Reuses existing player swap infrastructure from Phase 3
- Yahoo API endpoint: `league/{league_id}/players;status=FA` for free agents
- Sort by rank/ownership to get top available players
- Fetch 50-100 players, filter out goalies, run swap simulations
- Primary sort: Efficiency gain (games added to schedule)
- Secondary sort: Player value metric
- Performance: OR-Tools solves in milliseconds, main bottleneck is Yahoo API calls
- Use batch requests where possible to minimize API rate limit impact

### Command-Line Interface

```bash
# Basic usage: recommend adds for upcoming week
python create_bodies_table.py --recommend-add 3981

# Specify future week
python create_bodies_table.py --recommend-add 3981 --date 2026-01-06

# Show top 20 recommendations instead of default 10
python create_bodies_table.py --recommend-add 3981 --top 20

# Combine with compact mode
python create_bodies_table.py --recommend-add 3981 --compact

# Multiple drops: run twice
python create_bodies_table.py --recommend-add 3981
python create_bodies_table.py --recommend-add 5479
```

### Example Output

```
Fetching top 100 available free agents...
✓ Fetched 100 available players
✓ Filtered to 85 skaters (excluded 15 goalies)

Analyzing free agent swaps for week 2026-01-06 → 2026-01-12
Drop candidate: Connor McDavid (EDM, C/LW)

Simulating 85 potential swaps...
████████████████████████████████████████ 100%

=== Top 10 Free Agent Recommendations ===

RANK   PLAYER                    TEAM  POS        EFF   OR#   FPTS   OWN%
────── ───────────────────────── ───── ────────── ───── ───── ────── ──────
1      Nathan MacKinnon          COL   C/RW       +5     1   385.2  95.0%
2      Cale Makar                COL   D          +4     2   372.3  98.0%
3      Leon Draisaitl            EDM   C/LW       +4     3   378.1  96.0%
4      Artemi Panarin            NYR   LW         +3     4   368.9  94.0%
5      Quinn Hughes              VAN   D          +3     5   365.2  93.0%
6      Mika Zibanejad            NYR   C          +2     6   362.1  92.0%
7      Brady Tkachuk             OTT   LW         +2     7   358.4  91.0%
8      Roman Josi                NSH   D          +2     8   361.7  90.0%
9      Elias Pettersson          VAN   C/LW       +1     9   364.3  89.0%
10     Adam Fox                  NYR   D          +1    10   359.8  88.0%

Column Definitions:
- EFF: Schedule efficiency gain (games added to weekly roster)
- OR#: Overall Rank among available free agents (lower is better)
- FPTS: Total fantasy points accumulated this season
- OWN%: League ownership percentage

Green = positive impact, Red = negative impact, Yellow = neutral

To see full swap details for a specific player, use:
  python create_bodies_table.py --player-swap 3981 <PLAYER_ID>
```

### Validation and Error Handling
- [ ] Error if Yahoo API unavailable (requires API, cannot use --local)
- [ ] Error if used with --day mode (requires week mode)
- [ ] Error if combined with --player-swap or --compare-team (mutually exclusive)
- [ ] Handle API rate limits gracefully with retry/backoff
- [ ] Display progress indicator during bulk swap simulations
- [ ] Warning if no positive-impact recommendations found

### Future Enhancements
- [ ] Multi-drop optimization (find best pair of adds for two drops)
- [ ] Position-specific filtering (--position D to only see defensemen)
- [ ] Exclude specific players (--exclude-player PLAYER_ID)
- [ ] Save recommendations to file for later review
- [ ] Integration with team comparison to find waiver moves that close gaps
- [ ] Historical trend analysis (player hot/cold streaks)
- [ ] Injury status awareness (exclude injured players from recommendations)
- [ ] **Next 7/14 Days Projections**: Yahoo's UI shows "Next 7 Days" and "Next 14 Days" projected fantasy points. However, these projections are not available through the public Yahoo Fantasy API (tested with `projected_stats`, `projections`, `expert_picks` parameters - all return 400 errors). Potential workarounds:
  - Calculate rolling average from recent games (last 7/14/30 days)
  - Use external projection sources (FantasyPros, Daily Faceoff, etc.)
  - Scrape Yahoo's web interface (not recommended - fragile, may violate TOS)