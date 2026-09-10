# config/default_settings.py

TRUE_VALUES = {"true", "yes", "on", "1"}
FALSE_VALUES = {"false", "no", "off", "0"}
ID_LIST_KEYS = ("ignored_channels", "allowed_channels", "ignored_users")


# --- VALIDATORS ---
def is_bool(val):
    return str(val).lower() in TRUE_VALUES | FALSE_VALUES


def parse_bool(val):
    return str(val).lower() in TRUE_VALUES


def is_int(val):
    try:
        int(val)
        return True
    except ValueError:
        return False


def is_float(val):
    try:
        float(val)
        return True
    except ValueError:
        return False


# --- DEFAULTS ---
DEFAULTS = {
    "response_enabled": True,
    "cooldown_seconds": 10,
    "ignored_channels": [],
    "allowed_channels": [],
    "ignored_users": [],
    "trigger_on_mention": True,
    "trigger_on_reply": True,
    "conversation_window_seconds": 120,
    "indirect_reply_chance": 0.40,
    "reaction_chance": 0.05,
    "random_reply_chance": 0.30,
    "random_mention_chance": 0.10,
    "gif_chance": 0.10,
    "personality_prefix": "",
    "llm_model": "meta-llama/llama-3-8b-instruct",
    "fallback_llm_model": "google/gemma-2-9b-it:free",
    "response_chance": 0.15,
}

VALIDATORS = {
    "response_enabled": is_bool,
    "cooldown_seconds": is_int,
    "conversation_window_seconds": is_int,
    "indirect_reply_chance": is_float,
    "reaction_chance": is_float,
    "random_reply_chance": is_float,
    "random_mention_chance": is_float,
    "gif_chance": is_float,
    "response_chance": is_float,
    "trigger_on_mention": is_bool,
    "trigger_on_reply": is_bool,
}
