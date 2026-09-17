#!/usr/bin/env python3

import asyncio
import logging
import os
import sys
import signal
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
    level=getattr(
        logging,
        config.log_level,
        logging.INFO,
    ),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

PORT = int(
    os.getenv("PORT", "10000")
)

health_runner = None


async def health(request):
    return web.json_response(
        {
            "status": "ok",
            "service": "SILENT MUSIC BOT",
            "telegram": "online",
        }
    )


async def start_health_server():
    app = web.Application()

    app.router.add_get(
        "/",
        health,
    )

    app.router.add_get(
        "/health",
        health,
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=PORT,
    )

    await site.start()

    logger.info(
        "🌐 Render health server started on 0.0.0.0:%s",
        PORT,
    )

    return runner


# ============================================================
# PLATFORM
# ============================================================

platform_info = get_platform_info()

logger.info("=== Platform Info ===")

for key, value in platform_info.items():
    logger.info(
        "%s: %s",
        key,
        value,
    )

logger.info("=====================")


# ============================================================
# CONFIG
# ============================================================

errors = validate_config()

if errors:

    logger.error(
        "Configuration errors:"
    )

    for error in errors:
        logger.error(
            " - %s",
            error,
        )

    sys.exit(1)


voice_supported, voice_msg = (
    check_voice_chat_support()
)

if VOICE_CHAT_AVAILABLE:

    logger.info(
        "✅ Voice chat: AVAILABLE"
    )

else:

    logger.warning(
        "⚠️ Voice chat: NOT AVAILABLE - %s",
        voice_msg,
    )


# ============================================================
# GLOBAL RUNTIME OBJECTS
# ============================================================

app = None
pytgcalls = None
player = None

shutdown_event = None


# ============================================================
# CREATE CLIENTS
# ============================================================

def create_runtime():

    global app
    global pytgcalls
    global player
    global shutdown_event

    logger.info(
        "🔧 Creating runtime objects..."
    )

    # --------------------------------------------------------
    # Pyrogram
    # --------------------------------------------------------

    app = Client(
        config.session_name,
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token,
    )

    logger.info(
        "✅ Pyrogram object created"
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # PyTgCalls is created INSIDE asyncio.run(main())
    # so it belongs to the same running event loop.
    # --------------------------------------------------------

    if VOICE_CHAT_AVAILABLE:

        try:

            pytgcalls = PyTgCalls(app)

            logger.info(
                "✅ PyTgCalls object created inside main loop"
            )

        except Exception:

            logger.exception(
                "❌ Failed to create PyTgCalls"
            )

            pytgcalls = None

    else:

        logger.warning(
            "⚠️ PyTgCalls is unavailable"
        )

        pytgcalls = None

    # --------------------------------------------------------
    # Player
    # --------------------------------------------------------

    player = MusicPlayer(
        pytgcalls
    )

    logger.info(
        "✅ MusicPlayer created"
    )

    # --------------------------------------------------------
    # Shutdown event
    # --------------------------------------------------------

    shutdown_event = asyncio.Event()

    logger.info(
        "✅ Shutdown event created"
    )


# ============================================================
# STARTUP
# ============================================================

async def startup():

    global health_runner

    logger.info(
        "🚀 Starting SILENT MUSIC BOT..."
    )

    # ========================================================
    # CREATE RUNTIME INSIDE CURRENT LOOP
    # ========================================================

    create_runtime()

    # ========================================================
    # DATABASE
    # ========================================================

    try:

        await db.init()

        logger.info(
            "✅ Database initialized"
        )

    except Exception:

        logger.exception(
            "❌ Database initialization failed"
        )

        raise

    # ========================================================
    # RENDER HEALTH SERVER
    # ========================================================

    try:

        health_runner = (
            await start_health_server()
        )

    except Exception:

        logger.exception(
            "❌ Render health server could not start"
        )

        raise

    # ========================================================
    # PYROGRAM
    # ========================================================

    try:

        await app.start()

        logger.info(
            "✅ Pyrogram client started"
        )

    except Exception:

        logger.exception(
            "❌ Pyrogram failed to start"
        )

        raise

    # ========================================================
    # PYTGCALLS
    # ========================================================

    if pytgcalls:

        try:

            await pytgcalls.start()

            logger.info(
                "✅ PyTgCalls started"
            )

        except Exception:

            logger.exception(
                "❌ PyTgCalls failed to start"
            )

            raise

    # ========================================================
    # HANDLERS
    # ========================================================

    try:

        set_bot_instances(
            app,
            pytgcalls,
            player,
            shutdown_event,
        )

        logger.info(
            "✅ Telegram handlers registered"
        )

    except Exception:

        logger.exception(
            "❌ Handler registration failed"
        )

        raise

    # ========================================================
    # BOT INFO
    # ========================================================

    me = await app.get_me()

    logger.info(
        "🤖 Bot: @%s (%s)",
        me.username,
        me.first_name,
    )

    logger.info(
        "📋 Admin IDs: %s",
        config.admin_ids
        if config.admin_ids
        else "All users",
    )

    # ========================================================
    # READY
    # ========================================================

    logger.info(
        "=================================================="
    )

    logger.info(
        "🟢 SILENT MUSIC BOT IS ONLINE"
    )

    logger.info(
        "🟢 Render health server: PORT %s",
        PORT,
    )

    logger.info(
        "🎵 Persian commands are enabled"
    )

    logger.info(
        "🎧 Voice chat system initialized"
    )

    logger.info(
        "=================================================="
    )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():

    global health_runner
    global app
    global pytgcalls

    logger.info(
        "🛑 Shutting down..."
    )

    # ========================================================
    # SIGNAL EVENT
    # ========================================================

    if shutdown_event:

        try:
            shutdown_event.set()
        except Exception:
            pass

    # ========================================================
    # LEAVE CALLS
    # ========================================================

    if pytgcalls:

        try:

            await pytgcalls.leave_all_calls()

            logger.info(
                "✅ Left all voice calls"
            )

        except Exception:

            logger.exception(
                "Error leaving calls"
            )

    # ========================================================
    # PYTGCALLS STOP
    # ========================================================

    if pytgcalls:

        try:

            await pytgcalls.stop()

            logger.info(
                "✅ PyTgCalls stopped"
            )

        except Exception:

            logger.exception(
                "Error stopping PyTgCalls"
            )

    # ========================================================
    # PYROGRAM STOP
    # ========================================================

    if app:

        try:

            if getattr(
                app,
                "is_connected",
                False,
            ):

                await app.stop()

                logger.info(
                    "✅ Pyrogram stopped"
                )

        except Exception:

            logger.exception(
                "Error stopping Pyrogram"
            )

    # ========================================================
    # HEALTH SERVER STOP
    # ========================================================

    if health_runner:

        try:

            await health_runner.cleanup()

            logger.info(
                "✅ Health server stopped"
            )

        except Exception:

            logger.exception(
                "Error stopping health server"
            )

        health_runner = None

    logger.info(
        "✅ Shutdown complete"
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    loop = asyncio.get_running_loop()

    # --------------------------------------------------------
    # SIGNALS
    # --------------------------------------------------------

    def request_shutdown():

        logger.info(
            "🛑 Shutdown signal received"
        )

        if shutdown_event:

            try:
                shutdown_event.set()
            except Exception:
                pass

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):

        try:

            loop.add_signal_handler(
                sig,
                request_shutdown,
            )

        except (
            NotImplementedError,
            RuntimeError,
        ):

            pass

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    try:

        await startup()

        # ----------------------------------------------------
        # KEEP BOT ALIVE
        # ----------------------------------------------------

        await shutdown_event.wait()

    except Exception:

        logger.exception(
            "❌ Fatal startup/runtime error"
        )

        raise

    finally:

        await shutdown()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "Stopped by keyboard interrupt"
        )

    except Exception:

        logger.exception(
            "❌ Application stopped بسبب خطا"
        )

        sys.exit(1)
