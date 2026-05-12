import discord
from discord.ext import commands
from discord import app_commands
from config.default_settings import DEFAULTS, VALIDATORS
from engine.markov import MarkovChain
from utils import sanitize_message
from llm import generate_llm_response # CRITICAL LINT FIX: Added missing import
import json

class SettingsCog(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager

    group = app_commands.Group(name="botsettings", description="Configure the bot", default_permissions=discord.Permissions(manage_guild=True))

    async def setting_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
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
        if isinstance(DEFAULTS[key], bool): parsed_val = str(value).lower() in ["true", "yes", "on"]
        elif isinstance(DEFAULTS[key], int): parsed_val = int(value)
        elif isinstance(DEFAULTS[key], float): parsed_val = float(value)
        elif isinstance(DEFAULTS[key], list):
            try:
                parsed_val = json.loads(value)
                if not isinstance(parsed_val, list): raise ValueError
            except Exception:
                await interaction.response.send_message("❌ List values must be a JSON array", ephemeral=True)
                return
        else: parsed_val = value
        await self.settings_manager.set_setting(interaction.guild.id, key, parsed_val)
        await interaction.response.send_message(f"✅ Set `{key}` to `{parsed_val}`", ephemeral=True)

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
        await interaction.response.send_message(f"🗣️ Chattiness set to **{level.name}**. Response chance is now {chance*100}%", ephemeral=True)

    @group.command(name="mode", description="Switch between Markov (Free/Silly) and LLM (Cheap/Coherent)")
    @app_commands.describe(brain="Select the brain mode")
    @app_commands.choices(brain=[
        app_commands.Choice(name="Markov (Free, Silly, Random)", value="markov"),
        app_commands.Choice(name="LLM (Costs Cents, Human-like, Coherent)", value="llm")
    ])
    async def mode(self, interaction: discord.Interaction, brain: app_commands.Choice[str]):
        await self.settings_manager.set_setting(interaction.guild.id, "brain_mode", brain.value)
        await interaction.response.send_message(f"🧠 Brain mode set to **{brain.name}**.", ephemeral=True)

    @group.command(name="remember", description="Make the bot permanently remember a fact about a user")
    @app_commands.describe(user="The user this fact is about", fact="The fact to remember")
    async def remember(self, interaction: discord.Interaction, user: discord.Member, fact: str):
        await self.db.add_memory(interaction.guild.id, user.id, fact)
        await interaction.response.send_message(f"🧠 I'll remember that about {user.display_name}: {fact}", ephemeral=True)

    @group.command(name="forget", description="Make the bot forget all facts about a user")
    @app_commands.describe(user="The user to forget")
    async def forget(self, interaction: discord.Interaction, user: discord.Member):
        await self.db.forget_memories(interaction.guild.id, user.id)
        await interaction.response.send_message(f"🧠 I've forgotten everything I knew about {user.display_name}.", ephemeral=True)

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
                if len(user_msgs) >= 30: break
                
        if len(user_msgs) < 5:
            await interaction.followup.send(f"{user.display_name} hasn't said enough for me to roast them.", ephemeral=True)
            return

        settings = await self.settings_manager.get_settings(interaction.guild.id)
        roast_prompt = (
            f"You are a ruthless, sarcastic smart-ass. Analyze these recent messages from {user.display_name} "
            f"and deliver a devastating, witty roast based on what they talk about and how they type. "
            f"Keep it 2-4 sentences. Be savage but clever. DO NOT use @ symbols or names in your response."
        )
        
        chat_history = [{"role": "user", "content": "\n".join(user_msgs)}]
        chat_history.insert(0, {"role": "system", "content": roast_prompt, "model": settings.get("llm_model", "meta-llama/llama-3-8b-instruct")})
        
        response = await generate_llm_response(roast_prompt, chat_history)
        if response:
            await interaction.followup.send(f"🔥 **Roasting {user.display_name}:** {sanitize_message(response)}")
        else:
            await interaction.followup.send("Couldn't come up with a roast right now.", ephemeral=True)

    @group.command(name="mimic", description="Generate a message mimicking a specific user")
    @app_commands.describe(user="The user you want to mimic")
    async def mimic(self, interaction: discord.Interaction, user: discord.Member):
        if user.bot:
            await interaction.response.send_message("I only mimic humans! 🤖", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            temp_chain = MarkovChain(order=2)
            messages_found = 0
            exact_messages = set()
            async for msg in interaction.channel.history(limit=5000):
                if msg.author.id == user.id and not msg.content.startswith("/") and msg.content.strip():
                    temp_chain.learn(msg.content)
                    exact_messages.add(msg.content.lower().strip())
                    messages_found += 1
                    if messages_found >= 500: break
            if messages_found < 5:
                await interaction.followup.send(f"{user.display_name} hasn't talked enough here for me to mimic them!", ephemeral=True)
                return
            response = None
            for _ in range(5):
                generated = temp_chain.generate(min_words=4, max_words=40)
                if generated and generated.lower().strip() not in exact_messages:
                    response = generated
                    break
            if response:
                await interaction.followup.send(f"**{user.display_name}:** {sanitize_message(response)}")
            else:
                await interaction.followup.send(f"I couldn't figure out how to mix up {user.display_name}'s words creatively!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred while mimicking: {e}", ephemeral=True)

    @group.command(name="list", description="View all current settings")
    async def list_settings(self, interaction: discord.Interaction):
        settings = await self.settings_manager.get_settings(interaction.guild.id)
        embed = discord.Embed(title="Bot Settings", color=discord.Color.blue())
        for key, value in settings.items():
            embed.add_field(name=key, value=f"`{value}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="stats", description="View learning statistics")
    async def stats(self, interaction: discord.Interaction):
        stats = await self.db.get_stats(interaction.guild.id)
        embed = discord.Embed(title="Learning Stats", color=discord.Color.green())
        embed.add_field(name="Messages Learned", value=str(stats["messages_learned"]), inline=True)
        embed.add_field(name="Messages Sent", value=str(stats["messages_sent"]), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @group.command(name="resetdata", description="Delete ALL learned data for this server")
    async def reset_data(self, interaction: discord.Interaction):
        await self.db.delete_guild_data(interaction.guild.id)
        if interaction.guild.id in self.bot.get_cog("Chat").chains:
            del self.bot.get_cog("Chat").chains[interaction.guild.id]
        await self.settings_manager.reset_all(interaction.guild.id)
        await interaction.response.send_message("💣 All learned data and settings have been wiped.", ephemeral=True)

    @group.command(name="loadbrain", description="Manually load the starter brain text file")
    async def load_brain(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_id = interaction.guild.id
        try:
            with open("training_data.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            await interaction.followup.send("❌ No `training_data.txt` file found!", ephemeral=True)
            return
        settings = await self.settings_manager.get_settings(guild_id)
        chat_cog = self.bot.get_cog("Chat")
        if not chat_cog:
            await interaction.followup.send("❌ Chat cog not loaded.", ephemeral=True)
            return
        chain = await chat_cog.get_chain(guild_id, settings["markov_order"])
        learned_count = 0
        for line in lines:
            clean_line = line.strip()
            if clean_line:
                chain.learn(clean_line)
                learned_count += 1
        await self.db.save_full_chain(guild_id, chain.to_db_dict())
        await self.db.increment_stat(guild_id, "messages_learned", learned_count)
        await interaction.followup.send(f"🧠 Successfully loaded starter brain! Learned {learned_count} lines.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SettingsCog(bot, bot.db, bot.settings_manager))
