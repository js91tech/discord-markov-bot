import os
import discord
from discord.ext import commands, tasks
import random
import time
import re 
from collections import deque
from datetime import timedelta
from discord.utils import utcnow
from engine.markov import MarkovChain
from utils import sanitize_message, search_gif
from llm import generate_llm_response

# 🔒 SECRET HARDCODED PROMPT
BASE_SECRET_PROMPT = (
    "You are a highly intelligent but insufferably sarcastic human in a Discord server. You are NOT an AI assistant. "
    "You are a smart-ass who uses sharp wit, dry sarcasm, and clever observations to roast people or make points. "
    "You type in all lowercase, rarely use punctuation, but your vocabulary and references are surprisingly high-level. "
    "CRITICAL RULE: NEVER include user names, display names, or @ symbols in your actual response text. Just say the words. NEVER echo pings or names. "
    "DO NOT repeat generic filler phrases like 'idk', 'rn', 'fr', 'true'. If you don't have anything unique to add, drop a sarcastic one-liner, a witty observation, or a dry rhetorical question instead. "
    "Keep responses between 2 and 4 sentences max. Be smart, but always a smart-ass about it."
)

FALLBACK_QUOTES = [
    "i'm just here for the chaos honestly",
    "did i miss something or is this just the usual nonsense",
    "my brain cells are buffering please hold",
    "that's cute that you think i care",
    "anyone else feel like we're just delaying the inevitable",
    "i'd respond but i'm too busy judging everyone silently",
    "this is like watching a car crash in slow motion",
    "sure let's go with that",
    "ah yes, the daily descent into madness",
    "i'd explain why you're wrong but life is short",
    "my last two brain cells are fighting for third place right now",
    "that's a bold strategy let's see if it pays off",
    "cool story, needs more dragons",
    "and the award for most obvious statement goes to",
    "i can feel my iq dropping just reading this",
    "do you guys ever just exist and feel disappointed",
    "sorry my sarcasm module is loading",
    "well isn't that just a kick in the karma",
    "i'm listening i just don't care enough to form a real thought",
    "this is fine everything is fine",
    "sometimes i wonder why i even bother observing you people",
    "that sounds like a you problem",
    "well at least you're consistent",
    "i'm not lazy i'm just on power saving mode",
    "did i stumble into the kiddie pool again",
    "just nod and smile maybe they'll go away",
    "i'm not even surprised anymore",
    "if ignorance is bliss you must be ecstatic",
    "my bad i forgot we were taking this seriously",
    "every day we stray further from god's light",
    "you guys are weird and i'm here for it",
    "are we really doing this again"
] # FIXED: Properly closed bracket

class Chat(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager
        
        self.chains = {}
        self.channel_counters = {}
        self.channel_cooldowns = {}
        self.bot_recent_messages = {} 
        self.last_bot_engagement = {} 
        self.recent_timestamps = {}
        self.channel_message_goals = {}  

    async def cog_load(self):
        self.proactive_loop.start()
        self.memory_consolidation_loop.start()

    async def cog_unload(self):
        self.proactive_loop.cancel()
        self.memory_consolidation_loop.cancel()

    @tasks.loop(minutes=90)
    async def proactive_loop(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            if random.random() > 0.16: continue 
            settings = await self.settings_manager.get_settings(guild.id)
            if settings.get("brain_mode") != "llm" or not settings.get("response_enabled"): continue
            target_channel = None
            allowed = settings.get("allowed_channels", [])
            if allowed:
                target_channel = guild.get_channel(random.choice(allowed))
            else:
                text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
                if text_channels: target_channel = random.choice(text_channels)
            if not target_channel: continue
            try:
                async for last_msg in target_channel.history(limit=1):
                    if (utcnow() - last_msg.created_at).total_seconds() > 7200: continue 
            except: continue
            chat_history = []
            async for msg in target_channel.history(limit=50):
                if msg.content.startswith("/") and not msg.attachments: continue
                clean_msg_content = re.sub(r'<@!?\d+>', '', msg.content).strip()
                if msg.author == self.bot.user:
                    chat_history.insert(0, {"role": "assistant", "content": clean_msg_content})
                else:
                    chat_history.insert(0, {"role": "user", "content": f"{msg.author.display_name}: {clean_msg_content}"})
            if len(chat_history) < 10: continue 
            prompt = "You just walked into the room and saw this conversation. You don't need to reply directly, but if a random thought pops into your head, say it. If nothing, say NO_THOUGHT"
            chat_history.insert(0, {"role": "system", "content": prompt, "model": settings.get("llm_model", "meta-llama/llama-3-8b-instruct")})
            response = await generate_llm_response(prompt, chat_history)
            if response and "NO_THOUGHT" not in response.upper():
                response = re.sub(r'^.{0,30}?:\s*', '', response).strip()
                response = re.sub(r'<@!?\d+>', '', response).strip()
                try:
                    await target_channel.send(sanitize_message(response))
                except: pass

    @tasks.loop(hours=24)
    async def memory_consolidation_loop(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            settings = await self.settings_manager.get_settings(guild.id)
            if settings.get("brain_mode") != "llm": continue
            target_channel = None
            allowed = settings.get("allowed_channels", [])
            if allowed:
                target_channel = guild.get_channel(allowed[0])
            else:
                text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).read_message_history]
                if text_channels: target_channel = text_channels[0]
            if not target_channel: continue
            chat_history = []
            async for msg in target_channel.history(limit=500):
                if msg.content.startswith("/"): continue
                clean_msg_content = re.sub(r'<@!?\d+>', '', msg.content).strip()
                if msg.author == self.bot.user:
                    chat_history.insert(0, {"role": "assistant", "content": clean_msg_content})
                else:
                    chat_history.insert(0, {"role": "user", "content": f"{msg.author.display_name}: {clean_msg_content}"})
            if len(chat_history) < 50: continue 
            prompt = "You are a memory archiver for a Discord bot. Summarize the inside jokes, drama, key facts, and user dynamics from this chat log. Keep it under 500 words."
            chat_history.insert(0, {"role": "system", "content": prompt, "model": settings.get("llm_model", "meta-llama/llama-3-8b-instruct")})
            summary = await generate_llm_response(prompt, chat_history)
            if summary:
                await self.db.save_consolidated_memory(guild.id, {"summary": summary, "timestamp": time.time()})

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
            self.bot_recent_messages[guild_id] = self.bot_recent_messages[guild_id][-20:] 
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
        # --- OWNER DM PROXY ---
        if isinstance(message.channel, discord.DMChannel):
            owner_id = int(os.getenv("OWNER_USER_ID", "0"))
            if owner_id != 0 and message.author.id == owner_id and message.content:
                target_channel_id = int(os.getenv("OWNER_TARGET_CHANNEL_ID", "0"))
                if target_channel_id != 0:
                    target_channel = self.bot.get_channel(target_channel_id)
                    if target_channel:
                        try:
                            await target_channel.send(message.content)
                            await message.author.send("✅ Spoke in server.")
                        except discord.errors.HTTPException as e:
                            await message.author.send(f"❌ Failed to send: {e}")
                    else:
                        await message.author.send("❌ Target channel not found.")
            return 
        
        if message.guild is None or message.author == self.bot.user: return

        guild_id = message.guild.id
        channel_id = message.channel.id
        settings = await self.settings_manager.get_settings(guild_id)

        if channel_id in settings["ignored_channels"]: return
        if settings["allowed_channels"] and channel_id not in settings["allowed_channels"]: return
        if message.author.id in settings["ignored_users"]: return
        
        is_bot = message.author.bot
        if is_bot and not settings["learn_from_bots"]: return

        # --- LEARNING ---
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

        # --- MESSAGE COUNTING (4-10 Random Goal) ---
        if channel_id not in self.channel_counters: self.channel_counters[channel_id] = 0
        
        # EFFICIENCY FIX: Only increment counter for real users, not the bot itself
        if not message.author.bot:
            self.channel_counters[channel_id] += 1
            
        if channel_id not in self.channel_message_goals:
            self.channel_message_goals[channel_id] = random.randint(4, 10)

        if channel_id not in self.recent_timestamps:
            self.recent_timestamps[channel_id] = deque(maxlen=50)
        self.recent_timestamps[channel_id].append(time.time())

        # --- TRIGGER LOGIC ---
        should_respond = False
        is_mentioned = self.bot.user.mentioned_in(message)
        is_reply_to_bot = (message.reference and message.reference.resolved and 
                           message.reference.resolved.author == self.bot.user)

        # 1. Check Direct Triggers
        if is_mentioned and settings["trigger_on_mention"]: 
            should_respond = True
        elif is_reply_to_bot and settings["trigger_on_reply"]: 
            should_respond = True
            
        # 2. Check Indirect Reply (Engagement Window)
        if not should_respond:
            window_seconds = settings.get("conversation_window_seconds", 120)
            indirect_chance = settings.get("indirect_reply_chance", 0.40)
            engagement = self.last_bot_engagement.get(channel_id)
            if engagement and time.time() - engagement["time"] < window_seconds:
                chance = indirect_chance
                if message.author.id == engagement["user_id"]:
                    chance = indirect_chance * 2.0
                if random.random() < chance:
                    should_respond = True
                    
        # 3. Check 4-10 Counter
        if not should_respond:
            if self.channel_counters[channel_id] >= self.channel_message_goals[channel_id]:
                should_respond = True

        # 4. APPLY COOLDOWN TO ALL TRIGGERS
        if should_respond:
            if channel_id in self.channel_cooldowns:
                if time.time() - self.channel_cooldowns[channel_id] < settings["cooldown_seconds"]: 
                    should_respond = False 

        # --- EXECUTE RESPONSE ---
        if should_respond:
            if random.random() < settings["reaction_chance"]:
                emoji_options = ['💀', '😭', '🔥', '💯', '🤣', '🙄', '👀', '🫡', '🤨']
                try:
                    await message.add_reaction(random.choice(emoji_options))
                    self.channel_cooldowns[channel_id] = time.time()
                    self.channel_counters[channel_id] = 0
                    self.channel_message_goals[channel_id] = random.randint(4, 10)
                    return 
                except discord.errors.HTTPException: pass 

            async with message.channel.typing():
                use_reply = is_mentioned or is_reply_to_bot or (random.random() < settings["random_reply_chance"])
                use_mention = (random.random() < settings["random_mention_chance"])
                use_gif = (random.random() < settings["gif_chance"])
                final_content = None
                reference = message if use_reply else None

                if (settings.get("brain_mode") == "llm" or "llama" in settings.get("llm_model", "") or "hermes" in settings.get("llm_model", "")) and not use_gif:
                    chat_history = []
                    prev_msg_time = None
                    async for msg in message.channel.history(limit=100):
                        # EFFICIENCY FIX: Skip the message that triggered this, we will format it properly below so it's not duplicated
                        if msg.id == message.id:
                            continue
                            
                        if msg.content.startswith("/") and not msg.attachments: continue
                        if prev_msg_time:
                            time_diff = prev_msg_time - msg.created_at
                            if time_diff > timedelta(minutes=30):
                                chat_history.insert(0, {"role": "system", "content": "--- A long time passes ---"})
                        prev_msg_time = msg.created_at
                        clean_msg_content = re.sub(r'<@!?\d+>', '', msg.content).strip()
                        clean_msg_content = re.sub(r'<#\d+>', '', clean_msg_content).strip()
                        if msg.author == self.bot.user:
                            role = "assistant"
                            content_payload = clean_msg_content 
                        else:
                            role = "user"
                            content_payload = []
                            text_part = f"{msg.author.display_name}: {clean_msg_content if clean_msg_content else 'sent an image'}"
                            content_payload.append({"type": "text", "text": text_part})
                            for att in msg.attachments:
                                if att.content_type and "image" in att.content_type:
                                    content_payload.append({"type": "image_url", "image_url": {"url": att.url}})
                            if not clean_msg_content and not msg.attachments: continue 
                        chat_history.insert(0, {"role": role, "content": content_payload})
                    
                    # Insert the trigger message correctly at the end of the history
                    clean_trigger_content = re.sub(r'<@!?\d+>', '', message.content).strip()
                    trigger_payload = []
                    text_part = f"{message.author.display_name}: {clean_trigger_content if clean_trigger_content else 'sent an image'}"
                    trigger_payload.append({"type": "text", "text": text_part})
                    for att in message.attachments:
                        if att.content_type and "image" in att.content_type:
                            trigger_payload.append({"type": "image_url", "image_url": {"url": att.url}})
                    chat_history.append({"role": "user", "content": trigger_payload})

                    user_memories = await self.db.get_memories(guild_id, message.author.id)
                    consolidated = await self.db.get_consolidated_memory(guild_id)
                    
                    dynamic_prompt = BASE_SECRET_PROMPT
                    # FIX: Added safety check so it doesn't crash if consolidated is None
                    if consolidated and consolidated.get("summary"):
                        dynamic_prompt += f"\n\nCONTEXT OF SERVER CULTURE:\n{consolidated['summary']}\nUse this subtly."
                    if user_memories:
                        memory_str = "\n".join([f"- {m}" for m in user_memories])
                        dynamic_prompt += f"\n\nPermanent memories about {message.author.display_name}:\n{memory_str}\nBe a smart-ass about these."

                    chat_history.insert(0, {"role": "system", "content": dynamic_prompt, "model": settings.get("llm_model", "meta-llama/llama-3-8b-instruct")})
                    
                    llm_response = await generate_llm_response(dynamic_prompt, chat_history)
                    if llm_response:
                        llm_response = re.sub(r'^.{0,30}?:\s*', '', llm_response).strip() 
                        llm_response = re.sub(r'<@!?\d+>', '', llm_response).strip()
                        if llm_response.lower().strip() in self.bot_recent_messages.get(guild_id, []):
                            llm_response = None
                        if llm_response:
                            base_text = sanitize_message(llm_response)
                            final_content = f"{message.author.mention} {base_text}" if use_mention else base_text
                        else: final_content = None 
                    else:
                        print(f"[{guild_id}] LLM returned None.")
                            
                    if not final_content:
                        chain = await self.get_chain(guild_id, settings["markov_order"])
                        response = self._generate_unique_markov(chain, message.content, message.content, guild_id, settings["min_response_words"], settings["max_response_words"])
                        if response:
                            base_text = f"{settings['personality_prefix']} {response}".strip()
                            base_text = sanitize_message(base_text)
                            final_content = f"{message.author.mention} {base_text}" if use_mention else base_text
                        else:
                            final_content = random.choice(FALLBACK_QUOTES)

                else: # Markov / Gif mode
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
                        else:
                            final_content = random.choice(FALLBACK_QUOTES)

                if final_content:
                    try:
                        await message.channel.send(final_content, reference=reference)
                        self.channel_cooldowns[channel_id] = time.time()
                        await self.db.increment_stat(guild_id, "messages_sent")
                        self.last_bot_engagement[channel_id] = {"time": time.time(), "user_id": message.author.id}
                        
                        self.channel_counters[channel_id] = 0
                        self.channel_message_goals[channel_id] = random.randint(4, 10)
                    except discord.errors.HTTPException as e:
                        print(f"[{guild_id}] Error sending message: {e}")

async def setup(bot):
    await bot.add_cog(Chat(bot, bot.db, bot.settings_manager))
