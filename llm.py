import aiohttp
import os

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


async def generate_llm_response(system_prompt, chat_history, model_name=None):
    """Sends the context to OpenRouter and gets a coherent response."""
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing from environment variables!")
        return None

    # Fallback model if none specified
    if not model_name:
        # Legacy: check if old code passed model in first message
        if chat_history and "model" in chat_history[0]:
            model_name = chat_history[0]["model"]
            chat_history = chat_history[1:]  # strip it out
        else:
            model_name = "meta-llama/llama-3-8b-instruct"

    # Format the messages for the API — skip any legacy model keys
    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        if "model" in msg:
            continue
        messages.append(msg)

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
                    return content.strip() if content else None
                else:
                    error_text = await resp.text()
                    print(f"OpenRouter Error: {resp.status} - {error_text}")
                    return None
    except Exception as e:
        print(f"LLM API Error: {e}")
        return None
