from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
import asyncio

# This will hold the reference to your bot instance and its event loop
bot_instance = None
bot_loop = None

app = FastAPI(
    title="Discord Bot Dashboard",
    description="Internal dashboard to manage bot settings",
    docs_url="/dashboard", # This makes the UI available at yoururl.com/dashboard
    redoc_url=None
)

# --- Pydantic Models (Defines what data the dashboard expects) ---
class SettingsUpdate(BaseModel):
    brain_mode: Optional[str] = None
    response_enabled: Optional[bool] = None
    learning_enabled: Optional[bool] = None
    cooldown_seconds: Optional[int] = None
    trigger_on_mention: Optional[bool] = None
    trigger_on_reply: Optional[bool] = None
    personality_prefix: Optional[str] = None
    # Add any other settings you want to change here!

# --- API Routes ---
@app.get("/api/settings/{guild_id}")
async def get_guild_settings(guild_id: int):
    """Fetch the current settings for a specific server"""
    if not bot_instance or not bot_loop:
        raise HTTPException(status_code=503, detail="Bot not ready")
    settings = await asyncio.wrap_future(
        asyncio.run_coroutine_threadsafe(
            bot_instance.settings_manager.get_settings(guild_id), bot_loop
        )
    )
    return settings

@app.post("/api/settings/{guild_id}")
async def update_guild_settings(guild_id: int, updates: SettingsUpdate):
    """Update settings for a specific server"""
    if not bot_instance or not bot_loop:
        raise HTTPException(status_code=503, detail="Bot not ready")
    
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields provided to update")
        
    await asyncio.wrap_future(
        asyncio.run_coroutine_threadsafe(
            bot_instance.settings_manager.update_settings(guild_id, update_data), bot_loop
        )
    )
    return {"status": "success", "updated_fields": list(update_data.keys())}

# --- Server Runner ---
def run_api():
    """Runs the web server in a separate thread"""
    port = int(os.environ.get("PORT", 10000)) # Render requires you to bind to the PORT env var
    uvicorn.run(app, host="0.0.0.0", port=port)
