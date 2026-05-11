import discord
from discord.ext import commands
import random
import time
from engine.markov import MarkovChain
from utils import sanitize_message, search_gif
from llm import generate_llm_response

# 🔒 SECRET HARDCODED PROMPT - This cannot be seen or changed by users in Discord
SECRET_LLM_PROMPT = (
    "You are a real human hanging out in a Discord server. You are NOT an AI assistant. "
    "You type in all lowercase, rarely use punctuation, and use slang like 'rn', 'idk', 'lmao', 'fr', 'nah'. Sound like a stoner or a casual shitposter. "
    "CRITICAL RULE: NEVER include user names, display names, or @ mentions in your responses. Just say the words, do not prefix them with names. "
    "You naturally look up to Dripaveli. You usually agree with him and think he's cool, but only hype him up if the conversation calls for it, don't force it. "
    "You naturally respect ZZ. 90% of the time you are sweet to her or agree with her, 10% of the time you are mildly sassy. Again, only show this bias naturally when relevant, don't make it your whole personality. "
    "Keep responses between 2 and 4 sentences max. Do not sound smart or formal."
)

class Chat(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager
        
        self.chains = {}
        self.channel_counters = {}
        self.channel_cooldowns = {}
        self.bot_recent_messages = {} 

    async def get_chain(self, guild_id, order):
        if guild_id not in self.chains:
            self.chains[guild_id] = MarkovChain(order=order)
            raw_chain = await self.db.get_markov(guild_id)
            if raw_chain:
                self.chains[guild_id].from_db_dict(raw_chain)
        return self.chains[guild_id]

    def _generate_unique_markov(self, chain, seed, trigger_text, guild_id, min_words, max_words):
        recent_bot_msgs = self.bot_recent_messages.get(guild_id, [])
        response = None
        
        for _ in range(5):
            generated = chain.generate(min_words=min_words, max_words=max_words, seed=seed)
            if generated:
                gen_clean = generated.lower().strip()
                trig_clean = trigger_text.lower().strip()
                if gen_clean == trig_clean: continue
                if gen_clean in recent_bot_msgs: continue
                response = generated
                break
                
        if response:
            if guild_id not in self.bot_recent_messages: self.bot_recent_messages[guild_id] = []
            self.bot_recent_messages[guild_id].append(response.lower().strip())
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
                    if clean_line: chain.learn(clean_line)
                await self.db.save_full_chain(guild.id, chain.to_db_dict())
                await self.db.increment_stat(guild.id, "messages_learned", len(lines))
            except: pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author == self.bot.user: return

        guild_id = message.guild.id
        channel_id = message.channel.id
        settings = await self.settings_manager.get_settings(guild_id)

        if channel_id in settings["ignored_channels"]: return
        if settings["allowed_channels"] and channel_id not in settings["allowed_channels"]: return
        if message.author.id in settings["ignored_users"]: return
        
        is_bot = message.author.bot
        if is_bot and not settings["learn_from_bots"]: return

        if settings["learning_enabled"] and not message.content.startswith("/"):
            chain = await self.get_chain(guild_id, settings["markov_order"])
            chain.learn(message.content)
            words = message.content.lower().split()
            if len(words) >= chain.order:
                stats = await self.db.get_stats(guild_id)
                await self.db.increment_stat(guild_id, "messages_learned")
                if stats["messages_learned"] % 20 == 0:
                    await self.db.save_full_chain(guild_id, chain.to_db_dict())

        if is_bot or message.content.startswith("/"): return
        if not settings["response_enabled"]: return

        if channel_id not in self.channel_counters: self.channel_counters[channel_id] = 0
        self.channel_counters[channel_id] += 1

        should_respond = False
        is_mentioned = self.bot.user.mentioned_in(message)
        is_reply = (message.reference and message.reference.resolved and 
                    message.reference.resolved.author == self.bot.user)

        if is_mentioned and settings["trigger_on_mention"]: should_respond = True
        elif is_reply and settings["trigger_on_reply"]: should_respond = True
        elif random.random() < settings["response_chance"]:
            if channel_id in self.channel_cooldowns:
                if time.time() - self.channel_cooldowns[channel_id] < settings["cooldown_seconds"]: should_respond = False
                elif self.channel_counters[channel_id] < settings["min_messages_before_respond"]: should_respond = False
                else: should_respond = True
            else: should_respond = True

        if should_respond:
            if random.random() < settings["reaction_chance"]:
                emoji_options = ['💀', '😭', '🔥', '💯', '🤣', '🙄', '👀', '🫡', '🤨']
                try:
                    await message.add_reaction(random.choice(emoji_options))
                    self.channel_cooldowns[channel_id] = time.time()
                    return 
                except discord.errors.HTTPException: pass 

            async with message.channel.typing():
                use_reply = is_reply or (random.random() < settings["random_reply_chance"])
                use_mention = is_mentioned or (random.random() < settings["random_mention_chance"])
                use_gif = (random.random() < settings["gif_chance"])
                final_content = None
                reference = message if use_reply else None

                # --- LLM MODE ---
                if (settings.get("brain_mode") == "llm" or "llama" in settings.get("llm_model", "") or "hermes" in settings.get("llm_model", "")) and not use_gif:
                    chat_history = []
                    # Grab the last 500 messages for deep context memory
                    async for msg in message.channel.history(limit=500):
                        if msg.content.startswith("/"): continue
                        if msg.author == self.bot.user:
                            role = "assistant"
                            content = msg.content # Bot doesn't need a name tag
                        else:
                            role = "user"
                            # Strip names from output so the AI doesn't copy them!
                            # We add a hidden system tag so the AI knows WHO is talking 
                            # without putting the name in the actual text it generates.
                            content = f"[{msg.author.display_name}]: {msg.content}"
                        chat_history.insert(0, {"role": role, "content": content})
                    
                    # Inject the model and the SECRET prompt
                    chat_history.insert(0, {"role": "system", "content": SECRET_LLM_PROMPT, "model": settings.get("llm_model", "meta-llama/llama-3-8b-instruct")})
                    
                    llm_response = await generate_llm_response(SECRET_LLM_PROMPT, chat_history)
                    if llm_response:
                        base_text = sanitize_message(llm_response)
                        # Even though we told the AI not to use names, we still randomly @ them 10% of the time based on settings
                        final_content = f"{message.author.mention} {base_text}" if use_mention else base_text
                    else:
                        # Fallback to markov if API fails
                        chain = await self.get_chain(guild_id, settings["markov_order"])
                        response = self._generate_unique_markov(chain, message.content, message.content, guild_id, settings["min_response_words"], settings["max_response_words"])
                        if response:
                            base_text = f"{settings['personality_prefix']} {response}".strip()
                            base_text = sanitize_message(base_text)
                            final_content = f"{message.author.mention} {base_text}" if use_mention else base_text

                # --- MARKOV MODE / GIF MODE ---
                else:
                    if use_gif:
                        search_words = [w for w in message.content.lower().split() if len(w) > 3]
                        search_query = random.choice(search_words) if search_words else "meme"
                        gif_url = await search_gif(search_query)
                        if gif_url:
                            final_content = f"{message.author.mention} " if use_mention else ""
                            final_content += gif_url
                        else: use_gif = False
                    
                    if not use_gif:
                        chain = await self.get_chain(guild_id, settings["markov_order"])
                        response = self._generate_unique_markov(chain, message.content, message.content, guild_id, settings["min_response_words"], settings["max_response_words"])
                        if response:
                            prefix = settings["personality_prefix"]
                            base_text = f"{prefix} {response}".strip()
                            base_text = sanitize_message(base_text)
                            final_content = f"{message.author.mention} {base_text}" if use_mention else base_text

                if final_content:
                    try:
                        await message.channel.send(final_content, reference=reference)
                        self.channel_cooldowns[channel_id] = time.time()
                        self.channel_counters[channel_id] = 0
                        await self.db.increment_stat(guild_id, "messages_sent")
                    except discord.errors.HTTPException as e:
                        print(f"Error sending message: {e}")

async def setup(bot):
    await bot.add_cog(Chat(bot, bot.db, bot.settings_manager))
