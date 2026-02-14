# Roblox Background Check Discord Bot

A comprehensive Discord bot that performs complete background checks on Roblox users with a single command, providing a full report including CUSA membership, suspicious alts, blacklisted groups, account age, friends count, and more.

## Features

- 📋 **Single Unified Command**: One command does everything - complete background report
- 🎖️ **CUSA Membership Check**: Automatically checks if users are in CUSA United States Military with join date
- 👥 **Suspicious Alt Detection**: Finds accounts with similar usernames
- 🚫 **Blacklist Checking**: Verifies membership in blacklisted groups with join dates
- 📊 **Full Group History**: Shows all groups (up to 5 other groups displayed)
- 👫 **Friend Count Analysis**: Checks if user has less than 15 friends
- 📅 **Account Age Verification**: Determines if account is older than 6 months
- 🏆 **Badge Count**: Shows total number of badges earned
- ⚠️ **Risk Assessment**: Automated risk scoring (Low/Medium/High) based on multiple factors
- 🔗 **Profile Links**: Direct links to Roblox profiles

## Commands

### `/background-check <user_id>`
**The ONLY command you need!** Performs a comprehensive background check and outputs a full report.

**Example:**
```
/background-check 123456789
```

**Returns a complete report with:**
- 🔗 Profile link
- 🎖️ **CUSA Membership Status**
  - If member: Role, join date, days since joining
  - If not member: Clearly states not in CUSA
- 📅 Account age and creation date
- 👫 Friend count
- 🏆 Badge count
- 👥 List of suspicious similar accounts
- 🚫 **Blacklisted groups with join dates**
  - Group name, ID, and when they joined
  - Shows up to 3 with details
- 📊 **Other groups** (up to 5 displayed)
  - Group name, role, and join dates
- ⚠️ **Risk Assessment**
  - Risk level (Low/Medium/High)
  - Risk score out of 12
  - Specific risk factors identified

### `/reload-blacklist`
Reloads the blacklisted groups from the Google Document.

## What's New in v3.0

### Unified Command Approach
All functionality is now integrated into a single `/background-check` command that provides a comprehensive report. This means:
- No need to run multiple commands
- All information in one organized report
- Faster workflow for moderators
- Consistent output format
- CUSA membership automatically checked for everyone

## Installation & Setup

See the full README in the files for detailed setup instructions.

Quick start:
1. Install dependencies: `pip install -r requirements.txt`
2. Get bot token from Discord Developer Portal
3. Add token to code or .env file
4. Run: `python roblox_checker_bot.py`
