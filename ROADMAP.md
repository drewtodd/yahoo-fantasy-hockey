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

## Phase 1 — Yahoo! API Integration (Near-Term)

🎯 Goal

Eliminate manual roster maintenance and ensure lineup rules exactly match league configuration.

Features
	•	Authenticate with Yahoo Fantasy Sports API
	•	Automatically fetch:
	•	Team roster
	•	Position eligibility
	•	League roster configuration (slots, UTIL, bench)
	•	Replace or augment roster.yml with live data
	•	Allow fallback to YAML for offline or testing use

Notes
	•	OAuth setup will be isolated behind a small client module
	•	Yahoo data should be cached per run to avoid repeated API calls
	•	Initial implementation will prioritize read-only access

## Additional UX/Utility Enhancements
- [ ] Argument allowing users to export results to:
  - [ ] CSV
  - [ ] Markdown
  - [ ] Clipboard(?)
- [ ] Allow user to toggle single/multi-table output in an argument
- [ ] Implement color (green for filled slots, yellow for empty-but-not-critical e.g. low % open slots, red for empty-critical)