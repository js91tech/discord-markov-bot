DEFAULTS = {
    "response_chance": 0.05,
    "cooldown_seconds": 30,
    "min_messages_before_respond": 3,
    "markov_order": 2,
    "min_response_words": 4,
    "max_response_words": 40,
    "learn_from_bots": False,
    "trigger_on_mention": True,
    "trigger_on_reply": True,
    "personality_prefix": "",
    "ignored_channels": [],
    "allowed_channels": [],
    "ignored_users": [],
    "burst_chance": 0.1,
    "learning_enabled": True,
    "response_enabled": True
}

VALIDATORS = {
    "response_chance": lambda x: 0.0 <= float(x) <= 1.0,
    "cooldown_seconds": lambda x: int(x) > 0,
    "min_messages_before_respond": lambda x: int(x) > 0,
    "markov_order": lambda x: int(x) in [1, 2, 3],
    "min_response_words": lambda x: int(x) > 0,
    "max_response_words": lambda x: int(x) > 0,
    "learn_from_bots": lambda x: str(x).lower() in ["true", "false"],
    "trigger_on_mention": lambda x: str(x).lower() in ["true", "false"],
    "trigger_on_reply": lambda x: str(x).lower() in ["true", "false"],
    "personality_prefix": lambda x: isinstance(x, str),
    "ignored_channels": lambda x: True, # List parsing handled in command
    "allowed_channels": lambda x: True,
    "ignored_users": lambda x: True,
    "burst_chance": lambda x: 0.0 <= float(x) <= 1.0,
    "learning_enabled": lambda x: str(x).lower() in ["true", "false"],
    "response_enabled": lambda x: str(x).lower() in ["true", "false"],
}
