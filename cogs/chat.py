import discord
from discord.ext import commands
import random
import time
from engine.markov import MarkovChain

class Chat(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager
        
        # In-memory cache for Markov chains
        self.chains = {}
        # Track messages per channel for min_messages_before_respond
        self.channel_counters = {}
        # Track cooldowns per channel
        self.channel_cooldowns = {}

    async def get_chain(self, guild_id, order):
        if guild_id not in self.chains:
            self.chains[guild_id] = MarkovChain(order=order)
            self.chains[guild_id].chain = await self.db.get_markov(guild_id)
        return self.chains[guild_id]

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Automatically feeds the starter brain when joining a new server."""
        stats = await self.db.get_stats(guild.id)
        
        # If the bot has learned 0 messages in this server, it's brand new!
        if stats["messages_learned"] == 0:
            try:
                with open("training_data.txt", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                settings = await self.settings_manager.get_settings(guild.id)
                chain = await self.get_chain(guild.id, settings["markov_order"])
                
                for line in lines:
                    clean_line = line.strip()
                    if clean_line:
                        chain.learn(clean_line)
                
                # Save the newly learned chain to the database
                for key, values in chain.chain.items():
                    await self.db.save_markov_key(guild.id, key, values)
                
                await self.db.increment_stat(guild.id, "messages_learned", len(lines))
                print(f"Loaded starter brain for new guild: {guild.name}")
            except FileNotFoundError:
                print("No training_data.txt found, starting with an empty brain.")
            except Exception as e:
                print(f"Error loading starter brain: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author == self.bot.user:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        settings = await self.settings_manager.get_settings(guild_id)

        # Check ignored/allowed channels and users
        if channel_id in settings["ignored_channels"]: return
        if settings["allowed_channels"] and channel_id not in settings["allowed_channels"]: return
        if message.author.id in settings["ignored_users"]: return
        
        is_bot = message.author.bot
        if is_bot and not settings["learn_from_bots"]:
            return

        # 1. LEARNING
        if settings["learning_enabled"] and not message.content.startswith("/"):
            chain = await self.get_chain(guild_id, settings["markov_order"])
            chain.learn(message.content)
            words = message.content.lower().split()
            if len(words) >= chain.order:
                await self.db.increment_stat(guild_id, "messages_learned")

        # Don't respond to other bots or commands
        if is_bot or message.content.startswith("/"):
            return

        if not settings["response_enabled"]:
            return

        # Initialize counters
        if channel_id not in self.channel_counters:
            self.channel_counters[channel_id] = 0
            
        self.channel_counters[channel_id] += 1

        # 2. TRIGGER LOGIC
        should_respond = False
        is_mentioned = self.bot.user.mentioned_in(message)
        is_reply = (message.reference and message.reference.resolved and 
                    message.reference.resolved.author == self.bot.user)

        if is_mentioned and settings["trigger_on_mention"]:
            should_respond = True
        elif is_reply and settings["trigger_on_reply"]:
            should_respond = True
        elif random.random() < settings["response_chance"]:
            # Check constraints
            if channel_id in self.channel_cooldowns:
                if time.time() - self.channel_cooldowns[channel_id] < settings["cooldown_seconds"]:
                    should_respond = False
                elif self.channel_counters[channel_id] < settings["min_messages_before_respond"]:
                    should_respond = False
                else:
                    should_respond = True
            else:
                should_respond = True

        # 3. RESPONSE GENERATION
        if should_respond:
            chain = await self.get_chain(guild_id, settings["markov_order"])
            response = chain.generate(
                min_words=settings["min_response_words"],
                max_words=settings["max_response_words"],
                seed=message.content
            )
            
            # Fallback if generation fails
            if not response:
                response = chain.generate(
                    min_words=settings["min_response_words"],
                    max_words=settings["max_response_words"]
                )
            
            if response:
                prefix = settings["personality_prefix"]
                final_msg = f"{prefix} {response}".strip()
                
                await message.channel.send(final_msg)
                
                self.channel_cooldowns[channel_id] = time.time()
                self.channel_counters[channel_id] = 0
                await self.db.increment_stat(guild_id, "messages_sent")
                
                # BURST MODE
                if random.random() < settings["burst_chance"]:
                    burst_response = chain.generate(
                        min_words=settings["min_response_words"],
                        max_words=settings["max_response_words"]
                    )
                    if burst_response:
                        await message.channel.send(f"{prefix} {burst_response}".strip())

async def setup(bot):
    await bot.add_cog(Chat(bot, bot.db, bot.settings_manager))
