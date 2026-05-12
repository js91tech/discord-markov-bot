import os
import sys
import glob
import discord
from discord.ext import commands
import threading
import asyncio

# ==========================================
# BULLETPROOF PATH & FILE DIAGNOSTIC ENGINE
# ==========================================
# Find out exactly what folder this bot.py file is sitting in
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Force Python to look IN THIS EXACT FOLDER for imports
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Verify the files are actually next to bot.py before we even try to import them
required_files = ['database.py', 'settings_manager.py', 'api.py']
missing_files = [f for f in required_files if not os.path.exists(os.path.join(CURRENT_DIR, f))]

if missing_files:
    print(f"❌ CRITICAL ERROR: Missing files in {CURRENT_DIR}: {', '.join(missing_files)}")
    print(f"📂 Files actually present in this folder: {glob.glob(os.path.join(CURRENT_DIR, '*'))}")
    print("🛑 STOPPING: Ensure database.py, settings_manager.py, and api.py are in the same folder as bot.py on GitHub!")
    sys.exit(1)
# ==========================================


# Now Python knows EXACTLY where to find these
from database import Database
from settings_manager import SettingsManager
from config.default_settings import DEFAULTS
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
        # Loads the chat cog
        await self.load_extension("cogs.chat")
        # Loads the settings cog
        await self.load_extension("cogs.settings")

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
