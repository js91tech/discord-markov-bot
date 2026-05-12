import aiosqlite
import json
import os
import asyncio

class Database:
    def __init__(self):
        self.db_path = "data/bot.db"
        self.conn = None
        self.queue = asyncio.Queue()
        self._worker_task = None

    async def init(self):
        os.makedirs("data", exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("PRAGMA journal_mode=WAL")
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
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS memories (
                                    guild_id INTEGER, 
                                    user_id INTEGER, 
                                    note TEXT)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS consolidated_memories (
                                    guild_id INTEGER PRIMARY KEY, 
                                    summary_json TEXT)""")
        await self.conn.execute("""CREATE TABLE IF NOT EXISTS reminders (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_id INTEGER, 
                                    channel_id INTEGER,
                                    message TEXT,
                                    trigger_time REAL)""")
        await self.conn.commit()
        self._worker_task = asyncio.create_task(self._write_worker())

    async def _write_worker(self):
        while True:
            sql, params = await self.queue.get()
            try:
                await self.conn.execute(sql, params)
                await self.conn.commit()
            except Exception as e:
                print(f"DB Write Error: {e}")
            self.queue.task_done()

    async def get_markov(self, guild_id):
        cursor = await self.conn.execute("SELECT key, value FROM markov WHERE guild_id = ?", (guild_id,))
        rows = await cursor.fetchall()
        chain = {}
        for key, value in rows:
            chain[key] = json.loads(value)
        return chain

    async def save_full_chain(self, guild_id, db_dict):
        await self.queue.put(("DELETE FROM markov WHERE guild_id = ?", (guild_id,)))
        for json_key, values in db_dict.items():
            sql = "INSERT OR REPLACE INTO markov (guild_id, key, value) VALUES (?, ?, ?)"
            params = (guild_id, json_key, json.dumps(values))
            await self.queue.put((sql, params))

    async def get_settings(self, guild_id):
        cursor = await self.conn.execute("SELECT settings_json FROM settings WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def save_settings(self, guild_id, settings_dict):
        sql = "INSERT OR REPLACE INTO settings (guild_id, settings_json) VALUES (?, ?)"
        params = (guild_id, json.dumps(settings_dict))
        await self.queue.put((sql, params))

    async def increment_stat(self, guild_id, column, amount=1):
        sql = f"INSERT INTO stats (guild_id, {column}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {column} = {column} + ?"
        params = (guild_id, amount, amount)
        await self.queue.put((sql, params))

    async def get_stats(self, guild_id):
        cursor = await self.conn.execute("SELECT messages_learned, messages_sent FROM stats WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        return {"messages_learned": row[0], "messages_sent": row[1]} if row else {"messages_learned": 0, "messages_sent": 0}

    async def delete_guild_data(self, guild_id):
        await self.queue.put(("DELETE FROM markov WHERE guild_id = ?", (guild_id,)))
        await self.queue.put(("DELETE FROM settings WHERE guild_id = ?", (guild_id,)))
        await self.queue.put(("DELETE FROM stats WHERE guild_id = ?", (guild_id,)))
        await self.queue.put(("DELETE FROM memories WHERE guild_id = ?", (guild_id,)))
        await self.queue.put(("DELETE FROM consolidated_memories WHERE guild_id = ?", (guild_id,)))

    async def add_memory(self, guild_id, user_id, note):
        sql = "INSERT INTO memories (guild_id, user_id, note) VALUES (?, ?, ?)"
        await self.queue.put((sql, (guild_id, user_id, note)))

    async def get_memories(self, guild_id, user_id):
        cursor = await self.conn.execute("SELECT note FROM memories WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def forget_memories(self, guild_id, user_id):
        await self.queue.put(("DELETE FROM memories WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)))

    async def get_consolidated_memory(self, guild
