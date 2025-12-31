# Yahoo Fantasy Hockey Bodies Table Generator

A tool to optimize your Yahoo Fantasy Hockey lineup by visualizing roster slot coverage across the week and projecting multi-week schedules.

## Features

- **Weekly bodies table** - Visualize filled roster slots (Mon-Sun) with position-aware optimization
- **Single-day analysis** - Check lineup coverage for any specific date
- **Multi-week projections** - Forecast coverage for multiple consecutive weeks
- **Yahoo API integration** - Automatically fetch roster and league settings from Yahoo Fantasy
- **Color-coded output** - Green for filled, yellow for moderate gaps, red for critical issues
- **Export options** - CSV, Markdown, or clipboard for easy sharing
- **Flexible date selection** - Analyze any week by providing any date within it

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
   - Create a new app with redirect URI: `http://localhost:8000`
   - Copy your Client ID and Client Secret

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
   python create_bodies_table.py --yahoo

   # Subsequent runs use cached tokens
   python create_bodies_table.py -y -w 4 -c
   ```

## Usage

```bash
# Basic usage
python create_bodies_table.py [OPTIONS]

# Short form aliases
python create_bodies_table.py -y -w 4 -c -s
```

### Command-line Options

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
| `--yahoo` | `-y` | Fetch from Yahoo Fantasy API |

### Examples

```bash
# Current week with colors
python create_bodies_table.py -c

# Specific date with 4-week projection
python create_bodies_table.py -d 2025-01-15 -w 4

# Today's lineup only
python create_bodies_table.py -D

# Yahoo API with separate week tables
python create_bodies_table.py -y -w 3 -s -c

# Export to Markdown
python create_bodies_table.py -y -e markdown -o week.md

# Copy to clipboard
python create_bodies_table.py -e clipboard
```

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

1. **Fetch NHL schedules** - Uses NHL public API to get game schedules per team
2. **Position-aware optimization** - OR-Tools CP-SAT solver assigns players to maximize filled slots
3. **Constraint satisfaction** - Ensures each slot gets at most one player, each player fills at most one slot
4. **Multi-week projection** - Repeats process across consecutive weeks

## Color Coding

When using `--color`:
- **Green (X)** - Filled slot
- **Yellow (empty)** - 2-3 empty slots for this position (moderate concern)
- **Red (empty)** - 4+ empty slots for this position (critical gap)

## OAuth & Security

- OAuth tokens stored in `.yahoo_tokens.json` (gitignored, user-only permissions)
- Tokens auto-refresh - only authorize once
- Credentials never logged or exposed
- `.env` file gitignored for safety

## Files

- `create_bodies_table.py` - Main script
- `yahoo_client.py` - Yahoo OAuth and API wrapper
- `config.py` - Configuration management
- `roster.yml` - Manual roster input (optional)
- `.env` - Yahoo API credentials (gitignored)
- `.yahoo_tokens.json` - OAuth tokens (gitignored)

## License

MIT
