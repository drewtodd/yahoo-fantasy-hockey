#!/usr/bin/env python3
"""
Send weekly fantasy hockey report via email with HTML formatting.
Preserves color-coded output by converting ANSI codes to HTML.
"""

import subprocess
import sys
import os
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from pathlib import Path

# Email configuration - EDIT THESE
SENDER_EMAIL = "fantasy-hockey@yourdomain.com"
RECIPIENT_EMAIL = "your.email@example.com"  # CHANGE THIS
SMTP_HOST = "smtp.gmail.com"  # For Gmail
SMTP_PORT = 587  # For Gmail TLS
SMTP_USERNAME = "your.email@example.com"  # CHANGE THIS (often same as SENDER_EMAIL)
SMTP_PASSWORD = ""  # Use app password for Gmail - CHANGE THIS or use env var
USE_AUTH = False  # Set to True if using Gmail or other SMTP requiring auth

# Or use environment variables (recommended for security)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", SMTP_USERNAME)
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", SMTP_PASSWORD)


def ansi_to_html(text: str) -> str:
    """Convert ANSI color codes to HTML with inline styles."""
    # ANSI color code mappings
    colors = {
        '92': '#00ff00',  # Green
        '93': '#ffff00',  # Yellow
        '91': '#ff0000',  # Red
        '1': 'font-weight:bold',  # Bold
    }

    # Replace ANSI codes with HTML spans
    def replace_code(match):
        code = match.group(1)
        if code == '0':  # Reset
            return '</span>'
        elif code == '1':  # Bold
            return '<span style="font-weight:bold">'
        elif code in colors:
            color = colors[code]
            if color.startswith('#'):
                return f'<span style="color:{color}">'
            else:
                return f'<span style="{color}">'
        return ''

    # Process ANSI escape sequences
    html = re.sub(r'\033\[([0-9;]+)m', replace_code, text)

    # Ensure all spans are closed
    open_spans = html.count('<span')
    close_spans = html.count('</span>')
    html += '</span>' * (open_spans - close_spans)

    return html


def generate_report() -> str:
    """Run the weekly summary script and capture output."""
    script_dir = Path(__file__).parent
    cmd = ["uv", "run", "python", "create_bodies_table.py", "--weekly-summary"]

    try:
        result = subprocess.run(
            cmd,
            cwd=script_dir,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            return f"ERROR: Report generation failed\n\n{result.stderr}"

        return result.stdout

    except subprocess.TimeoutExpired:
        return "ERROR: Report generation timed out after 120 seconds"
    except Exception as e:
        return f"ERROR: {str(e)}"


def send_email(plain_text: str, html_content: str, subject: str):
    """Send email with both plain text and HTML versions."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL

    # Attach plain text version
    text_part = MIMEText(plain_text, 'plain', 'utf-8')
    msg.attach(text_part)

    # Attach HTML version
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)

    # Send email
    try:
        if USE_AUTH:
            # Use authenticated SMTP (e.g., Gmail)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            # Use local SMTP without auth
            with smtplib.SMTP('localhost') as server:
                server.send_message(msg)

        print(f"✓ Email sent successfully to {RECIPIENT_EMAIL}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("✗ SMTP authentication failed. Check username/password.")
        print("  For Gmail, you need an 'App Password': https://support.google.com/accounts/answer/185833")
        return False
    except Exception as e:
        print(f"✗ Failed to send email: {e}")
        return False


def main():
    print("Generating weekly fantasy hockey report...")

    # Generate the report
    report_text = generate_report()

    if report_text.startswith("ERROR:"):
        print(report_text)
        sys.exit(1)

    print("✓ Report generated successfully")

    # Create HTML version
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Courier New', monospace;
                background-color: #1e1e1e;
                color: #d4d4d4;
                padding: 20px;
                line-height: 1.4;
            }}
            pre {{
                white-space: pre;
                margin: 0;
                font-size: 13px;
            }}
            .checkmark {{
                color: #00ff00;
            }}
        </style>
    </head>
    <body>
        <pre>{ansi_to_html(report_text)}</pre>
    </body>
    </html>
    """

    # Email subject with date
    week_date = datetime.now().strftime("%Y-%m-%d")
    subject = f"Fantasy Hockey Weekly Report - Week of {week_date}"

    # Send email
    print("Sending email...")
    success = send_email(report_text, html_body, subject)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
