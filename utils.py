import aiohttp
import os
import re

TENOR_API_KEY = os.environ.get("TENOR_API_KEY", "")

async def search_gif(query):
    """Searches Tenor for a random GIF based on a query."""
    if not TENOR_API_KEY:
        return None
    
    url = f"https://tenor.googleapis.com/v2/search?q={query}&key={TENOR_API_KEY}&limit=10&media_filter=gif"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results:
                        import random
                        return random.choice(results)["media_formats"]["gif"]["url"]
    except Exception as e:
        print(f"Tenor API Error: {e}")
    return None

def sanitize_message(text):
    """Cleans up bot messages to prevent Discord API errors."""
    # Remove @everyone and @here to prevent mass pings
    text = text.replace("@everyone", "").replace("@here", "")
    # Remove duplicate whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Discord messages have a 2000 character limit
    if len(text) > 1950:
        text = text[:1950] + "..."
    return text
