import discord
import asyncio
import logging
import os
from dotenv import load_dotenv
from discord.ext import commands
from functions.loveroom import setup as setup_loveroom_handler

# Настройка логирования
logger = logging.getLogger('bot')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Логирование в файл
file_handler = logging.FileHandler('bot.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Загрузка переменных окружения
load_dotenv()

# Получение токена из переменных окружения
TOKEN = os.getenv('TOKEN')

# Создание экземпляра бота с указанием префикса и интентов
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Список расширений (когов) для загрузки
extensions = [
    'commands.marry',
    'commands.love'
]

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} ({bot.user.id})')
    logger.info(f'Connected to {len(bot.guilds)} guilds')
    
    # Синхронизация слеш-команд
    logger.info('Syncing slash commands...')
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=discord.Object(id=guild.id))
            logger.info(f'Synced commands for guild {guild.name} ({guild.id})')
        except Exception as e:
            logger.error(f'Failed to sync commands for guild {guild.name} ({guild.id}): {e}')
    logger.info('Slash commands synced successfully')
    
    # Инициализация обработчика лаврумов
    bot.loveroom_handler = setup_loveroom_handler(bot)
    logger.info('Loveroom handler initialized successfully')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f"Command error: {error}")

async def load_extensions():
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            logger.info(f'Loaded extension {extension}')
        except Exception as e:
            logger.error(f'Failed to load extension {extension}: {e}')

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())