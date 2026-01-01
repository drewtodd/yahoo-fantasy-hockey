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
	•	[ ] Compare your roster efficiency against a specific opponent for the upcoming matchup week
	•	[ ] Team specification via team ID: --compare-team <team_id>
	•	[ ] Force single-week analysis when comparison mode is active (ignore --weeks)
	•	[ ] Display separate grids for both teams (similar to --separate-weeks mode)
	•	[ ] Side-by-side comparison in Aggregate Stats section showing:
		•	[ ] Overall EFF (filled/total) for both teams
		•	[ ] Overall PCT for both teams
		•	[ ] Daily breakdown (M, T, W, Th, F, Sa, Su) comparing filled slots per day
		•	[ ] Visual indicators: green when ahead, red when behind, yellow when tied
		•	[ ] Differential values (e.g., "+5" or "-3") showing your advantage/deficit
	•	[ ] Fetch opponent roster via Yahoo API using team ID
	•	[ ] Support comparison with local roster files for testing/offline use

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

## Phase 3 — "What-If" Roster Scenarios

🎯 Goal

Test hypothetical roster moves (adds/drops) to quantify their impact on lineup efficiency before making actual transactions.

Features (To Be Specified)
	•	[ ] Simulate adding/dropping players to see efficiency impact
	•	[ ] Input method: TBD (command-line args, interactive mode, config file)
	•	[ ] Player data source: TBD (manual entry, Yahoo API lookup, free agent list)
	•	[ ] Output format: TBD (before/after comparison, delta only, full grid)
	•	[ ] Support multiple scenarios in one run
	•	[ ] Validate against league roster constraints (position limits, max roster size)

Implementation Notes
	•	Pending design decisions and requirements clarification
	•	Should integrate with Yahoo API to validate moves against actual available players
	•	Consider caching NHL schedule data to avoid redundant API calls during scenario testing