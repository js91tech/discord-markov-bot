import discord
from discord.ext import commands
from discord import app_commands
from config.default_settings import DEFAULTS, VALIDATORS
import json

class SettingsCog(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager

    group = app_commands.Group(name="botsettings", description="Configure the bot", default_permissions=discord.Permissions(manage_guild=True))

    # --- AUTOCOMPLETE FUNCTION ---
    async def setting_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Provides a dropdown list of all valid setting keys."""
        keys = list(DEFAULTS.keys())
        return [
            app_commands.Choice(name=key, value=key)
            for key in keys if current.lower() in key.lower()
        ][:25] # Discord limits to 25 choices

    # --- /botsettings set (WITH AUTOCOMPLETE) ---
    @group.command(name="set", description="Change a setting")
    @app_commands.autocomplete(key=setting_autocomplete)
    async def set_setting(self, interaction: discord.Interaction, key: str, value: str):
        key = key.lower()
        if key not in DEFAULTS:
            await interaction.response.send_message(f"❌ Invalid setting key: `{key}`", ephemeral=True)
            return

        validator = VALIDATORS.get(key)
        if validator and not validator(value):
            await interaction.response.send_message(f"❌ Invalid value for `{key}`. Check the type (true/false, number, etc).", ephemeral=True)
            return

        # Type casting
        if isinstance(DEFAULTS[key], bool):
            parsed_val = str(value).lower() in ["true", "yes", "on"]
        elif isinstance(DEFAULTS[key], int):
            parsed_val = int(value)
        elif isinstance(DEFAULTS[key], float):
            parsed_val = float(value)
        elif isinstance(DEFAULTS[key], list):
            try:
                parsed_val = json.loads(value)
                if not isinstance(parsed_val, list): raise ValueError
            except:
                await interaction.response.send_message("❌ List values must be a JSON array, e.g. `[1, 2]`", ephemeral=True)
                return
        else:
            parsed_val = value

        await self.settings_manager.set_setting(interaction.guild.id, key, parsed_val)
        await interaction.response.send_message(f"✅ Set `{key}` to `{parsed_val}`", ephemeral=True)

    # --- /botsettings toggle (EASY TRUE/FALSE) ---
    @group.command(name="toggle", description="Toggle a True/False setting on or off")
    @app_commands.describe(setting="Choose the setting to toggle")
    @app_commands.choices(setting=[
        app_commands.Choice(name="Response Enabled", value="response_enabled"),
        app_commands.Choice(name="Learning Enabled", value="learning_enabled"),
        app_commands.Choice(name="Learn From Bots", value="learn_from_bots"),
        app_commands.Choice(name="Trigger on Mention", value="trigger_on_mention"),
        app_commands.Choice(name="Trigger on Reply", value="trigger_on_reply")
    ])
    async def toggle_setting(self, interaction: discord.Interaction, setting: app_commands.Choice[str]):
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        current_val = settings[setting.value]
        new_val = not current_val
        
        await self.settings_manager.set_setting(interaction.guild.id, setting.value, new_val)
        status = "ON ✅" if new_val else "OFF ❌"
        await interaction.response.send_message(f"**{setting.name}** is now {status}", ephemeral=True)

    # --- /botsettings chattiness (SLIDER CHOICES) ---
    @group.command(name="chattiness", description
