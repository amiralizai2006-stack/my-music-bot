#!/usr/bin/env python3

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from aiohttp import web
from pyrogram import Client

from pytgcalls import filters as fl
from pytgcalls.types import StreamEnded

============================================================

PATH

============================================================

BASE_DIR = Path(file).resolve().parent

if str(BASE_DIR) not in sys.path:
sys.path.insert(0, str(BASE_DIR))

============================================================

PROJECT IMPORTS

============================================================

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

============================================================

LOGGING

============================================================

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

============================================================

RENDER HEALTH

============================================================

PORT = int(os.getenv("PORT", "10000"))

health_runner = None

============================================================

GLOBAL RUNTIME

============================================================

bot = None
assistant = None
pytgcalls = None
player = None
shutdown_event = None

============================================================

HEALTH

============================================================

async def health(request: web.Request):

bot_online = False
assistant_online = False

try:
    bot_online = bool(
        bot and bot.is_connected
    )
except Exception:
    pass

try:
    assistant_online = bool(
        assistant and assistant.is_connected
    )
except Exception:
    pass

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

app = web.Application()

app.router.add_get("/", health)
app.router.add_get("/health", health)

runner = web.AppRunner(app)

await runner.setup()

site = web.TCPSite(
    runner,
    "0.0.0.0",
    PORT,
)

await site.start()

logger.info(
    "🌐 Health server listening on 0.0.0.0:%s",
    PORT,
)

return runner

============================================================

PLATFORM

============================================================

try:

platform_info = get_platform_info()

logger.info("========== PLATFORM ==========")

for key, value in platform_info.items():
    logger.info(
        "%s: %s",
        key,
        value,
    )

logger.info("==============================")

except Exception:

logger.exception(
    "⚠️ Could not read platform information"
)

============================================================

CONFIG

============================================================

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

============================================================

VOICE SUPPORT

============================================================

try:

voice_supported, voice_message = (
    check_voice_chat_support()
)

except Exception as exc:

voice_supported = False
voice_message = str(exc)

if VOICE_CHAT_AVAILABLE and voice_supported:

logger.info(
    "🎧 Voice-chat support: AVAILABLE"
)

else:

logger.warning(
    "⚠️ Voice-chat support: UNAVAILABLE | %s",
    voice_message,
)

============================================================

STREAM END HANDLER

============================================================

async def stream_end_handler(
_: PyTgCalls,
update: StreamEnded,
):
"""
Called automatically when the current audio stream ends.

Queue behavior:

    Current song
         ↓
    Stream ends
         ↓
    Take first song from queue
         ↓
    Play automatically
"""

global player

if not player:
    return

try:

    chat_id = int(update.chat_id)

except Exception:

    logger.exception(
        "❌ Could not read ended stream chat_id"
    )

    return

logger.info(
    "🎵 Stream ended in chat %s",
    chat_id,
)

try:

    # MusicPlayer.next() must:
    #
    # 1. remove the finished current track
    # 2. take the first queued track
    # 3. play it
    # 4. leave the call if the queue is empty

    result = player.next(chat_id)

    if asyncio.iscoroutine(result):
        await result

    logger.info(
        "▶️ Queue advanced automatically | chat=%s",
        chat_id,
    )

except Exception:

    logger.exception(
        "❌ Automatic queue advance failed | chat=%s",
        chat_id,
    )

============================================================

RUNTIME

============================================================

def create_runtime():

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

if VOICE_CHAT_AVAILABLE and voice_supported:

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
        "⚠️ Assistant disabled"
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
            "🔊 PyTgCalls attached"
        )

        # ------------------------------------------------
        # IMPORTANT:
        # Register stream-end event BEFORE start().
        # ------------------------------------------------

        try:

            pytgcalls.on_update(
                fl.stream_end()
            )(stream_end_handler)

            logger.info(
                "🎵 Automatic queue event registered"
            )

        except Exception:

            logger.exception(
                "❌ Failed to register stream-end handler"
            )

            raise

    except Exception:

        logger.exception(
            "❌ Failed to create PyTgCalls"
        )

        raise

# --------------------------------------------------------
# PLAYER
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
# SHUTDOWN
# --------------------------------------------------------

shutdown_event = asyncio.Event()

logger.info(
    "✅ Runtime created successfully"
)

============================================================

STARTUP

============================================================

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
# HEALTH
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
# HANDLERS
# --------------------------------------------------------

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
# BOT
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
# ASSISTANT
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
# PYTGCALLS
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

============================================================

LEAVE VOICE CALLS

============================================================

async def leave_voice_calls():

if not pytgcalls:
    return

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

============================================================

SHUTDOWN

============================================================

async def shutdown():

global health_runner

logger.info(
    "🛑 Shutting down SILENT MUSIC BOT..."
)

if shutdown_event:

    try:
        shutdown_event.set()
    except Exception:
        pass

try:

    await leave_voice_calls()

except Exception:

    logger.exception(
        "⚠️ Voice-call cleanup failed"
    )

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

============================================================

MAIN

============================================================

async def main():

global shutdown_event

loop = asyncio.get_running_loop()

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
        "❌ Main runtime failed"
    )

    raise

finally:

    try:
        await shutdown()
    except Exception:
        logger.exception(
            "❌ Shutdown failed"
        )

if name == "main":

try:

    asyncio.run(main())

except KeyboardInterrupt:

    pass
