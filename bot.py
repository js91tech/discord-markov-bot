import os
import sys
import discord
from discord.ext import commands
import threading
import asyncio

# --- LOGIC FIX: DYNAMIC PATH RESOLVER ---
# If Render runs this from the root directory instead of /src, 
# imports will fail. This safely detects the /src folder and adds it.
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == 'src' and current_dir not in sys.path:
    sys.path.insert(0, current_dir)
# ----------------------------------------

# Import your actual Database class
from database import Database

# Import the REAL SettingsManager from your file
from settings_manager import SettingsManager

# Import the centralized defaults for safety merging
from config.default_settings import DEFAULTS

# Import the FastAPI app, the runner function, and the bot instance variable from api.py
from api import app, run_api, bot_instance as api_bot_instance

# --- BOT INTENTS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# --- BOT CLASS ---
class MarkovLLMBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="/",
            intents=intents
        )
        self.db = None
        self.settings_manager = None

    async def setup_hook(self):
        """Runs automatically before the bot connects to Discord."""
        
        # --- DATABASE & SETTINGS INITIALIZATION ---
        print("Initializing Database...")
        self.db = Database()
        await self.db.init()
        
        print("Initializing Settings Manager...")
        self.settings_manager = SettingsManager(self.db)

        # --- LOAD COGS ---
        print("Loading Cogs...")
        await self.load_extension("cogs.chat")
        await self.load_extension("cogs.settings")

    async def on_ready(self):
        """Runs when the bot successfully connects to Discord."""
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

# --- INITIALIZE AND RUN ---

# 1. Create the bot instance
bot = MarkovLLMBot()

# 2. Pass the bot instance to the API so the dashboard can access the database/settings
api_bot_instance = bot

# 3. Start the FastAPI server in a background thread
print("Starting API dashboard thread...")
threading.Thread(target=run_api, daemon=True).start()

# 4. Run the Discord Bot
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("CRITICAL ERROR: DISCORD_TOKEN environment variable is missing!")
else:
    bot.run(TOKEN)
