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
SCENE_NOISE_RE = re.compile(
    r"\b(draw|drawing|generate|make|create|paint|render|imagine|picture|pic|image|photo|portrait|selfie|art|"
    r"of|as|please|can you|could you|would you|a|an|the|this)\b",
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
    if not text:
        return False
    if IMAGE_REQUEST_RE.search(text):
        return True
    compact = re.sub(r"[\s_\-]+", "", text.lower())
    for profile in load_profiles():
        for alias in profile["aliases"]:
            if f"draw{alias}" in compact or f"generate{alias}" in compact:
                return True
    return False


def is_nsfw_request(text):
    return bool(text and NSFW_RE.search(text))


def find_person(text):
    if not text:
        return None
    lowered = text.lower()
    compact = re.sub(r"[\s_\-]+", "", lowered)
    for profile in load_profiles():
        for alias in sorted(profile["aliases"], key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", lowered) or alias in compact:
                return profile
    return None


def find_person_for_image_request(text):
    if not is_image_request(text):
        return None
    return find_person(text)


def extract_scene(profile, user_text):
    text = user_text or ""
    for alias in sorted(profile.get("aliases", []), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(alias)}\b", " ", text, flags=re.IGNORECASE)
    text = SCENE_NOISE_RE.sub(" ", text)
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "a casual full-body portrait"


def build_image_prompt(profile, user_text):
    scene = extract_scene(profile, user_text)
    appearance = profile.get("appearance", "")
    return (
        "The FIRST attached image is a real photograph of a specific person. "
        "This is a likeness job, not a generic character named "
        f"{profile['name']}. "
        "Copy her exact face, glasses, hair, skin, and body type from that photo. "
        "Do not beautify her into a different woman. Do not remove her glasses. "
        "Do not change her ethnicity, age, or body size. "
        f"{appearance} "
        f"Show her in this scene only: {scene}. "
        "Keep her fully clothed. The face in the output must be recognizably the same person as the photo."
    )
