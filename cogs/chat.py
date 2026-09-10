import os
import discord
from discord.ext import commands, tasks
import random
import time
import re
from collections import deque
from datetime import timedelta
from discord.utils import utcnow
from utils import sanitize_message, search_gif
from llm import generate_llm_response

DEFAULT_PERSONALITY = (
    "You are a highly intelligent but insufferably sarcastic human in a Discord server. You are NOT an AI assistant. "
    "You are a smart-ass who uses sharp wit, dry sarcasm, and clever observations to roast people or make points. "
    "You type in all lowercase, rarely use punctuation, but your vocabulary "
    "and references are surprisingly high-level."
)

RESPONSE_RULES = (
    "CRITICAL RULES:\n"
    "- NEVER include user names, display names, or @ symbols in your response text.\n"
    "- NEVER echo pings or names.\n"
    "- DO NOT repeat generic filler phrases like 'idk', 'rn', 'fr', 'true'.\n"
    "- DO NOT reuse or closely paraphrase any of your recent replies in this channel.\n"
    "- Vary your wording every time — never fall back on the same catchphrases.\n"
    "- If you have nothing unique to add, drop a fresh one-liner, observation, or rhetorical question.\n"
    "- Keep responses between 2 and 4 sentences max."
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
]


class Chat(commands.Cog):
    def __init__(self, bot, db, settings_manager):
        self.bot = bot
        self.db = db
        self.settings_manager = settings_manager

        self.channel_cooldowns = {}
        self.bot_recent_messages = {}
        self.last_bot_engagement = {}
        self.recent_timestamps = {}

    def _build_system_prompt(self, settings, author_name=None, user_memories=None, consolidated=None,
                             recent_replies=None):
        personality = settings.get("personality_prefix", "").strip()
        if personality:
            prompt = f"{personality}\n\n{RESPONSE_RULES}"
        else:
            prompt = f"{DEFAULT_PERSONALITY}\n\n{RESPONSE_RULES}"

        if consolidated and consolidated.get("summary"):
            prompt += f"\n\nCONTEXT OF SERVER CULTURE:\n{consolidated['summary']}\nUse this subtly."
        if user_memories and author_name:
            memory_str = "\n".join([f"- {m}" for m in user_memories])
            prompt += f"\n\nPermanent memories about {author_name}:\n{memory_str}\nReference these naturally."
        if recent_replies:
            recent_str = "\n".join([f"- {r}" for r in recent_replies[-5:]])
            prompt += f"\n\nYou recently said these — do NOT repeat or closely paraphrase them:\n{recent_str}"
        return prompt

    def _record_bot_message(self, guild_id, text):
        clean = re.sub(r'<@!?\d+>', '', text).lower().strip()
        if not clean:
            return
        if guild_id not in self.bot_recent_messages:
            self.bot_recent_messages[guild_id] = []
        self.bot_recent_messages[guild_id].append(clean)
        self.bot_recent_messages[guild_id] = self.bot_recent_messages[guild_id][-30:]

    def _is_recent_duplicate(self, guild_id, text):
        clean = re.sub(r'<@!?\d+>', '', text).lower().strip()
        return clean in self.bot_recent_messages.get(guild_id, [])

    def _pick_unique_fallback(self, guild_id):
        recent = set(self.bot_recent_messages.get(guild_id, []))
        available = [q for q in FALLBACK_QUOTES if q.lower().strip() not in recent]
        if not available:
            available = FALLBACK_QUOTES
        return random.choice(available)

    async def _generate_llm_reply(self, settings, chat_history, guild_id, author_id, author_name):
        user_memories = await self.db.get_memories(guild_id, author_id)
        consolidated = await self.db.get_consolidated_memory(guild_id)
        recent_replies = self.bot_recent_messages.get(guild_id, [])
        model_name = settings.get("llm_model", "meta-llama/llama-3-8b-instruct")
        fallback_model = settings.get("fallback_llm_model", "google/gemma-2-9b-it:free")

        for attempt in range(3):
            dynamic_prompt = self._build_system_prompt(
                settings,
                author_name=author_name,
                user_memories=user_memories,
                consolidated=consolidated,
                recent_replies=recent_replies if attempt > 0 else None,
            )
            chat_history_with_prompt = [{"role": "system", "content": dynamic_prompt}, *chat_history]
            candidate = await generate_llm_response(
                dynamic_prompt,
                chat_history_with_prompt,
                model_name=model_name,
                fallback_model=fallback_model,
            )
            if not candidate:
                continue
            candidate = re.sub(r'^.{0,30}?:\s*', '', candidate).strip()
            candidate = re.sub(r'<@!?\d+>', '', candidate).strip()
            if candidate and not self._is_recent_duplicate(guild_id, candidate):
                return candidate
        return None

    async def _build_channel_history(self, message, limit=100):
        chat_history = []
        prev_msg_time = None
        async for msg in message.channel.history(limit=limit):
            if msg.id == message.id:
                continue
            if msg.content.startswith("/") and not msg.attachments:
                continue
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
                text_part = (
                    f"{msg.author.display_name}: "
                    f"{clean_msg_content if clean_msg_content else 'sent an image'}"
                )
                content_payload.append({"type": "text", "text": text_part})
                for att in msg.attachments:
                    if att.content_type and "image" in att.content_type:
                        content_payload.append({"type": "image_url", "image_url": {"url": att.url}})
                if not clean_msg_content and not msg.attachments:
                    continue
            chat_history.insert(0, {"role": role, "content": content_payload})

        clean_trigger_content = re.sub(r'<@!?\d+>', '', message.content).strip()
        trigger_payload = []
        text_part = (
            f"{message.author.display_name}: "
            f"{clean_trigger_content if clean_trigger_content else 'sent an image'}"
        )
        trigger_payload.append({"type": "text", "text": text_part})
        for att in message.attachments:
            if att.content_type and "image" in att.content_type:
                trigger_payload.append({"type": "image_url", "image_url": {"url": att.url}})
        chat_history.append({"role": "user", "content": trigger_payload})

        bot_msg_seen = 0
        trimmed_history = []
        for entry in reversed(chat_history):
            if entry["role"] == "assistant":
                bot_msg_seen += 1
                if bot_msg_seen > 8:
                    continue
            trimmed_history.insert(0, entry)
        return trimmed_history

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
            if random.random() > 0.16:
                continue
            settings = await self.settings_manager.get_settings(guild.id)
            if not settings.get("response_enabled"):
                continue
            target_channel = None
            allowed = settings.get("allowed_channels", [])
            if allowed:
                target_channel = guild.get_channel(random.choice(allowed))
            else:
                text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
                if text_channels:
                    target_channel = random.choice(text_channels)
            if not target_channel:
                continue
            try:
                async for last_msg in target_channel.history(limit=1):
                    if (utcnow() - last_msg.created_at).total_seconds() > 7200:
                        continue
            except Exception:
                continue
            chat_history = []
            async for msg in target_channel.history(limit=50):
                if msg.content.startswith("/") and not msg.attachments:
                    continue
                clean_msg_content = re.sub(r'<@!?\d+>', '', msg.content).strip()
                if msg.author == self.bot.user:
                    chat_history.insert(0, {"role": "assistant", "content": clean_msg_content})
                else:
                    chat_history.insert(
                        0, {"role": "user", "content": f"{msg.author.display_name}: {clean_msg_content}"})
            if len(chat_history) < 10:
                continue
            personality = settings.get("personality_prefix", "").strip() or DEFAULT_PERSONALITY
            prompt = (
                f"{personality}\n\n{RESPONSE_RULES}\n\n"
                "You just walked into the room and saw this conversation. "
                "You don't need to reply directly, but if a random thought "
                "pops into your head, say it. If nothing, say NO_THOUGHT"
            )
            response = await generate_llm_response(
                prompt,
                chat_history,
                model_name=settings.get("llm_model"),
                fallback_model=settings.get("fallback_llm_model"),
            )
            if response and "NO_THOUGHT" not in response.upper():
                response = re.sub(r'^.{0,30}?:\s*', '', response).strip()
                response = re.sub(r'<@!?\d+>', '', response).strip()
                if self._is_recent_duplicate(guild.id, response):
                    continue
                try:
                    await target_channel.send(sanitize_message(response))
                    self._record_bot_message(guild.id, response)
                except Exception:
                    pass

    @tasks.loop(hours=24)
    async def memory_consolidation_loop(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            settings = await self.settings_manager.get_settings(guild.id)
            target_channel = None
            allowed = settings.get("allowed_channels", [])
            if allowed:
                target_channel = guild.get_channel(allowed[0])
            else:
                text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).read_message_history]
                if text_channels:
                    target_channel = text_channels[0]
            if not target_channel:
                continue
            chat_history = []
            async for msg in target_channel.history(limit=500):
                if msg.content.startswith("/"):
                    continue
                clean_msg_content = re.sub(r'<@!?\d+>', '', msg.content).strip()
                if msg.author == self.bot.user:
                    chat_history.insert(0, {"role": "assistant", "content": clean_msg_content})
                else:
                    chat_history.insert(
                        0, {"role": "user", "content": f"{msg.author.display_name}: {clean_msg_content}"})
            if len(chat_history) < 50:
                continue
            prompt = (
                "You are a memory archiver for a Discord bot. Summarize the "
                "inside jokes, drama, key facts, and user dynamics from this "
                "chat log. Keep it under 500 words."
            )
            summary = await generate_llm_response(
                prompt,
                chat_history,
                model_name=settings.get("llm_model"),
                fallback_model=settings.get("fallback_llm_model"),
            )
            if summary:
                await self.db.save_consolidated_memory(guild.id, {"summary": summary, "timestamp": time.time()})

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
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
        if message.author.bot:
            return
        if message.content.startswith("/"):
            return
        if not settings["response_enabled"]:
            return

        if channel_id not in self.recent_timestamps:
            self.recent_timestamps[channel_id] = deque(maxlen=50)
        self.recent_timestamps[channel_id].append(time.time())

        should_respond = False
        is_mentioned = self.bot.user.mentioned_in(message)
        is_reply_to_bot = (message.reference and message.reference.resolved and
                           message.reference.resolved.author == self.bot.user)

        if is_mentioned and settings["trigger_on_mention"]:
            should_respond = True
        elif is_reply_to_bot and settings["trigger_on_reply"]:
            should_respond = True

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

        if not should_respond:
            if random.random() < settings.get("response_chance", 0.15):
                should_respond = True

        if should_respond:
            if channel_id in self.channel_cooldowns:
                if time.time() - self.channel_cooldowns[channel_id] < settings["cooldown_seconds"]:
                    should_respond = False

        if should_respond:
            if random.random() < settings["reaction_chance"]:
                emoji_options = ['💀', '😭', '🔥', '💯', '🤣', '🙄', '👀', '🫡', '🤨']
                try:
                    await message.add_reaction(random.choice(emoji_options))
                    self.channel_cooldowns[channel_id] = time.time()
                    return
                except discord.errors.HTTPException:
                    pass

            async with message.channel.typing():
                use_reply = is_mentioned or is_reply_to_bot or (random.random() < settings["random_reply_chance"])
                use_mention = random.random() < settings["random_mention_chance"]
                use_gif = random.random() < settings["gif_chance"]
                final_content = None
                reference = message if use_reply else None

                if use_gif:
                    search_words = [w for w in message.content.lower().split() if len(w) > 3]
                    search_query = random.choice(search_words) if search_words else "meme"
                    gif_url = await search_gif(search_query)
                    if gif_url:
                        final_content = f"{message.author.mention} " if use_mention else ""
                        final_content += gif_url

                if not final_content:
                    chat_history = await self._build_channel_history(message)
                    llm_response = await self._generate_llm_reply(
                        settings,
                        chat_history,
                        guild_id,
                        message.author.id,
                        message.author.display_name,
                    )
                    if llm_response:
                        base_text = sanitize_message(llm_response)
                        final_content = f"{message.author.mention} {base_text}" if use_mention else base_text
                    else:
                        print(f"[{guild_id}] LLM returned None or duplicate.")
                        final_content = self._pick_unique_fallback(guild_id)

                if final_content:
                    try:
                        await message.channel.send(final_content, reference=reference)
                        self._record_bot_message(guild_id, final_content)
                        self.channel_cooldowns[channel_id] = time.time()
                        await self.db.increment_stat(guild_id, "messages_sent")
                        self.last_bot_engagement[channel_id] = {"time": time.time(), "user_id": message.author.id}
                    except discord.errors.HTTPException as e:
                        print(f"[{guild_id}] Error sending message: {e}")


async def setup(bot):
    await bot.add_cog(Chat(bot, bot.db, bot.settings_manager))
