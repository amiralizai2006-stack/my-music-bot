import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Config(BaseModel):
    # Telegram API credentials (get from my.telegram.org)
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    
    # Bot token from @BotFather
    bot_token: str = os.getenv("BOT_TOKEN", "")
    
    # Session name for Pyrogram session
    session_name: str = os.getenv("SESSION_NAME", "music_bot")
    
    # PyTgCalls session name
    pytgcalls_session: str = os.getenv("PYTGCALLS_SESSION", "pytgcalls_session")
    
    # Database path for queue persistence
    db_path: str = os.getenv("DB_PATH", "data/music_bot.db")
    
    # Downloads directory
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads")
    
    # Admin user IDs (comma-separated)
    admin_ids: list[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    
    # Command prefix
    command_prefix: str = os.getenv("COMMAND_PREFIX", "/")
    
    # Max queue size per chat
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "50"))
    
    # Default volume (0-200)
    default_volume: int = int(os.getenv("DEFAULT_VOLUME", "100"))
    
    # Auto leave after inactivity (seconds, 0 = disabled)
    auto_leave_timeout: int = int(os.getenv("AUTO_LEAVE_TIMEOUT", "300"))
    
    # yt-dlp format preference
    ytdl_format: str = os.getenv("YTDL_FORMAT", "bestaudio/best")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/music_bot.log")

# Create necessary directories
Path(Config().downloads_dir).mkdir(parents=True, exist_ok=True)
Path(Config().db_path).parent.mkdir(parents=True, exist_ok=True)
Path(Config().log_file).parent.mkdir(parents=True, exist_ok=True)

config = Config()