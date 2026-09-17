import os
import sys
import platform
from pathlib import Path
from typing import List


# ============================================================
# تشخیص محیط اجرا
# ============================================================

try:
    from optional_deps import IS_ANDROID, IS_TERMUX, VOICE_CHAT_AVAILABLE
except ImportError:
    IS_ANDROID = (
        sys.platform == "android"
        or "android" in platform.platform().lower()
    )

    IS_TERMUX = (
        "com.termux" in platform.platform().lower()
    )

    VOICE_CHAT_AVAILABLE = not IS_ANDROID


# ============================================================
# ابزارهای کمکی
# ============================================================

def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "فعال",
    }


def env_int(name: str, default: int = 0) -> int:
    value = os.getenv(name, "").strip()

    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def env_int_list(name: str) -> List[int]:
    value = os.getenv(name, "").strip()

    if not value:
        return []

    result = []

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            result.append(int(item))
        except ValueError:
            continue

    return result


# ============================================================
# تنظیمات اصلی
# ============================================================

class Config:

    # --------------------------------------------------------
    # Telegram Bot API
    # --------------------------------------------------------

    api_id: int = env_int("API_ID", 0)

    api_hash: str = os.getenv(
        "API_HASH",
        ""
    ).strip()

    bot_token: str = os.getenv(
        "BOT_TOKEN",
        ""
    ).strip()

    # --------------------------------------------------------
    # Telegram Assistant / User Account
    # --------------------------------------------------------

    assistant_session: str = os.getenv(
        "ASSISTANT_SESSION",
        ""
    ).strip()

    # نام Session ربات
    session_name: str = os.getenv(
        "SESSION_NAME",
        "music_bot"
    ).strip()

    # Session قدیمی PyTgCalls برای سازگاری
    pytgcalls_session: str = os.getenv(
        "PYTGCALLS_SESSION",
        "pytgcalls_session"
    ).strip()

    # --------------------------------------------------------
    # مالک اصلی ربات
    # --------------------------------------------------------

    owner_id: int = env_int(
        "OWNER_ID",
        0
    )

    # ادمین‌های اصلی
    admin_ids: List[int] = env_int_list(
        "ADMIN_IDS"
    )

    # --------------------------------------------------------
    # دیتابیس
    # --------------------------------------------------------

    db_path: str = os.getenv(
        "DB_PATH",
        "musicbot.sqlite3"
    ).strip()

    # در صورت استفاده در آینده از MongoDB
    mongo_db_url: str = os.getenv(
        "MONGO_DB_URL",
        ""
    ).strip()

    # --------------------------------------------------------
    # دانلود آهنگ
    # --------------------------------------------------------

    downloads_dir: str = os.getenv(
        "DOWNLOADS_DIR",
        "downloads"
    ).strip()

    ytdl_format: str = os.getenv(
        "YTDL_FORMAT",
        "bestaudio/best"
    ).strip()

    # --------------------------------------------------------
    # دستورات
    # --------------------------------------------------------

    command_prefix: str = os.getenv(
        "COMMAND_PREFIX",
        "/"
    ).strip()

    # حداکثر تعداد آهنگ در صف
    max_queue_size: int = max(
        1,
        env_int("MAX_QUEUE_SIZE", 50)
    )

    # --------------------------------------------------------
    # پخش موزیک
    # --------------------------------------------------------

    default_volume: int = max(
        1,
        min(
            200,
            env_int("DEFAULT_VOLUME", 100)
        )
    )

    auto_leave_timeout: int = max(
        0,
        env_int("AUTO_LEAVE_TIMEOUT", 300)
    )

    # فعال بودن ویس‌چت
    enable_voice_chat: bool = env_bool(
        "ENABLE_VOICE_CHAT",
        VOICE_CHAT_AVAILABLE
    )

    # --------------------------------------------------------
    # اشتراک / فعال‌سازی گروه و کانال
    # --------------------------------------------------------

    # فعال بودن سیستم اشتراک
    subscriptions_enabled: bool = env_bool(
        "SUBSCRIPTIONS_ENABLED",
        True
    )

    # فقط گروه/کانال فعال‌شده اجازه استفاده داشته باشد
    require_chat_activation: bool = env_bool(
        "REQUIRE_CHAT_ACTIVATION",
        True
    )

    # --------------------------------------------------------
    # عضویت اجباری
    # --------------------------------------------------------

    force_sub_enabled: bool = env_bool(
        "FORCE_SUB_ENABLED",
        True
    )

    # کانال پیش‌فرض عضویت اجباری
    force_sub_channel: str = os.getenv(
        "FORCE_SUB_CHANNEL",
        ""
    ).strip().lstrip("@")

    # --------------------------------------------------------
    # امنیت مدیریت
    # --------------------------------------------------------

    # فقط مالک اجازه مدیریت اصلی را داشته باشد
    owner_only_management: bool = env_bool(
        "OWNER_ONLY_MANAGEMENT",
        True
    )

    # --------------------------------------------------------
    # لاگ
    # --------------------------------------------------------

    log_level: str = os.getenv(
        "LOG_LEVEL",
        "INFO"
    ).strip().upper()

    log_file: str = os.getenv(
        "LOG_FILE",
        "logs/music_bot.log"
    ).strip()

    # --------------------------------------------------------
    # اطلاعات ظاهری ربات
    # --------------------------------------------------------

    bot_name: str = os.getenv(
        "BOT_NAME",
        "سایلنت موزیک پلیر"
    ).strip()

    bot_status: str = os.getenv(
        "BOT_STATUS",
        "ربات سایلنت همیشه آنلاین می‌باشد"
    ).strip()


# ============================================================
# ساخت Config
# ============================================================

config = Config()


# ============================================================
# آماده‌سازی مسیرها
# ============================================================

Path(config.downloads_dir).mkdir(
    parents=True,
    exist_ok=True
)

Path(config.db_path).parent.mkdir(
    parents=True,
    exist_ok=True
)

Path(config.log_file).parent.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# اعتبارسنجی تنظیمات
# ============================================================

def validate_config() -> List[str]:
    errors: List[str] = []

    # Telegram API
    if config.api_id <= 0:
        errors.append("API_ID is required")

    if not config.api_hash:
        errors.append("API_HASH is required")

    # Bot
    if not config.bot_token:
        errors.append("BOT_TOKEN is required")

    # Assistant
    if config.enable_voice_chat and not config.assistant_session:
        errors.append(
            "ASSISTANT_SESSION is required when voice chat is enabled"
        )

    # Owner
    if config.owner_id <= 0:
        errors.append("OWNER_ID is required")

    # Volume
    if not 1 <= config.default_volume <= 200:
        errors.append(
            "DEFAULT_VOLUME must be between 1 and 200"
        )

    # Queue
    if config.max_queue_size <= 0:
        errors.append(
            "MAX_QUEUE_SIZE must be greater than 0"
        )

    return errors


# ============================================================
# توابع دسترسی مدیریتی
# ============================================================

def is_owner(user_id: int) -> bool:
    """
    بررسی مالک اصلی ربات
    """
    return int(user_id) == int(config.owner_id)


def is_admin(user_id: int) -> bool:
    """
    بررسی مالک یا ادمین اصلی
    """
    user_id = int(user_id)

    return (
        is_owner(user_id)
        or user_id in config.admin_ids
    )


def get_all_admin_ids() -> List[int]:
    """
    لیست مالک + ادمین‌های اصلی بدون تکرار
    """
    ids = []

    if config.owner_id > 0:
        ids.append(config.owner_id)

    for user_id in config.admin_ids:
        if user_id not in ids:
            ids.append(user_id)

    return ids


# ============================================================
# Aliasهای سازگاری با فایل‌های قدیمی پروژه
# ============================================================

API_ID = config.api_id
API_HASH = config.api_hash
BOT_TOKEN = config.bot_token

ASSISTANT_SESSION = config.assistant_session

SESSION_NAME = config.session_name
PYTGCALLS_SESSION = config.pytgcalls_session

OWNER_ID = config.owner_id
ADMIN_IDS = config.admin_ids

DB_PATH = config.db_path
MONGO_DB_URL = config.mongo_db_url

DOWNLOADS_DIR = config.downloads_dir

COMMAND_PREFIX = config.command_prefix
MAX_QUEUE_SIZE = config.max_queue_size

DEFAULT_VOLUME = config.default_volume
AUTO_LEAVE_TIMEOUT = config.auto_leave_timeout

YTDL_FORMAT = config.ytdl_format

ENABLE_VOICE_CHAT = config.enable_voice_chat

SUBSCRIPTIONS_ENABLED = config.subscriptions_enabled
REQUIRE_CHAT_ACTIVATION = config.require_chat_activation

FORCE_SUB_ENABLED = config.force_sub_enabled
FORCE_SUB_CHANNEL = config.force_sub_channel

OWNER_ONLY_MANAGEMENT = config.owner_only_management

LOG_LEVEL = config.log_level
LOG_FILE = config.log_file

BOT_NAME = config.bot_name
BOT_STATUS = config.bot_status
