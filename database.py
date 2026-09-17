import aiosqlite
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path("bot_data.db")


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id INTEGER PRIMARY KEY,
                activated_by INTEGER NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS required_channels (
                chat_id INTEGER PRIMARY KEY,
                channel TEXT NOT NULL,
                added_by INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS music_admins (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_by INTEGER NOT NULL,
                PRIMARY KEY(chat_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS music_owner (
                chat_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                added_by INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                played INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            )
        """)

        await db.commit()


async def set_subscription(chat_id: int, user_id: int, days: int):
    expires = now() + timedelta(days=days)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO subscriptions(chat_id, activated_by, expires_at)
            VALUES(?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                activated_by=excluded.activated_by,
                expires_at=excluded.expires_at
        """, (chat_id, user_id, iso(expires)))
        await db.commit()

    return expires


async def get_subscription(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT expires_at FROM subscriptions WHERE chat_id=?",
            (chat_id,)
        )
        row = await cur.fetchone()

    if not row:
        return None

    try:
        return datetime.fromisoformat(row[0])
    except Exception:
        return None


async def subscription_active(chat_id: int):
    expires = await get_subscription(chat_id)

    if not expires:
        return False

    return expires > now()


async def set_required_channel(chat_id: int, channel: str, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO required_channels(chat_id, channel, added_by)
            VALUES(?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                channel=excluded.channel,
                added_by=excluded.added_by
        """, (chat_id, channel, user_id))
        await db.commit()


async def get_required_channel(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel FROM required_channels WHERE chat_id=?",
            (chat_id,)
        )
        row = await cur.fetchone()

    return row[0] if row else None


async def remove_required_channel(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM required_channels WHERE chat_id=?",
            (chat_id,)
        )
        await db.commit()


async def add_music_admin(chat_id: int, user_id: int, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO music_admins
            (chat_id, user_id, added_by)
            VALUES(?, ?, ?)
        """, (chat_id, user_id, added_by))
        await db.commit()


async def remove_music_admin(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM music_admins WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        await db.commit()


async def is_music_admin(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT 1 FROM music_admins
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id))
        return await cur.fetchone() is not None


async def set_music_owner(chat_id: int, user_id: int, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO music_owner(chat_id, user_id, added_by)
            VALUES(?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                user_id=excluded.user_id,
                added_by=excluded.added_by
        """, (chat_id, user_id, added_by))
        await db.commit()


async def get_music_owner(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id FROM music_owner WHERE chat_id=?",
            (chat_id,)
        )
        row = await cur.fetchone()

    return row[0] if row else None


async def increment_played(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO stats(chat_id, user_id, played)
            VALUES(?, ?, 1)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET played=played+1
        """, (chat_id, user_id))
        await db.commit()


async def get_played(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT played FROM stats
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id))
        row = await cur.fetchone()

    return int(row[0]) if row else 0
