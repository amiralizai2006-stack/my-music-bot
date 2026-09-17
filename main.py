#!/usr/bin/env python3

import asyncio
import logging
import os
import sys
import signal
from pathlib import Path

from aiohttp import web

sys.path.insert(
    0,
    str(Path(__file__).parent),
)

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

from assistant import create_assistant


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(
        logging,
        config.log_level,
        logging.INFO,
    ),
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    handlers=[
        logging.FileHandler(
            config.log_file
        ),
        logging.StreamHandler(
            sys.stdout
        ),
    ],
)

logger = logging.getLogger(__name__)


# ============================================================
# RENDER
# ============================================================

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)

health_runner = None


async def health(request):
    return web.json_response(
        {
            "status": "ok",
            "service": "SILENT MUSIC BOT",
            "telegram": "online",
            "voice_chat": (
                "assistant"
                if VOICE_CHAT_AVAILABLE
                else "unavailable"
            ),
        }
    )


async def start_health_server():

    server = web.Application()

    server.router.add_get(
        "/",
        health,
    )

    server.router.add_get(
        "/health",
        health,
    )

    runner = web.AppRunner(
        server
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=PORT,
    )

    await site.start()

    logger.info(
        "🌐 Render health server started on port %s",
        PORT,
    )

    return runner


# ============================================================
# PLATFORM
# ============================================================

platform_info = get_platform_info()

logger.info(
    "=== Platform Info ==="
)

for key, value in platform_info.items():
    logger.info(
        "%s: %s",
        key,
        value,
    )

logger.info(
    "====================="
)


# ============================================================
# CONFIG VALIDATION
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


# ============================================================
# VOICE CHAT SUPPORT
# ============================================================

voice_supported, voice_msg = (
    check_voice_chat_support()
)

if VOICE_CHAT_AVAILABLE:

    logger.info(
        "✅ Voice chat support available"
    )

else:

    logger.warning(
        "⚠️ Voice chat unavailable: %s",
        voice_msg,
    )


# ============================================================
# GLOBAL OBJECTS
# ============================================================

bot = None
assistant = None
pytgcalls = None
player = None
shutdown_event = None


# ============================================================
# CREATE RUNTIME
# ============================================================

def create_runtime():

    global bot
    global assistant
    global pytgcalls
    global player
    global shutdown_event

    logger.info(
        "🔧 Creating runtime..."
    )

    # ========================================================
    # BOT CLIENT
    # ========================================================

    bot = Client(
        config.session_name,
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token,
    )

    logger.info(
        "✅ Bot client created"
    )

    # ========================================================
    # ASSISTANT USER CLIENT
    # ========================================================

    if VOICE_CHAT_AVAILABLE:

        try:

            assistant = create_assistant(
                config.api_id,
                config.api_hash,
            )

            logger.info(
                "✅ Assistant client created"
            )

        except Exception:

            logger.exception(
                "❌ Could not create assistant"
            )

            raise

    else:

        assistant = None

    # ========================================================
    # PYTGCALLS
    #
    # IMPORTANT:
    # PyTgCalls MUST use the assistant USER account.
    # It must NOT use the Bot client.
    # ========================================================

    if assistant:

        try:

            pytgcalls = PyTgCalls(
                assistant
            )

            logger.info(
                "✅ PyTgCalls attached to ASSISTANT account"
            )

        except Exception:

            logger.exception(
                "❌ Failed to create PyTgCalls"
            )

            pytgcalls = None

            raise

    else:

        pytgcalls = None

    # ========================================================
    # MUSIC PLAYER
    # ========================================================

    player = MusicPlayer(
        pytgcalls
    )

    logger.info(
        "✅ MusicPlayer created"
    )

    # ========================================================
    # SHUTDOWN EVENT
    # ========================================================

    shutdown_event = asyncio.Event()

    logger.info(
        "✅ Runtime created successfully"
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
    # CREATE EVERYTHING IN CURRENT EVENT LOOP
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
    # HEALTH SERVER
    # ========================================================

    try:

        health_runner = (
            await start_health_server()
        )

    except Exception:

        logger.exception(
            "❌ Health server failed"
        )

        raise

    # ========================================================
    # BOT START
    # ========================================================

    try:

        await bot.start()

        logger.info(
            "✅ Telegram BOT started"
        )

    except Exception:

        logger.exception(
            "❌ Bot failed to start"
        )

        raise

    # ========================================================
    # ASSISTANT START
    # ========================================================

    if assistant:

        try:

            await assistant.start()

            logger.info(
                "✅ Telegram ASSISTANT started"
            )

            # ------------------------------------------------
            # Assistant account information
            # ------------------------------------------------

            assistant_me = (
                await assistant.get_me()
            )

            logger.info(
                "🎧 Assistant: @%s",
                assistant_me.username
                or assistant_me.first_name,
            )

        except Exception:

            logger.exception(
                "❌ Assistant failed to start"
            )

            raise

    # ========================================================
    # PYTGCALLS START
    # ========================================================

    if pytgcalls:

        try:

            await pytgcalls.start()

            logger.info(
                "✅ PyTgCalls started"
            )

            logger.info(
                "🎧 Voice chat is using ASSISTANT account"
            )

        except Exception:

            logger.exception(
                "❌ PyTgCalls failed to start"
            )

            raise

    else:

        logger.warning(
            "⚠️ PyTgCalls is not available"
        )

    # ========================================================
    # HANDLERS
    #
    # handlers still receive BOT as the message client.
    # PyTgCalls/player use ASSISTANT.
    # ========================================================

    try:

        set_bot_instances(
            bot,
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

    bot_me = await bot.get_me()

    logger.info(
        "🤖 Bot: @%s (%s)",
        bot_me.username,
        bot_me.first_name,
    )

    logger.info(
        "📋 Admin IDs: %s",
        (
            config.admin_ids
            if config.admin_ids
            else "All users"
        ),
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
        "🤖 Bot account: ONLINE"
    )

    logger.info(
        "🎧 Assistant account: ONLINE"
    )

    logger.info(
        "🎵 Persian commands: ENABLED"
    )

    logger.info(
        "🔊 Voice Chat: ASSISTANT ACCOUNT"
    )

    logger.info(
        "🟢 Render health server: PORT %s",
        PORT,
    )

    logger.info(
        "=================================================="
    )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():

    global health_runner

    logger.info(
        "🛑 Shutting down..."
    )

    # ========================================================
    # EVENT
    # ========================================================

    if shutdown_event:

        try:
            shutdown_event.set()
        except Exception:
            pass

    # ========================================================
    # LEAVE VOICE CALLS
    # ========================================================

    if pytgcalls:

        try:

            await pytgcalls.leave_all_calls()

            logger.info(
                "✅ Assistant left all voice calls"
            )

        except Exception:

            logger.exception(
                "Error leaving voice calls"
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
    # ASSISTANT STOP
    # ========================================================

    if assistant:

        try:

            if assistant.is_connected:

                await assistant.stop()

                logger.info(
                    "✅ Assistant stopped"
                )

        except Exception:

            logger.exception(
                "Error stopping assistant"
            )

    # ========================================================
    # BOT STOP
    # ========================================================

    if bot:

        try:

            if bot.is_connected:

                await bot.stop()

                logger.info(
                    "✅ Bot stopped"
                )

        except Exception:

            logger.exception(
                "Error stopping bot"
            )

    # ========================================================
    # HEALTH SERVER
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

    global shutdown_event

    loop = asyncio.get_running_loop()

    # ========================================================
    # SIGNALS
    # ========================================================

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

    # ========================================================
    # START
    # ========================================================

    try:

        await startup()

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
