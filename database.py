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

    # جدول چت‌ها — برای سازگاری با نسخه‌های قبلی نگه داشته شده
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            activated_until INTEGER DEFAULT 0
        )
    """)

    # کانال اجباری — برای سازگاری با نسخه قبلی نگه داشته شده
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forced_channels (
            chat_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT DEFAULT ''
        )
    """)

    # ادمین‌های موزیک
    conn.execute("""
        CREATE TABLE IF NOT EXISTS music_admins (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            promoted_by INTEGER,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    # معاون‌های پلیر
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_deputies (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            promoted_by INTEGER,
            PRIMARY KEY(chat_id, user_id)
        )
    """)

    # =========================================================
    # دکمه‌های سفارشی پیوی ربات
    # فقط مالک ربات می‌تواند این دکمه‌ها را مدیریت کند.
    # =========================================================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            url TEXT NOT NULL,
            row_order INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# سیستم قدیمی فعال‌سازی — برای سازگاری نگه داشته شده
# =========================================================

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


# =========================================================
# کانال اجباری — برای سازگاری
# =========================================================

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


# =========================================================
# ادمین موزیک
# =========================================================

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


# =========================================================
# معاون پلیر
# =========================================================

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


# =========================================================
# دکمه‌های سفارشی پیوی
# =========================================================

def add_custom_button(
    owner_id: int,
    text: str,
    url: str,
    row_order: int = 0
):
    text = (text or "").strip()
    url = (url or "").strip()

    if not text or not url:
        return False

    conn = db()

    conn.execute("""
        INSERT INTO custom_buttons
        (owner_id, text, url, row_order, enabled)
        VALUES (?, ?, ?, ?, 1)
    """, (
        int(owner_id),
        text,
        url,
        int(row_order)
    ))

    conn.commit()
    conn.close()

    return True


def get_custom_buttons(owner_id: int):
    conn = db()

    rows = conn.execute("""
        SELECT id, owner_id, text, url, row_order, enabled
        FROM custom_buttons
        WHERE owner_id=? AND enabled=1
        ORDER BY row_order ASC, id ASC
    """, (int(owner_id),)).fetchall()

    conn.close()

    return rows


def get_all_custom_buttons(owner_id: int):
    conn = db()

    rows = conn.execute("""
        SELECT id, owner_id, text, url, row_order, enabled
        FROM custom_buttons
        WHERE owner_id=?
        ORDER BY row_order ASC, id ASC
    """, (int(owner_id),)).fetchall()

    conn.close()

    return rows


def get_custom_button(button_id: int, owner_id: int):
    conn = db()

    row = conn.execute("""
        SELECT id, owner_id, text, url, row_order, enabled
        FROM custom_buttons
        WHERE id=? AND owner_id=?
    """, (
        int(button_id),
        int(owner_id)
    )).fetchone()

    conn.close()

    return row


def delete_custom_button(button_id: int, owner_id: int):
    conn = db()

    cursor = conn.execute("""
        DELETE FROM custom_buttons
        WHERE id=? AND owner_id=?
    """, (
        int(button_id),
        int(owner_id)
    ))

    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    return deleted


def clear_custom_buttons(owner_id: int):
    conn = db()

    conn.execute("""
        DELETE FROM custom_buttons
        WHERE owner_id=?
    """, (int(owner_id),))

    conn.commit()
    conn.close()


def set_custom_button_order(
    button_id: int,
    owner_id: int,
    row_order: int
):
    conn = db()

    cursor = conn.execute("""
        UPDATE custom_buttons
        SET row_order=?
        WHERE id=? AND owner_id=?
    """, (
        int(row_order),
        int(button_id),
        int(owner_id)
    ))

    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    return updated


def set_custom_button_enabled(
    button_id: int,
    owner_id: int,
    enabled: bool
):
    conn = db()

    cursor = conn.execute("""
        UPDATE custom_buttons
        SET enabled=?
        WHERE id=? AND owner_id=?
    """, (
        1 if enabled else 0,
        int(button_id),
        int(owner_id)
    ))

    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    return updated
