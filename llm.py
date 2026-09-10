import aiohttp
import os

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
DEFAULT_FREE_MODEL = os.environ.get("FREE_LLM_MODEL", "google/gemma-2-9b-it:free")

_BILLING_KEYWORDS = (
    "credit", "quota", "insufficient", "billing", "payment", "balance",
    "afford", "limit exceeded", "rate limit", "out of tokens",
)


def _should_fallback(status, error_text):
    if status in (402, 429, 503):
        return True
    lowered = (error_text or "").lower()
    return any(keyword in lowered for keyword in _BILLING_KEYWORDS)


def _has_images(messages):
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _strip_images(messages):
    """Convert multimodal content to plain text for text-only fallback models."""
    stripped = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            stripped.append(msg)
            continue
        texts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                texts.append("[image]")
        stripped.append({**msg, "content": " ".join(t for t in texts if t).strip() or "[image]"})
    return stripped


async def _request_completion(model_name, messages):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://discord-bot.local",
    }
    data = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.85,
        "frequency_penalty": 0.6,
        "presence_penalty": 0.4,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return content.strip() if content else None, resp.status, ""
                error_text = await resp.text()
                print(f"OpenRouter Error ({model_name}): {resp.status} - {error_text}")
                return None, resp.status, error_text
    except Exception as e:
        print(f"LLM API Error ({model_name}): {e}")
        return None, 0, str(e)


async def generate_llm_response(system_prompt, chat_history, model_name=None,
                                fallback_model=None, allow_fallback=True):
    """Send context to OpenRouter. Falls back to a free model on billing/quota errors."""
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing from environment variables!")
        return None

    if not model_name:
        if chat_history and "model" in chat_history[0]:
            model_name = chat_history[0]["model"]
            chat_history = chat_history[1:]
        else:
            model_name = "meta-llama/llama-3-8b-instruct"

    if not fallback_model:
        fallback_model = DEFAULT_FREE_MODEL

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        if "model" in msg:
            continue
        messages.append(msg)

    content, status, error_text = await _request_completion(model_name, messages)
    if content:
        return content

    if not allow_fallback or fallback_model == model_name:
        return None

    print(f"Falling back from {model_name} to {fallback_model} (status {status})")
    fallback_messages = _strip_images(messages) if _has_images(messages) else messages
    content, _, _ = await _request_completion(fallback_model, fallback_messages)
    return content
