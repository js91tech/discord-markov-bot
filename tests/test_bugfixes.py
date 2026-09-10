import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.default_settings import DEFAULTS, parse_bool
from config.settings_manager import SettingsManager
from llm import _should_fallback, generate_llm_response
from utils import sanitize_message, search_gif
from cogs.settings_cog import build_roast_prompt
from cogs.chat import DEFAULT_PERSONALITY


class FakeDB:
    def __init__(self):
        self.settings = {}

    async def get_settings(self, guild_id):
        return self.settings.get(guild_id)

    async def save_settings(self, guild_id, settings_dict):
        self.settings[guild_id] = settings_dict

    async def get_memories(self, guild_id, user_id):
        return []

    async def get_consolidated_memory(self, guild_id):
        return None


class TestUtils(unittest.TestCase):
    def test_sanitize_strips_mass_pings(self):
        self.assertNotIn("@everyone", sanitize_message("hello @everyone world"))

    def test_sanitize_truncates_long_messages(self):
        self.assertLessEqual(len(sanitize_message("x" * 3000)), 1953)


class TestLLMFallback(unittest.TestCase):
    def test_should_fallback_on_billing_errors(self):
        self.assertTrue(_should_fallback(402, ""))
        self.assertTrue(_should_fallback(429, ""))
        self.assertTrue(_should_fallback(400, "insufficient credits"))

    def test_should_not_fallback_on_generic_400(self):
        self.assertFalse(_should_fallback(400, "bad request"))

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_falls_back_when_primary_returns_404(self):
        calls = []

        async def fake_request(model_name, messages):
            calls.append(model_name)
            if model_name == "primary-model":
                return None, 404, "model not found"
            return "fallback reply", 200, ""

        with patch("llm.OPENROUTER_API_KEY", "test-key"):
            with patch("llm._request_completion", side_effect=fake_request):
                result = self.run_async(generate_llm_response(
                    "system",
                    [{"role": "user", "content": "hi"}],
                    model_name="primary-model",
                    fallback_model="free-model",
                ))

        self.assertEqual(result, "fallback reply")
        self.assertEqual(calls, ["primary-model", "free-model"])

    def test_falls_back_on_network_error(self):
        calls = []

        async def fake_request(model_name, messages):
            calls.append(model_name)
            if model_name == "primary-model":
                return None, 0, "connection reset"
            return "fallback reply", 200, ""

        with patch("llm.OPENROUTER_API_KEY", "test-key"):
            with patch("llm._request_completion", side_effect=fake_request):
                result = self.run_async(generate_llm_response(
                    "system",
                    [{"role": "user", "content": "hi"}],
                    model_name="primary-model",
                    fallback_model="free-model",
                ))

        self.assertEqual(result, "fallback reply")
        self.assertEqual(calls, ["primary-model", "free-model"])

    def test_single_system_message_in_payload(self):
        captured = []

        async def fake_request(model_name, messages):
            captured.append(messages)
            return "ok", 200, ""

        with patch("llm.OPENROUTER_API_KEY", "test-key"):
            with patch("llm._request_completion", side_effect=fake_request):
                self.run_async(generate_llm_response(
                    "personality prompt",
                    [{"role": "user", "content": "hello"}],
                    model_name="primary-model",
                ))

        system_messages = [m for m in captured[0] if m["role"] == "system"]
        self.assertEqual(len(system_messages), 1)
        self.assertEqual(system_messages[0]["content"], "personality prompt")

    def test_fallback_strips_images(self):
        captured = []

        async def fake_request(model_name, messages):
            captured.append((model_name, messages))
            if model_name == "primary-model":
                return None, 404, "vision not available"
            return "saw the pic", 200, ""

        history = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Alice: check this out"},
                {"type": "image_url", "image_url": {"url": "https://example.com/pic.png"}},
            ],
        }]

        with patch("llm.OPENROUTER_API_KEY", "test-key"):
            with patch("llm._request_completion", side_effect=fake_request):
                result = self.run_async(generate_llm_response(
                    "system",
                    history,
                    model_name="primary-model",
                    fallback_model="free-model",
                ))

        self.assertEqual(result, "saw the pic")
        fallback_messages = captured[1][1]
        user_content = fallback_messages[1]["content"]
        self.assertIsInstance(user_content, str)
        self.assertIn("Alice: check this out", user_content)
        self.assertIn("[image]", user_content)
        self.assertNotIn("image_url", str(user_content))


class TestRoastPersonality(unittest.TestCase):
    def test_roast_uses_custom_personality(self):
        prompt = build_roast_prompt({"personality_prefix": "You are a pirate."}, "Alice")
        self.assertIn("You are a pirate.", prompt)
        self.assertIn("Alice", prompt)
        self.assertNotIn("insufferably sarcastic", prompt)

    def test_roast_uses_default_when_personality_empty(self):
        prompt = build_roast_prompt({"personality_prefix": "  "}, "Bob")
        self.assertIn(DEFAULT_PERSONALITY[:40], prompt)
        self.assertIn("Bob", prompt)


class TestSettingsManager(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_merges_new_defaults_for_old_guilds(self):
        db = FakeDB()
        db.settings[1] = {"response_enabled": False, "brain_mode": "markov"}
        manager = SettingsManager(db)

        settings = self.run_async(manager.get_settings(1))
        self.assertFalse(settings["response_enabled"])
        self.assertIn("fallback_llm_model", settings)
        self.assertEqual(settings["fallback_llm_model"], DEFAULTS["fallback_llm_model"])

    def test_normalizes_string_channel_ids(self):
        db = FakeDB()
        db.settings[2] = {"ignored_channels": ["111", "222"], "allowed_channels": ["333"]}
        manager = SettingsManager(db)
        settings = self.run_async(manager.get_settings(2))
        self.assertEqual(settings["ignored_channels"], [111, 222])
        self.assertEqual(settings["allowed_channels"], [333])
        self.assertIn(111, settings["ignored_channels"])


class TestBoolParsing(unittest.TestCase):
    def test_parse_bool_accepts_one(self):
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("on"))

    def test_parse_bool_rejects_zero(self):
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("off"))


class TestChatHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cogs.chat import Chat

        bot = MagicMock()
        db = MagicMock()
        db.get_memories = AsyncMock(return_value=["likes pizza"])
        db.get_consolidated_memory = AsyncMock(return_value={"summary": "chaotic server"})
        settings_manager = MagicMock()
        cls.chat = Chat(bot, db, settings_manager)

    def test_build_system_prompt_uses_personality_prefix(self):
        prompt = self.chat._build_system_prompt(
            {"personality_prefix": "You are a pirate."},
            author_name="Alice",
            user_memories=["likes pizza"],
            consolidated={"summary": "chaotic server"},
        )
        self.assertIn("You are a pirate.", prompt)
        self.assertNotIn("insufferably sarcastic", prompt)
        self.assertIn("Alice", prompt)
        self.assertIn("chaotic server", prompt)

    def test_duplicate_tracking_strips_mentions(self):
        guild_id = 99
        self.chat._record_bot_message(guild_id, "<@123> hello there")
        self.assertTrue(self.chat._is_recent_duplicate(guild_id, "hello there"))

    def test_pick_unique_fallback_avoids_recent(self):
        guild_id = 100
        quote = "i'm just here for the chaos honestly"
        self.chat._record_bot_message(guild_id, quote)
        with patch("cogs.chat.random.choice", side_effect=lambda items: items[0]):
            picked = self.chat._pick_unique_fallback(guild_id)
            self.assertNotEqual(picked.lower().strip(), quote)


class TestTriggerLogic(unittest.TestCase):
    def test_forced_response_should_bypass_cooldown(self):
        forced_response = True
        should_respond = True
        channel_id = 1
        channel_cooldowns = {1: 9999999999}
        cooldown_seconds = 10

        if should_respond and not forced_response:
            if channel_id in channel_cooldowns:
                if 9999999999 - channel_cooldowns[channel_id] < cooldown_seconds:
                    should_respond = False

        self.assertTrue(should_respond)

    def test_random_response_blocked_by_cooldown(self):
        forced_response = False
        should_respond = True
        channel_id = 1
        now = 1000.0
        channel_cooldowns = {1: now - 5}
        cooldown_seconds = 10

        if should_respond and not forced_response:
            if channel_id in channel_cooldowns:
                if now - channel_cooldowns[channel_id] < cooldown_seconds:
                    should_respond = False

        self.assertFalse(should_respond)


class TestGifSearch(unittest.TestCase):
    def test_search_gif_url_encodes_query(self):
        captured = {}

        class FakeResp:
            status = 200

            async def text(self):
                return ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def get(self, url, headers=None):
                captured["url"] = url
                return FakeResp()

        async def run():
            with patch("utils.aiohttp.ClientSession", return_value=FakeSession()):
                await search_gif("hello world")

        asyncio.run(run())
        self.assertIn("hello%20world", captured["url"])


if __name__ == "__main__":
    unittest.main()
