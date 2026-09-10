import json
import os
import re

PEOPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "people")
PROFILES_PATH = os.path.join(PEOPLE_DIR, "profiles.json")

IMAGE_REQUEST_RE = re.compile(
    r"\b(draw|drawing|generate|make|create|paint|render|imagine|picture|pic|image|photo|portrait|selfie|art)\b",
    re.IGNORECASE,
)
NSFW_RE = re.compile(
    r"\b(nude|naked|nsfw|sex|porn|xxx|explicit|undress|lingerie|onlyfans|lewd|nsfl)\b",
    re.IGNORECASE,
)

_profiles_cache = None


def load_profiles():
    global _profiles_cache
    if _profiles_cache is not None:
        return _profiles_cache
    if not os.path.exists(PROFILES_PATH):
        _profiles_cache = []
        return _profiles_cache
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    profiles = []
    for key, data in raw.items():
        profile = dict(data)
        profile["id"] = key
        profile["aliases"] = [a.lower() for a in profile.get("aliases", [])] + [key.lower()]
        if profile.get("name"):
            profile["aliases"].append(profile["name"].lower())
        profile["aliases"] = sorted(set(profile["aliases"]))
        image_name = profile.get("image")
        profile["image_path"] = os.path.join(PEOPLE_DIR, image_name) if image_name else None
        profiles.append(profile)
    _profiles_cache = profiles
    return profiles


def people_prompt_block():
    lines = []
    for profile in load_profiles():
        notes = " ".join(profile.get("notes") or [])
        lines.append(f"- {profile['name']}: {notes}")
    if not lines:
        return ""
    return (
        "\n\nKNOWN PEOPLE (reference photos on file):\n"
        + "\n".join(lines)
        + "\nIf someone asks you to draw/generate/show a picture of one of these people, "
        "acknowledge it briefly. Image generation is handled separately."
    )


def is_image_request(text):
    return bool(text and IMAGE_REQUEST_RE.search(text))


def is_nsfw_request(text):
    return bool(text and NSFW_RE.search(text))


def find_person(text):
    if not text:
        return None
    lowered = text.lower()
    for profile in load_profiles():
        for alias in profile["aliases"]:
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return profile
    return None


def find_person_for_image_request(text):
    if not is_image_request(text):
        return None
    return find_person(text)


def build_image_prompt(profile, user_text):
    appearance = profile.get("appearance", "")
    return (
        f"Create a new photorealistic image of this exact person named {profile['name']}. "
        f"Match their face, hair, glasses, and likeness from the reference photo. "
        f"Appearance: {appearance} "
        f"User request: {user_text.strip()} "
        f"Keep them fully clothed and recognizable as the same person. Do not change their identity."
    )
