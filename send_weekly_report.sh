#!/bin/bash
#
# Automated Weekly Fantasy Hockey Report
# Runs --weekly-summary and emails the results
#
# Usage: ./send_weekly_report.sh

set -e

# Configuration
RECIPIENT_EMAIL="your.email@example.com"  # CHANGE THIS
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD="uv run python"
LOG_FILE="$SCRIPT_DIR/.cache/weekly_report.log"
TEMP_OUTPUT="/tmp/fantasy_hockey_report_$$.txt"

# Email subject with date
WEEK_DATE=$(date +"%Y-%m-%d")
SUBJECT="Fantasy Hockey Weekly Report - Week of $WEEK_DATE"

# Ensure log directory exists
mkdir -p "$SCRIPT_DIR/.cache"

# Log start time
echo "=== Weekly report started at $(date) ===" >> "$LOG_FILE"

# Change to script directory
cd "$SCRIPT_DIR"

# Activate virtual environment if using venv instead of uv
# Uncomment if needed:
# source .venv/bin/activate

# Run the weekly summary and capture output
echo "Running weekly summary..." >> "$LOG_FILE"
if $PYTHON_CMD create_bodies_table.py --weekly-summary > "$TEMP_OUTPUT" 2>&1; then
    echo "✓ Report generated successfully" >> "$LOG_FILE"

    # Send email using mail command (most compatible)
    if command -v mail &> /dev/null; then
        cat "$TEMP_OUTPUT" | mail -s "$SUBJECT" "$RECIPIENT_EMAIL"
        echo "✓ Email sent via mail command" >> "$LOG_FILE"
    # Fallback to Python SMTP if mail command not available
    elif command -v python3 &> /dev/null; then
        python3 << 'EOF'
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# Read the report
report_file = Path(sys.argv[1])
with open(report_file, 'r') as f:
    report_content = f.read()

# Email configuration
sender = "fantasy-hockey@localhost"  # Change if needed
recipient = "YOUR_EMAIL@example.com"  # CHANGE THIS
subject = sys.argv[2]

# Create message
msg = MIMEMultipart('alternative')
msg['Subject'] = subject
msg['From'] = sender
msg['To'] = recipient

# Plain text version
text_part = MIMEText(report_content, 'plain')
msg.attach(text_part)

# Send email (using localhost SMTP)
try:
    with smtplib.SMTP('localhost') as server:
        server.send_message(msg)
    print("✓ Email sent via Python SMTP")
except Exception as e:
    print(f"✗ Failed to send email: {e}")
    sys.exit(1)
EOF
        python3 -c "$(cat)" "$TEMP_OUTPUT" "$SUBJECT" >> "$LOG_FILE" 2>&1
        echo "✓ Email sent via Python SMTP" >> "$LOG_FILE"
    else
        echo "✗ No email method available (install mail or configure SMTP)" >> "$LOG_FILE"
        cat "$TEMP_OUTPUT" >> "$LOG_FILE"
    fi
else
    echo "✗ Report generation failed" >> "$LOG_FILE"
    cat "$TEMP_OUTPUT" >> "$LOG_FILE"
fi

# Clean up
rm -f "$TEMP_OUTPUT"

echo "=== Weekly report completed at $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
