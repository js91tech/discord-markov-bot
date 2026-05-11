import aiosqlite
import json
import os

class Database:
    def __init__(self):
        self.db_path = "data/bot.db"
        self.conn = None

    async def init(self):
        os.makedirs("data", exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("PRAGMA journal_mode=WAL") # Safer DB writes
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS markov (
                                    guild_id INTEGER, 
                                    key TEXT, 
                                    value TEXT, 
                                    PRIMARY KEY (guild_id, key))""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS settings (
                                    guild_id INTEGER PRIMARY KEY, 
                                    settings_json TEXT)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS stats (
                                    guild_id INTEGER PRIMARY KEY, 
                                    messages_learned INTEGER DEFAULT 0,
                                    messages_sent INTEGER DEFAULT 0)""")
        await self.conn.commit()

    async def get_markov(self, guild_id):
        cursor = await self.conn.execute("SELECT key, value FROM markov WHERE guild_id = ?", (guild_id,))
        rows = await cursor.fetchall()
        chain = {}
        for key, value in rows:
            chain[key] = json.loads(value)
        return chain

    async def save_markov_key(self, guild_id, key, values):
        await self.conn.execute("INSERT OR REPLACE INTO markov (guild_id, key, value) VALUES (?, ?, ?)",
                                (guild_id, key, json.dumps(values)))
        await self.conn.commit()

    async def get_settings(self, guild_id):
        cursor = await self.conn.execute("SELECT settings_json FROM settings WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def save_settings(self, guild_id, settings_dict):
        await self.conn.execute("INSERT OR REPLACE INTO settings (guild_id, settings_json) VALUES (?, ?)",
                                (guild_id, json.dumps(settings_dict)))
        await self.conn.commit()

    async def increment_stat(self, guild_id, column, amount=1):
        await self.conn.execute(f"INSERT INTO stats (guild_id, {column}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {column} = {column} + ?",
                                (guild_id, amount, amount))
        await self.conn.commit()

    async def get_stats(self, guild_id):
        cursor = await self.conn.execute("SELECT messages_learned, messages_sent FROM stats WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        return {"messages_learned": row[0], "messages_sent": row[1]} if row else {"messages_learned": 0, "messages_sent": 0}

    async def delete_guild_data(self, guild_id):
        await self.conn.execute("DELETE FROM markov WHERE guild_id = ?", (guild_id,))
        await self.conn.execute("DELETE FROM settings WHERE guild_id = ?", (guild_id,))
        await self.conn.execute("DELETE FROM stats WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()
