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