# Changelog

## Version 3.0 - Unified Command & Full Report

### Major Changes 🎉

#### Single Comprehensive Command
**All functionality is now integrated into ONE command: `/background-check`**

Instead of running multiple separate commands, moderators now get a complete, organized report from a single command. This provides:
- Complete background analysis in one view
- CUSA membership automatically checked
- All groups displayed with join dates
- Blacklist check with detailed join information
- Risk assessment based on all factors
- Much faster moderation workflow

### What's Included in the Report

The `/background-check` command now provides:

1. **User Information**
   - Username and display name
   - User ID
   - Profile link

2. **CUSA Membership (Automatic)**
   - ✅ Member status with role and join date
   - ❌ Clear indication if not a member
   - Days since joining CUSA

3. **Account Details**
   - Account creation date
   - Age verification (older than 6 months)
   - Friend count and analysis
   - Total badges earned

4. **Suspicious Accounts**
   - Similar usernames detected
   - User IDs of potential alts

5. **Blacklisted Groups (with join dates)**
   - Group names and IDs
   - When user joined each blacklisted group
   - Days since joining
   - Shows up to 3 detailed, notes if more exist

6. **Other Groups**
   - Up to 5 other groups displayed
   - Role in each group
   - Join dates when available
   - Total group count

7. **Risk Assessment**
   - Risk level (Low/Medium/High)
   - Risk score out of 12
   - Specific factors identified
   - Color-coded embed (green/yellow/red)

### Removed Commands

The following commands have been **consolidated** into `/background-check`:
- ~~`/check-cusa`~~ → Now automatic in every report
- ~~`/quick-check`~~ → Use `/background-check` directly
- ~~`/group-history`~~ → Included in every report

### Technical Improvements

- Single API call workflow for efficiency
- Better error handling and status messages
- Improved embed formatting and organization
- Optimized group join date fetching
- More detailed risk factor reporting

### Migration Guide

If upgrading from v2.x:
- Simply run `/background-check <user_id>` to get everything
- No need to run multiple commands anymore
- All information now in one comprehensive report
- `/reload-blacklist` command still available

### Example Output

```
📋 COMPREHENSIVE BACKGROUND REPORT
User: TestUser (DisplayName)
ID: 123456789

🔗 Profile Link
[View Roblox Profile]

🎖️ CUSA United States Military
✅ MEMBER
Role: Private
Joined: February 1, 2024 (10 days ago)

📅 Account Age                 👫 Friends                    🏆 Badges
Created: 2023-08-15            Total Friends: 8              Total: 45
Older than 6 months: ✅ Yes    Less than 15: ❌ Yes

👥 Suspicious Similar Accounts
• TestUser123 (ID: 111222333)
• TestUser456 (ID: 444555666)

🚫 Blacklisted Groups (2 found)
🚫 Scam Group
ID: 12345678 | Joined: Jan 15, 2024 (27 days ago)

🚫 Bad Group
ID: 87654321 | Joined: Feb 5, 2024 (6 days ago)

📊 Other Groups (Total: 3)
• Game Group
  Role: Member | Joined: Dec 1, 2023 (72d ago)

⚠️ RISK ASSESSMENT
Level: 🔴 HIGH RISK
Score: 9/12

Factors:
• Similar usernames detected
• Member of 2 blacklisted group(s)
• Low friend count
```

---

## Version 2.1 - CUSA Membership Check

### Features
- Added `/check-cusa` command for CUSA-specific checks
- Shows role and join date for CUSA members
- Clear indication when user is not in CUSA

---

## Version 2.0 - Group Join Date Tracking

### Features
- Group join dates displayed for blacklisted groups
- New `/group-history` command for full group timeline
- Enhanced blacklist display with dates
- Shows "days since joining" calculation

---

## Version 1.0 - Initial Release

### Features
- `/background-check` command
- `/quick-check` command by username
- `/reload-blacklist` command
- Suspicious alt detection
- Blacklist checking
- Friend count analysis
- Account age verification
- Badge counting
- Risk assessment system
