from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# =========================================================
# تنظیمات
# =========================================================

DB_PATH = Path("data/music_bot.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# =========================================================
# اتصال دیتابیس
# =========================================================

def get_connection():
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    return conn


# =========================================================
# ساخت جداول
# =========================================================

def init_db():
    conn = get_connection()

    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                created_at TEXT,
                last_seen TEXT,
                play_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS music_admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                activated_at TEXT,
                expires_at TEXT,
                active INTEGER DEFAULT 1
            );
            """
        )

        conn.commit()

    finally:
        conn.close()


# =========================================================
# تنظیمات عمومی
# =========================================================

def set_setting(
    key: str,
    value: str,
):
    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO settings(key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (
                key,
                str(value),
            ),
        )

        conn.commit()

    finally:
        conn.close()


def get_setting(
    key: str,
    default: Optional[str] = None,
):
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        if not row:
            return default

        return row["value"]

    finally:
        conn.close()


def delete_setting(key: str):
    conn = get_connection()

    try:
        conn.execute(
            """
            DELETE FROM settings
            WHERE key = ?
            """,
            (key,),
        )

        conn.commit()

    finally:
        conn.close()


# =========================================================
# مالک ربات
# =========================================================

def set_owner(user_id: int):
    set_setting(
        "owner_id",
        str(user_id),
    )


def get_owner() -> Optional[int]:
    value = get_setting(
        "owner_id"
    )

    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def is_owner(user_id: int) -> bool:
    owner_id = get_owner()

    return (
        owner_id is not None
        and owner_id == int(user_id)
    )


# =========================================================
# کاربران
# =========================================================

def add_user(
    user_id: int,
    username: str = "",
    first_name: str = "",
):
    now = datetime.utcnow().isoformat()

    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT INTO users (
                user_id,
                username,
                first_name,
                created_at,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen
            """,
            (
                int(user_id),
                username or "",
                first_name or "",
                now,
                now,
            ),
        )

        conn.commit()

    finally:
        conn.close()


def get_user(
    user_id: int,
):
    conn = get_connection()

    try:
        return conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()

    finally:
        conn.close()


def get_user_count() -> int:
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM users
            """
        ).fetchone()

        return int(row["count"])

    finally:
        conn.close()


def increase_play_count(
    user_id: int,
):
    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE users
            SET play_count = play_count + 1,
                last_seen = ?
            WHERE user_id = ?
            """,
            (
                datetime.utcnow().isoformat(),
                int(user_id),
            ),
        )

        conn.commit()

    finally:
        conn.close()


def get_total_plays() -> int:
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT COALESCE(
                SUM(play_count),
                0
            ) AS total
            FROM users
            """
        ).fetchone()

        return int(row["total"])

    finally:
        conn.close()


# =========================================================
# مدیران موزیک
# =========================================================

def add_music_admin(
    user_id: int,
):
    conn = get_connection()

    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO music_admins(
                user_id,
                added_at
            )
            VALUES (?, ?)
            """,
            (
                int(user_id),
                datetime.utcnow().isoformat(),
            ),
        )

        conn.commit()

    finally:
        conn.close()


def remove_music_admin(
    user_id: int,
):
    conn = get_connection()

    try:
        conn.execute(
            """
            DELETE FROM music_admins
            WHERE user_id = ?
            """,
            (int(user_id),),
        )

        conn.commit()

    finally:
        conn.close()


def is_music_admin(
    user_id: int,
) -> bool:
    if is_owner(user_id):
        return True

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT user_id
            FROM music_admins
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()

        return row is not None

    finally:
        conn.close()


def get_music_admins() -> list[int]:
    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT user_id
            FROM music_admins
            ORDER BY added_at ASC
            """
        ).fetchall()

        return [
            int(row["user_id"])
            for row in rows
        ]

    finally:
        conn.close()


# =========================================================
# اشتراک
# =========================================================

def activate_subscription(
    user_id: int,
    days: int,
):
    """
    فعال‌سازی اشتراک.

    اگر کاربر اشتراک فعال داشته باشد،
    زمان جدید از تاریخ انقضای فعلی اضافه می‌شود.
    """

    now = datetime.utcnow()

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT expires_at, active
            FROM subscriptions
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()

        if (
            row
            and row["expires_at"]
            and row["active"]
        ):
            try:
                old_expiry = datetime.fromisoformat(
                    row["expires_at"]
                )
            except ValueError:
                old_expiry = now

            if old_expiry > now:
                start = old_expiry
            else:
                start = now

        else:
            start = now

        expires = start + timedelta(
            days=int(days)
        )

        conn.execute(
            """
            INSERT INTO subscriptions(
                user_id,
                activated_at,
                expires_at,
                active
            )
            VALUES (?, ?, ?, 1)

            ON CONFLICT(user_id)
            DO UPDATE SET
                activated_at = excluded.activated_at,
                expires_at = excluded.expires_at,
                active = 1
            """,
            (
                int(user_id),
                now.isoformat(),
                expires.isoformat(),
            ),
        )

        conn.commit()

        return expires

    finally:
        conn.close()


def deactivate_subscription(
    user_id: int,
):
    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE subscriptions
            SET active = 0
            WHERE user_id = ?
            """,
            (int(user_id),),
        )

        conn.commit()

    finally:
        conn.close()


def get_subscription(
    user_id: int,
):
    conn = get_connection()

    try:
        return conn.execute(
            """
            SELECT *
            FROM subscriptions
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()

    finally:
        conn.close()


def is_subscription_active(
    user_id: int,
) -> bool:
    row = get_subscription(
        user_id
    )

    if not row:
        return False

    if not row["active"]:
        return False

    expires_at = row["expires_at"]

    if not expires_at:
        return False

    try:
        expires = datetime.fromisoformat(
            expires_at
        )
    except ValueError:
        return False

    if expires <= datetime.utcnow():
        deactivate_subscription(
            user_id
        )
        return False

    return True


def subscription_days_left(
    user_id: int,
) -> int:
    row = get_subscription(
        user_id
    )

    if not row or not row["active"]:
        return 0

    try:
        expires = datetime.fromisoformat(
            row["expires_at"]
        )
    except (ValueError, TypeError):
        return 0

    remaining = (
        expires - datetime.utcnow()
    ).total_seconds()

    if remaining <= 0:
        deactivate_subscription(
            user_id
        )
        return 0

    return max(
        0,
        int(
            remaining / 86400
        ),
    )


# =========================================================
# اشتراک‌های آماده
# =========================================================

SUBSCRIPTION_DURATIONS = {
    "10 روز": 10,
    "یک ماه": 30,
    "2 ماه": 60,
    "3 ماه": 90,
    "6 ماه": 180,
}


def activate_10_days(user_id: int):
    return activate_subscription(
        user_id,
        10,
    )


def activate_1_month(user_id: int):
    return activate_subscription(
        user_id,
        30,
    )


def activate_2_months(user_id: int):
    return activate_subscription(
        user_id,
        60,
    )


def activate_3_months(user_id: int):
    return activate_subscription(
        user_id,
        90,
    )


def activate_6_months(user_id: int):
    return activate_subscription(
        user_id,
        180,
    )


# =========================================================
# کانال اجباری
# =========================================================

def set_required_channel(
    channel: str,
):
    set_setting(
        "required_channel",
        channel,
    )


def get_required_channel() -> str:
    return get_setting(
        "required_channel",
        "",
    ) or ""


# =========================================================
# پشتیبانی
# =========================================================

def set_support_username(
    username: str,
):
    set_setting(
        "support_username",
        username,
    )


def get_support_username() -> str:
    return get_setting(
        "support_username",
        "",
    ) or ""


# =========================================================
# آمار
# =========================================================

def get_stats() -> dict:
    return {
        "users": get_user_count(),
        "plays": get_total_plays(),
        "music_admins": len(
            get_music_admins()
        ),
    }


# =========================================================
# اجرای اولیه
# =========================================================

init_db()
