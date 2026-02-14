import discord
from discord.ext import commands
from discord import app_commands
import requests
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Roblox API endpoints
ROBLOX_USER_API = "https://users.roblox.com/v1/users/{}"
ROBLOX_FRIENDS_API = "https://friends.roblox.com/v1/users/{}/friends"
ROBLOX_GROUPS_API = "https://groups.roblox.com/v2/users/{}/groups/roles"
ROBLOX_BADGES_API = "https://badges.roblox.com/v1/users/{}/badges"
ROBLOX_USERNAME_SEARCH = "https://users.roblox.com/v1/users/search?keyword={}&limit=100"

# Google Doc blacklist URL (can be overridden by environment variable)
BLACKLIST_DOC_URL = os.getenv(
    "BLACKLIST_DOC_URL",
    "https://docs.google.com/document/d/1vzYg0-zXWNLPXdd8KJVOzKsfdL5MV2CC9IX47JblvB0/export?format=txt"
)

# CUSA Group ID
CUSA_GROUP_ID = "4219097"
CUSA_GROUP_NAME = "CUSA United States Military"

class RobloxChecker:
    def __init__(self):
        self.blacklisted_groups = []
        
    async def fetch_blacklist(self):
        """Fetch blacklisted groups from Google Doc"""
        try:
            response = requests.get(BLACKLIST_DOC_URL, timeout=10)
            if response.status_code == 200:
                content = response.text
                group_ids = re.findall(r'\b(\d{6,})\b', content)
                self.blacklisted_groups = list(set(group_ids))
                print(f"Loaded {len(self.blacklisted_groups)} blacklisted groups")
                return True
            return False
        except Exception as e:
            print(f"Error fetching blacklist: {e}")
            return False
    
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Get basic user information"""
        try:
            response = requests.get(ROBLOX_USER_API.format(user_id))
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error fetching user info: {e}")
            return None
    
    def get_friends_count(self, user_id: int) -> Optional[int]:
        """Get number of friends"""
        try:
            response = requests.get(ROBLOX_FRIENDS_API.format(user_id))
            if response.status_code == 200:
                friends = response.json().get('data', [])
                return len(friends)
            return None
        except Exception as e:
            print(f"Error fetching friends: {e}")
            return None
    
    def get_user_groups(self, user_id: int) -> Optional[List[Dict]]:
        """Get user's group IDs and membership info"""
        try:
            response = requests.get(ROBLOX_GROUPS_API.format(user_id))
            if response.status_code == 200:
                data = response.json().get('data', [])
                groups = []
                for group_data in data:
                    group_info = {
                        'id': str(group_data['group']['id']),
                        'name': group_data['group']['name'],
                        'role': group_data['role']['name']
                    }
                    groups.append(group_info)
                return groups
            return None
        except Exception as e:
            print(f"Error fetching groups: {e}")
            return None
    
    def get_badges_count(self, user_id: int) -> Optional[int]:
        """Get number of badges"""
        try:
            response = requests.get(ROBLOX_BADGES_API.format(user_id))
            if response.status_code == 200:
                data = response.json()
                return len(data.get('data', []))
            return None
        except Exception as e:
            print(f"Error fetching badges: {e}")
            return None
    
    def check_account_age(self, created_date: str) -> bool:
        """Check if account is older than 6 months"""
        try:
            created = datetime.strptime(created_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            six_months_ago = datetime.now() - timedelta(days=180)
            return created < six_months_ago
        except Exception as e:
            print(f"Error checking account age: {e}")
            return False
    
    def find_similar_usernames(self, username: str, limit: int = 50) -> List[Dict]:
        """Find users with similar usernames"""
        try:
            response = requests.get(ROBLOX_USERNAME_SEARCH.format(username))
            if response.status_code == 200:
                data = response.json().get('data', [])
                similar = []
                username_lower = username.lower()
                
                for user in data[:limit]:
                    other_username = user.get('name', '').lower()
                    if (username_lower in other_username or 
                        other_username in username_lower or
                        self._username_similarity(username_lower, other_username) > 0.6):
                        similar.append(user)
                
                return similar
            return []
        except Exception as e:
            print(f"Error searching usernames: {e}")
            return []
    
    def _username_similarity(self, name1: str, name2: str) -> float:
        """Calculate basic username similarity"""
        clean1 = re.sub(r'[^a-z]', '', name1)
        clean2 = re.sub(r'[^a-z]', '', name2)
        
        if not clean1 or not clean2:
            return 0.0
        
        common = sum(1 for c in clean1 if c in clean2)
        return common / max(len(clean1), len(clean2))
    
    def get_group_join_date(self, group_id: str, user_id: int) -> Optional[str]:
        """Get when a user joined a specific group"""
        try:
            url = f"https://groups.roblox.com/v1/groups/{group_id}/users?limit=100"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json().get('data', [])
                for member in data:
                    if member.get('userId') == user_id:
                        join_date = member.get('joinedDate') or member.get('created')
                        if join_date:
                            return join_date
            return None
        except Exception as e:
            print(f"Error fetching group join date for group {group_id}: {e}")
            return None
    
    def get_all_group_join_dates(self, user_groups: List[Dict], user_id: int) -> Dict[str, Optional[str]]:
        """Get join dates for all user's groups"""
        join_dates = {}
        for group in user_groups:
            group_id = group['id']
            join_date = self.get_group_join_date(group_id, user_id)
            join_dates[group_id] = join_date
        return join_dates
    
    def check_blacklisted_groups(self, user_groups: List[Dict]) -> List[Dict]:
        """Check if user is in any blacklisted groups"""
        blacklisted = []
        for group in user_groups:
            if group['id'] in self.blacklisted_groups:
                blacklisted.append(group)
        return blacklisted

# Initialize checker
checker = RobloxChecker()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await checker.fetch_blacklist()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.tree.command(name="background-check", description="Comprehensive background check on a Roblox user")
@app_commands.describe(user_id="The Roblox user ID to check")
async def background_check(interaction: discord.Interaction, user_id: int):
    """Perform comprehensive background check with full report"""
    await interaction.response.defer()
    
    try:
        # Send initial status
        status_msg = await interaction.followup.send(f"🔍 **Running comprehensive background check...**\nGathering data, please wait...")
        
        # Get user info
        user_info = checker.get_user_info(user_id)
        if not user_info:
            await interaction.edit_original_response(content=f"❌ Could not find user with ID: {user_id}")
            return
        
        username = user_info.get('name', 'Unknown')
        display_name = user_info.get('displayName', username)
        created_date = user_info.get('created', '')
        
        # Perform all checks
        friends_count = checker.get_friends_count(user_id)
        user_groups = checker.get_user_groups(user_id)
        badges_count = checker.get_badges_count(user_id)
        account_older_than_6m = checker.check_account_age(created_date)
        similar_users = checker.find_similar_usernames(username)
        
        # Check CUSA membership
        cusa_membership = None
        cusa_join_date = None
        if user_groups:
            for group in user_groups:
                if group['id'] == CUSA_GROUP_ID:
                    cusa_membership = group
                    cusa_join_date = checker.get_group_join_date(CUSA_GROUP_ID, user_id)
                    break
        
        # Check blacklisted groups
        blacklisted = []
        blacklist_join_dates = {}
        if user_groups:
            blacklisted = checker.check_blacklisted_groups(user_groups)
            if blacklisted:
                blacklist_join_dates = checker.get_all_group_join_dates(blacklisted, user_id)
        
        # Get all group join dates
        all_group_join_dates = {}
        if user_groups:
            all_group_join_dates = checker.get_all_group_join_dates(user_groups, user_id)
        
        # === BUILD COMPREHENSIVE REPORT ===
        embed = discord.Embed(
            title=f"📋 COMPREHENSIVE BACKGROUND REPORT",
            description=f"**User:** {username} ({display_name})\n**ID:** {user_id}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        profile_url = f"https://www.roblox.com/users/{user_id}/profile"
        embed.add_field(
            name="🔗 Profile Link",
            value=f"[View Roblox Profile]({profile_url})",
            inline=False
        )
        
        # === CUSA MEMBERSHIP CHECK ===
        if cusa_membership:
            cusa_role = cusa_membership['role']
            if cusa_join_date:
                try:
                    parsed_date = datetime.strptime(cusa_join_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                    formatted_date = parsed_date.strftime("%B %d, %Y")
                    days_ago = (datetime.now() - parsed_date).days
                    cusa_info = f"✅ **MEMBER**\nRole: {cusa_role}\nJoined: {formatted_date} ({days_ago} days ago)"
                except:
                    cusa_info = f"✅ **MEMBER**\nRole: {cusa_role}\nJoined: Unknown"
            else:
                cusa_info = f"✅ **MEMBER**\nRole: {cusa_role}\nJoin date unavailable"
        else:
            cusa_info = "❌ **NOT A MEMBER**"
        
        embed.add_field(
            name="🎖️ CUSA United States Military",
            value=cusa_info,
            inline=False
        )
        
        # === ACCOUNT DETAILS ===
        created_formatted = created_date.split('T')[0] if created_date else "Unknown"
        age_status = "✅ Yes" if account_older_than_6m else "❌ No"
        
        account_info = f"**Created:** {created_formatted}\n**Older than 6 months:** {age_status}"
        embed.add_field(
            name="📅 Account Age",
            value=account_info,
            inline=True
        )
        
        # Friends
        friends_status = "❌ Yes" if friends_count is not None and friends_count < 15 else "✅ No"
        friends_info = f"**Total Friends:** {friends_count if friends_count is not None else 'Unknown'}\n**Less than 15:** {friends_status}"
        embed.add_field(
            name="👫 Friends",
            value=friends_info,
            inline=True
        )
        
        # Badges
        embed.add_field(
            name="🏆 Badges",
            value=f"**Total:** {badges_count if badges_count is not None else 'Unknown'}",
            inline=True
        )
        
        # === SUSPICIOUS ALTS ===
        if similar_users:
            alt_usernames = [f"• {u.get('name')} (ID: {u.get('id')})" for u in similar_users[:5]]
            alt_text = "\n".join(alt_usernames)
            if len(similar_users) > 5:
                alt_text += f"\n*...and {len(similar_users) - 5} more similar accounts*"
        else:
            alt_text = "✅ None detected"
        
        embed.add_field(
            name="👥 Suspicious Similar Accounts",
            value=alt_text,
            inline=False
        )
        
        # === BLACKLISTED GROUPS ===
        if blacklisted:
            blacklist_details = []
            for group in blacklisted[:3]:
                group_id = group['id']
                group_name = group['name']
                join_date = blacklist_join_dates.get(group_id)
                
                if join_date:
                    try:
                        parsed_date = datetime.strptime(join_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                        formatted_date = parsed_date.strftime("%b %d, %Y")
                        days_ago = (datetime.now() - parsed_date).days
                        blacklist_details.append(f"🚫 **{group_name}**\nID: {group_id} | Joined: {formatted_date} ({days_ago} days ago)")
                    except:
                        blacklist_details.append(f"🚫 **{group_name}**\nID: {group_id} | Joined: Unknown")
                else:
                    blacklist_details.append(f"🚫 **{group_name}**\nID: {group_id} | Join date unavailable")
            
            blacklist_text = "\n\n".join(blacklist_details)
            if len(blacklisted) > 3:
                blacklist_text += f"\n\n*...and {len(blacklisted) - 3} more blacklisted groups*"
        else:
            blacklist_text = "✅ User is not in any blacklisted groups"
        
        embed.add_field(
            name=f"🚫 Blacklisted Groups ({len(blacklisted)} found)",
            value=blacklist_text,
            inline=False
        )
        
        # === ALL GROUPS ===
        if user_groups:
            blacklisted_ids = [g['id'] for g in blacklisted]
            other_groups = [g for g in user_groups if g['id'] not in blacklisted_ids and g['id'] != CUSA_GROUP_ID]
            
            if other_groups:
                group_list = []
                for group in other_groups[:5]:
                    group_id = group['id']
                    group_name = group['name']
                    join_date = all_group_join_dates.get(group_id)
                    
                    if join_date:
                        try:
                            parsed_date = datetime.strptime(join_date, "%Y-%m-%dT%H:%M:%S.%fZ")
                            formatted_date = parsed_date.strftime("%b %d, %Y")
                            days_ago = (datetime.now() - parsed_date).days
                            group_list.append(f"• **{group_name}**\n  Role: {group['role']} | Joined: {formatted_date} ({days_ago}d ago)")
                        except:
                            group_list.append(f"• **{group_name}**\n  Role: {group['role']} | Joined: Unknown")
                    else:
                        group_list.append(f"• **{group_name}**\n  Role: {group['role']} | Join date unavailable")
                
                groups_text = "\n\n".join(group_list)
                if len(other_groups) > 5:
                    groups_text += f"\n\n*...and {len(other_groups) - 5} more groups*"
            else:
                groups_text = "No other groups"
        else:
            groups_text = "User is not in any groups"
        
        total_groups = len(user_groups) if user_groups else 0
        embed.add_field(
            name=f"📊 Other Groups (Total: {total_groups})",
            value=groups_text,
            inline=False
        )
        
        # === RISK ASSESSMENT ===
        risk_score = 0
        risk_factors = []
        
        if similar_users:
            risk_score += 2
            risk_factors.append("Similar usernames detected")
        if blacklisted:
            risk_score += 5
            risk_factors.append(f"Member of {len(blacklisted)} blacklisted group(s)")
        if friends_count is not None and friends_count < 15:
            risk_score += 2
            risk_factors.append("Low friend count")
        if not account_older_than_6m:
            risk_score += 3
            risk_factors.append("New account (< 6 months)")
        
        risk_level = "🟢 LOW RISK"
        risk_color = discord.Color.green()
        if risk_score >= 7:
            risk_level = "🔴 HIGH RISK"
            risk_color = discord.Color.red()
        elif risk_score >= 4:
            risk_level = "🟡 MEDIUM RISK"
            risk_color = discord.Color.yellow()
        
        embed.color = risk_color
        
        risk_text = f"**Level:** {risk_level}\n**Score:** {risk_score}/12\n\n"
        if risk_factors:
            risk_text += "**Factors:**\n" + "\n".join([f"• {factor}" for factor in risk_factors])
        else:
            risk_text += "✅ No significant risk factors detected"
        
        embed.add_field(
            name="⚠️ RISK ASSESSMENT",
            value=risk_text,
            inline=False
        )
        
        embed.set_footer(text=f"Report generated for User ID: {user_id}")
        
        await interaction.edit_original_response(content=None, embed=embed)
        
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ An error occurred: {str(e)}")
        print(f"Error in background check: {e}")

@bot.tree.command(name="reload-blacklist", description="Reload the blacklisted groups from Google Doc")
async def reload_blacklist(interaction: discord.Interaction):
    """Reload blacklist (admin only)"""
    await interaction.response.defer()
    
    success = await checker.fetch_blacklist()
    if success:
        await interaction.followup.send(f"✅ Blacklist reloaded! {len(checker.blacklisted_groups)} groups loaded.")
    else:
        await interaction.followup.send("❌ Failed to reload blacklist.")

# Run the bot
if __name__ == "__main__":
    print("Starting Roblox Background Check Bot...")
    
    # Get token from environment variable or use placeholder
    TOKEN = os.getenv("DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN_HERE")
    
    if TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE" or not TOKEN:
        print("\n⚠️  WARNING: No Discord bot token found!")
        print("Please set the DISCORD_BOT_TOKEN environment variable or create a .env file")
        print("Get your token from: https://discord.com/developers/applications\n")
    else:
        bot.run(TOKEN)
