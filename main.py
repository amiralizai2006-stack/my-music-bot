#!/usr/bin/env python3
"""
Telegram Music Bot - Main Entry Point
A self-bot for playing music in Telegram group voice calls.
Gracefully handles environments where PyTgCalls is not available (Android/Termux).
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config, validate_config
from database import db
from player import downloader, MusicPlayer
from optional_deps import (
    VOICE_CHAT_AVAILABLE, PyTgCalls, check_voice_chat_support, get_platform_info
)
from handlers import set_bot_instances
from pyrogram import Client

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Print platform info on startup
platform_info = get_platform_info()
logger.info("=== Platform Info ===")
for key, value in platform_info.items():
    logger.info(f"  {key}: {value}")
logger.info("=====================")

# Validate config
errors = validate_config()
if errors:
    logger.error("Configuration errors:")
    for error in errors:
        logger.error(f"  - {error}")
    sys.exit(1)

# Print voice chat status
voice_supported, voice_msg = check_voice_chat_support()
if VOICE_CHAT_AVAILABLE:
    logger.info("✅ Voice chat: AVAILABLE")
else:
    logger.warning(f"⚠️ Voice chat: NOT AVAILABLE - {voice_msg}")

# Initialize Pyrogram client
app = Client(
    config.session_name,
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token
)

# Initialize PyTgCalls (only if available)
pytgcalls = None
if VOICE_CHAT_AVAILABLE:
    pytgcalls = PyTgCalls(app)

# Initialize MusicPlayer
player = MusicPlayer(pytgcalls)

# Global shutdown flag
shutdown_event = asyncio.Event()


async def startup():
    """Initialize database and start clients."""
    logger.info("🚀 Starting Telegram Music Bot...")
    
    # Initialize database
    await db.init()
    logger.info("✅ Database initialized")
    
    # Start Pyrogram
    await app.start()
    logger.info("✅ Pyrogram client started")
    
    # Start PyTgCalls (only if available)
    if pytgcalls:
        await pytgcalls.start()
        logger.info("✅ PyTgCalls started")
    else:
        logger.info("ℹ️ PyTgCalls skipped (not available on this platform)")
    
    # Set bot instances in handlers
    set_bot_instances(app, pytgcalls, player, shutdown_event)
    
    # Get bot info
    me = await app.get_me()
    logger.info(f"🤖 Bot: @{me.username} ({me.first_name})")
    logger.info(f"📋 Admin IDs: {config.admin_ids if config.admin_ids else 'All users'}")
    
    if VOICE_CHAT_AVAILABLE:
        logger.info("🎵 Bot is ready! Send /play <song> in a group to start.")
    else:
        logger.info("🎵 Bot is ready (LIMITED MODE - no voice chat). Send /play <song> to download music.")


async def shutdown():
    """Graceful shutdown."""
    logger.info("🛑 Shutting down...")
    shutdown_event.set()
    
    # Leave all active calls
    try:
        if pytgcalls:
            await pytgcalls.leave_all_calls()
    except Exception as e:
        logger.warning(f"Error leaving calls: {e}")
    
    # Stop clients
    if pytgcalls:
        await pytgcalls.stop()
    await app.stop()
    
    logger.info("✅ Shutdown complete")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}")
    asyncio.create_task(shutdown())


async def main():
    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler, sig, None)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    try:
        await startup()
        # Wait for shutdown signal
        await shutdown_event.wait()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)