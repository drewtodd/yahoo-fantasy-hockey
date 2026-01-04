# Automated Weekly Report Setup Guide

This guide walks you through setting up automated Sunday morning fantasy hockey reports via email.

## Quick Start (Recommended)

**Option 1: Gmail (Easiest)**
```bash
# 1. Edit send_weekly_email.py with your email
nano send_weekly_email.py
# Set RECIPIENT_EMAIL, SMTP_USERNAME, USE_AUTH = True

# 2. Get Gmail App Password (required for Gmail)
# Visit: https://myaccount.google.com/apppasswords
# Generate an app password and set it as environment variable

# 3. Test the email sender
export SMTP_PASSWORD="your-app-password-here"
uv run python send_weekly_email.py

# 4. If successful, set up the scheduler (see below)
```

**Option 2: Local Mail Command (No Auth Required)**
```bash
# 1. Edit send_weekly_report.sh with your email
nano send_weekly_report.sh
# Set RECIPIENT_EMAIL

# 2. Make executable
chmod +x send_weekly_report.sh

# 3. Test it
./send_weekly_report.sh

# 4. If successful, set up the scheduler (see below)
```

---

## Email Configuration Options

### Option A: Gmail (HTML email with colors)

**Pros:**
- Works from anywhere
- Preserves color-coded output
- Professional HTML formatting

**Setup:**
1. Edit `send_weekly_email.py`:
   ```python
   RECIPIENT_EMAIL = "your.email@gmail.com"
   SMTP_USERNAME = "your.email@gmail.com"
   USE_AUTH = True
   ```

2. Get Gmail App Password:
   - Go to https://myaccount.google.com/apppasswords
   - Generate app password for "Mail"
   - Store it securely

3. Set environment variable:
   ```bash
   echo 'export SMTP_PASSWORD="your-app-password"' >> ~/.zshrc
   source ~/.zshrc
   ```

4. Test:
   ```bash
   uv run python send_weekly_email.py
   ```

### Option B: macOS Mail Command (Plain text)

**Pros:**
- No authentication needed
- Simple setup
- Uses system mail

**Setup:**
1. Edit `send_weekly_report.sh`:
   ```bash
   RECIPIENT_EMAIL="your.email@example.com"
   ```

2. Make executable:
   ```bash
   chmod +x send_weekly_report.sh
   ```

3. Test:
   ```bash
   ./send_weekly_report.sh
   ```

### Option C: Custom SMTP Server

**For other email providers (Outlook, Yahoo, etc.):**

Edit `send_weekly_email.py`:
```python
SMTP_HOST = "smtp.office365.com"  # For Outlook
SMTP_PORT = 587
SMTP_USERNAME = "your.email@outlook.com"
SMTP_PASSWORD = "your-password"
USE_AUTH = True
```

Common SMTP settings:
- **Outlook/Office365**: `smtp.office365.com:587`
- **Yahoo**: `smtp.mail.yahoo.com:587`
- **iCloud**: `smtp.mail.me.com:587`

---

## Scheduling Options

### Option 1: launchd (Recommended for macOS)

**Pros:**
- Native macOS scheduler
- Persists across reboots
- Better than cron for user tasks

**Setup:**

1. Edit `com.fantasyhockey.weeklyreport.plist` to match your setup:
   ```xml
   <key>ProgramArguments</key>
   <array>
       <string>/Users/drew/Projects/yahoo-fantasy-hockey/.venv/bin/python</string>
       <string>/Users/drew/Projects/yahoo-fantasy-hockey/send_weekly_email.py</string>
   </array>
   ```

   Or if using shell script:
   ```xml
   <key>ProgramArguments</key>
   <array>
       <string>/bin/bash</string>
       <string>/Users/drew/Projects/yahoo-fantasy-hockey/send_weekly_report.sh</string>
   </array>
   ```

2. Adjust schedule (currently Sunday 8 AM):
   ```xml
   <key>StartCalendarInterval</key>
   <dict>
       <key>Weekday</key>
       <integer>0</integer>  <!-- 0=Sunday, 1=Monday, ..., 6=Saturday -->
       <key>Hour</key>
       <integer>8</integer>  <!-- 24-hour format -->
       <key>Minute</key>
       <integer>0</integer>
   </dict>
   ```

3. Install the launch agent:
   ```bash
   # Copy to LaunchAgents directory
   cp com.fantasyhockey.weeklyreport.plist ~/Library/LaunchAgents/

   # Load it
   launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

   # Verify it's loaded
   launchctl list | grep fantasyhockey
   ```

4. Test it manually (doesn't wait for schedule):
   ```bash
   launchctl start com.fantasyhockey.weeklyreport
   ```

5. Check logs:
   ```bash
   cat .cache/weekly_report_stdout.log
   cat .cache/weekly_report_stderr.log
   ```

**Management commands:**
```bash
# Unload (disable)
launchctl unload ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

# Reload (after making changes)
launchctl unload ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

# Check status
launchctl list | grep fantasyhockey

# Remove completely
launchctl unload ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
rm ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
```

### Option 2: cron (Alternative)

**Setup:**

1. Edit crontab:
   ```bash
   crontab -e
   ```

2. Add entry for Sunday 8 AM:
   ```cron
   # Sunday at 8:00 AM - Fantasy Hockey Weekly Report
   0 8 * * 0 cd /Users/drew/Projects/yahoo-fantasy-hockey && ./send_weekly_report.sh
   ```

   Or for Python version:
   ```cron
   0 8 * * 0 cd /Users/drew/Projects/yahoo-fantasy-hockey && /Users/drew/Projects/yahoo-fantasy-hockey/.venv/bin/python send_weekly_email.py
   ```

3. Verify:
   ```bash
   crontab -l
   ```

**Cron schedule format:**
```
* * * * *
│ │ │ │ │
│ │ │ │ └─ Day of week (0-7, 0=Sunday)
│ │ │ └─── Month (1-12)
│ │ └───── Day of month (1-31)
│ └─────── Hour (0-23)
└───────── Minute (0-59)
```

**Common schedules:**
- `0 8 * * 0` - Sunday 8 AM
- `0 7 * * 0` - Sunday 7 AM
- `30 19 * * 6` - Saturday 7:30 PM (night before)

---

## Environment Variables for Gmail

For security, store your Gmail app password as an environment variable:

**Option A: Per-session (temporary)**
```bash
export SMTP_PASSWORD="your-app-password"
uv run python send_weekly_email.py
```

**Option B: Shell profile (persistent)**
```bash
# Add to ~/.zshrc (or ~/.bash_profile for bash)
echo 'export SMTP_PASSWORD="your-app-password"' >> ~/.zshrc
source ~/.zshrc
```

**Option C: In launchd plist**
```xml
<key>EnvironmentVariables</key>
<dict>
    <key>SMTP_PASSWORD</key>
    <string>your-app-password</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
</dict>
```

---

## Troubleshooting

### Email not sending

**Check 1: Test the script manually**
```bash
cd /Users/drew/Projects/yahoo-fantasy-hockey
uv run python send_weekly_email.py
```

**Check 2: Gmail authentication**
- Make sure you're using an App Password, not your regular password
- Enable 2-factor authentication on your Google account first
- Generate app password at https://myaccount.google.com/apppasswords

**Check 3: SMTP settings**
- Verify `SMTP_HOST` and `SMTP_PORT` are correct for your provider
- Check firewall isn't blocking outbound connections on port 587

### Script not running on schedule

**For launchd:**
```bash
# Check if loaded
launchctl list | grep fantasyhockey

# Check logs
cat .cache/weekly_report_stdout.log
cat .cache/weekly_report_stderr.log

# Test manually
launchctl start com.fantasyhockey.weeklyreport
```

**For cron:**
```bash
# Check if cron entry exists
crontab -l

# Check system logs
tail -f /var/log/system.log | grep cron
```

### Yahoo API authentication failing

**Check 1: Token expiration**
```bash
# Test manually to re-authenticate
uv run python create_bodies_table.py --weekly-summary
```

**Check 2: Token file permissions**
```bash
ls -la .yahoo_tokens.json
# Should be: -rw------- (600)
```

---

## Testing Checklist

Before relying on automation, verify:

- [ ] Email script runs manually: `uv run python send_weekly_email.py`
- [ ] Email arrives with correct formatting
- [ ] Colors are preserved (if using HTML email)
- [ ] Yahoo OAuth tokens persist (check `.yahoo_tokens.json`)
- [ ] Schedule is loaded: `launchctl list | grep fantasyhockey`
- [ ] Logs are being written: `cat .cache/weekly_report_stdout.log`
- [ ] Environment variables are set (if using Gmail)

---

## Recommended Setup

**For best results:**

1. **Use Python email sender** (`send_weekly_email.py`) for HTML formatting
2. **Use Gmail** with App Password for reliability
3. **Use launchd** instead of cron (more reliable on macOS)
4. **Test on Saturday** before relying on Sunday automation
5. **Check logs weekly** for first month to ensure reliability

**Example final setup:**
```bash
# 1. Configure email
nano send_weekly_email.py
# Set RECIPIENT_EMAIL and SMTP_USERNAME

# 2. Set environment variable
echo 'export SMTP_PASSWORD="xxxx-xxxx-xxxx-xxxx"' >> ~/.zshrc
source ~/.zshrc

# 3. Test
uv run python send_weekly_email.py

# 4. Install scheduler
cp com.fantasyhockey.weeklyreport.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist

# 5. Verify
launchctl list | grep fantasyhockey
launchctl start com.fantasyhockey.weeklyreport  # Test run
```

---

## Security Notes

- **Never commit** `.env` files or files containing passwords to git
- Use **App Passwords** for Gmail, never your main password
- Store sensitive credentials in **environment variables** or system keychain
- The `.yahoo_tokens.json` file is already gitignored - keep it that way
- OAuth tokens auto-refresh, so authentication should persist indefinitely

---

## Maintenance

**Weekly:**
- Check email arrived successfully
- Verify report looks correct

**Monthly:**
- Check log files for errors: `cat .cache/weekly_report_*.log`
- Clear old logs if needed: `rm .cache/weekly_report_*.log`

**When updating the script:**
```bash
# Reload launchd after changes
launchctl unload ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
launchctl load ~/Library/LaunchAgents/com.fantasyhockey.weeklyreport.plist
```

---

## Need Help?

Common issues and solutions at: https://github.com/drewtodd/yahoo-fantasy-hockey/issues
