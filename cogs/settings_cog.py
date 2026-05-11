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

    @group.command(name="list", description="View all current settings")
    async def list_settings(self, interaction: discord.Interaction):
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        embed = discord.Embed(title="Bot Settings", color=discord.Color.blue())
        for key, value in settings.items():
            embed.add_field(name=key, value=f"`{value}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="set", description="Change a setting")
    async def set_setting(self, interaction: discord.Interaction, key: str, value: str):
        key = key.lower()
        if key not in DEFAULTS:
            await interaction.response.send_message(f"❌ Invalid setting key: `{key}`", ephemeral=True)
            return

        # Validation
        validator = VALIDATORS.get(key)
        if validator and not validator(value):
            await interaction.response.send_message(f"❌ Invalid value for `{key}`", ephemeral=True)
            return

        # Type casting for DB
        if isinstance(DEFAULTS[key], bool):
            parsed_val = str(value).lower() == "true"
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

    @group.command(name="reset", description="Reset a setting to default")
    async def reset_setting(self, interaction: discord.Interaction, key: str):
        key = key.lower()
        if key not in DEFAULTS:
            await interaction.response.send_message(f"❌ Invalid setting key: `{key}`", ephemeral=True)
            return
        await self.settings_manager.reset_setting(interaction.guild.id, key)
        await interaction.response.send_message(f"🔄 Reset `{key}` to default (`{DEFAULTS[key]}`)", ephemeral=True)

    @group.command(name="resetall", description="Reset ALL settings to defaults")
    async def reset_all(self, interaction: discord.Interaction):
        await self.settings_manager.reset_all(interaction.guild.id)
        await interaction.response.send_message("🔄 All settings have been reset to defaults.", ephemeral=True)

    @group.command(name="stats", description="View learning statistics")
    async def stats(self, interaction: discord.Interaction):
        stats = await self.db.get_stats(interaction.guild.id)
        embed = discord.Embed(title="Learning Stats", color=discord.Color.green())
        embed.add_field(name="Messages Learned", value=str(stats["messages_learned"]), inline=True)
        embed.add_field(name="Messages Sent", value=str(stats["messages_sent"]), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="toggle", description="Quick toggle responses on/off")
    async def toggle(self, interaction: discord.Interaction):
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        new_val = not settings["response_enabled"]
        await self.settings_manager.set_setting(interaction.guild.id, "response_enabled", new_val)
        status = "ON ✅" if new_val else "OFF ❌"
        await interaction.response.send_message(f"Responses are now {status}", ephemeral=True)

    @group.command(name="chattiness", description="Quick adjust how chatty the bot is (1-10)")
    async def chattiness(self, interaction: discord.Interaction, level: int):
        if level < 1 or level > 10:
            await interaction.response.send_message("❌ Chattiness must be between 1 and 10", ephemeral=True)
            return
        
        # Map 1-10 to 0.01 - 0.30
        chance = round(level * 0.03, 2)
        await self.settings_manager.set_setting(interaction.guild.id, "response_chance", chance)
        await interaction.response.send_message(f"🗣️ Chattiness set to {level}. Response chance is now {chance*100}%", ephemeral=True)

    @group.command(name="resetdata", description="Delete ALL learned data for this server")
    async def reset_data(self, interaction: discord.Interaction):
        await self.db.delete_guild_data(interaction.guild.id)
        # Clear from memory cache if loaded
        if interaction.guild.id in self.bot.get_cog("Chat").chains:
            del self.bot.get_cog("Chat").chains[interaction.guild.id]
        # Re-initialize default settings
        await self.settings_manager.reset_all(interaction.guild.id)
        await interaction.response.send_message("💣 All learned data and settings have been wiped.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SettingsCog(bot, bot.db, bot.settings_manager))
