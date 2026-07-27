# Telegram Music Bot - Example Configuration
# Copy this file to config.py and fill in your values
# OR set environment variables (recommended for production)

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Config(BaseModel):
    # ===== REQUIRED: Telegram API Credentials =====
    # Get from https://my.telegram.org/apps
    api_id: int = int(os.getenv("API_ID", "0"))  # e.g., 1234567
    api_hash: str = os.getenv("API_HASH", "")    # e.g., "abcdef1234567890abcdef1234567890"
    
    # ===== REQUIRED: Bot Token =====
    # Get from @BotFather
    bot_token: str = os.getenv("BOT_TOKEN", "")  # e.g., "123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    
    # ===== Optional Settings =====
    session_name: str = os.getenv("SESSION_NAME", "music_bot")
    pytgcalls_session: str = os.getenv("PYTGCALLS_SESSION", "pytgcalls_session")
    
    # Database & Storage
    db_path: str = os.getenv("DB_PATH", "data/music_bot.db")
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads")
    
    # Admin user IDs (comma-separated) - for admin-only commands
    admin_ids: list[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    
    # Command prefix
    command_prefix: str = os.getenv("COMMAND_PREFIX", "/")
    
    # Limits
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "50"))
    default_volume: int = int(os.getenv("DEFAULT_VOLUME", "100"))  # 0-200
    auto_leave_timeout: int = int(os.getenv("AUTO_LEAVE_TIMEOUT", "300"))  # seconds, 0 = disabled
    
    # yt-dlp format preference
    ytdl_format: str = os.getenv("YTDL_FORMAT", "bestaudio/best")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/music_bot.log")

# Create necessary directories
from pathlib import Path
Path(Config().downloads_dir).mkdir(parents=True, exist_ok=True)
Path(Config().db_path).parent.mkdir(parents=True, exist_ok=True)
Path(Config().log_file).parent.mkdir(parents=True, exist_ok=True)

config = Config()