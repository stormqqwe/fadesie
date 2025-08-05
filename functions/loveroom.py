import discord
import asyncio
from datetime import datetime
from functions.database import get_loveroom_by_user, update_loveroom_time, get_marriage_status, register_loveroom, delete_loveroom, DEFAULT_HEART, AVAILABLE_HEARTS

class LoveroomHandler:
    def __init__(self, bot):
        self.bot = bot
        self.active_loverooms = {}  # {channel_id: {user_ids: set(), start_time: datetime, update_task: Task}}
        self.check_interval = 1  # seconds
        self.empty_loveroom_timeouts = {}  # {channel_id: Task}
        
        # Start background task to track loverooms
        bot.loop.create_task(self.initialize_loverooms())
    
    async def initialize_loverooms(self):
        """Initialize tracking for existing loverooms with users already in them"""
        await self.bot.wait_until_ready()
        
        # Scan all guilds for voice channels
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                # Check if this is a loveroom
                for member in voice_channel.members:
                    loveroom = await get_loveroom_by_user(guild.id, member.id)
                    if loveroom and loveroom.get('channel_id') == voice_channel.id:
                        # This is a loveroom with users in it
                        await self.check_and_update_loveroom(voice_channel, loveroom)
                        break
                
                # Also check empty voice channels that might be loverooms
                if len(voice_channel.members) == 0:
                    # Try to find if this is a loveroom by querying the database
                    try:
                        from config import CONFIG
                        # Skip if this is a loveroom creation channel
                        if voice_channel.id in CONFIG["LOVEROOM_CHANNELS"]:
                            continue
                    except (ImportError, KeyError):
                        pass
                    
                    # Check if this channel is in a loveroom category
                    try:
                        from config import CONFIG
                        if voice_channel.category_id == CONFIG["LOVEROOM_CATEGORY"]:
                            # Start deletion timer for empty loveroom
                            self.start_empty_loveroom_timer(voice_channel)
                    except (ImportError, KeyError):
                        pass
        
        print("Loveroom handler initialized successfully")
    
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates for loveroom tracking"""
        # Skip bot users
        if member.bot:
            return
        
        # Check if user joined a voice channel
        if after.channel and (not before.channel or before.channel != after.channel):
            # Check if this is a loveroom creation channel
            try:
                from config import CONFIG
                if after.channel.id in CONFIG["LOVEROOM_CHANNELS"]:
                    # Check if user is in a marriage
                    partner_id = await get_marriage_status(member.guild.id, member.id)
                    if not partner_id:
                        # User is not married, disconnect them
                        await member.move_to(None, reason="Нет брака для создания лаврума")
                        try:
                            await member.send(embed=discord.Embed(
                                title="Отсутствие брака",
                                description=f"{member.mention}, у вас отсутствует брак."
                            ).set_thumbnail(url=member.display_avatar.url))
                        except:
                            pass
                        return
                    
                    # Check if user already has a loveroom
                    existing_loveroom = await get_loveroom_by_user(member.guild.id, member.id)
                    if existing_loveroom and existing_loveroom.get("channel_id"):
                        # User already has a loveroom, move them there
                        channel = member.guild.get_channel(existing_loveroom["channel_id"])
                        if channel:
                            await member.move_to(channel)
                            await self.check_and_update_loveroom(channel, existing_loveroom)
                        else:
                            # Channel doesn't exist, create a new one
                            await self.create_loveroom(member, partner_id, existing_loveroom)
                    else:
                        # Create a new loveroom
                        await self.create_loveroom(member, partner_id, existing_loveroom)
                    return
            except (ImportError, KeyError):
                pass
            
            # Check if this channel is a loveroom
            loveroom = await get_loveroom_by_user(member.guild.id, member.id)
            if loveroom and loveroom.get('channel_id') == after.channel.id:
                # Cancel any deletion timer for this channel
                if after.channel.id in self.empty_loveroom_timeouts:
                    self.empty_loveroom_timeouts[after.channel.id].cancel()
                    self.empty_loveroom_timeouts.pop(after.channel.id, None)
                
                # Update tracking
                await self.check_and_update_loveroom(after.channel, loveroom)
        
        # Check if user left a voice channel
        elif before.channel and not after.channel:
            # Check if this was a loveroom
            if before.channel.id in self.active_loverooms:
                # Remove user from active users in this loveroom
                if member.id in self.active_loverooms[before.channel.id]['user_ids']:
                    self.active_loverooms[before.channel.id]['user_ids'].remove(member.id)
                
                # If no couple members left in channel, stop tracking
                if not self.active_loverooms[before.channel.id]['user_ids']:
                    await self.stop_tracking_loveroom(before.channel.id)
                    
                    # If channel is now empty, start deletion timer
                    if len(before.channel.members) == 0:
                        self.start_empty_loveroom_timer(before.channel)
        
        # Check if user moved between voice channels
        elif before.channel and after.channel and before.channel != after.channel:
            # Check if user left a loveroom
            if before.channel.id in self.active_loverooms:
                if member.id in self.active_loverooms[before.channel.id]['user_ids']:
                    self.active_loverooms[before.channel.id]['user_ids'].remove(member.id)
                
                # If no couple members left in channel, stop tracking
                if not self.active_loverooms[before.channel.id]['user_ids']:
                    await self.stop_tracking_loveroom(before.channel.id)
                    
                    # If channel is now empty, start deletion timer
                    if len(before.channel.members) == 0:
                        self.start_empty_loveroom_timer(before.channel)
            
            # Check if user joined a loveroom
            loveroom = await get_loveroom_by_user(member.guild.id, member.id)
            if loveroom and loveroom.get('channel_id') == after.channel.id:
                # Cancel any deletion timer for this channel
                if after.channel.id in self.empty_loveroom_timeouts:
                    self.empty_loveroom_timeouts[after.channel.id].cancel()
                    self.empty_loveroom_timeouts.pop(after.channel.id, None)
                
                # Update tracking
                await self.check_and_update_loveroom(after.channel, loveroom)
    
    def start_empty_loveroom_timer(self, channel):
        """Start a timer to delete an empty loveroom"""
        try:
            from config import CONFIG
            timeout = CONFIG["LOVEROOM_SETTINGS"].get("timeout", 60)
        except (ImportError, KeyError):
            timeout = 60  # Default timeout of 60 seconds
        
        # Cancel any existing timer
        if channel.id in self.empty_loveroom_timeouts:
            self.empty_loveroom_timeouts[channel.id].cancel()
        
        # Create a new timer task
        task = self.bot.loop.create_task(self.delete_empty_loveroom(channel, timeout))
        self.empty_loveroom_timeouts[channel.id] = task
    
    async def delete_empty_loveroom(self, channel, timeout):
        """Delete an empty loveroom after the timeout period"""
        try:
            # Wait for the timeout period
            await asyncio.sleep(timeout)
            
            # Check if the channel still exists and is still empty
            channel = self.bot.get_channel(channel.id)
            if channel and len(channel.members) == 0:
                # Get the server ID
                server_id = channel.guild.id
                
                # Remove from database
                await delete_loveroom(server_id, channel.id)
                
                # Delete the channel
                await channel.delete(reason="Лаврум пуст")
                
                # Remove from tracking
                if channel.id in self.active_loverooms:
                    await self.stop_tracking_loveroom(channel.id)
                
                print(f"Deleted empty loveroom: {channel.name}")
            
            # Remove the timer from tracking
            if channel.id in self.empty_loveroom_timeouts:
                self.empty_loveroom_timeouts.pop(channel.id, None)
                
        except asyncio.CancelledError:
            # Timer was cancelled
            pass
        except Exception as e:
            print(f"Error deleting empty loveroom: {e}")
    
    async def create_loveroom(self, member, partner_id, existing_loveroom=None):
        """Create a new loveroom for a married couple"""
        try:
            from config import CONFIG
            
            # Get partner member
            partner = member.guild.get_member(partner_id)
            if not partner:
                await member.move_to(None, reason="Партнер не найден на сервере")
                return None
            
            # Get category for loverooms
            category = member.guild.get_channel(CONFIG["LOVEROOM_CATEGORY"])
            if not category:
                await member.move_to(None, reason="Категория для лаврумов не найдена")
                return None
            
            # Get heart symbol from existing loveroom or use default
            heart = DEFAULT_HEART
            if existing_loveroom and "heart" in existing_loveroom:
                heart = existing_loveroom["heart"]
            
            # Create channel name with the appropriate heart symbol
            room_name = CONFIG["LOVEROOM_SETTINGS"]["name_format"].format(
                user=member.display_name, 
                partner=partner.display_name,
                heart=heart
            )
            
            # Set up permissions
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(
                    connect=False,
                    view_channel=True
                )
            }
            
            # Add permissions for the couple
            for user in [member, partner]:
                overwrites[user] = discord.PermissionOverwrite(
                    connect=True, 
                    view_channel=True,
                    speak=True,
                    send_messages=True
                )
            
            # Add role-specific permissions
            for role_id in CONFIG["ROLES"]["NO_VIEW_ACCESS"]:
                role = member.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=False
                    )
            
            for role_id in CONFIG["ROLES"]["NO_MOVE_ACCESS"]:
                role = member.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        move_members=False
                    )
            
            # Add special role permissions
            special_role_id = CONFIG["ROLES"]["SPECIAL_ROLE"]["id"]
            special_role = member.guild.get_role(special_role_id)
            if special_role:
                overwrites[special_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    manage_channels=True,
                    manage_permissions=True,
                    connect=True,
                    speak=True,
                    stream=True,
                    mute_members=True,
                    deafen_members=True,
                    move_members=True,
                    send_messages=True,
                    manage_webhooks=False
                )
            
            # Create the voice channel
            channel = await category.create_voice_channel(
                name=room_name,
                overwrites=overwrites,
                user_limit=CONFIG["LOVEROOM_SETTINGS"]["user_limit"]
            )
            
            # Register the loveroom in the database
            await register_loveroom(member.guild.id, channel.id, member.id, partner_id)
            
            # Move the member to the new channel
            await member.move_to(channel)
            
            # Start tracking the loveroom
            await self.check_and_update_loveroom(channel, {
                "server_id": member.guild.id,
                "channel_id": channel.id,
                "couple": [
                    {"user_id": member.id},
                    {"user_id": partner_id}
                ],
                "heart": heart
            })
            
            return channel
        
        except Exception as e:
            print(f"Error creating loveroom: {e}")
            await member.move_to(None, reason="Ошибка при создании лаврума")
            return None
    
    async def check_and_update_loveroom(self, voice_channel, loveroom_data):
        """Check if both partners are in the loveroom and start tracking if they are"""
        # Get the couple's user IDs
        couple_user_ids = [member['user_id'] for member in loveroom_data['couple']]
        
        # Check which users from the couple are in the voice channel
        present_couple_members = set()
        for member in voice_channel.members:
            if member.id in couple_user_ids:
                present_couple_members.add(member.id)
        
        # If both partners are in the channel, start tracking if not already tracking
        if len(present_couple_members) == 2:
            if voice_channel.id not in self.active_loverooms:
                await self.start_tracking_loveroom(voice_channel.id, loveroom_data['server_id'], present_couple_members)
            else:
                # Update the set of users in the loveroom
                self.active_loverooms[voice_channel.id]['user_ids'] = present_couple_members
        # If only one partner is in the channel, update tracking data but don't count time together
        elif len(present_couple_members) == 1:
            if voice_channel.id in self.active_loverooms:
                self.active_loverooms[voice_channel.id]['user_ids'] = present_couple_members
            else:
                # Start tracking but with only one user
                await self.start_tracking_loveroom(voice_channel.id, loveroom_data['server_id'], present_couple_members)
    
    async def start_tracking_loveroom(self, channel_id, server_id, user_ids):
        """Start tracking time for a loveroom"""
        # Create tracking data
        self.active_loverooms[channel_id] = {
            'user_ids': user_ids,
            'server_id': server_id,
            'start_time': datetime.utcnow(),
            'last_update': datetime.utcnow(),
            'update_task': None
        }
        
        # Start update task
        update_task = self.bot.loop.create_task(self.update_loveroom_time_task(channel_id))
        self.active_loverooms[channel_id]['update_task'] = update_task
    
    async def stop_tracking_loveroom(self, channel_id):
        """Stop tracking time for a loveroom and update the database"""
        if channel_id in self.active_loverooms:
            # Cancel the update task if it exists
            if self.active_loverooms[channel_id]['update_task']:
                self.active_loverooms[channel_id]['update_task'].cancel()
            
            # Calculate final time
            await self.update_time_in_database(channel_id)
            
            # Remove from active loverooms
            del self.active_loverooms[channel_id]
    
    async def update_loveroom_time_task(self, channel_id):
        """Background task to update loveroom time in the database"""
        try:
            while True:
                # Wait for the check interval
                await asyncio.sleep(self.check_interval)
                
                # Update time in database
                await self.update_time_in_database(channel_id)
        except asyncio.CancelledError:
            # Task was cancelled, cleanup if needed
            pass
        except Exception as e:
            print(f"Error in loveroom time update task: {e}")
    
    async def update_time_in_database(self, channel_id):
        """Update the time spent in the loveroom in the database"""
        if channel_id not in self.active_loverooms:
            return
        
        loveroom_data = self.active_loverooms[channel_id]
        now = datetime.utcnow()
        
        # Calculate elapsed time since last update
        elapsed_seconds = (now - loveroom_data['last_update']).total_seconds()
        elapsed_minutes = elapsed_seconds / 60  # Convert to minutes for database
        
        # Update last update time
        self.active_loverooms[channel_id]['last_update'] = now
        
        # Determine if both partners are present (for together time)
        both_present = len(loveroom_data['user_ids']) == 2
        
        # Update time in database
        # Together time only if both partners are present
        together_time_minutes = elapsed_minutes if both_present else 0
        
        # Update in database
        await update_loveroom_time(
            loveroom_data['server_id'],
            channel_id,
            0,  # total_time_minutes параметр оставляем для совместимости
            together_time_minutes
        )
        
    async def update_loveroom_channel_name(self, server_id, channel_id, heart):
        """Update the loveroom channel name with the new heart symbol"""
        try:
            # Validate heart symbol
            if heart not in AVAILABLE_HEARTS:
                heart = DEFAULT_HEART
                
            # Get the channel object
            guild = self.bot.get_guild(server_id)
            if not guild:
                return False
                
            channel = guild.get_channel(channel_id)
            if not channel:
                return False
                
            # Get loveroom data from database by channel_id
            from functions.database import loverooms_collection
            loveroom = await loverooms_collection.find_one({"server_id": server_id, "channel_id": channel_id})
            if not loveroom:
                return False
                
            # Get member objects
            user_id = loveroom['couple'][0]['user_id']
            partner_id = loveroom['couple'][1]['user_id']
            
            user = guild.get_member(user_id)
            partner = guild.get_member(partner_id)
            
            if not user or not partner:
                return False
                
            # Get config for name format
            from config import CONFIG
            
            # Create new channel name with the updated heart symbol
            room_name = CONFIG["LOVEROOM_SETTINGS"]["name_format"].format(
                user=user.display_name, 
                partner=partner.display_name,
                heart=heart
            )
            
            # Update channel name
            await channel.edit(name=room_name)
            return True
            
        except Exception as e:
            print(f"Error updating loveroom channel name: {e}")
            return False

def setup(bot):
    handler = LoveroomHandler(bot)
    bot.add_listener(handler.on_voice_state_update, 'on_voice_state_update')
    return handler
