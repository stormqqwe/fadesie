import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sys
import os
from functions.database import register_loveroom, get_loveroom_by_user, delete_loveroom, update_loveroom_time, get_marriage_status, register_marriage, get_love_profile
from config import CONFIG

class MarryCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_proposals = {}
    
    @app_commands.command(name="marry", description="Предложить пользователю пожениться")
    @app_commands.describe(пользователь="Пользователь, которому вы хотите сделать предложение")
    async def marry_command(self, interaction: discord.Interaction, пользователь: discord.Member):
        if пользователь.id == interaction.user.id:
            embed = discord.Embed(title="Предложение невозможно", description=f"{interaction.user.mention}, вы не можете отправить предложение себе же.")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
            return
        
        if пользователь.bot:
            embed = discord.Embed(title="Предложение невозможно", description=f"{interaction.user.mention}, боты служат людям а не люди ботам.")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
            return
        
        user_status = await get_marriage_status(interaction.guild.id, interaction.user.id)
        if user_status:
            embed = discord.Embed(title="Предложение невозможно", description=f"{interaction.user.mention}, вы уже состоите в браке с <@{user_status}>")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
            return
        
        partner_status = await get_marriage_status(interaction.guild.id, пользователь.id)
        if partner_status:
            embed = discord.Embed(title="Предложение невозможно", description=f"{interaction.user.mention}, пользователь <@{пользователь.id}> уже состоит в браке с <@{partner_status}>")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
            return
        
        for (server_id, user_id), p_id in self.pending_proposals.items():
            if server_id == interaction.guild.id and (user_id == interaction.user.id or p_id == interaction.user.id):
                embed = discord.Embed(title="Предложение невозможно", description=f"{interaction.user.mention}, у вас уже есть активное предложение брака")
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.response.send_message(embed=embed)
                return
        
        key = (interaction.guild.id, interaction.user.id)
        self.pending_proposals[key] = пользователь.id
        
        proposal_embed = discord.Embed(
            title="Заключение брака",
            description=f"{interaction.user.mention}, вы успешно отправили запрос на заключение брака пользователю {пользователь.mention}"
        )
        proposal_embed.set_thumbnail(url=пользователь.display_avatar.url)
        
        dm_embed = discord.Embed(
            title="Заключение брака",
            description=f"{пользователь.mention}, пользователь {interaction.user.mention} предлагает вам заключить брак на сервере **{interaction.guild.name}**"
        )
        dm_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        class ResponseView(discord.ui.View):
            def __init__(self, cog, timeout=60):
                super().__init__(timeout=timeout)
                self.cog = cog
                self.accepted = None
                self.message = None
                self.server_message = None
            
            @discord.ui.button(label="Согласится", style=discord.ButtonStyle.primary)
            async def accept(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != пользователь.id:
                    await button_interaction.response.send_message("Только тот, кому адресовано предложение, может ответить!", ephemeral=True)
                    return
                
                self.accepted = True
                
                await register_marriage(interaction.guild.id, interaction.user.id, пользователь.id)
                
                accept_dm_embed = discord.Embed(
                    title="Заключение брака",
                    description=f"{пользователь.mention}, вы успешно согласились на брак с пользователем {interaction.user.mention} на сервере **{interaction.guild.name}**"
                )
                accept_dm_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                
                accept_server_embed = discord.Embed(
                    title="Заключение брака",
                    description=f"{interaction.user.mention}, {пользователь.mention} успешно согласился на брак с вами."
                )
                accept_server_embed.set_thumbnail(url=пользователь.display_avatar.url)
                
                for child in self.children:
                    child.disabled = True
                
                await button_interaction.response.edit_message(embed=accept_dm_embed, view=None)
                
                if self.server_message:
                    try:
                        await self.server_message.edit(embed=accept_server_embed)
                    except Exception:
                        pass
                
                self.stop()
                
                if key in self.cog.pending_proposals:
                    del self.cog.pending_proposals[key]
            
            @discord.ui.button(label="Отказать", style=discord.ButtonStyle.danger)
            async def decline(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                if button_interaction.user.id != пользователь.id:
                    await button_interaction.response.send_message("Только тот, кому адресовано предложение, может ответить!", ephemeral=True)
                    return
                
                self.accepted = False
                
                decline_dm_embed = discord.Embed(
                    title="Заключение брака",
                    description=f"{пользователь.mention}, вы отказались от брака с пользователем {interaction.user.mention} на сервере **{interaction.guild.name}**"
                )
                decline_dm_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                
                decline_server_embed = discord.Embed(
                    title="Заключение брака",
                    description=f"{пользователь.mention}, к сожалению, {interaction.user.mention} отказался от брака с вами."
                )
                decline_server_embed.set_thumbnail(url=пользователь.display_avatar.url)
                
                for child in self.children:
                    child.disabled = True
                
                await button_interaction.response.edit_message(embed=decline_dm_embed, view=None)
                
                if self.server_message:
                    try:
                        await self.server_message.edit(embed=decline_server_embed)
                    except Exception:
                        pass
                
                self.stop()
                
                if key in self.cog.pending_proposals:
                    del self.cog.pending_proposals[key]
            
            async def on_timeout(self):
                if key in self.cog.pending_proposals:
                    del self.cog.pending_proposals[key]
                
                timeout_embed = discord.Embed(
                    title="Заключение брака",
                    description=f"{пользователь.mention} не ответил(а) на предложение {interaction.user.mention} вовремя.\n\nПредложение отменено."
                )
                timeout_embed.set_thumbnail(url=пользователь.display_avatar.url)
                
                for child in self.children:
                    child.disabled = True
                
                if self.message:
                    try:
                        await self.message.edit(embed=timeout_embed, view=self)
                    except Exception:
                        pass
                
                if self.server_message:
                    try:
                        await self.server_message.edit(embed=timeout_embed)
                    except Exception:
                        pass
        
        view = ResponseView(self)
        
        await interaction.response.send_message(embed=proposal_embed)
        original_message = await interaction.original_response()
        view.server_message = original_message
        
        try:
            dm_message = await пользователь.send(embed=dm_embed, view=view)
            view.message = dm_message
        except discord.Forbidden:
            await interaction.followup.send(f"Не удалось отправить сообщение пользователю {пользователь.mention}. Возможно, у него закрыты личные сообщения.", ephemeral=True)
            if key in self.pending_proposals:
                del self.pending_proposals[key]

async def setup(bot):
    await bot.add_cog(MarryCommands(bot))