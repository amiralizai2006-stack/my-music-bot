#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).parent))

from config import config, validate_config
from database import db
from player import MusicPlayer
from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    PyTgCalls,
    check_voice_chat_support,
    get_platform_info,
)
from handlers import set_bot_instances
from pyrogram import Client


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(config, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# ============================================================
# PLATFORM
# ============================================================

platform_info = get_platform_info()

logger.info("=== Platform Info ===")
for key, value in platform_info.items():
    logger.info(f"  {key}: {value}")
logger.info("=====================")


# ============================================================
# CONFIG VALIDATION
# ============================================================

errors = validate_config()

if errors:
    logger.error("Configuration errors:")
    for error in errors:
        logger.error(f"  - {error}")
    sys.exit(1)


voice_supported, voice_msg = check_voice_chat_support()

if VOICE_CHAT_AVAILABLE:
    logger.info("✅ Voice chat: AVAILABLE")
else:
    logger.warning(f"⚠️ Voice chat: NOT AVAILABLE - {voice_msg}")


# ============================================================
# PYROGRAM
# ============================================================

app = Client(
    config.session_name,
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token,
)


# ============================================================
# PYTG CALLS
# ============================================================

pytgcalls = None

if VOICE_CHAT_AVAILABLE and PyTgCalls is not None:
    try:
        pytgcalls = PyTgCalls(app)
        logger.info("✅ PyTgCalls client created")
    except Exception:
        logger.exception("❌ Failed to create PyTgCalls client")
        pytgcalls = None
        VOICE_CHAT_AVAILABLE = False


# ============================================================
# MUSIC PLAYER
# ============================================================

player = MusicPlayer(pytgcalls)


# ============================================================
# SHUTDOWN
# ============================================================

shutdown_event = asyncio.Event()

health_runner = None


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

async def health_handler(request):
    return web.json_response(
        {
            "status": "ok",
            "service": "Persian Telegram Music Bot",
            "voice_chat": bool(VOICE_CHAT_AVAILABLE and pytgcalls),
        }
    )


async def start_health_server():
    global health_runner

    port = int(os.getenv("PORT", "10000"))

    health_app = web.Application()

    health_app.router.add_get("/", health_handler)
    health_app.router.add_get("/health", health_handler)

    health_runner = web.AppRunner(health_app)

    await health_runner.setup()

    site = web.TCPSite(
        health_runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logger.info(f"🌐 Render health server listening on 0.0.0.0:{port}")


async def stop_health_server():
    global health_runner

    if health_runner:
        try:
            await health_runner.cleanup()
        except Exception as e:
            logger.warning(f"Health server shutdown error: {e}")

        health_runner = None


# ============================================================
# STARTUP
# ============================================================

async def startup():
    logger.info("🚀 Starting Telegram Music Bot...")

    # Database
    await db.init()
    logger.info("✅ Database initialized")

    # Render health server
    await start_health_server()

    # Pyrogram
    await app.start()
    logger.info("✅ Pyrogram client started")

    # PyTgCalls
    if pytgcalls:
        try:
            await pytgcalls.start()
            logger.info("✅ PyTgCalls started")
        except Exception:
            logger.exception("❌ PyTgCalls failed to start")
            raise
    else:
        logger.warning("⚠️ PyTgCalls is not running")

    # Register handlers
    set_bot_instances(
        app,
        pytgcalls,
        player,
        shutdown_event,
    )

    # Bot information
    me = await app.get_me()

    logger.info(
        f"🤖 Bot: @{me.username} ({me.first_name})"
    )

    logger.info(
        f"📋 Admin IDs: "
        f"{config.admin_ids if config.admin_ids else 'All users'}"
    )

    if pytgcalls:
        logger.info(
            "🎵 Bot is ready with Voice Chat support!"
        )
    else:
        logger.warning(
            "🎵 Bot is running without Voice Chat."
        )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():
    logger.info("🛑 Shutting down...")

    if shutdown_event.is_set():
        return

    shutdown_event.set()

    # Leave voice calls
    if pytgcalls:
        try:
            await pytgcalls.leave_all_calls()
        except Exception as e:
            logger.warning(
                f"Error leaving calls: {e}"
            )

    # Stop PyTgCalls
    if pytgcalls:
        try:
            await pytgcalls.stop()
        except Exception as e:
            logger.warning(
                f"Error stopping PyTgCalls: {e}"
            )

    # Stop Pyrogram
    try:
        if app.is_connected:
            await app.stop()
    except Exception as e:
        logger.warning(
            f"Error stopping Pyrogram: {e}"
        )

    # Stop Render health server
    await stop_health_server()

    logger.info("✅ Shutdown complete")


# ============================================================
# SIGNAL HANDLING
# ============================================================

def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(shutdown())
    except RuntimeError:
        pass


# ============================================================
# MAIN
# ============================================================

async def main():

    loop = asyncio.get_running_loop()

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):
        try:
            loop.add_signal_handler(
                sig,
                signal_handler,
                sig,
                None,
            )
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await startup()

        logger.info(
            "🟢 Bot is running continuously."
        )

        await shutdown_event.wait()

    except asyncio.CancelledError:
        logger.info("Main task cancelled.")

    except Exception as e:
        logger.error(
            f"❌ Fatal error: {e}",
            exc_info=True,
        )

    finally:
        await shutdown()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        pass

    except Exception as e:
        logger.error(
            f"❌ Fatal error: {e}",
            exc_info=True,
        )

        sys.exit(1)
