import aiosqlite
import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from config import config


@dataclass
class QueueItem:
    id: Optional[int]
    chat_id: int
    user_id: int
    title: str
    duration: int
    url: str
    filepath: Optional[str]
    requested_by: str
    added_at: datetime
    position: int


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.db_path
        self._initialized = False
    
    async def init(self):
        if self._initialized:
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    filepath TEXT,
                    requested_by TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    position INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    volume INTEGER DEFAULT 100,
                    auto_leave_timeout INTEGER DEFAULT 300,
                    repeat_mode TEXT DEFAULT 'off',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_queue_chat_position 
                ON queue(chat_id, position)
            """)
            await db.commit()
        self._initialized = True
    
    async def add_to_queue(self, item: QueueItem) -> int:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO queue (chat_id, user_id, title, duration, url, filepath, requested_by, position)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item.chat_id, item.user_id, item.title, item.duration, 
                  item.url, item.filepath, item.requested_by, item.position))
            await db.commit()
            return cursor.lastrowid
    
    async def get_queue(self, chat_id: int) -> List[QueueItem]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM queue WHERE chat_id = ? ORDER BY position
            """, (chat_id,))
            rows = await cursor.fetchall()
            return [QueueItem(
                id=row["id"],
                chat_id=row["chat_id"],
                user_id=row["user_id"],
                title=row["title"],
                duration=row["duration"],
                url=row["url"],
                filepath=row["filepath"],
                requested_by=row["requested_by"],
                added_at=datetime.fromisoformat(row["added_at"]),
                position=row["position"]
            ) for row in rows]
    
    async def get_next_in_queue(self, chat_id: int) -> Optional[QueueItem]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM queue WHERE chat_id = ? ORDER BY position LIMIT 1
            """, (chat_id,))
            row = await cursor.fetchone()
            if row:
                return QueueItem(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    duration=row["duration"],
                    url=row["url"],
                    filepath=row["filepath"],
                    requested_by=row["requested_by"],
                    added_at=datetime.fromisoformat(row["added_at"]),
                    position=row["position"]
                )
            return None
    
    async def remove_from_queue(self, item_id: int) -> bool:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM queue WHERE id = ?", (item_id,))
            await db.commit()
            return cursor.rowcount > 0
    
    async def clear_queue(self, chat_id: int) -> int:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM queue WHERE chat_id = ?", (chat_id,))
            await db.commit()
            return cursor.rowcount
    
    async def reorder_queue(self, chat_id: int):
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE queue SET position = (
                    SELECT COUNT(*) FROM queue q2 
                    WHERE q2.chat_id = queue.chat_id AND q2.id <= queue.id
                ) WHERE chat_id = ?
            """, (chat_id,))
            await db.commit()
    
    async def get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {
                "chat_id": chat_id,
                "volume": config.default_volume,
                "auto_leave_timeout": config.auto_leave_timeout,
                "repeat_mode": "off"
            }
    
    async def update_chat_settings(self, chat_id: int, **kwargs):
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO chat_settings (chat_id, volume, auto_leave_timeout, repeat_mode, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    volume = COALESCE(?, volume),
                    auto_leave_timeout = COALESCE(?, auto_leave_timeout),
                    repeat_mode = COALESCE(?, repeat_mode),
                    updated_at = CURRENT_TIMESTAMP
            """, (chat_id, kwargs.get("volume"), kwargs.get("auto_leave_timeout"), 
                  kwargs.get("repeat_mode"),
                  kwargs.get("volume"), kwargs.get("auto_leave_timeout"), kwargs.get("repeat_mode")))
            await db.commit()


db = Database()