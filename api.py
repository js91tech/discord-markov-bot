from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import os
import asyncio

bot_instance = None
bot_loop = None

app = FastAPI(
    title="Discord Bot Dashboard",
    description="Internal dashboard to manage bot settings",
    docs_url="/dashboard",
    redoc_url=None
)


class SettingsUpdate(BaseModel):
    response_enabled: Optional[bool] = None
    cooldown_seconds: Optional[int] = None
    ignored_channels: Optional[List[int]] = None
    allowed_channels: Optional[List[int]] = None
    ignored_users: Optional[List[int]] = None
    trigger_on_mention: Optional[bool] = None
    trigger_on_reply: Optional[bool] = None
    conversation_window_seconds: Optional[int] = None
    indirect_reply_chance: Optional[float] = None
    reaction_chance: Optional[float] = None
    random_reply_chance: Optional[float] = None
    random_mention_chance: Optional[float] = None
    gif_chance: Optional[float] = None
    personality_prefix: Optional[str] = None
    llm_model: Optional[str] = None
    fallback_llm_model: Optional[str] = None
    response_chance: Optional[float] = None


@app.get("/api/settings/{guild_id}")
async def get_guild_settings(guild_id: int):
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


def run_api():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
