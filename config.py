import os
from pathlib import Path
from typing import List

class Config:
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    bot_token: str = os.getenv("BOT_TOKEN", "")

    session_name: str = os.getenv("SESSION_NAME", "music_bot")
    pytgcalls_session: str = os.getenv("PYTGCALLS_SESSION", "pytgcalls_session")

    db_path: str = os.getenv("DB_PATH", "data/music_bot.db")
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads")

    admin_ids: List[int] = [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ]

    command_prefix: str = os.getenv("COMMAND_PREFIX", "/")
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "50"))
    default_volume: int = int(os.getenv("DEFAULT_VOLUME", "100"))
    auto_leave_timeout: int = int(os.getenv("AUTO_LEAVE_TIMEOUT", "300"))
    ytdl_format: str = os.getenv("YTDL_FORMAT", "bestaudio/best")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/music_bot.log")
    enable_voice_chat: bool = os.getenv("ENABLE_VOICE_CHAT", "true").lower() == "true"

Path(Config().downloads_dir).mkdir(parents=True, exist_ok=True)
Path(Config().db_path).parent.mkdir(parents=True, exist_ok=True)
Path(Config().log_file).parent.mkdir(parents=True, exist_ok=True)

config = Config()

def validate_config() -> List[str]:
    errors = []

    if config.api_id == 0:
        errors.append("API_ID is required")

    if not config.api_hash:
        errors.append("API_HASH is required")

    if not config.bot_token:
        errors.append("BOT_TOKEN is required")

    return errors

API_ID = config.api_id
API_HASH = config.api_hash
BOT_TOKEN = config.bot_token
SESSION_NAME = config.session_name
DB_PATH = config.db_path
DOWNLOADS_DIR = config.downloads_dir
ADMIN_IDS = config.admin_ids
COMMAND_PREFIX = config.command_prefix
MAX_QUEUE_SIZE = config.max_queue_size
DEFAULT_VOLUME = config.default_volume
AUTO_LEAVE_TIMEOUT = config.auto_leave_timeout
YTDL_FORMAT = config.ytdl_format
LOG_LEVEL = config.log_level
LOG_FILE = config.log_file
