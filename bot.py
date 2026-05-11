import os
import discord
from discord.ext import commands
from engine.database import Database
from config.settings_manager import SettingsManager
from flask import Flask
import threading

# --- KEEP AWAKE WEB SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()
# ------------------------------

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
    keep_alive() # Start the web server to keep Render awake
    async with bot:
        await bot.add_cog(Chat(bot, db, settings_manager))
        await bot.add_cog(SettingsCog(bot, db, settings_manager))
        
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable not set!")
        await bot.start(token)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
