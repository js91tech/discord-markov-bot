import discord
from discord.ext import commands
from discord import app_commands
from config.default_settings import DEFAULTS, VALIDATORS, parse_bool
from utils import sanitize_message
from llm import generate_llm_response, generate_image
from cogs.chat import DEFAULT_PERSONALITY
from people import load_profiles, is_nsfw_request, build_image_prompt, find_person
import json
import io


def build_roast_prompt(settings, display_name):
    personality = (settings.get("personality_prefix") or "").strip() or DEFAULT_PERSONALITY
    return (
        f"{personality}\n\n"
        f"Analyze these recent messages from {display_name} and deliver a witty roast "
        f"based on what they talk about and how they type. Stay in character. "
        f"Keep it 2-4 sentences. Be clever. DO NOT use @ symbols or names in your response."
    )


class SettingsCog(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager

    group = app_commands.Group(
        name="botsettings",
        description="Configure the bot",
        default_permissions=discord.Permissions(
            manage_guild=True))

    async def setting_autocomplete(self, interaction: discord.Interaction,
                                   current: str) -> list[app_commands.Choice[str]]:
        keys = list(DEFAULTS.keys())
        return [app_commands.Choice(name=key, value=key) for key in keys if current.lower() in key.lower()][:25]

    @group.command(name="set", description="Change a setting")
    @app_commands.autocomplete(key=setting_autocomplete)
    async def set_setting(self, interaction: discord.Interaction, key: str, value: str):
        key = key.lower()
        if key not in DEFAULTS:
            await interaction.response.send_message(f"❌ Invalid setting key: `{key}`", ephemeral=True)
            return
        validator = VALIDATORS.get(key)
        if validator and not validator(value):
            await interaction.response.send_message(f"❌ Invalid value for `{key}`.", ephemeral=True)
            return
        if isinstance(DEFAULTS[key], bool):
            parsed_val = parse_bool(value)
        elif isinstance(DEFAULTS[key], int):
            parsed_val = int(value)
        elif isinstance(DEFAULTS[key], float):
            parsed_val = float(value)
        elif isinstance(DEFAULTS[key], list):
            try:
                parsed_val = json.loads(value)
                if not isinstance(parsed_val, list):
                    raise ValueError
            except Exception:
                await interaction.response.send_message("❌ List values must be a JSON array", ephemeral=True)
                return
        else:
            parsed_val = value
        await self.settings_manager.set_setting(interaction.guild.id, key, parsed_val)
        await interaction.response.send_message(f"✅ Set `{key}` to `{parsed_val}`", ephemeral=True)

    @group.command(name="toggle", description="Toggle a True/False setting on or off")
    @app_commands.describe(setting="Choose the setting to toggle")
    @app_commands.choices(setting=[
        app_commands.Choice(name="Response Enabled", value="response_enabled"),
        app_commands.Choice(name="Trigger on Mention", value="trigger_on_mention"),
        app_commands.Choice(name="Trigger on Reply", value="trigger_on_reply")
    ])
    async def toggle_setting(self, interaction: discord.Interaction, setting: app_commands.Choice[str]):
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        new_val = not settings[setting.value]
        await self.settings_manager.set_setting(interaction.guild.id, setting.value, new_val)
        status = "ON ✅" if new_val else "OFF ❌"
        await interaction.response.send_message(f"**{setting.name}** is now {status}", ephemeral=True)

    @group.command(name="chattiness", description="Quick adjust how chatty the bot is")
    @app_commands.describe(level="Select a chattiness level")
    @app_commands.choices(level=[
        app_commands.Choice(name="1 - Almost Never Speaks", value=1), app_commands.Choice(name="2", value=2),
        app_commands.Choice(name="3 - Occasional", value=3), app_commands.Choice(name="4", value=4),
        app_commands.Choice(name="5 - Average", value=5), app_commands.Choice(name="6", value=6),
        app_commands.Choice(name="7 - Fairly Chatty", value=7), app_commands.Choice(name="8", value=8),
        app_commands.Choice(name="9", value=9), app_commands.Choice(name="10 - Won't Shut Up", value=10)
    ])
    async def chattiness(self, interaction: discord.Interaction, level: app_commands.Choice[int]):
        chance = round(level.value * 0.03, 2)
        await self.settings_manager.set_setting(interaction.guild.id, "response_chance", chance)
        await interaction.response.send_message(
            f"🗣️ Chattiness set to **{level.name}**. Response chance is now {chance * 100}%",
            ephemeral=True,
        )

    @group.command(name="remember", description="Make the bot permanently remember a fact about a user")
    @app_commands.describe(user="The user this fact is about", fact="The fact to remember")
    async def remember(self, interaction: discord.Interaction, user: discord.Member, fact: str):
        await self.db.add_memory(interaction.guild.id, user.id, fact)
        await interaction.response.send_message(
            f"🧠 I'll remember that about {user.display_name}: {fact}",
            ephemeral=True,
        )

    @group.command(name="forget", description="Make the bot forget all facts about a user")
    @app_commands.describe(user="The user to forget")
    async def forget(self, interaction: discord.Interaction, user: discord.Member):
        await self.db.forget_memories(interaction.guild.id, user.id)
        await interaction.response.send_message(
            f"🧠 I've forgotten everything I knew about {user.display_name}.",
            ephemeral=True,
        )

    @group.command(name="roast", description="Roast a user based on their recent messages")
    @app_commands.describe(user="The user you want to roast")
    async def roast(self, interaction: discord.Interaction, user: discord.Member):
        if user.bot:
            await interaction.response.send_message("I only roast humans! 🤖", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)

        user_msgs = []
        async for msg in interaction.channel.history(limit=500):
            if msg.author.id == user.id and not msg.content.startswith("/") and msg.content.strip():
                user_msgs.insert(0, msg.content)
                if len(user_msgs) >= 30:
                    break

        if len(user_msgs) < 5:
            await interaction.followup.send(
                f"{user.display_name} hasn't said enough for me to roast them.",
                ephemeral=True,
            )
            return

        settings = await self.settings_manager.get_settings(interaction.guild.id)
        roast_prompt = build_roast_prompt(settings, user.display_name)

        chat_history = [{"role": "user", "content": "\n".join(user_msgs)}]
        response = await generate_llm_response(
            roast_prompt,
            chat_history,
            model_name=settings.get("llm_model"),
            fallback_model=settings.get("fallback_llm_model"),
        )
        if response:
            await interaction.followup.send(f"🔥 **Roasting {user.display_name}:** {sanitize_message(response)}")
        else:
            await interaction.followup.send("Couldn't come up with a roast right now.", ephemeral=True)

    @group.command(name="list", description="View all current settings")
    async def list_settings(self, interaction: discord.Interaction):
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        embed = discord.Embed(title="Bot Settings", color=discord.Color.blue())
        for key in DEFAULTS:
            embed.add_field(name=key, value=f"`{settings.get(key)}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="stats", description="View bot statistics")
    async def stats(self, interaction: discord.Interaction):
        stats = await self.db.get_stats(interaction.guild.id)
        embed = discord.Embed(title="Bot Stats", color=discord.Color.green())
        embed.add_field(name="Messages Sent", value=str(stats["messages_sent"]), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="resetdata", description="Delete ALL data for this server")
    async def reset_data(self, interaction: discord.Interaction):
        await self.db.delete_guild_data(interaction.guild.id)
        await self.settings_manager.reset_all(interaction.guild.id)
        await interaction.response.send_message("💣 All data and settings have been wiped.", ephemeral=True)

    async def person_autocomplete(self, interaction: discord.Interaction,
                                  current: str) -> list[app_commands.Choice[str]]:
        current_lower = current.lower()
        choices = []
        for profile in load_profiles():
            if current_lower in profile["name"].lower() or current_lower in profile["id"]:
                choices.append(app_commands.Choice(name=profile["name"], value=profile["id"]))
        return choices[:25]

    @app_commands.command(name="imagine", description="Generate an image of a known person")
    @app_commands.describe(person="Who to generate", prompt="What they should be doing")
    @app_commands.autocomplete(person=person_autocomplete)
    async def imagine(self, interaction: discord.Interaction, person: str, prompt: str = "a casual portrait"):
        profile = find_person(person) or next(
            (p for p in load_profiles() if p["id"] == person.lower()),
            None,
        )
        if not profile:
            await interaction.response.send_message("I don't have a reference for that person.", ephemeral=True)
            return
        if is_nsfw_request(prompt):
            await interaction.response.send_message("Yeah no, I'm not generating that.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        image_bytes = await generate_image(
            build_image_prompt(profile, prompt),
            reference_path=profile.get("image_path"),
            model_name=settings.get("image_model"),
        )
        if image_bytes:
            await interaction.followup.send(
                file=discord.File(io.BytesIO(image_bytes), filename=f"{profile['id']}.png")
            )
        else:
            await interaction.followup.send("Couldn't generate that image right now.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SettingsCog(bot, bot.db, bot.settings_manager))
