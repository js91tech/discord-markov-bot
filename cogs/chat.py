import discord
from discord.ext import commands
import random
import time
from engine.markov import MarkovChain
from utils import sanitize_message, search_gif

class Chat(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager
        
        self.chains = {}
        self.channel_counters = {}
        self.channel_cooldowns = {}
        
        # Short-term memory to prevent the bot from repeating itself or copy-pasting users
        self.bot_recent_messages = {} 

    async def get_chain(self, guild_id, order):
        if guild_id not in self.chains:
            self.chains[guild_id] = MarkovChain(order=order)
            self.chains[guild_id].chain = await self.db.get_markov(guild_id)
        return self.chains[guild_id]

    def _generate_unique_response(self, chain, seed, trigger_text, guild_id, min_words, max_words):
        """Generates a response and ensures it's not a direct copy of the trigger or recent bot messages."""
        recent_bot_msgs = self.bot_recent_messages.get(guild_id, [])
        response = None
        
        for _ in range(5): # Try up to 5 times to get a unique message
            generated = chain.generate(min_words=min_words, max_words=max_words, seed=seed)
            if generated:
                gen_clean = generated.lower().strip()
                trig_clean = trigger_text.lower().strip()
                
                # 1. Make sure it's not a word-for-word copy of what the user just said
                if gen_clean == trig_clean:
                    continue
                    
                # 2. Make sure the bot hasn't said this exact thing in its last 10 messages
                if gen_clean in recent_bot_msgs:
                    continue
                    
                # Success! It's unique enough.
                response = generated
                break
                
        # Update the bot's short-term memory with the new message
        if response:
            if guild_id not in self.bot_recent_messages:
                self.bot_recent_messages[guild_id] = []
            self.bot_recent_messages[guild_id].append(response.lower().strip())
            # Only keep the last 10 messages in memory to save RAM
            self.bot_recent_messages[guild_id] = self.bot_recent_messages[guild_id][-10:]
            
        return response

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        stats = await self.db.get_stats(guild.id)
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
                for key, values in chain.chain.items():
                    await self.db.save_markov_key(guild.id, key, values)
                await self.db.increment_stat(guild.id, "messages_learned", len(lines))
                print(f"Loaded starter brain for new guild: {guild.name}")
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Error loading starter brain: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author == self.bot.user:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        settings = await self.settings_manager.get_settings(guild_id)

        if channel_id in settings["ignored_channels"]: 
            return
        if settings["allowed_channels"] and channel_id not in settings["allowed_channels"]: 
            return
        if message.author.id in settings["ignored_users"]: 
            return
        
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

        if is_bot or message.content.startswith("/"):
            return

        if not settings["response_enabled"]:
            return

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
            # --- EMOJI REACTION FEATURE ---
            if random.random() < settings["reaction_chance"]:
                emoji_options = ['💀', '😭', '🔥', '💯', '🤣', '🙄', '👀', '🫡', '🤨']
                try:
                    await message.add_reaction(random.choice(emoji_options))
                    self.channel_cooldowns[channel_id] = time.time()
                    return 
                except discord.errors.HTTPException:
                    pass 

            # --- FAKE TYPING FEATURE ---
            async with message.channel.typing():
                use_reply = is_reply or (random.random() < settings["random_reply_chance"])
                use_mention = is_mentioned or (random.random() < settings["random_mention_chance"])
                use_gif = (random.random() < settings["gif_chance"])

                final_content = None
                reference = message if use_reply else None

                if use_gif:
                    search_words = [w for w in message.content.lower().split() if len(w) > 3]
                    search_query = random.choice(search_words) if search_words else "meme"
                    gif_url = await search_gif(search_query)
                    
                    if gif_url:
                        final_content = f"{message.author.mention} " if use_mention else ""
                        final_content += gif_url
                    else:
                        use_gif = False
                
                if not use_gif:
                    chain = await self.get_chain(guild_id, settings["markov_order"])
                    
                    # Use the new deduplication generator
                    response = self._generate_unique_response(
                        chain=chain,
                        seed=message.content,
                        trigger_text=message.content,
                        guild_id=guild_id,
                        min_words=settings["min_response_words"],
                        max_words=settings["max_response_words"]
                    )
                    
                    if response:
                        prefix = settings["personality_prefix"]
                        base_text = f"{prefix} {response}".strip()
                        base_text = sanitize_message(base_text)
                        final_content = f"{message.author.mention} {base_text}" if use_mention else base_text

                # Send the message
                if final_content:
                    try:
                        await message.channel.send(final_content, reference=reference)
                        self.channel_cooldowns[channel_id] = time.time()
                        self.channel_counters[channel_id] = 0
                        await self.db.increment_stat(guild_id, "messages_sent")
                        
                        # BURST MODE
                        if not use_gif and random.random() < settings["burst_chance"]:
                            async with message.channel.typing():
                                chain = await self.get_chain(guild_id, settings["markov_order"])
                                # Burst message uses the generated response as the trigger text to avoid repeating it
                                burst_response = self._generate_unique_response(
                                    chain=chain,
                                    seed=None,
                                    trigger_text=final_content,
                                    guild_id=guild_id,
                                    min_words=settings["min_response_words"],
                                    max_words=settings["max_response_words"]
                                )
                                if burst_response:
                                    burst_text = sanitize_message(f"{settings['personality_prefix']} {burst_response}".strip())
                                    await message.channel.send(burst_text)
                    except discord.errors.HTTPException as e:
                        print(f"Error sending message: {e}")

async def setup(bot):
    await bot.add_cog(Chat(bot, bot.db, bot.settings_manager))
