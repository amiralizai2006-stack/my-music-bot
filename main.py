#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import pyrogram.errors

# =========================================================
# PYROGRAM COMPATIBILITY
# =========================================================

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


from aiohttp import web
from pyrogram import Client
from pytgcalls import PyTgCalls

# =========================================================
# PATH
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# =========================================================
# PROJECT IMPORTS
# =========================================================

from config import config, validate_config
from database import db
from player import MusicPlayer
from handlers import (
    set_bot_instances,
    register_handlers,
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=getattr(
        logging,
        getattr(
            config,
            "log_level",
            "INFO",
        ).upper(),
        logging.INFO,
    ),
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
)

logger = logging.getLogger(
    "PersianMusicBot"
)


# =========================================================
# CONFIGURATION
# =========================================================

config_errors = validate_config()

if config_errors:

    logger.error(
        "Configuration errors:"
    )

    for error in config_errors:
        logger.error(
            "  - %s",
            error,
        )

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
        "ASSISTANT_SESSION is not configured."
    )

    sys.exit(1)


# =========================================================
# TELEGRAM CLIENTS
# =========================================================

bot = Client(
    "telegram_music_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


assistant = Client(
    "music_assistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=ASSISTANT_SESSION,
    in_memory=True,
)


# =========================================================
# GLOBAL OBJECTS
# =========================================================

pytgcalls = None
player = None
shutdown_event = None
health_runner = None


# =========================================================
# HEALTH SERVER
# =========================================================

async def health_handler(request):

    return web.json_response(
        {
            "status": "ok",
            "service": "Persian Telegram Music Bot",
            "bot": bot.is_connected,
            "assistant": assistant.is_connected,
            "voice_chat": (
                pytgcalls is not None
            ),
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

    health_runner = web.AppRunner(
        app
    )

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
# STARTUP
# =========================================================

async def startup():

    global pytgcalls
    global player
    global shutdown_event

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
    # DATABASE
    # -----------------------------------------------------

    logger.info(
        "Initializing database..."
    )

    await db.init()

    logger.info(
        "Database initialized successfully"
    )

    # -----------------------------------------------------
    # HEALTH SERVER
    # -----------------------------------------------------

    await start_health_server()

    # -----------------------------------------------------
    # TELEGRAM BOT
    # -----------------------------------------------------

    logger.info(
        "Starting Telegram bot..."
    )

    await bot.start()

    logger.info(
        "Telegram bot started successfully"
    )

    # -----------------------------------------------------
    # ASSISTANT
    # -----------------------------------------------------

    logger.info(
        "Starting assistant account..."
    )

    await assistant.start()

    logger.info(
        "Assistant account started successfully"
    )

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
    # PYTGCALLS
    # -----------------------------------------------------

    logger.info(
        "Creating PyTgCalls on current event loop..."
    )

    pytgcalls = PyTgCalls(
        assistant
    )

    logger.info(
        "PyTgCalls object created"
    )

    logger.info(
        "Starting PyTgCalls..."
    )

    await pytgcalls.start()

    logger.info(
        "PyTgCalls started successfully"
    )

    # -----------------------------------------------------
    # PLAYER
    # -----------------------------------------------------

    player = MusicPlayer(
        pytgcalls
    )

    logger.info(
        "MusicPlayer created"
    )

    # -----------------------------------------------------
    # SHUTDOWN EVENT
    # -----------------------------------------------------

    shutdown_event = asyncio.Event()

    # -----------------------------------------------------
    # CONNECT OBJECTS TO HANDLERS
    # -----------------------------------------------------

    set_bot_instances(
        bot,
        pytgcalls,
        player,
        shutdown_event,
    )

    # IMPORTANT:
    # Actually register Telegram message handlers.
    register_handlers()

    logger.info(
        "Bot handlers registered successfully"
    )

    # -----------------------------------------------------
    # BOT INFO
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
    # FINAL STATUS
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
        "HANDLERS: READY"
    )

    logger.info(
        "PERSIAN MUSIC BOT IS RUNNING"
    )

    logger.info(
        "EVENT LOOP: %s",
        id(asyncio.get_running_loop()),
    )

    logger.info(
        "========================================"
    )


# =========================================================
# SHUTDOWN
# =========================================================

async def shutdown():

    global pytgcalls

    logger.info(
        "Shutting down bot..."
    )

    # -----------------------------------------------------
    # VOICE CALLS
    # -----------------------------------------------------

    if pytgcalls is not None:

        try:

            await pytgcalls.leave_all_calls()

            logger.info(
                "Voice chats closed"
            )

        except Exception:

            logger.exception(
                "Could not close voice chats"
            )

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
    # ASSISTANT
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
    # BOT
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
    # HEALTH SERVER
    # -----------------------------------------------------

    await stop_health_server()

    logger.info(
        "Shutdown complete"
    )


# =========================================================
# SIGNAL HANDLING
# =========================================================

def request_shutdown():

    global shutdown_event

    if shutdown_event is None:
        return

    if not shutdown_event.is_set():

        shutdown_event.set()


# =========================================================
# MAIN
# =========================================================

async def main():

    global shutdown_event

    loop = asyncio.get_running_loop()

    logger.info(
        "MAIN EVENT LOOP: %s",
        id(loop),
    )

    # -----------------------------------------------------
    # SIGNALS
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
# ENTRY POINT
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
