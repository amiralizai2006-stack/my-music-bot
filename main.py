#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web
from pyrogram import Client


# ============================================================
# PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ============================================================
# PROJECT IMPORTS
# ============================================================

from config import config, validate_config
from database import init_db
from player import MusicPlayer

from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    PyTgCalls,
    check_voice_chat_support,
    get_platform_info,
)

from handlers import set_bot_instances
from assistant import create_assistant


# ============================================================
# LOGGING
# ============================================================

LOG_LEVEL = getattr(
    logging,
    str(getattr(config, "log_level", "INFO")).upper(),
    logging.INFO,
)

LOG_FILE = getattr(
    config,
    "log_file",
    "musicbot.log",
)

logging.basicConfig(
    level=LOG_LEVEL,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    handlers=[
        logging.FileHandler(
            LOG_FILE,
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("SILENT")


# ============================================================
# RENDER / HEALTH SERVER
# ============================================================

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)

health_runner = None


# ============================================================
# GLOBAL RUNTIME OBJECTS
# ============================================================

bot = None
assistant = None
pytgcalls = None
player = None
shutdown_event = None


# ============================================================
# HEALTH ENDPOINT
# ============================================================

async def health(request: web.Request):
    """
    Render health endpoint.
    """

    bot_online = False
    assistant_online = False

    try:
        bot_online = bool(
            bot
            and bot.is_connected
        )
    except Exception:
        bot_online = False

    try:
        assistant_online = bool(
            assistant
            and assistant.is_connected
        )
    except Exception:
        assistant_online = False

    return web.json_response(
        {
            "status": "ok",
            "service": "SILENT MUSIC BOT",
            "telegram": (
                "online"
                if bot_online
                else "starting"
            ),
            "assistant": (
                "online"
                if assistant_online
                else "offline"
            ),
            "voice_chat": (
                "ready"
                if pytgcalls
                else "unavailable"
            ),
        }
    )


async def start_health_server():
    """
    Starts the HTTP health server used by Render.
    """

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
        "🌐 Health server listening on 0.0.0.0:%s",
        PORT,
    )

    return runner


# ============================================================
# PLATFORM INFORMATION
# ============================================================

try:

    platform_info = get_platform_info()

    logger.info(
        "========== PLATFORM =========="
    )

    for key, value in platform_info.items():
        logger.info(
            "%s: %s",
            key,
            value,
        )

    logger.info(
        "=============================="
    )

except Exception:

    logger.exception(
        "⚠️ Could not read platform information"
    )


# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

config_errors = validate_config()

if config_errors:

    logger.error(
        "❌ Configuration validation failed:"
    )

    for error in config_errors:
        logger.error(
            "   • %s",
            error,
        )

    raise SystemExit(1)


# ============================================================
# VOICE CHAT SUPPORT
# ============================================================

try:

    voice_supported, voice_message = (
        check_voice_chat_support()
    )

except Exception as exc:

    voice_supported = False
    voice_message = str(exc)


if (
    VOICE_CHAT_AVAILABLE
    and voice_supported
):

    logger.info(
        "🎧 Voice-chat support: AVAILABLE"
    )

else:

    logger.warning(
        "⚠️ Voice-chat support: UNAVAILABLE | %s",
        voice_message,
    )


# ============================================================
# RUNTIME CREATION
# ============================================================

def create_runtime():
    """
    Creates the long-lived Telegram runtime.

    Architecture:

        Telegram Bot
             ↓
        Assistant Account
             ↓
          PyTgCalls
             ↓
         MusicPlayer
    """

    global bot
    global assistant
    global pytgcalls
    global player
    global shutdown_event

    logger.info(
        "🔧 Creating runtime..."
    )

    # --------------------------------------------------------
    # BOT
    # --------------------------------------------------------

    bot = Client(
        name=config.session_name,
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token,
    )

    logger.info(
        "🤖 Bot client created"
    )

    # --------------------------------------------------------
    # ASSISTANT
    # --------------------------------------------------------

    assistant = None

    if (
        VOICE_CHAT_AVAILABLE
        and voice_supported
    ):

        try:

            assistant = create_assistant(
                config.api_id,
                config.api_hash,
            )

            logger.info(
                "🎧 Assistant client created"
            )

        except Exception:

            logger.exception(
                "❌ Failed to create assistant client"
            )

            raise

    else:

        logger.warning(
            "⚠️ Assistant disabled because voice chat is unavailable"
        )

    # --------------------------------------------------------
    # PYTGCALLS
    # --------------------------------------------------------

    pytgcalls = None

    if assistant:

        try:

            pytgcalls = PyTgCalls(
                assistant
            )

            logger.info(
                "🔊 PyTgCalls attached to assistant"
            )

        except Exception:

            logger.exception(
                "❌ Failed to create PyTgCalls"
            )

            raise

    # --------------------------------------------------------
    # MUSIC PLAYER
    # --------------------------------------------------------

    try:

        player = MusicPlayer(
            call=pytgcalls
        )

        logger.info(
            "🎵 MusicPlayer created"
        )

    except Exception:

        logger.exception(
            "❌ Failed to create MusicPlayer"
        )

        raise

    # --------------------------------------------------------
    # SHUTDOWN EVENT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    try:

        init_db()

        logger.info(
            "🗄️ Database initialized"
        )

    except Exception:

        logger.exception(
            "❌ Database initialization failed"
        )

        raise

    # --------------------------------------------------------
    # RUNTIME
    # --------------------------------------------------------

    create_runtime()

    # --------------------------------------------------------
    # HEALTH SERVER
    # --------------------------------------------------------

    try:

        health_runner = (
            await start_health_server()
        )

    except Exception:

        logger.exception(
            "❌ Failed to start health server"
        )

        raise

    # --------------------------------------------------------
    # REGISTER HANDLERS
    # --------------------------------------------------------
    #
    # Register handlers BEFORE starting the bot.
    # This keeps the runtime initialization clean.
    #

    try:

        set_bot_instances(
            bot,
            pytgcalls,
            player,
            shutdown_event,
        )

        logger.info(
            "🎛️ Bot handlers connected"
        )

    except Exception:

        logger.exception(
            "❌ Failed to connect handlers"
        )

        raise

    # --------------------------------------------------------
    # START BOT
    # --------------------------------------------------------

    try:

        await bot.start()

        logger.info(
            "🤖 Telegram bot started"
        )

    except Exception:

        logger.exception(
            "❌ Telegram bot failed to start"
        )

        raise

    # --------------------------------------------------------
    # START ASSISTANT
    # --------------------------------------------------------

    if assistant:

        try:

            await assistant.start()

            assistant_me = (
                await assistant.get_me()
            )

            assistant_name = (
                f"@{assistant_me.username}"
                if assistant_me.username
                else (
                    assistant_me.first_name
                    or "Assistant"
                )
            )

            logger.info(
                "🎧 Assistant started: %s",
                assistant_name,
            )

        except Exception:

            logger.exception(
                "❌ Assistant failed to start"
            )

            raise

    # --------------------------------------------------------
    # START PYTGCALLS
    # --------------------------------------------------------

    if pytgcalls:

        try:

            await pytgcalls.start()

            logger.info(
                "🔊 PyTgCalls started"
            )

            logger.info(
                "🎧 Voice calls use the assistant account"
            )

        except Exception:

            logger.exception(
                "❌ PyTgCalls failed to start"
            )

            raise

    else:

        logger.warning(
            "⚠️ PyTgCalls is not running"
        )

    # --------------------------------------------------------
    # BOT INFO
    # --------------------------------------------------------

    try:

        bot_me = await bot.get_me()

        bot_name = (
            f"@{bot_me.username}"
            if bot_me.username
            else (
                bot_me.first_name
                or "SILENT"
            )
        )

        logger.info(
            "🤖 Bot identity: %s",
            bot_name,
        )

    except Exception:

        logger.exception(
            "⚠️ Could not read bot profile"
        )

    # --------------------------------------------------------
    # ADMIN INFO
    # --------------------------------------------------------

    admin_ids = getattr(
        config,
        "admin_ids",
        [],
    )

    logger.info(
        "👑 Owner/Admin configuration loaded: %s",
        "YES" if admin_ids else "OWNER ONLY",
    )

    # --------------------------------------------------------
    # READY
    # --------------------------------------------------------

    logger.info(
        "=================================================="
    )

    logger.info(
        "🟢 SILENT MUSIC BOT IS ONLINE"
    )

    logger.info(
        "🤖 Telegram Bot       : ONLINE"
    )

    logger.info(
        "🎧 Assistant          : %s",
        "ONLINE" if assistant else "OFFLINE",
    )

    logger.info(
        "🔊 Voice Engine       : %s",
        "ONLINE" if pytgcalls else "OFFLINE",
    )

    logger.info(
        "🎵 Music Player       : %s",
        "READY" if player else "FAILED",
    )

    logger.info(
        "🇮🇷 Persian Interface : ENABLED"
    )

    logger.info(
        "🌐 Render Health      : :%s",
        PORT,
    )

    logger.info(
        "=================================================="
    )


# ============================================================
# LEAVE VOICE CALLS
# ============================================================

async def leave_voice_calls():

    if not pytgcalls:
        return

    # --------------------------------------------------------
    # Newer / compatible implementations
    # --------------------------------------------------------

    leave_all = getattr(
        pytgcalls,
        "leave_all_calls",
        None,
    )

    if callable(leave_all):

        try:

            result = leave_all()

            if asyncio.iscoroutine(result):
                await result

            logger.info(
                "✅ Left all voice calls"
            )

            return

        except Exception:

            logger.exception(
                "⚠️ leave_all_calls failed"
            )

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------
    #
    # Some PyTgCalls versions expose only leave_call(chat_id).
    # Try the currently known chat from the player if available.
    #

    chat_ids = set()

    try:

        active_chat_ids = getattr(
            player,
            "active_chat_ids",
            None,
        )

        if active_chat_ids:

            chat_ids.update(
                active_chat_ids
            )

    except Exception:
        pass

    try:

        current = getattr(
            player,
            "current",
            None,
        )

        if isinstance(current, dict):

            chat_id = current.get(
                "chat_id"
            )

            if chat_id:
                chat_ids.add(
                    int(chat_id)
                )

    except Exception:
        pass

    leave_call = getattr(
        pytgcalls,
        "leave_call",
        None,
    )

    if callable(leave_call):

        for chat_id in chat_ids:

            try:

                result = leave_call(
                    chat_id
                )

                if asyncio.iscoroutine(result):
                    await result

                logger.info(
                    "✅ Left voice call: %s",
                    chat_id,
                )

            except Exception:

                logger.exception(
                    "⚠️ Failed to leave voice call: %s",
                    chat_id,
                )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():

    global health_runner

    logger.info(
        "🛑 Shutting down SILENT MUSIC BOT..."
    )

    # --------------------------------------------------------
    # SIGNAL EVENT
    # --------------------------------------------------------

    if shutdown_event:

        try:
            shutdown_event.set()
        except Exception:
            pass

    # --------------------------------------------------------
    # LEAVE VOICE CALLS
    # --------------------------------------------------------

    try:

        await leave_voice_calls()

    except Exception:

        logger.exception(
            "⚠️ Voice-call cleanup failed"
        )

    # --------------------------------------------------------
    # STOP PYTGCALLS
    # --------------------------------------------------------

    if pytgcalls:

        try:

            stop_method = getattr(
                pytgcalls,
                "stop",
                None,
            )

            if callable(stop_method):

                result = stop_method()

                if asyncio.iscoroutine(result):
                    await result

            logger.info(
                "✅ PyTgCalls stopped"
            )

        except Exception:

            logger.exception(
                "⚠️ Failed to stop PyTgCalls"
            )

    # --------------------------------------------------------
    # STOP ASSISTANT
    # --------------------------------------------------------

    if assistant:

        try:

            if assistant.is_connected:

                await assistant.stop()

                logger.info(
                    "✅ Assistant stopped"
                )

        except Exception:

            logger.exception(
                "⚠️ Failed to stop assistant"
            )

    # --------------------------------------------------------
    # STOP BOT
    # --------------------------------------------------------

    if bot:

        try:

            if bot.is_connected:

                await bot.stop()

                logger.info(
                    "✅ Bot stopped"
                )

        except Exception:

            logger.exception(
                "⚠️ Failed to stop bot"
            )

    # --------------------------------------------------------
    # HEALTH SERVER
    # --------------------------------------------------------

    if health_runner:

        try:

            await health_runner.cleanup()

            logger.info(
                "✅ Health server stopped"
            )

        except Exception:

            logger.exception(
                "⚠️ Failed to stop health server"
            )

        finally:

            health_runner = None

    logger.info(
        "🟢 Shutdown complete"
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    global shutdown_event

    loop = asyncio.get_running_loop()

    # --------------------------------------------------------
    # SIGNAL HANDLER
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

        if shutdown_event:

            await shutdown_event.wait()

    except asyncio.CancelledError:

        logger.info(
            "🛑 Main task cancelled"
        )

        raise

    except Exception:

        logger.exception(
            "❌ Fatal runtime error"
        )

        raise

    finally:

        await shutdown()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info(
            "🛑 Stopped by keyboard interrupt"
        )

    except Exception:

        logger.exception(
            "❌ Application stopped بسبب خطا"
        )

        sys.exit(1)
