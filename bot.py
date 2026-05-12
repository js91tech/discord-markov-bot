import os
import discord
from discord.ext import commands
import threading
import asyncio

# Import your actual Database class
from database import Database

# Import the centralized defaults
from config.default_settings import DEFAULTS

# Import the FastAPI app, the runner function, and the bot instance variable from api.py
from api import app, run_api, bot_instance as api_bot_instance

# --- SETTINGS MANAGER ---
class SettingsManager:
    def __init__(self, db):
        self.db = db
        # Use the imported DEFAULTS instead of hardcoding them here
        self.defaults = DEFAULTS

    async def get_settings(self, guild_id):
        settings = await self.db.get_settings(guild_id)
        if not settings:
            return self.defaults.copy()
        
        # Ensure all default keys exist (in case you add new features later)
        full_settings = self.defaults.copy()
        full_settings.update(settings)
        return full_settings

    async def set_setting(self, guild_id, key, value):
        settings = await self.get_settings(guild_id)
        settings[key] = value
        await self.db.save_settings(guild_id, settings)

    async def update_settings(self, guild_id, update_data):
        """Used by the FastAPI dashboard to update multiple settings at once"""
        settings = await self.get_settings(guild_id)
        settings.update(update_data)
        await self.db.save_settings(guild_id, settings)

    async def reset_all(self, guild_id):
        """Used by the /botsettings resetdata command"""
        await self.db.save_settings(guild_id, self.defaults.copy())


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
        self.settings_manager = SettingsManager(self.db)

        # --- LOAD COGS ---
        print("Loading Cogs...")
        # Loads the chat cog you just fixed
        await self.load_extension("cogs.chat")
        # Loads the settings cog you provided
        await self.load_extension("cogs.settings")
        # If you have other cogs (e.g., cogs.admin), load them here too

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
