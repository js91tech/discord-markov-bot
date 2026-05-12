import threading
import os
from api import app, bot_instance as api_bot_instance
import os
import discord
from discord.ext import commands
from engine.database import Database
from config.settings_manager import SettingsManager
from cogs.chat import Chat
from cogs.settings_cog import SettingsCog
from keep_alive import keep_alive
import asyncio
import aiohttp

# Self-ping to keep Render awake
async def self_ping():
    await asyncio.sleep(60)
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    if render_url:
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    await session.get(render_url)
            except:
                pass
            await asyncio.sleep(240)

intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.members = True

db = Database()
settings_manager = SettingsManager(db)

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await db.init()
    await settings_manager.load_settings()
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
        
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready to learn and chat!")

async def main():
    keep_alive() # Start the web server
    asyncio.create_task(self_ping()) # Start self-ping
    
    async with bot:
        await bot.add_cog(Chat(bot, db, settings_manager))
        await bot.add_cog(SettingsCog(bot, db, settings_manager))
        
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable not set!")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
