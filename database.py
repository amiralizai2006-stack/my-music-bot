import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta, timezone


DB_PATH = Path("bot_data.db")


class Database:

    def __init__(self, path=DB_PATH):
        self.path = str(path)

    def connect(self):
        return aiosqlite.connect(self.path)

    async def init(self):

        async with self.connect() as db:

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
                    PRIMARY KEY (chat_id, user_id)
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
                    played INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)

            await db.commit()


    # =====================================================
    # SUBSCRIPTION
    # =====================================================

    async def set_subscription(
        self,
        chat_id: int,
        user_id: int,
        days: int
    ):

        now = datetime.now(timezone.utc)

        current = await self.get_subscription(chat_id)

        if current and current > now:
            expires = current + timedelta(days=days)
        else:
            expires = now + timedelta(days=days)

        async with self.connect() as db:

            await db.execute("""
                INSERT INTO subscriptions
                (chat_id, activated_by, expires_at)
                VALUES (?, ?, ?)

                ON CONFLICT(chat_id)
                DO UPDATE SET
                    activated_by=excluded.activated_by,
                    expires_at=excluded.expires_at
            """, (
                chat_id,
                user_id,
                expires.isoformat()
            ))

            await db.commit()

        return expires


    async def get_subscription(self, chat_id: int):

        async with self.connect() as db:

            cursor = await db.execute("""
                SELECT expires_at
                FROM subscriptions
                WHERE chat_id=?
            """, (chat_id,))

            row = await cursor.fetchone()

        if not row:
            return None

        try:
            value = datetime.fromisoformat(row[0])

            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)

            return value

        except Exception:
            return None


    async def subscription_active(self, chat_id: int):

        expires = await self.get_subscription(chat_id)

        if expires is None:
            return False

        return expires > datetime.now(timezone.utc)


    async def remove_subscription(self, chat_id: int):

        async with self.connect() as db:

            await db.execute("""
                DELETE FROM subscriptions
                WHERE chat_id=?
            """, (chat_id,))

            await db.commit()


    # =====================================================
    # REQUIRED CHANNEL
    # =====================================================

    async def set_required_channel(
        self,
        chat_id: int,
        channel: str,
        user_id: int
    ):

        async with self.connect() as db:

            await db.execute("""
                INSERT INTO required_channels
                (chat_id, channel, added_by)
                VALUES (?, ?, ?)

                ON CONFLICT(chat_id)
                DO UPDATE SET
                    channel=excluded.channel,
                    added_by=excluded.added_by
            """, (
                chat_id,
                channel,
                user_id
            ))

            await db.commit()


    async def get_required_channel(self, chat_id: int):

        async with self.connect() as db:

            cursor = await db.execute("""
                SELECT channel
                FROM required_channels
                WHERE chat_id=?
            """, (chat_id,))

            row = await cursor.fetchone()

        return row[0] if row else None


    async def remove_required_channel(self, chat_id: int):

        async with self.connect() as db:

            await db.execute("""
                DELETE FROM required_channels
                WHERE chat_id=?
            """, (chat_id,))

            await db.commit()


    # =====================================================
    # MUSIC ADMINS
    # =====================================================

    async def add_music_admin(
        self,
        chat_id: int,
        user_id: int,
        added_by: int
    ):

        async with self.connect() as db:

            await db.execute("""
                INSERT OR REPLACE INTO music_admins
                (chat_id, user_id, added_by)
                VALUES (?, ?, ?)
            """, (
                chat_id,
                user_id,
                added_by
            ))

            await db.commit()


    async def remove_music_admin(
        self,
        chat_id: int,
        user_id: int
    ):

        async with self.connect() as db:

            await db.execute("""
                DELETE FROM music_admins
                WHERE chat_id=? AND user_id=?
            """, (
                chat_id,
                user_id
            ))

            await db.commit()


    async def is_music_admin(
        self,
        chat_id: int,
        user_id: int
    ):

        async with self.connect() as db:

            cursor = await db.execute("""
                SELECT 1
                FROM music_admins
                WHERE chat_id=? AND user_id=?
            """, (
                chat_id,
                user_id
            ))

            row = await cursor.fetchone()

        return row is not None


    # =====================================================
    # MUSIC OWNER
    # =====================================================

    async def set_music_owner(
        self,
        chat_id: int,
        user_id: int,
        added_by: int
    ):

        async with self.connect() as db:

            await db.execute("""
                INSERT INTO music_owner
                (chat_id, user_id, added_by)
                VALUES (?, ?, ?)

                ON CONFLICT(chat_id)
                DO UPDATE SET
                    user_id=excluded.user_id,
                    added_by=excluded.added_by
            """, (
                chat_id,
                user_id,
                added_by
            ))

            await db.commit()


    async def get_music_owner(self, chat_id: int):

        async with self.connect() as db:

            cursor = await db.execute("""
                SELECT user_id
                FROM music_owner
                WHERE chat_id=?
            """, (chat_id,))

            row = await cursor.fetchone()

        return row[0] if row else None


    # =====================================================
    # STATISTICS
    # =====================================================

    async def increment_played(
        self,
        chat_id: int,
        user_id: int
    ):

        async with self.connect() as db:

            await db.execute("""
                INSERT INTO stats
                (chat_id, user_id, played)
                VALUES (?, ?, 1)

                ON CONFLICT(chat_id, user_id)
                DO UPDATE SET
                    played=played+1
            """, (
                chat_id,
                user_id
            ))

            await db.commit()


    async def get_played(
        self,
        chat_id: int,
        user_id: int
    ):

        async with self.connect() as db:

            cursor = await db.execute("""
                SELECT played
                FROM stats
                WHERE chat_id=? AND user_id=?
            """, (
                chat_id,
                user_id
            ))

            row = await cursor.fetchone()

        return int(row[0]) if row else 0


# =========================================================
# GLOBAL DATABASE OBJECT
# =========================================================

db = Database()


# =========================================================
# COMPATIBILITY FUNCTIONS
# =========================================================

async def init_db():
    return await db.init()


async def set_subscription(chat_id, user_id, days):
    return await db.set_subscription(chat_id, user_id, days)


async def get_subscription(chat_id):
    return await db.get_subscription(chat_id)


async def subscription_active(chat_id):
    return await db.subscription_active(chat_id)


async def remove_subscription(chat_id):
    return await db.remove_subscription(chat_id)


async def set_required_channel(chat_id, channel, user_id):
    return await db.set_required_channel(
        chat_id,
        channel,
        user_id
    )


async def get_required_channel(chat_id):
    return await db.get_required_channel(chat_id)


async def remove_required_channel(chat_id):
    return await db.remove_required_channel(chat_id)


async def add_music_admin(chat_id, user_id, added_by):
    return await db.add_music_admin(
        chat_id,
        user_id,
        added_by
    )


async def remove_music_admin(chat_id, user_id):
    return await db.remove_music_admin(
        chat_id,
        user_id
    )


async def is_music_admin(chat_id, user_id):
    return await db.is_music_admin(
        chat_id,
        user_id
    )


async def set_music_owner(chat_id, user_id, added_by):
    return await db.set_music_owner(
        chat_id,
        user_id,
        added_by
    )


async def get_music_owner(chat_id):
    return await db.get_music_owner(chat_id)


async def increment_played(chat_id, user_id):
    return await db.increment_played(
        chat_id,
        user_id
    )


async def get_played(chat_id, user_id):
    return await db.get_played(
        chat_id,
        user_id
    )
