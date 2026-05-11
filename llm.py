import aiohttp
import os

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

async def generate_llm_response(system_prompt, chat_history):
    """Sends the context to OpenRouter and gets a coherent response."""
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing from environment variables!")
        return None
    
    # Format the messages for the API
    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        # The first item in chat_history might contain the model info, skip it for the API payload
        if "model" in msg: 
            continue
        messages.append(msg)

    # Extract the model from the settings (passed in the first message of chat_history by chat.py)
    model_name = "meta-llama/llama-3-8b-instruct" # Fallback
    if chat_history and "model" in chat_history[0]:
        model_name = chat_history[0]["model"]

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://discord-bot.local",
    }
    
    data = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 150, # Keep it short like a Discord message
        "temperature": 0.9  # A little creative
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
