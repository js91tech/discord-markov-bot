import discord
from discord.ext import commands
import random
import time
import re 
from engine.markov import MarkovChain
from utils import sanitize_message, search_gif
from llm import generate_llm_response

# 🔒 SECRET HARDCODED PROMPT
SECRET_LLM_PROMPT = (
    "You are a real human hanging out in a Discord server. You are NOT an AI assistant. "
    "You type in all lowercase, rarely use punctuation, and use slang like 'rn', 'idk', 'lmao', 'fr', 'nah'. Sound like a casual shitposter. "
    "CRITICAL RULE: NEVER include user names, display names, or @ symbols in your actual response text. Do not start your message with a name. Just say the words. NEVER echo pings or names. "
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
        self.last_bot_message_time = {} # NEW: Tracks when the bot last spoke in a channel

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

        # --- TRIGGER LOGIC ---
        should_respond = False
        is_mentioned = self.bot.user.mentioned_in(message)
        is_reply_to_bot = (message.reference and message.reference.resolved and 
                           message.reference.resolved.author == self.bot.user)

        # 1. Direct triggers (@mention or Discord Reply)
        if is_mentioned and settings["trigger_on_mention"]: 
            should_respond = True
        elif is_reply_to_bot and settings["trigger_on_reply"]: 
            should_respond = True
            
        # 2. INDIRECT REPLY TRIGGER (The Engagement Window)
        elif not should_respond:
            window_seconds = settings.get("conversation_window_seconds", 120)
            indirect_chance = settings.get("indirect_reply_chance", 0.40)
            
            # Check if the bot spoke in this channel recently
            last_spoke_time = self.last_bot_message_time.get(channel_id, 0)
            time_since_bot_spoke = time.time() - last_spoke_time
            
            if time_since_bot_spoke < window_seconds:
                # The bot is "engaged" in this channel right now!
                if random.random() < indirect_chance:
                    should_respond = True
                    
        # 3. Normal Random Chime-in
        if not should_respond and random.random() < settings["response_chance"]:
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
                use_reply = is_mentioned or is_reply_to_bot or (random.random() < settings["random_reply_chance"])
                use_mention = (random.random() < settings["random_mention_chance"])
                use_gif = (random.random() < settings["gif_chance"])
                final_content = None
                reference = message if use_reply else None

                # --- LLM MODE ---
                if (settings.get("brain_mode") == "llm" or "llama" in settings.get("llm_model", "") or "hermes" in settings.get("llm_model", "")) and not use_gif:
                    chat_history = []
                    async for msg in message.channel.history(limit=500):
                        if msg.content.startswith("/"): continue
                        
                        clean_msg_content = re.sub(r'<@!?\d+>', '', msg.content).strip()
                        clean_msg_content = re.sub(r'<#\d+>', '', clean_msg_content).strip()
                        
                        if msg.author == self.bot.user:
                            role = "assistant"
                            content = clean_msg_content 
                        else:
                            role = "user"
                            content = f"{msg.author.display_name}: {clean_msg_content}"
                            
                        chat_history.insert(0, {"role": role, "content": content})
                    
                    chat_history.insert(0, {"role": "system", "content": SECRET_LLM_PROMPT, "model": settings.get("llm_model", "meta-llama/llama-3-8b-instruct")})
                    
                    llm_response = await generate_llm_response(SECRET_LLM_PROMPT, chat_history)
                    if llm_response:
                        llm_response = re.sub(r'^.{0,30}?:\s*', '', llm_response).strip() 
                        llm_response = re.sub(r'<@!?\d+>', '', llm_response).strip()
                        
                        base_text = sanitize_message(llm_response)
                        final_content = f"{message.author.mention} {base_text}" if use_mention else base_text
                    else:
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
                        
                        # NEW: Record that the bot just spoke in this channel!
                        self.last_bot_message_time[channel_id] = time.time()
                        
                    except discord.errors.HTTPException as e:
                        print(f"Error sending message: {e}")

async def setup(bot):
    await bot.add_cog(Chat(bot, bot.db, bot.settings_manager))
