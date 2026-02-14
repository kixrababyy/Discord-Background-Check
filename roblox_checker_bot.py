import discord
from discord.ext import commands
from discord import app_commands
import requests
import re
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ── Roblox API endpoints ───────────────────────────────────────────────────────
ROBLOX_USER_API        = "https://users.roblox.com/v1/users/{}"
ROBLOX_FRIENDS_API     = "https://friends.roblox.com/v1/users/{}/friends"
ROBLOX_GROUPS_API      = "https://groups.roblox.com/v2/users/{}/groups/roles"
ROBLOX_BADGES_API      = "https://badges.roblox.com/v1/users/{}/badges"
ROBLOX_USERNAME_SEARCH = "https://users.roblox.com/v1/users/search?keyword={}&limit=100"
ROBLOX_PROFILE_URL     = "https://www.roblox.com/users/{}/profile"

# ── Blacklist sources ──────────────────────────────────────────────────────────

# Google Doc — group ID blacklist
BLACKLIST_DOC_URL = "https://docs.google.com/document/d/1vzYg0-zXWNLPXdd8KJVOzKsfdL5MV2CC9IX47JblvB0/export?format=txt"

# [DHS] Blacklist Database
# Columns: B=Name, D=User ID, H/I=Length, K=Appealable
DHS_SHEET_ID  = "1w-wsgtVdPsVotwvkk-v6jR0ZO673j4zgxmjV4mGymIs"
DHS_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{DHS_SHEET_ID}/export?format=csv"

# [CUSA] House of Representatives Blacklist Database
# Columns: A=Length, C=Name, D=User ID, E=Appealable, G=Reason
HOR_SHEET_ID  = "1KRR1b92q2-NgCt9DJ7L_un0E5x1v9I5YwoE1Zc_elRg"
HOR_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{HOR_SHEET_ID}/export?format=csv"

# [CUSA] Senate Blacklist Database
# Columns: A=Length, C=Name, D=User ID, E=Appealable, G=Reason
SENATE_SHEET_ID  = "1bhCQLx3J3pXjVA1HVxurRSacukVF00w8XBbwib4qB5k"
SENATE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SENATE_SHEET_ID}/export?format=csv"

# Google Sheets API key — needed to detect strikethrough formatting in DHS sheet
# Get one free at: https://console.cloud.google.com → Enable Sheets API → Create API key
GOOGLE_API_KEY = ""  # Optional: add your Google API key here for strikethrough detection

# ── CUSA group ─────────────────────────────────────────────────────────────────
CUSA_GROUP_ID   = "4219097"
CUSA_GROUP_NAME = "CUSA United States Military"


# ── Helper to normalise appealable values ──────────────────────────────────────
def fmt_appealable(value: str) -> str:
    v = value.strip().lower().rstrip('.')
    if v in ('yes', 'y', 'true', '✓', '✔'):
        return '✅ Yes'
    if v in ('no', 'n', 'false', '✗', '✘', '×', 'x'):
        return '❌ No'
    return value or 'Not specified'


class RobloxChecker:
    def __init__(self):
        self.blacklisted_groups = []

        # DHS database — keyed by user_id (str) and lowercased username
        self.dhs_by_id       = {}
        self.dhs_by_username = {}

        # HoR database — keyed by user_id (str) and lowercased username
        self.hor_by_id       = {}
        self.hor_by_username = {}

        # Senate database — keyed by user_id (str) and lowercased username
        self.senate_by_id       = {}
        self.senate_by_username = {}

    # ── Group doc blacklist ────────────────────────────────────────────────────
    async def fetch_blacklist(self):
        try:
            r = requests.get(BLACKLIST_DOC_URL, timeout=10)
            if r.status_code == 200:
                group_ids = re.findall(r'\b(\d{6,})\b', r.text)
                self.blacklisted_groups = list(set(group_ids))
                print(f"[Groups] Loaded {len(self.blacklisted_groups)} blacklisted groups")
                return True
            return False
        except Exception as e:
            print(f"[Groups] Error: {e}")
            return False

    # ── DHS sheet ──────────────────────────────────────────────────────────────
    async def fetch_dhs(self):
        """
        [DHS] Blacklist Database column layout (0-indexed):
          1  = B = Roblox Name
          3  = D = Roblox User ID
          7  = H = Ban length (merged H/I)
          10 = K = Appealable

        Strikethrough on a row = previously blacklisted, now removed.
        Detected via Google Sheets API v4 if GOOGLE_API_KEY is set,
        otherwise falls back to CSV (all entries treated as active).
        """
        self.dhs_by_id       = {}
        self.dhs_by_username = {}

        if GOOGLE_API_KEY:
            return await self._fetch_dhs_with_formatting()
        else:
            return await self._fetch_dhs_csv()

    async def _fetch_dhs_with_formatting(self):
        """Fetch DHS sheet via Sheets API v4 — detects strikethrough (removed) entries."""
        try:
            fields = "sheets.data.rowData.values(formattedValue,userEnteredFormat.textFormat.strikethrough)"
            url = (
                f"https://sheets.googleapis.com/v4/spreadsheets/{DHS_SHEET_ID}"
                f"?includeGridData=true&fields={fields}&key={GOOGLE_API_KEY}"
            )
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                print(f"[DHS] Sheets API failed (HTTP {r.status_code}), falling back to CSV")
                return await self._fetch_dhs_csv()

            rows = r.json().get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])

            # Skip header row (index 0)
            for row_data in rows[1:]:
                cells = row_data.get('values', [])

                # Pad to at least 11 cells
                while len(cells) < 11:
                    cells.append({})

                def cell_val(c):
                    return c.get('formattedValue', '').strip()

                def is_strikethrough(c):
                    return c.get('userEnteredFormat', {}).get('textFormat', {}).get('strikethrough', False)

                name       = cell_val(cells[1])   # B
                uid        = cell_val(cells[3])   # D
                length     = cell_val(cells[7])   # H
                appealable = cell_val(cells[10])  # K

                if not uid or not uid.isdigit():
                    continue

                # Row is removed if the name OR uid cell has strikethrough
                removed = is_strikethrough(cells[1]) or is_strikethrough(cells[3])

                entry = {
                    'source':     'DHS Database',
                    'username':   name,
                    'user_id':    uid,
                    'length':     length     or 'Not specified',
                    'appealable': appealable or 'Not specified',
                    'removed':    removed,
                }

                self.dhs_by_id[uid] = entry
                if name:
                    self.dhs_by_username[name.lower()] = entry

            active  = sum(1 for e in self.dhs_by_id.values() if not e['removed'])
            removed = sum(1 for e in self.dhs_by_id.values() if e['removed'])
            print(f"[DHS] Loaded {len(self.dhs_by_id)} entries ({active} active, {removed} removed)")
            return True

        except Exception as e:
            print(f"[DHS] Sheets API error: {e}, falling back to CSV")
            return await self._fetch_dhs_csv()

    async def _fetch_dhs_csv(self):
        """Fallback: fetch DHS sheet as CSV — cannot detect strikethrough."""
        try:
            r = requests.get(DHS_SHEET_URL, timeout=10)
            if r.status_code != 200:
                print(f"[DHS] CSV fetch failed: HTTP {r.status_code}")
                return False

            reader = csv.reader(io.StringIO(r.text))
            for row in list(reader)[1:]:
                while len(row) < 11:
                    row.append('')

                name       = row[1].strip()
                uid        = row[3].strip()
                length     = row[7].strip()
                appealable = row[10].strip()

                if not uid or not uid.isdigit():
                    continue

                entry = {
                    'source':     'DHS Database',
                    'username':   name,
                    'user_id':    uid,
                    'length':     length     or 'Not specified',
                    'appealable': appealable or 'Not specified',
                    'removed':    False,  # unknown without API key
                }

                self.dhs_by_id[uid] = entry
                if name:
                    self.dhs_by_username[name.lower()] = entry

            print(f"[DHS] Loaded {len(self.dhs_by_id)} entries (strikethrough detection disabled — no API key)")
            return True
        except Exception as e:
            print(f"[DHS] CSV error: {e}")
            return False

    # ── HoR sheet ──────────────────────────────────────────────────────────────
    async def fetch_hor(self):
        """
        [CUSA] HoR Blacklist Database column layout (0-indexed):
          0 = A = Expiration (ban length)
          2 = C = Roblox Username
          3 = D = Roblox ID
          4 = E = Appealable
          6 = G = Reason

        Row layout:
          Row 0 = Title
          Row 1 = Blank
          Row 2 = Headers
          Row 3 = Blank
          Row 4+ = Data
        """
        try:
            r = requests.get(HOR_SHEET_URL, timeout=10)
            if r.status_code != 200:
                print(f"[HoR] Fetch failed: HTTP {r.status_code}")
                return False

            self.hor_by_id       = {}
            self.hor_by_username = {}

            reader = csv.reader(io.StringIO(r.text))
            rows   = list(reader)

            # Skip first 4 rows (title, blank, headers, blank)
            for row in rows[4:]:
                while len(row) < 7:
                    row.append('')

                length     = row[0].strip()   # A - Expiration
                name       = row[2].strip()   # C - Roblox Username
                uid        = row[3].strip()   # D - Roblox ID
                appealable = row[4].strip()   # E - Appealable
                reason     = row[6].strip()   # G - Reason

                if not uid or not uid.isdigit():
                    continue

                entry = {
                    'source':     'HoR Database',
                    'username':   name,
                    'user_id':    uid,
                    'length':     length     or 'Not specified',
                    'appealable': appealable or 'Not specified',
                    'reason':     reason     or 'Not specified',
                }

                self.hor_by_id[uid] = entry
                if name:
                    self.hor_by_username[name.lower()] = entry

            print(f"[HoR] Loaded {len(self.hor_by_id)} entries")
            return True
        except Exception as e:
            print(f"[HoR] Error: {e}")
            return False

    # ── Senate sheet ───────────────────────────────────────────────────────────
    async def fetch_senate(self):
        """
        [CUSA] Senate Blacklist Database column layout (0-indexed):
          0 = A = Expiration (ban length)
          2 = C = Roblox Username
          3 = D = Roblox ID
          4 = E = Appealable
          6 = G = Reason

        Row layout:
          Row 0 = Title
          Row 1 = Blank
          Row 2 = Headers
          Row 3 = Blank
          Row 4+ = Data
        """
        try:
            r = requests.get(SENATE_SHEET_URL, timeout=10)
            if r.status_code != 200:
                print(f"[Senate] Fetch failed: HTTP {r.status_code}")
                return False

            self.senate_by_id       = {}
            self.senate_by_username = {}

            reader = csv.reader(io.StringIO(r.text))
            rows   = list(reader)

            for row in rows[4:]:
                while len(row) < 7:
                    row.append('')

                length     = row[0].strip()   # A - Expiration
                name       = row[2].strip()   # C - Roblox Username
                uid        = row[3].strip()   # D - Roblox ID
                appealable = row[4].strip()   # E - Appealable
                reason     = row[6].strip()   # G - Reason

                if not uid or not uid.isdigit():
                    continue

                entry = {
                    'source':     'Senate Database',
                    'username':   name,
                    'user_id':    uid,
                    'length':     length     or 'Not specified',
                    'appealable': appealable or 'Not specified',
                    'reason':     reason     or 'Not specified',
                }

                self.senate_by_id[uid] = entry
                if name:
                    self.senate_by_username[name.lower()] = entry

            print(f"[Senate] Loaded {len(self.senate_by_id)} entries")
            return True
        except Exception as e:
            print(f"[Senate] Error: {e}")
            return False

    # ── Lookup helpers ─────────────────────────────────────────────────────────
    def check_dhs(self, username: str, user_id: int) -> Optional[Dict]:
        return (
            self.dhs_by_id.get(str(user_id)) or
            self.dhs_by_username.get(username.lower())
        )

    def check_hor(self, username: str, user_id: int) -> Optional[Dict]:
        return (
            self.hor_by_id.get(str(user_id)) or
            self.hor_by_username.get(username.lower())
        )

    def check_senate(self, username: str, user_id: int) -> Optional[Dict]:
        return (
            self.senate_by_id.get(str(user_id)) or
            self.senate_by_username.get(username.lower())
        )

    def format_entry(self, entry: Dict) -> str:
        """Format a database entry for display in the embed."""
        lines = []
        if entry.get('length'):
            lines.append(f"**Length:** {entry['length']}")
        if entry.get('reason'):
            lines.append(f"**Reason:** {entry['reason']}")
        if entry.get('appealable'):
            lines.append(f"**Appealable:** {fmt_appealable(entry['appealable'])}")
        return "\n".join(lines) if lines else "Listed (no details)"

    # ── Roblox API methods ─────────────────────────────────────────────────────
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        try:
            r = requests.get(ROBLOX_USER_API.format(user_id))
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching user info: {e}")
            return None

    def resolve_user(self, query: str) -> Optional[Dict]:
        """Resolve a query (numeric ID, @username, or display name) to a user info dict."""
        query = query.strip().lstrip('@')

        # ── Try numeric ID first ───────────────────────────────────────────────
        if query.isdigit():
            info = self.get_user_info(int(query))
            if info and not info.get('errors'):
                return info

        # ── Try exact username match (POST endpoint) ───────────────────────────
        try:
            r = requests.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [query], "excludeBannedUsers": False},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json().get('data', [])
                if data:
                    return self.get_user_info(data[0]['id'])
        except Exception as e:
            print(f"Error resolving by username: {e}")

        # ── Fall back to keyword search (catches display names) ────────────────
        try:
            r = requests.get(ROBLOX_USERNAME_SEARCH.format(requests.utils.quote(query)), timeout=10)
            if r.status_code == 200:
                results = r.json().get('data', [])
                if results:
                    return self.get_user_info(results[0]['id'])
        except Exception as e:
            print(f"Error resolving by display name search: {e}")

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

    def get_account_age_months(self, created_date: str) -> Optional[float]:
        try:
            created = datetime.strptime(created_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            return (datetime.now() - created).days / 30.44
        except Exception as e:
            print(f"Error calculating account age: {e}")
            return None

    def find_similar_usernames(self, username: str, user_id: int) -> List[Dict]:
        try:
            r = requests.get(ROBLOX_USERNAME_SEARCH.format(username))
            if r.status_code != 200:
                return []
            username_lower = username.lower()
            similar = []
            for user in r.json().get('data', []):
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
        return sum(1 for c in ca if c in cb) / max(len(ca), len(cb))

    def get_group_join_date(self, group_id: str, user_id: int) -> Optional[str]:
        try:
            r = requests.get(f"https://groups.roblox.com/v1/groups/{group_id}/users?limit=100")
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

    def check_blacklisted_groups(self, user_groups: List[Dict]) -> List[Dict]:
        return [g for g in user_groups if g['id'] in self.blacklisted_groups]


checker = RobloxChecker()


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await checker.fetch_blacklist()
    await checker.fetch_dhs()
    await checker.fetch_hor()
    await checker.fetch_senate()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")


@bot.tree.command(name="background-check", description="Run a full background check on a Roblox user")
@app_commands.describe(user="Roblox user ID, username, or display name")
async def background_check(interaction: discord.Interaction, user: str):
    await interaction.response.defer()

    try:
        # ── Resolve the user ───────────────────────────────────────────────────
        user_info = checker.resolve_user(user)
        if not user_info or user_info.get('errors'):
            await interaction.followup.send(f"❌ Could not find a Roblox user matching `{user}`.")
            return

        # name = @username (the unique login name), displayName = in-game display name
        username     = user_info.get('name', 'Unknown')        # @username — used for all checks
        display_name = user_info.get('displayName', username)  # display name — shown as extra info
        user_id      = user_info.get('id')
        created_date = user_info.get('created', '')
        profile_url  = ROBLOX_PROFILE_URL.format(user_id)

        friends       = checker.get_friends(user_id)
        user_groups   = checker.get_user_groups(user_id) or []
        age_months    = checker.get_account_age_months(created_date)
        similar_users = checker.find_similar_usernames(username, user_id)
        blacklisted   = checker.check_blacklisted_groups(user_groups)
        dhs_entry     = checker.check_dhs(username, user_id)
        hor_entry     = checker.check_hor(username, user_id)
        senate_entry  = checker.check_senate(username, user_id)

        # CUSA check
        cusa_membership = next((g for g in user_groups if g['id'] == CUSA_GROUP_ID), None)
        cusa_months_in  = None
        if cusa_membership:
            cusa_join_date = checker.get_group_join_date(CUSA_GROUP_ID, user_id)
            if cusa_join_date:
                cusa_months_in = checker.get_join_date_months_ago(cusa_join_date)

        friends_count = len(friends) if friends is not None else None

        # ── Format each field ──────────────────────────────────────────────────

        # Suspicious alts
        if similar_users:
            alt_lines  = [
                f"[{u.get('name')}]({ROBLOX_PROFILE_URL.format(u.get('id'))})"
                for u in similar_users[:5]
            ]
            alts_value = ", ".join(alt_lines)
            if len(similar_users) > 5:
                alts_value += f" (+{len(similar_users) - 5} more)"
        else:
            alts_value = "None"

        # Blacklisted groups (doc)
        if blacklisted:
            blacklist_value = ", ".join(g['name'] for g in blacklisted[:3])
            if len(blacklisted) > 3:
                blacklist_value += f" (+{len(blacklisted) - 3} more)"
        else:
            blacklist_value = "No"

        # DHS database
        if dhs_entry:
            dhs_name = dhs_entry.get('username', username)
            if dhs_entry.get('removed'):
                dhs_value = f"ℹ️ **Previously blacklisted (removed) — {dhs_name}**\n{checker.format_entry(dhs_entry)}"
            else:
                dhs_value = f"⚠️ **Yes — {dhs_name}**\n{checker.format_entry(dhs_entry)}"
        else:
            dhs_value = "No"

        # HoR database
        if hor_entry:
            hor_name  = hor_entry.get('username', username)
            hor_value = f"⚠️ **Yes — {hor_name}**\n{checker.format_entry(hor_entry)}"
        else:
            hor_value = "No"

        # Senate database
        if senate_entry:
            senate_name  = senate_entry.get('username', username)
            senate_value = f"⚠️ **Yes — {senate_name}**\n{checker.format_entry(senate_entry)}"
        else:
            senate_value = "No"

        # Affiliations
        affil_value = f"{len(user_groups)} group(s)" if user_groups else "None"

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

        # ── Factors & result ───────────────────────────────────────────────────
        factors = []

        if similar_users:
            factors.append(f"Suspicious alts detected ({len(similar_users)})")
        if blacklisted:
            factors.append(f"In {len(blacklisted)} blacklisted group(s)")
        if dhs_entry:
            if dhs_entry.get('removed'):
                factors.append("Previously in DHS Database (removed)")
            else:
                factors.append("Found in DHS Database")
        if hor_entry:
            factors.append(f"Found in HoR Database")
        if senate_entry:
            factors.append(f"Found in Senate Database")
        if friends_count is not None and friends_count < 15:
            factors.append(f"Low friend count ({friends_count})")
        if age_months is not None and age_months < 6:
            factors.append(f"Account under 6 months ({int(age_months)} months old)")
        if cusa_membership and cusa_months_in is not None and cusa_months_in < 3:
            factors.append(f"In CUSA less than 3 months ({int(cusa_months_in)} months)")

        dhs_active   = dhs_entry and not dhs_entry.get('removed')
        hard_fail    = bool(blacklisted or dhs_active or hor_entry or senate_entry) or \
                       (friends_count is not None and friends_count < 15) or \
                       (age_months is not None and age_months < 6)
        result_value = "❌ Failed" if hard_fail else "✅ Passed"
        embed_color  = discord.Color.red() if hard_fail else discord.Color.green()

        # ── Build embed ────────────────────────────────────────────────────────
        embed = discord.Embed(color=embed_color, timestamp=datetime.now())

        embed.add_field(name="Agent",                value=interaction.user.mention,                      inline=False)
        embed.add_field(name="Target",               value=f"[{username}]({profile_url}) | `{user_id}`", inline=False)
        embed.add_field(name="Suspicious Alts",      value=alts_value,                                     inline=False)
        embed.add_field(name="Blacklisted (Groups)", value=blacklist_value,                                inline=False)
        embed.add_field(name="Blacklisted (DHS)",    value=dhs_value,                                      inline=False)
        embed.add_field(name="Blacklisted (HoR)",    value=hor_value,                                      inline=False)
        embed.add_field(name="Blacklisted (Senate)", value=senate_value,                                   inline=False)
        embed.add_field(name="Affiliations",         value=affil_value,                                    inline=False)
        embed.add_field(name="Friends ≥ 15",         value=friends_value,                                  inline=True)
        embed.add_field(name="Account 6+ months",    value=age_value,                                      inline=True)
        embed.add_field(name="In CUSA 3+ months",    value=cusa_value,                                     inline=True)
        embed.add_field(name="BGC Profile",          value=f"[View Profile]({profile_url})",               inline=False)

        if factors:
            embed.add_field(name="Factors", value="\n".join(f"• {f}" for f in factors), inline=False)

        embed.add_field(name="Result", value=result_value, inline=False)
        embed.set_footer(text=f"Roblox ID: {user_id}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")
        print(f"Error in background check: {e}")


@bot.tree.command(name="friend-check", description="Scan a user's friends list against all blacklist databases")
@app_commands.describe(user="Roblox user ID, username, or display name")
async def friend_check(interaction: discord.Interaction, user: str):
    await interaction.response.defer()

    try:
        # ── Resolve the user ───────────────────────────────────────────────────
        user_info = checker.resolve_user(user)
        if not user_info or user_info.get('errors'):
            await interaction.followup.send(f"❌ Could not find a Roblox user matching `{user}`.")
            return

        username    = user_info.get('name', 'Unknown')
        user_id     = user_info.get('id')
        profile_url = ROBLOX_PROFILE_URL.format(user_id)

        # ── Fetch friends ──────────────────────────────────────────────────────
        friends = checker.get_friends(user_id)
        if friends is None:
            await interaction.followup.send("❌ Could not fetch friends list.")
            return
        if not friends:
            await interaction.followup.send(f"**{username}** has no friends.")
            return

        # ── Check each friend against all databases ────────────────────────────
        flagged = []

        for friend in friends:
            fid      = friend.get('id')
            fname    = friend.get('name', '').strip()
            # Fallback: if name missing, fetch directly
            if not fname:
                finfo = checker.get_user_info(fid)
                fname = finfo.get('name', str(fid)) if finfo else str(fid)
            fprofile = ROBLOX_PROFILE_URL.format(fid)
            hits     = []

            # Blacklisted groups
            fgroups = checker.get_user_groups(fid) or []
            bl_groups = checker.check_blacklisted_groups(fgroups)
            if bl_groups:
                hits.append(f"Blacklisted group(s): {', '.join(g['name'] for g in bl_groups[:2])}")

            # DHS
            fdhs = checker.check_dhs(fname, fid)
            if fdhs:
                if fdhs.get('removed'):
                    hits.append("DHS Database (removed)")
                else:
                    hits.append("DHS Database")

            # HoR
            if checker.check_hor(fname, fid):
                hits.append("HoR Database")

            # Senate
            if checker.check_senate(fname, fid):
                hits.append("Senate Database")

            if hits:
                flagged.append({
                    'name':    fname,
                    'id':      fid,
                    'profile': fprofile,
                    'hits':    hits,
                })

        # ── Build embed ────────────────────────────────────────────────────────
        total     = len(friends)
        embed_color = discord.Color.red() if flagged else discord.Color.green()
        embed = discord.Embed(
            title=f"Friend Check — {username}",
            color=embed_color,
            timestamp=datetime.now()
        )

        embed.add_field(
            name="Agent",
            value=interaction.user.mention,
            inline=False
        )
        embed.add_field(
            name="Target",
            value=f"[{username}]({profile_url}) | `{user_id}`",
            inline=False
        )
        embed.add_field(
            name="Friends Scanned",
            value=str(total),
            inline=True
        )
        embed.add_field(
            name="Flagged",
            value=str(len(flagged)),
            inline=True
        )

        if flagged:
            # Split into chunks to avoid hitting Discord's 1024 char field limit
            chunk      = []
            chunk_num  = 1
            chunk_len  = 0

            for f in flagged:
                line = f"**[{f['name']}]({f['profile']})** — {', '.join(f['hits'])}\n"
                if chunk_len + len(line) > 950:
                    embed.add_field(
                        name=f"Flagged Friends ({chunk_num})",
                        value="".join(chunk),
                        inline=False
                    )
                    chunk     = []
                    chunk_len = 0
                    chunk_num += 1
                chunk.append(line)
                chunk_len += len(line)

            if chunk:
                embed.add_field(
                    name=f"Flagged Friends{f' ({chunk_num})' if chunk_num > 1 else ''}",
                    value="".join(chunk),
                    inline=False
                )
        else:
            embed.add_field(
                name="Flagged Friends",
                value="None found ✅",
                inline=False
            )

        embed.set_footer(text=f"Roblox ID: {user_id}")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")
        print(f"Error in friend check: {e}")



async def reload_blacklist(interaction: discord.Interaction):
    await interaction.response.defer()

    doc_ok    = await checker.fetch_blacklist()
    dhs_ok    = await checker.fetch_dhs()
    hor_ok    = await checker.fetch_hor()
    senate_ok = await checker.fetch_senate()

    dhs_active  = sum(1 for e in checker.dhs_by_id.values() if not e.get('removed'))
    dhs_removed = sum(1 for e in checker.dhs_by_id.values() if e.get('removed'))
    dhs_detail  = f"{dhs_active} active, {dhs_removed} removed" if GOOGLE_API_KEY else f"{len(checker.dhs_by_id)} entries (no API key — strikethrough detection disabled)"

    lines = [
        f"{'✅' if doc_ok    else '❌'} Group blacklist — {len(checker.blacklisted_groups)} groups",
        f"{'✅' if dhs_ok    else '❌'} DHS Database    — {dhs_detail}",
        f"{'✅' if hor_ok    else '❌'} HoR Database    — {len(checker.hor_by_id)} entries",
        f"{'✅' if senate_ok else '❌'} Senate Database — {len(checker.senate_by_id)} entries",
    ]

    if not all([dhs_ok, hor_ok, senate_ok]):
        lines.append("\n⚠️ A sheet failed to load. Make sure it's set to **Anyone with the link → Viewer**.")

    await interaction.followup.send("\n".join(lines))


if __name__ == "__main__":
    TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"  # ← Replace this

    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("\n⚠️  Replace YOUR_DISCORD_BOT_TOKEN_HERE with your actual token.")
        print("    Get your token from: https://discord.com/developers/applications\n")
    else:
        bot.run(TOKEN)