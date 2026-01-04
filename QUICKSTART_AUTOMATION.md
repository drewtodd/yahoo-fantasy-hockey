# Quick Start: Automated Weekly Reports

Get your fantasy hockey report delivered every Sunday morning in 5 minutes.

## Fastest Setup (Gmail)

```bash
# 1. Edit email configuration
nano send_weekly_email.py
# Change line 14: RECIPIENT_EMAIL = "your.email@gmail.com"
# Change line 16: SMTP_USERNAME = "your.email@gmail.com"
# Change line 18: USE_AUTH = True

# 2. Get Gmail App Password
# Visit: https://myaccount.google.com/apppasswords
# Create password for "Mail" → copy the 16-character password

# 3. Set password as environment variable
echo 'export SMTP_PASSWORD="xxxx-xxxx-xxxx-xxxx"' >> ~/.zshrc
source ~/.zshrc

# 4. Test it (sends email now)
uv run python send_weekly_email.py

# 5. Schedule it for Sunday 8 AM
cp com.fantasyhockey.weeklyreport.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

# 6. Verify it's scheduled
launchctl list | grep fantasyhockey
```

**Done!** You'll get your first automated report next Sunday at 8 AM.

---

## What You'll Receive

Every Sunday morning at 8 AM, you'll get an email with:

**Section 1: Roster Saturation**
- Color-coded bodies table showing week's lineup coverage
- Efficiency percentages by position
- Daily slot fill summary

**Section 2: Drop Candidates** (Top 5)
- Underutilized players sitting on bench despite having games
- Utilization % and wasted games

**Section 3: Top Free Agent Targets** (Top 5)
- Best available FAs ranked by efficiency gain
- Projected weekly impact

---

## Customize Schedule

Edit the time before installing:

```bash
nano com.fantasyhockey.weeklyreport.plist
```

Change these values:
```xml
<key>Weekday</key>
<integer>0</integer>  <!-- 0=Sun, 1=Mon, ..., 6=Sat -->
<key>Hour</key>
<integer>8</integer>  <!-- 24-hour format -->
```

Common options:
- **Sunday 7 AM**: `Weekday=0, Hour=7`
- **Saturday 7 PM**: `Weekday=6, Hour=19` (night before)
- **Monday 6 AM**: `Weekday=1, Hour=6` (waiver deadline morning)

---

## Test Before Waiting for Sunday

```bash
# Send email right now (doesn't affect schedule)
uv run python send_weekly_email.py

# Or trigger the scheduled task manually
launchctl start com.fantasyhockey.weeklyreport

# Check if it worked
cat .cache/weekly_report_stdout.log
```

---

## Troubleshooting

**Email didn't arrive?**
```bash
# Check logs
cat .cache/weekly_report_stderr.log

# Common fix: Make sure App Password is set
echo $SMTP_PASSWORD  # Should show your password
```

**Task not running on schedule?**
```bash
# Check if loaded
launchctl list | grep fantasyhockey

# If not listed, load it
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
```

**Yahoo authentication failed?**
```bash
# Re-authenticate (run manually once)
uv run python create_bodies_table.py --weekly-summary
```

---

## Stop/Disable Automation

```bash
# Temporarily disable
launchctl unload ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

# Re-enable
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

# Remove completely
launchctl unload ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
rm ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
```

---

## Advanced Setup

For detailed instructions on other email providers, cron setup, or troubleshooting, see [AUTOMATION_GUIDE.md](AUTOMATION_GUIDE.md).

---

## Security Note

Your Gmail App Password is stored in `~/.zshrc`. This is reasonably secure (only you can read it), but for maximum security, consider using macOS Keychain instead. See the full guide for details.
