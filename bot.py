import os
import sys

# --- PATH FIX FOR RENDER ---
# This tells Python to look in the exact folder where this bot.py file lives
# so it can find database.py, settings_manager.py, api.py, etc.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ---------------------------

import discord
from discord.ext import commands
import threading
import asyncio

# Import your actual Database class
from database import Database

# Import the REAL SettingsManager from your file
from settings_manager import SettingsManager

# Import the centralized defaults for safety merging
from config.default_settings import DEFAULTS

# Import the FastAPI app, the runner function, and the bot instance variable from api.py
from api import app, run_api, bot_instance as api_bot_instance

# --- BOT INTENTS ---
# Make sure to enable these in the Discord Developer Portal under the "Bot" tab
intents = discord.Intents.default()
intents.message_content = True  # REQUIRED: To read what users say
intents.members = True          # REQUIRED: To track engagement and user names

# --- BOT CLASS ---
class MarkovLLMBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="/",  # Fallback prefix, though you're using slash commands
            intents=intents
        )
        # Initialize attributes that cogs will attach to
        self.db = None
        self.settings_manager = None

    async def setup_hook(self):
        """
        This runs automatically before the bot connects to Discord.
        It's the best place to initialize database connections and load cogs.
        """
        
        # --- DATABASE & SETTINGS INITIALIZATION ---
        print("Initializing Database...")
        self.db = Database()
        await self.db.init() # Connects to SQLite and creates tables
        
        print("Initializing Settings Manager...")
        # Now using your ACTUAL settings_manager.py with caching!
        self.settings_manager = SettingsManager(self.db)

        # --- LOAD COGS ---
        print("Loading Cogs...")
        await self.load_extension("cogs.chat")
        await self.load_extension("cogs.settings")
        # If you have other cogs, load them here

    async def on_ready(self):
        """
        This runs when the bot successfully connects to Discord.
        """
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

# --- INITIALIZE AND RUN ---

# 1. Create the bot instance
bot = MarkovLLMBot()

# 2. Pass the bot instance to the API so the dashboard can access the database/settings
api_bot_instance = bot

# 3. Start the FastAPI server in a background thread
# Render requires the app to bind to the PORT environment variable
print("Starting API dashboard thread...")
threading.Thread(target=run_api, daemon=True).start()

# 4. Run the Discord Bot
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("CRITICAL ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(TOKEN)
