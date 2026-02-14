import discord
from discord.ext import commands
from discord import app_commands
import requests
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

ROBLOX_USER_API        = "https://users.roblox.com/v1/users/{}"
ROBLOX_FRIENDS_API     = "https://friends.roblox.com/v1/users/{}/friends"
ROBLOX_GROUPS_API      = "https://groups.roblox.com/v2/users/{}/groups/roles"
ROBLOX_BADGES_API      = "https://badges.roblox.com/v1/users/{}/badges"
ROBLOX_USERNAME_SEARCH = "https://users.roblox.com/v1/users/search?keyword={}&limit=100"
ROBLOX_PROFILE_URL     = "https://www.roblox.com/users/{}/profile"

BLACKLIST_DOC_URL = "https://docs.google.com/document/d/1vzYg0-zXWNLPXdd8KJVOzKsfdL5MV2CC9IX47JblvB0/export?format=txt"

# Google Sheets blacklist — exported as CSV (sheet must be set to "Anyone with link can view")
BLACKLIST_SHEET_ID  = "1w-wsgtVdPsVotwvkk-v6jR0ZO673j4zgxmjV4mGymIs"
BLACKLIST_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{BLACKLIST_SHEET_ID}/export?format=csv"

CUSA_GROUP_ID   = "4219097"
CUSA_GROUP_NAME = "CUSA United States Military"


class RobloxChecker:
    def __init__(self):
        self.blacklisted_groups          = []
        self.sheet_blacklist_by_username = {}
        self.sheet_blacklist_by_id       = {}

    async def fetch_blacklist(self):
        try:
            response = requests.get(BLACKLIST_DOC_URL, timeout=10)
            if response.status_code == 200:
                group_ids = re.findall(r'\b(\d{6,})\b', response.text)
                self.blacklisted_groups = list(set(group_ids))
                print(f"Loaded {len(self.blacklisted_groups)} blacklisted groups")
                return True
            return False
        except Exception as e:
            print(f"Error fetching blacklist: {e}")
            return False

    async def fetch_sheet_blacklist(self):
        """Fetch and parse the Google Sheets blacklist using exact column positions.
        
        Sheet layout (1-indexed columns):
          B (index 1)  = Username / Name
          D (index 3)  = Roblox User ID
          H/I (index 7) = Ban length (merged cells)
          K (index 10) = Appealable
        """
        try:
            response = requests.get(BLACKLIST_SHEET_URL, timeout=10)
            if response.status_code != 200:
                print(f"Sheet blacklist fetch failed: HTTP {response.status_code}")
                return False

            import csv, io
            reader = csv.reader(io.StringIO(response.text))
            rows   = list(reader)

            if not rows:
                print("Sheet blacklist is empty.")
                return False

            self.sheet_blacklist_by_username = {}
            self.sheet_blacklist_by_id       = {}

            # Skip header row(s) — skip any row where column D isn't a number
            for row in rows[1:]:
                # Pad short rows so index access never throws
                while len(row) < 11:
                    row.append('')

                name      = row[1].strip()   # Column B
                uid       = row[3].strip()   # Column D
                length    = row[7].strip()   # Column H (merged H/I)
                appealable = row[10].strip() # Column K

                # Skip blank/header rows
                if not uid or not uid.isdigit():
                    continue

                entry = {
                    'username':   name,
                    'user_id':    uid,
                    'length':     length or 'Not specified',
                    'appealable': appealable or 'Not specified',
                }

                if name:
                    self.sheet_blacklist_by_username[name.lower()] = entry
                self.sheet_blacklist_by_id[uid] = entry

            total = len(self.sheet_blacklist_by_id)
            print(f"Loaded {total} entries from sheet blacklist")
            return True

        except Exception as e:
            print(f"Error fetching sheet blacklist: {e}")
            return False

    def check_sheet_blacklist(self, username: str, user_id: int) -> Optional[Dict]:
        """Return the blacklist entry if user is found by ID or username, else None."""
        return (
            self.sheet_blacklist_by_id.get(str(user_id)) or
            self.sheet_blacklist_by_username.get(username.lower())
        )

    def format_sheet_entry(self, entry: Dict) -> str:
        """Format a sheet entry for display in the embed."""
        appealable = entry.get('appealable', 'Not specified')
        length     = entry.get('length', 'Not specified')

        # Normalise common appealable values
        appeal_lower = appealable.lower()
        if appeal_lower in ('yes', 'y', 'true'):
            appeal_display = '✅ Yes'
        elif appeal_lower in ('no', 'n', 'false'):
            appeal_display = '❌ No'
        else:
            appeal_display = appealable or 'Not specified'

        return (
            f"**Length:** {length}\n"
            f"**Appealable:** {appeal_display}"
        )

    def get_user_info(self, user_id: int) -> Optional[Dict]:
        try:
            r = requests.get(ROBLOX_USER_API.format(user_id))
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching user info: {e}")
            return None

    def get_friends(self, user_id: int) -> Optional[List]:
        try:
            r = requests.get(ROBLOX_FRIENDS_API.format(user_id))
            return r.json().get('data', []) if r.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching friends: {e}")
            return None

    def get_user_groups(self, user_id: int) -> Optional[List[Dict]]:
        try:
            r = requests.get(ROBLOX_GROUPS_API.format(user_id))
            if r.status_code == 200:
                return [
                    {
                        'id':   str(g['group']['id']),
                        'name': g['group']['name'],
                        'role': g['role']['name']
                    }
                    for g in r.json().get('data', [])
                ]
            return None
        except Exception as e:
            print(f"Error fetching groups: {e}")
            return None

    def get_badges_count(self, user_id: int) -> Optional[int]:
        try:
            r = requests.get(ROBLOX_BADGES_API.format(user_id))
            return len(r.json().get('data', [])) if r.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching badges: {e}")
            return None

    def get_account_age_months(self, created_date: str) -> Optional[float]:
        try:
            created = datetime.strptime(created_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            delta = datetime.now() - created
            return delta.days / 30.44  # average days per month
        except Exception as e:
            print(f"Error calculating account age: {e}")
            return None

    def get_group_join_date(self, group_id: str, user_id: int) -> Optional[str]:
        try:
            url = f"https://groups.roblox.com/v1/groups/{group_id}/users?limit=100"
            r = requests.get(url)
            if r.status_code == 200:
                for member in r.json().get('data', []):
                    if member.get('userId') == user_id:
                        return member.get('joinedDate') or member.get('created')
            return None
        except Exception as e:
            print(f"Error fetching group join date: {e}")
            return None

    def get_join_date_months_ago(self, join_date_str: str) -> Optional[float]:
        try:
            parsed = datetime.strptime(join_date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            return (datetime.now() - parsed).days / 30.44
        except:
            return None

    def find_similar_usernames(self, username: str, user_id: int) -> List[Dict]:
        """Find similar usernames, excluding the account being checked."""
        try:
            r = requests.get(ROBLOX_USERNAME_SEARCH.format(username))
            if r.status_code != 200:
                return []

            username_lower = username.lower()
            similar = []

            for user in r.json().get('data', []):
                # Skip the account we're checking
                if user.get('id') == user_id:
                    continue

                other = user.get('name', '').lower()
                if (username_lower in other or
                        other in username_lower or
                        self._similarity(username_lower, other) > 0.6):
                    similar.append(user)

            return similar
        except Exception as e:
            print(f"Error searching usernames: {e}")
            return []

    def _similarity(self, a: str, b: str) -> float:
        ca = re.sub(r'[^a-z]', '', a)
        cb = re.sub(r'[^a-z]', '', b)
        if not ca or not cb:
            return 0.0
        common = sum(1 for c in ca if c in cb)
        return common / max(len(ca), len(cb))

    def check_blacklisted_groups(self, user_groups: List[Dict]) -> List[Dict]:
        return [g for g in user_groups if g['id'] in self.blacklisted_groups]


checker = RobloxChecker()


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await checker.fetch_blacklist()
    await checker.fetch_sheet_blacklist()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")


@bot.tree.command(name="background-check", description="Run a full background check on a Roblox user")
@app_commands.describe(user_id="The Roblox user ID to check")
async def background_check(interaction: discord.Interaction, user_id: int):
    await interaction.response.defer()

    try:
        # ── Fetch all data ────────────────────────────────────────────────────
        user_info = checker.get_user_info(user_id)
        if not user_info:
            await interaction.followup.send(f"❌ Could not find a Roblox user with ID `{user_id}`.")
            return

        username     = user_info.get('name', 'Unknown')
        created_date = user_info.get('created', '')
        profile_url  = ROBLOX_PROFILE_URL.format(user_id)

        friends      = checker.get_friends(user_id)
        user_groups  = checker.get_user_groups(user_id) or []
        age_months   = checker.get_account_age_months(created_date)
        similar_users = checker.find_similar_usernames(username, user_id)
        blacklisted  = checker.check_blacklisted_groups(user_groups)
        sheet_entry  = checker.check_sheet_blacklist(username, user_id)

        # CUSA check
        cusa_membership  = next((g for g in user_groups if g['id'] == CUSA_GROUP_ID), None)
        cusa_months_in   = None
        if cusa_membership:
            cusa_join_date = checker.get_group_join_date(CUSA_GROUP_ID, user_id)
            if cusa_join_date:
                cusa_months_in = checker.get_join_date_months_ago(cusa_join_date)

        friends_count = len(friends) if friends is not None else None

        # ── Evaluate each field ───────────────────────────────────────────────

        # Suspicious alts
        if similar_users:
            alt_lines = [
                f"[{u.get('name')}]({ROBLOX_PROFILE_URL.format(u.get('id'))})"
                for u in similar_users[:5]
            ]
            alts_value = ", ".join(alt_lines)
            if len(similar_users) > 5:
                alts_value += f" (+{len(similar_users) - 5} more)"
        else:
            alts_value = "None"

        # Blacklisted — groups doc
        if blacklisted:
            blacklist_value = ", ".join(g['name'] for g in blacklisted[:3])
            if len(blacklisted) > 3:
                blacklist_value += f" (+{len(blacklisted) - 3} more)"
        else:
            blacklist_value = "No"

        # Blacklisted — sheet database
        if sheet_entry:
            sheet_display = checker.format_sheet_entry(sheet_entry)
            sheet_name    = sheet_entry.get('username', username)
            sheet_value   = f"⚠️ **Yes — {sheet_name}**\n{sheet_display}"
        else:
            sheet_value = "No"

        # Affiliations (total group count, minimal)
        affil_count   = len(user_groups)
        affil_value   = f"{affil_count} group(s)" if affil_count else "None"

        # Friends ≥ 15
        if friends_count is None:
            friends_value = "Unknown"
        elif friends_count >= 15:
            friends_value = f"Yes ({friends_count})"
        else:
            friends_value = f"No ({friends_count})"

        # Account age 6+ months
        if age_months is None:
            age_value = "Unknown"
        elif age_months >= 6:
            age_value = f"Yes ({int(age_months)} months)"
        else:
            age_value = f"No ({int(age_months)} months)"

        # CUSA 3+ months
        if not cusa_membership:
            cusa_value = "Not a member"
        elif cusa_months_in is None:
            cusa_value = "Member (join date unavailable)"
        elif cusa_months_in >= 3:
            cusa_value = f"Yes ({int(cusa_months_in)} months)"
        else:
            cusa_value = f"No ({int(cusa_months_in)} months)"

        # ── Factors & Result ─────────────────────────────────────────────────
        factors = []

        if similar_users:
            factors.append(f"Suspicious alts detected ({len(similar_users)})")
        if blacklisted:
            factors.append(f"In {len(blacklisted)} blacklisted group(s)")
        if sheet_entry:
            factors.append("Found in blacklist database")
        if friends_count is not None and friends_count < 15:
            factors.append(f"Low friend count ({friends_count})")
        if age_months is not None and age_months < 6:
            factors.append(f"Account under 6 months ({int(age_months)} months old)")
        if cusa_membership and cusa_months_in is not None and cusa_months_in < 3:
            factors.append(f"In CUSA for less than 3 months ({int(cusa_months_in)} months)")

        # Hard fail conditions
        hard_fail = bool(blacklisted) or bool(sheet_entry) or (friends_count is not None and friends_count < 15) or (age_months is not None and age_months < 6)
        result_value = "❌ Failed" if hard_fail else "✅ Passed"
        embed_color  = discord.Color.red() if hard_fail else discord.Color.green()

        # ── Build embed ───────────────────────────────────────────────────────
        embed = discord.Embed(color=embed_color, timestamp=datetime.now())

        embed.add_field(name="Agent",                value=interaction.user.mention, inline=False)
        embed.add_field(name="Target",               value=f"[{username}]({profile_url}) | `{user_id}`", inline=False)
        embed.add_field(name="Suspicious Alts",      value=alts_value,    inline=False)
        embed.add_field(name="Blacklisted (Groups)", value=blacklist_value, inline=False)
        embed.add_field(name="Blacklisted (Database)", value=sheet_value,  inline=False)
        embed.add_field(name="Affiliations",         value=affil_value,   inline=False)
        embed.add_field(name="Friends ≥ 15",         value=friends_value, inline=True)
        embed.add_field(name="Account 6+ months",    value=age_value,     inline=True)
        embed.add_field(name="In CUSA 3+ months",    value=cusa_value,    inline=True)
        embed.add_field(name="BGC Profile",          value=f"[View Profile]({profile_url})", inline=False)

        if factors:
            embed.add_field(name="Factors", value="\n".join(f"• {f}" for f in factors), inline=False)

        embed.add_field(name="Result", value=result_value, inline=False)

        embed.set_footer(text=f"Roblox ID: {user_id}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")
        print(f"Error in background check: {e}")


@bot.tree.command(name="reload-blacklist", description="Reload the blacklisted groups and database from their sources")
async def reload_blacklist(interaction: discord.Interaction):
    await interaction.response.defer()
    doc_ok   = await checker.fetch_blacklist()
    sheet_ok = await checker.fetch_sheet_blacklist()

    lines = []
    lines.append(f"{'✅' if doc_ok   else '❌'} Group blacklist — {len(checker.blacklisted_groups)} groups loaded")
    sheet_total = max(len(checker.sheet_blacklist_by_id), len(checker.sheet_blacklist_by_username))
    lines.append(f"{'✅' if sheet_ok else '❌'} Sheet blacklist — {sheet_total} entries loaded")

    if not sheet_ok:
        lines.append("\n⚠️ Sheet may not be publicly accessible. Set it to **Anyone with the link → Viewer** in Google Sheets.")

    await interaction.followup.send("\n".join(lines))


if __name__ == "__main__":
    TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("\n⚠️  Replace YOUR_DISCORD_BOT_TOKEN_HERE with your actual token.")
        print("    Get your token from: https://discord.com/developers/applications\n")
    else:
        bot.run(TOKEN)