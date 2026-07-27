#!/usr/bin/env python3
"""
Telegram Music Bot - Main Entry Point
A self-bot for playing music in Telegram group voice calls.
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from database import db
from player import downloader, player
from pyrogram import Client
from pytgcalls import PyTgCalls

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

# Initialize Pyrogram client
app = Client(
    config.session_name,
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token
)

# Initialize PyTgCalls
pytgcalls = PyTgCalls(app)
# Bind the pytgcalls instance to player
player.client = pytgcalls

# Import handlers after app/pytgcalls are created (to avoid circular imports)
import handlers  # noqa: F401

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
    
    # Start PyTgCalls
    await pytgcalls.start()
    logger.info("✅ PyTgCalls started")
    
    # Get bot info
    me = await app.get_me()
    logger.info(f"🤖 Bot: @{me.username} ({me.first_name})")
    logger.info(f"📋 Admin IDs: {config.admin_ids if config.admin_ids else 'All users'}")
    logger.info("🎵 Bot is ready! Send /play <song> in a group to start.")


async def shutdown():
    """Graceful shutdown."""
    logger.info("🛑 Shutting down...")
    shutdown_event.set()
    
    # Leave all active calls
    try:
        await pytgcalls.leave_all_calls()
    except Exception as e:
        logger.warning(f"Error leaving calls: {e}")
    
    # Stop clients
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
        loop.add_signal_handler(sig, signal_handler, sig, None)
    
    try:
        await startup()
        # Wait for shutdown signal
        await shutdown_event.wait()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await shutdown()


if __name__ == "__main__":
    # Validate config
    if config.api_id == 0 or not config.api_hash or not config.bot_token:
        print("❌ Config incomplete! Please edit config.py with your credentials:")
        print("   API_ID, API_HASH (from my.telegram.org)")
        print("   BOT_TOKEN (from @BotFather)")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)