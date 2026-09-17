import sqlite3
import time
from pathlib import Path

DB_PATH = Path("musicbot.sqlite3")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            activated_until INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS forced_channels (
            chat_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS music_admins (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            promoted_by INTEGER,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_deputies (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            promoted_by INTEGER,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


def activate_chat(chat_id: int, title: str, days: int):
    until = int(time.time()) + days * 86400

    conn = db()
    conn.execute("""
        INSERT INTO chats(chat_id, title, activated_until)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET
            title=excluded.title,
            activated_until=excluded.activated_until
    """, (chat_id, title, until))
    conn.commit()
    conn.close()


def is_chat_active(chat_id: int) -> bool:
    conn = db()
    row = conn.execute(
        "SELECT activated_until FROM chats WHERE chat_id=?",
        (chat_id,)
    ).fetchone()
    conn.close()

    if not row:
        return False

    return int(row["activated_until"]) > int(time.time())


def get_chat_expiry(chat_id: int):
    conn = db()
    row = conn.execute(
        "SELECT activated_until FROM chats WHERE chat_id=?",
        (chat_id,)
    ).fetchone()
    conn.close()

    return row["activated_until"] if row else 0


def add_forced_channel(chat_id: int, username: str, title: str = ""):
    username = username.strip().lstrip("@")

    conn = db()
    conn.execute("""
        INSERT INTO forced_channels(chat_id, username, title)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET
            username=excluded.username,
            title=excluded.title
    """, (chat_id, username, title))
    conn.commit()
    conn.close()


def remove_forced_channel(chat_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM forced_channels WHERE chat_id=?",
        (chat_id,)
    )
    conn.commit()
    conn.close()


def get_forced_channel(chat_id: int):
    conn = db()
    row = conn.execute(
        "SELECT * FROM forced_channels WHERE chat_id=?",
        (chat_id,)
    ).fetchone()
    conn.close()

    return row


def promote_music_admin(chat_id: int, user_id: int, promoted_by: int):
    conn = db()
    conn.execute("""
        INSERT OR REPLACE INTO music_admins(chat_id, user_id, promoted_by)
        VALUES (?, ?, ?)
    """, (chat_id, user_id, promoted_by))
    conn.commit()
    conn.close()


def demote_music_admin(chat_id: int, user_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM music_admins WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()


def is_music_admin(chat_id: int, user_id: int) -> bool:
    conn = db()
    row = conn.execute("""
        SELECT 1 FROM music_admins
        WHERE chat_id=? AND user_id=?
    """, (chat_id, user_id)).fetchone()
    conn.close()

    return row is not None


def promote_deputy(chat_id: int, user_id: int, promoted_by: int):
    conn = db()
    conn.execute("""
        INSERT OR REPLACE INTO player_deputies(chat_id, user_id, promoted_by)
        VALUES (?, ?, ?)
    """, (chat_id, user_id, promoted_by))
    conn.commit()
    conn.close()


def demote_deputy(chat_id: int, user_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM player_deputies WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()


def is_deputy(chat_id: int, user_id: int) -> bool:
    conn = db()
    row = conn.execute("""
        SELECT 1 FROM player_deputies
        WHERE chat_id=? AND user_id=?
    """, (chat_id, user_id)).fetchone()
    conn.close()

    return row is not None


def clear_music_admins(chat_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM music_admins WHERE chat_id=?",
        (chat_id,)
    )
    conn.commit()
    conn.close()


def clear_deputies(chat_id: int):
    conn = db()
    conn.execute(
        "DELETE FROM player_deputies WHERE chat_id=?",
        (chat_id,)
    )
    conn.commit()
    conn.close()
