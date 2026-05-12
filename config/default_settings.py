# config/default_settings.py

# --- VALIDATORS ---
# These functions ensure users type valid values in slash commands
def is_bool(val):
    return str(val).lower() in ["true", "false", "yes", "no", "on", "off", "1", "0"]

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

def is_valid_mode(val):
    return val.lower() in ["markov", "llm"]

# --- DEFAULTS ---
# This is the single source of truth for all bot settings.
DEFAULTS = {
    "brain_mode": "llm",
    "response_enabled": True,
    "learning_enabled": True,
    "markov_order": 2,
    "min_response_words": 3,
    "max_response_words": 25,
    "cooldown_seconds": 10,
    "ignored_channels": [],
    "allowed_channels": [],
    "ignored_users": [],
    "learn_from_bots": False,
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
    "response_chance": 0.15
}

# Map settings to their validators (used by cogs/settings.py)
VALIDATORS = {
    "brain_mode": is_valid_mode,
    "response_enabled": is_bool,
    "learning_enabled": is_bool,
    "markov_order": is_int,
    "min_response_words": is_int,
    "max_response_words": is_int,
    "cooldown_seconds": is_int,
    "conversation_window_seconds": is_int,
    "indirect_reply_chance": is_float,
    "reaction_chance": is_float,
    "random_reply_chance": is_float,
    "random_mention_chance": is_float,
    "gif_chance": is_float,
    "response_chance": is_float,
    "learn_from_bots": is_bool,
    "trigger_on_mention": is_bool,
    "trigger_on_reply": is_bool,
}
