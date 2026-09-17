#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web
from pyrogram import Client
from pytgcalls import PyTgCalls

sys.path.insert(0, str(Path(__file__).parent))

from config import config, validate_config
from database import db
from player import MusicPlayer
from handlers import set_bot_instances


# =========================
# Logging
# =========================

logging.basicConfig(
    level=getattr(
        logging,
        config.log_level.upper(),
        logging.INFO,
    ),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# =========================
# Configuration
# =========================

errors = validate_config()

if errors:
    logger.error("Configuration errors:")

    for error in errors:
        logger.error(f"  - {error}")

    sys.exit(1)


API_ID = config.api_id
API_HASH = config.api_hash
BOT_TOKEN = config.bot_token

ASSISTANT_SESSION = os.getenv(
    "ASSISTANT_SESSION",
    "",
).strip()


if not ASSISTANT_SESSION:
    logger.error(
        "❌ ASSISTANT_SESSION is not configured."
    )
    sys.exit(1)


# =========================
# Telegram Bot Client
# =========================

bot = Client(
    "telegram_music_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# =========================
# Assistant User Client
# =========================

assistant = Client(
    "music_assistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=ASSISTANT_SESSION,
    in_memory=True,
)


# =========================
# PyTgCalls
# =========================

pytgcalls = PyTgCalls(
    assistant
)


# =========================
# Music Player
# =========================

player = MusicPlayer(
    pytgcalls
)


# =========================
# Shutdown
# =========================

shutdown_event = asyncio.Event()


# =========================
# Render Health Server
# =========================

health_runner = None


async def health_handler(request):

    return web.json_response(
        {
            "status": "ok",
            "service": "Persian Telegram Music Bot",
            "bot": bot.is_connected,
            "assistant": assistant.is_connected,
            "voice_chat": True,
        }
    )


async def start_health_server():

    global health_runner

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    health_app = web.Application()

    health_app.router.add_get(
        "/",
        health_handler,
    )

    health_app.router.add_get(
        "/health",
        health_handler,
    )

    health_runner = web.AppRunner(
        health_app
    )

    await health_runner.setup()

    site = web.TCPSite(
        health_runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logger.info(
        f"🌐 Render health server listening on 0.0.0.0:{port}"
    )


async def stop_health_server():

    global health_runner

    if health_runner:

        try:
            await health_runner.cleanup()

        except Exception as e:

            logger.warning(
                f"Health server shutdown error: {e}"
            )

        health_runner = None


# =========================
# Startup
# =========================

async def startup():

    logger.info(
        "🚀 Starting Telegram Music Bot..."
    )

    # Database
    await db.init()

    logger.info(
        "✅ Database initialized"
    )

    # Render health server
    await start_health_server()

    # Bot
    logger.info(
        "🤖 Starting Telegram Bot..."
    )

    await bot.start()

    logger.info(
        "✅ Telegram Bot started"
    )

    # Assistant
    logger.info(
        "👤 Starting Assistant account..."
    )

    await assistant.start()

    logger.info(
        "✅ Assistant account started"
    )

    # Verify assistant identity
    assistant_me = await assistant.get_me()

    logger.info(
        f"👤 Assistant: "
        f"@{assistant_me.username or 'no_username'} "
        f"({assistant_me.first_name})"
    )

    # PyTgCalls
    logger.info(
        "🎵 Starting PyTgCalls..."
    )

    await pytgcalls.start()

    logger.info(
        "✅ PyTgCalls started successfully"
    )

    # Register bot handlers
    set_bot_instances(
        bot,
        pytgcalls,
        player,
        shutdown_event,
    )

    bot_me = await bot.get_me()

    logger.info(
        f"🤖 Bot: "
        f"@{bot_me.username} "
        f"({bot_me.first_name})"
    )

    logger.info(
        "🎵 Voice Chat: READY"
    )

    logger.info(
        "🟢 Bot is running continuously."
    )


# =========================
# Shutdown
# =========================

async def shutdown():

    if shutdown_event.is_set():
        return

    logger.info(
        "🛑 Shutting down..."
    )

    shutdown_event.set()

    # Leave voice chats
    try:

        await pytgcalls.leave_all_calls()

        logger.info(
            "✅ Voice chats closed"
        )

    except Exception as e:

        logger.warning(
            f"Voice chat shutdown error: {e}"
        )

    # Stop PyTgCalls
    try:

        await pytgcalls.stop()

        logger.info(
            "✅ PyTgCalls stopped"
        )

    except Exception as e:

        logger.warning(
            f"PyTgCalls stop error: {e}"
        )

    # Stop assistant
    try:

        if assistant.is_connected:

            await assistant.stop()

            logger.info(
                "✅ Assistant stopped"
            )

    except Exception as e:

        logger.warning(
            f"Assistant stop error: {e}"
        )

    # Stop bot
    try:

        if bot.is_connected:

            await bot.stop()

            logger.info(
                "✅ Bot stopped"
            )

    except Exception as e:

        logger.warning(
            f"Bot stop error: {e}"
        )

    # Health server
    await stop_health_server()

    logger.info(
        "✅ Shutdown complete"
    )


# =========================
# Signals
# =========================

def signal_handler(
    signum,
    frame,
):

    logger.info(
        f"Received signal {signum}"
    )

    try:

        loop = asyncio.get_running_loop()

        loop.create_task(
            shutdown()
        )

    except RuntimeError:

        pass


# =========================
# Main
# =========================

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

        except (
            NotImplementedError,
            RuntimeError,
        ):

            pass

    try:

        await startup()

        await shutdown_event.wait()

    except asyncio.CancelledError:

        logger.info(
            "Main task cancelled."
        )

    except Exception as e:

        logger.exception(
            f"❌ Fatal error: {e}"
        )

    finally:

        await shutdown()


# =========================
# Run
# =========================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        pass

    except Exception as e:

        logger.exception(
            f"❌ Fatal error: {e}"
        )

        sys.exit(1)
