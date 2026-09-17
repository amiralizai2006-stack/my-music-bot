#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# =========================================================
# Pyrogram / PyTgCalls compatibility patch
# MUST run before importing PyTgCalls
# =========================================================

import pyrogram.errors


if not hasattr(pyrogram.errors, "GroupcallForbidden"):
    if hasattr(pyrogram.errors, "GroupCallForbidden"):
        pyrogram.errors.GroupcallForbidden = (
            pyrogram.errors.GroupCallForbidden
        )
    else:
        class GroupcallForbidden(Exception):
            pass

        pyrogram.errors.GroupcallForbidden = GroupcallForbidden


if not hasattr(pyrogram.errors, "GroupcallInvalid"):
    if hasattr(pyrogram.errors, "GroupCallInvalid"):
        pyrogram.errors.GroupcallInvalid = (
            pyrogram.errors.GroupCallInvalid
        )
    else:
        class GroupcallInvalid(Exception):
            pass

        pyrogram.errors.GroupcallInvalid = GroupcallInvalid


# =========================================================
# Imports
# =========================================================

from aiohttp import web
from pyrogram import Client
from pytgcalls import PyTgCalls


# =========================================================
# Project imports
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from config import config, validate_config
from database import db
from player import MusicPlayer
from handlers import set_bot_instances


# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    level=getattr(
        logging,
        getattr(config, "log_level", "INFO").upper(),
        logging.INFO,
    ),
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("PersianMusicBot")


# =========================================================
# Configuration
# =========================================================

config_errors = validate_config()

if config_errors:
    logger.error("Configuration errors:")

    for error in config_errors:
        logger.error("  - %s", error)

    sys.exit(1)


API_ID = config.api_id
API_HASH = config.api_hash
BOT_TOKEN = config.bot_token


# =========================================================
# Assistant Session
# =========================================================

ASSISTANT_SESSION = os.getenv(
    "ASSISTANT_SESSION",
    "",
).strip()


if not ASSISTANT_SESSION:
    logger.error(
        "ASSISTANT_SESSION is not configured in Render Environment Variables."
    )
    sys.exit(1)


# =========================================================
# Telegram Bot
# =========================================================

bot = Client(
    "telegram_music_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# =========================================================
# Telegram Assistant User
# =========================================================

assistant = Client(
    "music_assistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=ASSISTANT_SESSION,
    in_memory=True,
)


# =========================================================
# PyTgCalls
# =========================================================

pytgcalls = PyTgCalls(
    assistant
)


# =========================================================
# Music Player
# =========================================================

player = MusicPlayer(
    pytgcalls
)


# =========================================================
# Application State
# =========================================================

shutdown_event = asyncio.Event()

health_runner = None


# =========================================================
# Render Health Check
# =========================================================

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

    app = web.Application()

    app.router.add_get(
        "/",
        health_handler,
    )

    app.router.add_get(
        "/health",
        health_handler,
    )

    health_runner = web.AppRunner(app)

    await health_runner.setup()

    site = web.TCPSite(
        health_runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logger.info(
        "Health server started on port %s",
        port,
    )


async def stop_health_server():

    global health_runner

    if health_runner is not None:

        try:
            await health_runner.cleanup()

        except Exception:
            logger.exception(
                "Health server shutdown error"
            )

        health_runner = None


# =========================================================
# Startup
# =========================================================

async def startup():

    logger.info(
        "========================================"
    )

    logger.info(
        "Starting Persian Telegram Music Bot"
    )

    logger.info(
        "========================================"
    )

    # -----------------------------------------------------
    # Database
    # -----------------------------------------------------

    logger.info(
        "Initializing database..."
    )

    await db.init()

    logger.info(
        "Database initialized successfully"
    )

    # -----------------------------------------------------
    # Render health server
    # -----------------------------------------------------

    await start_health_server()

    # -----------------------------------------------------
    # Telegram Bot
    # -----------------------------------------------------

    logger.info(
        "Starting Telegram bot..."
    )

    await bot.start()

    logger.info(
        "Telegram bot started successfully"
    )

    # -----------------------------------------------------
    # Assistant
    # -----------------------------------------------------

    logger.info(
        "Starting assistant account..."
    )

    await assistant.start()

    logger.info(
        "Assistant account started successfully"
    )

    # -----------------------------------------------------
    # Assistant information
    # -----------------------------------------------------

    try:

        assistant_me = await assistant.get_me()

        assistant_username = (
            f"@{assistant_me.username}"
            if assistant_me.username
            else "no username"
        )

        logger.info(
            "Assistant: %s",
            assistant_username,
        )

    except Exception:
        logger.exception(
            "Could not get assistant information"
        )

    # -----------------------------------------------------
    # PyTgCalls
    # -----------------------------------------------------

    logger.info(
        "Starting PyTgCalls..."
    )

    await pytgcalls.start()

    logger.info(
        "PyTgCalls started successfully"
    )

    # -----------------------------------------------------
    # Handlers
    # -----------------------------------------------------

    set_bot_instances(
        bot,
        pytgcalls,
        player,
        shutdown_event,
    )

    logger.info(
        "Bot handlers registered"
    )

    # -----------------------------------------------------
    # Bot information
    # -----------------------------------------------------

    try:

        bot_me = await bot.get_me()

        bot_username = (
            f"@{bot_me.username}"
            if bot_me.username
            else "no username"
        )

        logger.info(
            "Bot: %s",
            bot_username,
        )

    except Exception:
        logger.exception(
            "Could not get bot information"
        )

    # -----------------------------------------------------
    # Ready
    # -----------------------------------------------------

    logger.info(
        "========================================"
    )

    logger.info(
        "VOICE CHAT: READY"
    )

    logger.info(
        "BOT: READY"
    )

    logger.info(
        "ASSISTANT: READY"
    )

    logger.info(
        "PERSIAN MUSIC BOT IS RUNNING"
    )

    logger.info(
        "========================================"
    )


# =========================================================
# Shutdown
# =========================================================

async def shutdown():

    if shutdown_event.is_set():
        return

    logger.info(
        "Shutting down bot..."
    )

    shutdown_event.set()

    # -----------------------------------------------------
    # Leave voice chats
    # -----------------------------------------------------

    try:

        await pytgcalls.leave_all_calls()

        logger.info(
            "Voice chats closed"
        )

    except Exception:
        logger.exception(
            "Could not close voice chats"
        )

    # -----------------------------------------------------
    # Stop PyTgCalls
    # -----------------------------------------------------

    try:

        await pytgcalls.stop()

        logger.info(
            "PyTgCalls stopped"
        )

    except Exception:
        logger.exception(
            "PyTgCalls shutdown error"
        )

    # -----------------------------------------------------
    # Stop Assistant
    # -----------------------------------------------------

    try:

        if assistant.is_connected:

            await assistant.stop()

            logger.info(
                "Assistant stopped"
            )

    except Exception:
        logger.exception(
            "Assistant shutdown error"
        )

    # -----------------------------------------------------
    # Stop Bot
    # -----------------------------------------------------

    try:

        if bot.is_connected:

            await bot.stop()

            logger.info(
                "Bot stopped"
            )

    except Exception:
        logger.exception(
            "Bot shutdown error"
        )

    # -----------------------------------------------------
    # Stop Health Server
    # -----------------------------------------------------

    await stop_health_server()

    logger.info(
        "Shutdown complete"
    )


# =========================================================
# Signal Handler
# =========================================================

def request_shutdown():

    try:

        loop = asyncio.get_running_loop()

        if not shutdown_event.is_set():

            loop.create_task(
                shutdown()
            )

    except RuntimeError:

        pass


# =========================================================
# Main
# =========================================================

async def main():

    loop = asyncio.get_running_loop()

    # -----------------------------------------------------
    # Linux / Render signal handlers
    # -----------------------------------------------------

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

    try:

        await startup()

        await shutdown_event.wait()

    except asyncio.CancelledError:

        logger.info(
            "Main task cancelled"
        )

    except Exception:

        logger.exception(
            "Fatal startup/runtime error"
        )

        raise

    finally:

        await shutdown()


# =========================================================
# Entry Point
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "Stopped by user"
        )

    except Exception:

        logger.exception(
            "Fatal application error"
        )

        sys.exit(1)
