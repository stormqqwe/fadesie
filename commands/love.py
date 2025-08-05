import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sys
import os
import re
from functions.database import get_love_profile, get_marriage_status, update_loveroom_quote, get_loveroom_by_user, delete_loveroom, delete_marriage, update_loveroom_banner, update_loveroom_heart, AVAILABLE_HEARTS
from functions.loveroom import LoveroomHandler

class LoveCommands(commands.GroupCog, group_name="love", description="Команды для управления любовным профилем"):
    def __init__(self, bot):
        self.bot = bot
        # Словарь для хранения состояний ожидания ввода (цитаты или баннера)
        self.waiting_for_input = {}
    
    @app_commands.command(name="profile", description="Показать любовный профиль")
    @app_commands.describe(пользователь="Пользователь, чей профиль вы хотите посмотреть")
    async def profile(self, interaction: discord.Interaction, пользователь: discord.Member = None):
        # If no user is specified, use the command author
        if пользователь is None:
            пользователь = interaction.user
        
        # Get love profile data
        profile_data = await get_love_profile(interaction.guild.id, пользователь.id)
        
        # Check if the user has a love profile
        if not profile_data:
            # Different message depending on whether the user is checking their own profile or someone else's
            if пользователь.id == interaction.user.id:
                description = f"{interaction.user.mention}, вы полностью свободный человек."
            else:
                description = f"{interaction.user.mention}, {пользователь.mention} не имеет брачных связей."
            
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Любовный профиль",
                    description=description
                )
                .set_thumbnail(url=пользователь.display_avatar.url)
            )
            return
        
        # Get partner user object
        partner = interaction.guild.get_member(profile_data["partner_id"])
        partner_name = partner.display_name if partner else "Неизвестно"
        
        # Create embed
        embed = discord.Embed(
            title=f"Любовный профиль — {пользователь.display_name}",
        )
        
        # Add fields
        embed.add_field(
            name="Партнер",
            value=f"```{partner_name}```",
            inline=False
        )
        
        embed.add_field(
            name="Дата регистрации",
            value=f"```{profile_data['registration_date']}```",
            inline=True
        )
        
        embed.add_field(
            name="Цитата",
            value=f"```{profile_data['quote'] or 'Нет цитаты'}```",
            inline=False
        )
        
        # Format time values
        together = profile_data["together"]
        embed.add_field(
            name="Проведенное вместе время",
            value=f"```{together['hours']} часов, {together['minutes']} минут, {together['seconds']} секунд```",
            inline=False
        )
        
        embed.add_field(
            name="Общее время брака",
            value=f"```{profile_data['days_since_registration']} дней```",
            inline=False
        )
        
        
        # Set thumbnail to user's avatar
        embed.set_thumbnail(url=пользователь.display_avatar.url)
        
        # Set banner image if available
        if 'banner' in profile_data and profile_data['banner']:
            embed.set_image(url=profile_data['banner'])
        
        # Add buttons only if the profile belongs to the user who requested it
        view = None
        if пользователь.id == interaction.user.id:
            view = self.create_profile_view(interaction, profile_data)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    def create_profile_view(self, interaction, profile_data):
        """Create view with buttons for profile management"""
        class ProfileView(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=180)  # 3 minutes timeout
                self.cog = cog
                self.value = None
                self.interaction = interaction
                self.profile_data = profile_data
                self.message = None
            
            @discord.ui.button(label="Изменить цитату", style=discord.ButtonStyle.primary, row=0)
            async def change_quote_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != self.interaction.user.id:
                    await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                    return
                
                # Create quote input embed
                quote_embed = discord.Embed(
                    title="Изменение цитаты",
                    description=f"{self.interaction.user.mention}, напишите новую цитату для вашего любовного профиля",
                )
                quote_embed.set_thumbnail(url=self.interaction.user.display_avatar.url)
                
                await button_interaction.response.edit_message(embed=quote_embed, view=None)
                
                # Set waiting state for quote input
                self.cog.waiting_for_input[self.interaction.user.id] = {
                    'type': 'quote',
                    'channel_id': button_interaction.channel_id,
                    'message_id': button_interaction.message.id,
                    'guild_id': self.interaction.guild_id,
                    'loveroom_id': self.profile_data.get('channel_id'),
                    'current_quote': self.profile_data.get('quote', '')
                }
            
            @discord.ui.button(label="Изменить баннер", style=discord.ButtonStyle.primary, row=0)
            async def change_banner_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != self.interaction.user.id:
                    await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                    return
                
                # Create banner input embed
                banner_embed = discord.Embed(
                    title="Изменение баннера",
                    description=f"{self.interaction.user.mention}, укажите ссылку или загрузите файл изображения для баннера",
                )
                banner_embed.set_thumbnail(url=self.interaction.user.display_avatar.url)
                
                await button_interaction.response.edit_message(embed=banner_embed, view=None)
                
                # Set waiting state for banner input
                self.cog.waiting_for_input[self.interaction.user.id] = {
                    'type': 'banner',
                    'channel_id': button_interaction.channel_id,
                    'message_id': button_interaction.message.id,
                    'guild_id': self.interaction.guild_id,
                    'loveroom_id': self.profile_data.get('channel_id')
                }
            
            @discord.ui.button(label="Изменить сердечко", style=discord.ButtonStyle.primary, row=0)
            async def change_heart_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != self.interaction.user.id:
                    await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                    return
                
                # Create heart selection view
                heart_view = self.create_heart_selection_view()
                
                # Create heart selection embed
                heart_embed = discord.Embed(
                    title="Выбор сердечка",
                    description=f"{self.interaction.user.mention}, выберите символ сердца для вашего любовного профиля",
                )
                heart_embed.set_thumbnail(url=self.interaction.user.display_avatar.url)
                
                await button_interaction.response.edit_message(embed=heart_embed, view=heart_view)
            
            @discord.ui.button(label="Расстаться", style=discord.ButtonStyle.danger, row=1)
            async def divorce_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != self.interaction.user.id:
                    await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                    return
                
                # Create confirmation view
                confirm_view = self.create_confirm_view()
                
                # Create confirmation embed
                confirm_embed = discord.Embed(
                    title="Подтверждение расторжения брака",
                    description=f"{self.interaction.user.mention}, вы уверены, что хотите расторгнуть брак? Подумайте еще раз."
                )
                confirm_embed.set_thumbnail(url=self.interaction.user.display_avatar.url)
                await button_interaction.response.edit_message(embed=confirm_embed, view=confirm_view)
            
            def create_heart_selection_view(self):
                """Create a view with heart selection dropdown"""
                class HeartSelectionView(discord.ui.View):
                    def __init__(self, parent_view):
                        super().__init__(timeout=60)
                        self.parent_view = parent_view
                        self.add_item(HeartSelect(parent_view))
                    
                    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary, row=1)
                    async def cancel_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != self.parent_view.interaction.user.id:
                            await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                            return
                        
                        # Get updated profile data
                        profile_data = await get_love_profile(self.parent_view.interaction.guild.id, self.parent_view.interaction.user.id)
                        
                        # Create updated embed
                        embed = await self.parent_view.cog.create_profile_embed(self.parent_view.interaction.user, profile_data)
                        
                        # Create new view
                        view = self.parent_view.cog.create_profile_view(self.parent_view.interaction, profile_data)
                        
                        # Edit the message with the updated profile
                        await button_interaction.response.edit_message(embed=embed, view=view)
                
                class HeartSelect(discord.ui.Select):
                    def __init__(self, parent_view):
                        current_heart = parent_view.profile_data.get('heart', '💖')
                        options = []
                        
                        for heart in AVAILABLE_HEARTS:
                            is_current = heart == current_heart
                            options.append(discord.SelectOption(
                                label=heart,
                                value=heart,
                                description="Текущий выбор" if is_current else None,
                                default=is_current
                            ))
                        
                        super().__init__(
                            placeholder="Выберите сердечко...",
                            min_values=1,
                            max_values=1,
                            options=options,
                            
                        )
                        self.parent_view = parent_view
                    
                    async def callback(self, interaction: discord.Interaction):
                        if interaction.user.id != self.parent_view.interaction.user.id:
                            await interaction.response.send_message("Только владелец профиля может использовать это меню!", ephemeral=True)
                            return
                        
                        selected_heart = self.values[0]
                        
                        # Update heart in database
                        success = await update_loveroom_heart(
                            self.parent_view.interaction.guild.id,
                            self.parent_view.profile_data.get('channel_id'),
                            selected_heart
                        )
                        
                        if success:
                            # Update channel name with new heart
                            server_id = self.parent_view.interaction.guild.id
                            channel_id = self.parent_view.profile_data.get('channel_id')
                            
                            # Update channel name if channel exists
                            if channel_id:
                                # Try to update channel name
                                await self.parent_view.cog.bot.loveroom_handler.update_loveroom_channel_name(
                                    server_id,
                                    channel_id,
                                    selected_heart
                                )
                            
                            # Get updated profile data
                            profile_data = await get_love_profile(self.parent_view.interaction.guild.id, self.parent_view.interaction.user.id)
                            
                            # Create updated embed
                            embed = await self.parent_view.cog.create_profile_embed(self.parent_view.interaction.user, profile_data)
                            
                            # Create new view
                            view = self.parent_view.cog.create_profile_view(self.parent_view.interaction, profile_data)
                            
                            # Edit the message with the updated profile
                            await interaction.response.edit_message(embed=embed, view=view)
                        else:
                            # Error updating heart
                            error_embed = discord.Embed(
                                title="Ошибка",
                                description="Не удалось обновить символ сердца. Пожалуйста, попробуйте позже.",
                                color=discord.Color.red()
                            )
                            await interaction.response.edit_message(embed=error_embed, view=None)
                
                return HeartSelectionView(self)
            
            def create_confirm_view(self):
                """Create confirmation view for divorce"""
                class ConfirmView(discord.ui.View):
                    def __init__(self, parent_view):
                        super().__init__(timeout=60)
                        self.parent_view = parent_view
                    
                    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.danger)
                    async def confirm_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != self.parent_view.interaction.user.id:
                            await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                            return
                        
                        # Get loveroom info
                        loveroom = await get_loveroom_by_user(self.parent_view.interaction.guild.id, self.parent_view.interaction.user.id)
                        
                        # Get partner ID
                        partner_id = self.parent_view.profile_data["partner_id"]
                        user_id = self.parent_view.interaction.user.id
                        
                        # Delete marriage from database
                        await delete_marriage(self.parent_view.interaction.guild.id, user_id, partner_id)
                        
                        # Delete loveroom from database and kick users from voice channel
                        if loveroom:
                            # Try to get the voice channel
                            voice_channel = self.parent_view.interaction.guild.get_channel(loveroom["channel_id"])
                            if voice_channel:
                                # Kick all members from the voice channel
                                for member in voice_channel.members:
                                    try:
                                        await member.move_to(None)  # Disconnect the member
                                    except:
                                        pass
                                
                                # Try to delete the voice channel
                                try:
                                    await voice_channel.delete(reason="Брак расторгнут")
                                except:
                                    pass
                            
                            # Delete from database
                            await delete_loveroom(self.parent_view.interaction.guild.id, loveroom["channel_id"])
                        
                        # Create success embed
                        success_embed = discord.Embed(
                            title="Брак расторгнут",
                            description=f"{self.parent_view.interaction.user.mention}, ваш брак был успешно расторгнут."
                        )
                        success_embed.set_thumbnail(url=self.parent_view.interaction.user.display_avatar.url)
                        
                        await button_interaction.response.edit_message(embed=success_embed, view=None)
                    
                    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
                    async def cancel_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != self.parent_view.interaction.user.id:
                            await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                            return
                        
                        # Get updated profile data
                        profile_data = await get_love_profile(self.parent_view.interaction.guild.id, self.parent_view.interaction.user.id)
                        
                        # Create updated embed
                        embed = await self.parent_view.cog.create_profile_embed(self.parent_view.interaction.user, profile_data)
                        
                        # Create new view
                        view = self.parent_view.cog.create_profile_view(self.parent_view.interaction, profile_data)
                        
                        # Edit the message with the updated profile
                        await button_interaction.response.edit_message(embed=embed, view=view)
                
                return ConfirmView(self)
        
        return ProfileView(self)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if user is in waiting state
        if message.author.id in self.waiting_for_input:
            waiting_data = self.waiting_for_input[message.author.id]
            
            # Check if message is in the correct channel
            if message.channel.id != waiting_data['channel_id']:
                return
            
            # Get the original message
            try:
                channel = self.bot.get_channel(waiting_data['channel_id'])
                original_message = await channel.fetch_message(waiting_data['message_id'])
            except (discord.NotFound, discord.Forbidden):
                # Message not found or no permissions
                del self.waiting_for_input[message.author.id]
                return
            
            if waiting_data['type'] == 'quote':
                # Check if the quote is the same as current
                if 'current_quote' in waiting_data and message.content == waiting_data['current_quote']:
                    # Get profile data without updating
                    profile_data = await get_love_profile(waiting_data['guild_id'], message.author.id)
                else:
                    # Update quote in database
                    success = await update_loveroom_quote(waiting_data['guild_id'], waiting_data['loveroom_id'], message.content)
                    
                    if not success:
                        # Error updating quote
                        error_embed = discord.Embed(
                            title="Ошибка",
                            description="Не удалось обновить цитату. Пожалуйста, попробуйте позже.",
                            color=discord.Color.red()
                        )
                        await message.channel.send(embed=error_embed, delete_after=5)
                        return
                    
                # Get updated profile data
                profile_data = await get_love_profile(waiting_data['guild_id'], message.author.id)
                
                # Create updated embed
                embed = await self.create_profile_embed(message.author, profile_data)
                
                # Create new view
                interaction = await self.create_interaction_from_message(message, waiting_data['guild_id'])
                view = self.create_profile_view(interaction, profile_data)
                
                # Edit the original message
                await original_message.edit(embed=embed, view=view)
                
                # Delete user input message
                try:
                    await message.delete()
                except:
                    pass
            
            elif waiting_data['type'] == 'banner':
                banner_url = None
                
                # Check if message contains attachments (uploaded file)
                if message.attachments and len(message.attachments) > 0:
                    attachment = message.attachments[0]
                    # Check if it's an image
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        banner_url = attachment.url
                else:
                    # Accept any URL as banner
                    content = message.content.strip()
                    if content.startswith('http://') or content.startswith('https://'):
                        banner_url = content
                
                if not banner_url:
                    # Create retry view
                    class RetryView(discord.ui.View):
                        def __init__(self, cog, waiting_data):
                            super().__init__(timeout=60)
                            self.cog = cog
                            self.waiting_data = waiting_data
                        
                        @discord.ui.button(label="Повторить", style=discord.ButtonStyle.primary)
                        async def retry_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                            if button_interaction.user.id != message.author.id:
                                await button_interaction.response.send_message("Только владелец профиля может использовать эту кнопку!", ephemeral=True)
                                return
                            
                            # Create banner input embed again
                            banner_embed = discord.Embed(
                                title="Изменение баннера",
                                description=f"{message.author.mention}, укажите ссылку или загрузите файл изображения для баннера",
                            )
                            banner_embed.set_thumbnail(url=message.author.display_avatar.url)
                            
                            # Update the original message
                            await original_message.edit(embed=banner_embed, view=None)
                            
                            # Delete this message
                            await button_interaction.message.delete()
                            
                            # Re-add the waiting state
                            self.cog.waiting_for_input[message.author.id] = self.waiting_data
                    
                    # Error embed for invalid URL/image
                    error_embed = discord.Embed(
                        title="Неверный формат",
                        description=f"{message.author.mention}, пожалуйста, отправьте действительное изображение или ссылку на изображение.",
                        color=discord.Color.orange()
                    )
                    
                    # Send error message with retry button
                    await original_message.edit(embed=error_embed, view=RetryView(self, waiting_data))
                    
                    # Delete user input message
                    try:
                        await message.delete()
                    except:
                        pass
                    
                    # Don't remove waiting state yet
                    return
                
                # Update banner in database
                success = await update_loveroom_banner(waiting_data['guild_id'], waiting_data['loveroom_id'], banner_url)
                
                if success:
                    # Get updated profile data
                    profile_data = await get_love_profile(waiting_data['guild_id'], message.author.id)
                    
                    # Create updated embed
                    embed = await self.create_profile_embed(message.author, profile_data)
                    
                    # Create new view
                    interaction = await self.create_interaction_from_message(message, waiting_data['guild_id'])
                    view = self.create_profile_view(interaction, profile_data)
                    
                    # Edit the original message
                    await original_message.edit(embed=embed, view=view)
                    
                    # Delete user input message
                    try:
                        await message.delete()
                    except:
                        pass
                else:
                    # Error updating banner
                    error_embed = discord.Embed(
                        title="Ошибка",
                        description="Не удалось обновить баннер. Пожалуйста, попробуйте позже.",
                        color=discord.Color.red()
                    )
                    await original_message.edit(embed=error_embed, view=None)
                    
                    # Delete user input message
                    try:
                        await message.delete()
                    except:
                        pass
            
            # Remove waiting state
            if message.author.id in self.waiting_for_input:
                del self.waiting_for_input[message.author.id]
    
    async def create_interaction_from_message(self, message, guild_id):
        """Create a simple interaction object with necessary attributes"""
        class SimpleInteraction:
            def __init__(self, user, guild_id, guild):
                self.user = user
                self.guild_id = guild_id
                self.guild = guild
        
        return SimpleInteraction(message.author, guild_id, message.guild)
    
    async def create_profile_embed(self, user, profile_data):
        """Create profile embed with updated data"""
        # Get partner user object
        partner = user.guild.get_member(profile_data["partner_id"])
        partner_name = partner.display_name if partner else "Неизвестно"
        
        # Create embed
        embed = discord.Embed(
            title=f"Любовный профиль — {user.display_name}"
        )
        
        # Add fields
        embed.add_field(
            name="Партнер",
            value=f"```{partner_name}```",
            inline=False
        )
        
        embed.add_field(
            name="Регистрация брака",
            value=f"```{profile_data['registration_date']}```",
            inline=True
        )
        
        embed.add_field(
            name="Цитата",
            value=f"```{profile_data['quote'] or 'Нет цитаты'}```",
            inline=False
        )
        
        # Format time values
        together = profile_data["together"]
        embed.add_field(
            name="Проведенное вместе время",
            value=f"```{together['hours']} часов, {together['minutes']} минут, {together['seconds']} секунд```",
            inline=False
        )
        
        embed.add_field(
            name="Общее время брака",
            value=f"```{profile_data['days_since_registration']} дней```",
            inline=False
        )
        
        # Set thumbnail to user's avatar
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Set banner image if available
        if 'banner' in profile_data and profile_data['banner']:
            embed.set_image(url=profile_data['banner'])
        
        return embed

async def setup(bot):
    await bot.add_cog(LoveCommands(bot))