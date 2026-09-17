import inspect
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from player import TrackInfo

logger = logging.getLogger(__name__)

# ============================================================
# Runtime
# ============================================================

bot = None
pytgcalls = None
player = None
shutdown_event = None

_handlers_registered = False

_music_admins = set()
_music_owner_id = 0

_stats = {
    "plays": 0,
    "errors": 0,
    "started_at": time.time(),
}


# ============================================================
# Config / permissions
# ============================================================

def get_owner_id() -> int:
    global _music_owner_id

    if _music_owner_id:
        return _music_owner_id

    try:
        from config import config
        value = getattr(config, "owner_id", 0)
    except Exception:
        value = os.getenv("OWNER_ID", "0")

    try:
        _music_owner_id = int(value or 0)
    except (TypeError, ValueError):
        _music_owner_id = 0

    return _music_owner_id


def is_owner(user_id: int) -> bool:
    owner_id = get_owner_id()
    return bool(owner_id and user_id == owner_id)


def is_music_admin(user_id: int) -> bool:
    return is_owner(user_id) or user_id in _music_admins


# ============================================================
# Telegram helpers
# ============================================================

async def reply(message, text: str, **kwargs):
    try:
        return await message.reply_text(
            text,
            quote=True,
            **kwargs,
        )
    except Exception:
        logger.exception("Failed to send Telegram message")
        return None


def chat_id(message) -> Optional[int]:
    return getattr(
        getattr(message, "chat", None),
        "id",
        None,
    )


# ============================================================
# Media detection
# ============================================================

def get_replied_media(message):
    """
    Detect:
    Audio
    Voice
    Document
    Video

    The COMPLETE Message object is returned.
    """

    replied = getattr(message, "reply_to_message", None)

    if not replied:
        return None

    for media_type in (
        "audio",
        "voice",
        "document",
        "video",
    ):
        if getattr(replied, media_type, None):
            return replied

    return None


def get_media_title(message) -> str:
    audio = getattr(message, "audio", None)

    if audio:
        title = getattr(audio, "title", None)
        performer = getattr(audio, "performer", None)

        if title and performer:
            return f"{performer} - {title}"

        if title:
            return title

        if performer:
            return performer

    document = getattr(message, "document", None)

    if document:
        filename = getattr(
            document,
            "file_name",
            None,
        )

        if filename:
            return filename

    video = getattr(message, "video", None)

    if video:
        filename = getattr(
            video,
            "file_name",
            None,
        )

        if filename:
            return filename

    return "موزیک"


def get_media_duration(message) -> int:
    for media_type in (
        "audio",
        "voice",
        "video",
    ):
        media = getattr(
            message,
            media_type,
            None,
        )

        if media:
            try:
                return int(
                    getattr(
                        media,
                        "duration",
                        0,
                    ) or 0
                )
            except Exception:
                return 0

    return 0


def get_extension(message) -> str:
    audio = getattr(message, "audio", None)

    if audio:
        filename = getattr(
            audio,
            "file_name",
            "",
        ) or ""

        extension = Path(filename).suffix.lower()

        return extension or ".mp3"

    voice = getattr(message, "voice", None)

    if voice:
        return ".ogg"

    document = getattr(
        message,
        "document",
        None,
    )

    if document:
        filename = getattr(
            document,
            "file_name",
            "",
        ) or ""

        extension = Path(filename).suffix.lower()

        return extension or ".mp3"

    video = getattr(
        message,
        "video",
        None,
    )

    if video:
        return ".mp4"

    return ".mp3"


def safe_filename(name: str) -> str:
    name = name or "music"

    name = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name[:120] or "music"


# ============================================================
# Download Telegram media
# ============================================================

def downloads_directory() -> Path:
    directory = Path("downloads")

    try:
        from config import config

        configured = getattr(
            config,
            "downloads_dir",
            None,
        )

        if configured:
            directory = Path(configured)

    except Exception:
        pass

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


async def download_telegram_media(message) -> Optional[str]:
    """
    IMPORTANT:
    Pyrogram receives the complete Message object here.

    This fixes the common:
    «در حال آماده‌سازی فایل»
    →
    «پخش آهنگ انجام نشد»
    problem caused by passing the wrong media object.
    """

    if bot is None:
        logger.error("Bot instance is not ready")
        return None

    title = safe_filename(
        get_media_title(message)
    )

    extension = get_extension(message)

    message_id = getattr(
        message,
        "id",
        int(time.time()),
    )

    target = (
        downloads_directory()
        / f"{title}_{message_id}{extension}"
    )

    try:
        downloaded = await bot.download_media(
            message,
            file_name=str(target),
        )

        if not downloaded:
            logger.error(
                "Pyrogram download_media returned empty result"
            )
            return None

        path = Path(downloaded)

        if not path.exists():
            logger.error(
                "Downloaded file does not exist: %s",
                path,
            )
            return None

        if path.stat().st_size <= 0:
            logger.error(
                "Downloaded file is empty: %s",
                path,
            )
            return None

        logger.info(
            "Telegram media downloaded: %s (%d bytes)",
            path,
            path.stat().st_size,
        )

        return str(path)

    except Exception:
        logger.exception(
            "Telegram media download failed"
        )

        return None


# ============================================================
# TrackInfo
# ============================================================

def create_track(filepath: str, message):
    audio = getattr(
        message,
        "audio",
        None,
    )

    title = None
    performer = None

    if audio:
        title = getattr(
            audio,
            "title",
            None,
        )

        performer = getattr(
            audio,
            "performer",
            None,
        )

    title = title or get_media_title(message)

    return TrackInfo(
        title=title or "موزیک",
        duration=get_media_duration(message),
        url="",
        webpage_url="",
        thumbnail="",
        uploader=performer or "Telegram",
        filepath=str(filepath),
    )


# ============================================================
# Player bridge
# ============================================================

async def player_call(
    method_name: str,
    chat: int,
    *args,
):
    if player is None:
        logger.error(
            "Player is not initialized"
        )
        return False

    method = getattr(
        player,
        method_name,
        None,
    )

    if not callable(method):
        logger.error(
            "Player method missing: %s",
            method_name,
        )
        return False

    try:
        result = method(
            chat,
            *args,
        )

        if inspect.isawaitable(result):
            result = await result

        # IMPORTANT:
        # None is NOT failure.
        #
        # Some PyTgCalls methods return None
        # after successful execution.
        #
        # Only explicit False is failure.

        return result

    except Exception:
        logger.exception(
            "Player operation failed: %s",
            method_name,
        )

        return False


# ============================================================
# PLAY
# ============================================================

async def play_replied_audio(
    client,
    message,
):
    """
    Full flow:

    Telegram reply
          ↓
    detect media
          ↓
    download
          ↓
    TrackInfo
          ↓
    player.play_track()
          ↓
    voice chat
    """

    if player is None:
        await reply(
            message,
            "❌ پلیر هنوز آماده نشده است.",
        )
        return

    current_chat = chat_id(message)

    if not current_chat:
        return

    media_message = get_replied_media(
        message
    )

    if not media_message:
        await reply(
            message,
            "🎵 روی آهنگ ریپلای کن و فقط «پخش» را بفرست.",
        )
        return

    progress = await reply(
        message,
        "⏳ در حال آماده‌سازی فایل...",
    )

    filepath = await download_telegram_media(
        media_message
    )

    if not filepath:

        _stats["errors"] += 1

        if progress:
            try:
                await progress.edit_text(
                    "❌ دریافت فایل انجام نشد.\n\n"
                    "روی یک فایل صوتی معتبر ریپلای کن "
                    "و دوباره «پخش» بزن."
                )
            except Exception:
                pass

        return

    try:
        track = create_track(
            filepath,
            media_message,
        )

    except Exception:

        _stats["errors"] += 1

        logger.exception(
            "TrackInfo creation failed"
        )

        if progress:
            try:
                await progress.edit_text(
                    "❌ اطلاعات آهنگ ساخته نشد."
                )
            except Exception:
                pass

        return

    try:

        result = await player_call(
            "play_track",
            current_chat,
            track,
        )

        # Only explicit False means failure.
        if result is False:

            _stats["errors"] += 1

            text = (
                "❌ پخش آهنگ انجام نشد.\n\n"
                "⚠️ ویس‌چت گروه را فعال کن و "
                "مطمئن شو اکانت دستیار داخل ویس‌چت است."
            )

        else:

            _stats["plays"] += 1

            text = (
                "🎵 **پخش شروع شد**\n\n"
                f"🎧 {track.title}\n"
                f"👤 {track.uploader}"
            )

        if progress:
            try:
                await progress.edit_text(
                    text,
                    reply_markup=controls(),
                )
            except Exception:
                pass

    except Exception:

        _stats["errors"] += 1

        logger.exception(
            "Playback failed"
        )

        if progress:
            try:
                await progress.edit_text(
                    "❌ پخش آهنگ انجام نشد."
                )
            except Exception:
                pass


# ============================================================
# Commands
# ============================================================

async def cmd_play(
    client,
    message,
):
    await play_replied_audio(
        client,
        message,
    )


async def cmd_pause(
    client,
    message,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    result = await player_call(
        "pause",
        chat_id(message),
    )

    await reply(
        message,
        "⏸️ موزیک مکث شد."
        if result is not False
        else "❌ مکث انجام نشد.",
    )


async def cmd_resume(
    client,
    message,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    result = await player_call(
        "resume",
        chat_id(message),
    )

    await reply(
        message,
        "▶️ پخش ادامه یافت."
        if result is not False
        else "❌ ادامه پخش انجام نشد.",
    )


async def cmd_stop(
    client,
    message,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    result = await player_call(
        "stop",
        chat_id(message),
    )

    await reply(
        message,
        "⏹️ پخش متوقف شد."
        if result is not False
        else "❌ توقف انجام نشد.",
    )


async def cmd_next(
    client,
    message,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    result = await player_call(
        "next",
        chat_id(message),
    )

    await reply(
        message,
        "⏭️ آهنگ بعدی اجرا شد."
        if result is not False
        else "❌ آهنگ بعدی موجود نیست.",
    )


async def cmd_previous(
    client,
    message,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    result = await player_call(
        "previous",
        chat_id(message),
    )

    await reply(
        message,
        "⏮️ آهنگ قبلی اجرا شد."
        if result is not False
        else "❌ آهنگ قبلی موجود نیست.",
    )


async def cmd_id(
    client,
    message,
):
    user = message.from_user

    if not user:
        return

    if is_owner(user.id):
        role = "👑 مالک ربات"
    elif is_music_admin(user.id):
        role = "🎧 مدیر موزیک"
    else:
        role = "👤 کاربر"

    await reply(
        message,
        "🆔 **اطلاعات کاربر**\n\n"
        f"👤 نام: {user.first_name or 'نامشخص'}\n"
        f"🔢 آیدی: `{user.id}`\n"
        f"👑 نقش: {role}",
    )


async def cmd_status(
    client,
    message,
):
    uptime = int(
        time.time()
        - _stats["started_at"]
    )

    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    seconds = uptime % 60

    await reply(
        message,
        "🎧 **وضعیت ربات**\n\n"
        "🟢 آنلاین\n"
        f"⏱️ {hours:02d}:{minutes:02d}:{seconds:02d}\n"
        f"🎵 پخش‌ها: {_stats['plays']}\n"
        f"❌ خطاها: {_stats['errors']}",
    )


async def cmd_robot(
    client,
    message,
):
    await reply(
        message,
        "🟢 ربات سایلنت همیشه آنلاین می‌باشد.",
    )


async def cmd_start(
    client,
    message,
):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎵 راهنمای پخش",
                    callback_data="music_help",
                ),
                InlineKeyboardButton(
                    "🆔 آیدی",
                    callback_data="music_id",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎧 وضعیت",
                    callback_data="music_status",
                )
            ],
        ]
    )

    await message.reply_text(
        "🎵 **ربات موزیک سایلنت**\n\n"
        "روی فایل آهنگ ریپلای کن و فقط «پخش» بفرست.",
        reply_markup=keyboard,
    )


async def cmd_promote(
    client,
    message,
):
    if not is_owner(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مالک ربات دسترسی دارد.",
        )

    target_message = getattr(
        message,
        "reply_to_message",
        None,
    )

    target = getattr(
        target_message,
        "from_user",
        None,
    )

    if not target:
        return await reply(
            message,
            "👤 روی کاربر ریپلای کن.",
        )

    _music_admins.add(
        target.id
    )

    await reply(
        message,
        f"👑 {target.first_name} مدیر موزیک شد.",
    )


async def cmd_demote(
    client,
    message,
):
    if not is_owner(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مالک ربات دسترسی دارد.",
        )

    target_message = getattr(
        message,
        "reply_to_message",
        None,
    )

    target = getattr(
        target_message,
        "from_user",
        None,
    )

    if not target:
        return await reply(
            message,
            "👤 روی کاربر ریپلای کن.",
        )

    _music_admins.discard(
        target.id
    )

    await reply(
        message,
        f"👤 {target.first_name} از مدیریت موزیک عزل شد.",
    )


async def cmd_music_owner(
    client,
    message,
):
    global _music_owner_id

    if not is_owner(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مالک فعلی دسترسی دارد.",
        )

    target_message = getattr(
        message,
        "reply_to_message",
        None,
    )

    target = getattr(
        target_message,
        "from_user",
        None,
    )

    if not target:
        return await reply(
            message,
            "👤 روی کاربر ریپلای کن.",
        )

    _music_owner_id = target.id

    await reply(
        message,
        f"👑 مالک موزیک به {target.first_name} تغییر کرد.",
    )


async def cmd_volume(
    client,
    message,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    parts = (
        message.text or ""
    ).split()

    value = 100

    if len(parts) > 1:
        try:
            value = int(parts[1])
        except ValueError:
            value = 100

    value = max(
        1,
        min(200, value),
    )

    result = await player_call(
        "set_volume",
        chat_id(message),
        value,
    )

    await reply(
        message,
        f"🔊 صدا روی {value}% تنظیم شد."
        if result is not False
        else "❌ تغییر صدا انجام نشد.",
    )


async def seek(
    message,
    forward: bool,
):
    if not is_music_admin(
        message.from_user.id
    ):
        return await reply(
            message,
            "⛔ فقط مدیر موزیک دسترسی دارد.",
        )

    parts = (
        message.text or ""
    ).split()

    seconds = 10

    if len(parts) > 1:
        try:
            seconds = int(parts[1])
        except ValueError:
            seconds = 10

    seconds = max(
        1,
        min(100, seconds),
    )

    method = (
        "forward"
        if forward
        else "backward"
    )

    result = await player_call(
        method,
        chat_id(message),
        seconds,
    )

    symbol = (
        "⏩"
        if forward
        else "⏪"
    )

    await reply(
        message,
        f"{symbol} {seconds} ثانیه انجام شد."
        if result is not False
        else "❌ عملیات انجام نشد.",
    )


async def cmd_forward(
    client,
    message,
):
    await seek(
        message,
        True,
    )


async def cmd_backward(
    client,
    message,
):
    await seek(
        message,
        False,
    )


# ============================================================
# Buttons
# ============================================================

def controls():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏸ مکث",
                    callback_data="music_pause",
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data="music_resume",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏭ بعدی",
                    callback_data="music_next",
                ),
                InlineKeyboardButton(
                    "⏹ اتمام",
                    callback_data="music_stop",
                ),
            ],
        ]
    )


async def callbacks(
    client,
    query,
):
    try:
        data = query.data or ""

        message = query.message

        current_chat = getattr(
            getattr(
                message,
                "chat",
                None,
            ),
            "id",
            None,
        )

        user_id = query.from_user.id

        if data == "music_help":

            await query.answer(
                "روی فایل آهنگ ریپلای کن و «پخش» بزن.",
                show_alert=True,
            )

        elif data == "music_id":

            await query.answer(
                f"🆔 {user_id}",
                show_alert=True,
            )

        elif data == "music_status":

            await query.answer(
                "🟢 ربات آنلاین است.",
                show_alert=True,
            )

        elif data == "music_pause":

            if not is_music_admin(user_id):
                return await query.answer(
                    "⛔ دسترسی ندارید.",
                    show_alert=True,
                )

            result = await player_call(
                "pause",
                current_chat,
            )

            await query.answer(
                "⏸️ مکث شد."
                if result is not False
                else "❌ انجام نشد.",
            )

        elif data == "music_resume":

            if not is_music_admin(user_id):
                return await query.answer(
                    "⛔ دسترسی ندارید.",
                    show_alert=True,
                )

            result = await player_call(
                "resume",
                current_chat,
            )

            await query.answer(
                "▶️ ادامه یافت."
                if result is not False
                else "❌ انجام نشد.",
            )

        elif data == "music_next":

            if not is_music_admin(user_id):
                return await query.answer(
                    "⛔ دسترسی ندارید.",
                    show_alert=True,
                )

            result = await player_call(
                "next",
                current_chat,
            )

            await query.answer(
                "⏭️ اجرا شد."
                if result is not False
                else "❌ آهنگ بعدی نیست.",
            )

        elif data == "music_stop":

            if not is_music_admin(user_id):
                return await query.answer(
                    "⛔ دسترسی ندارید.",
                    show_alert=True,
                )

            result = await player_call(
                "stop",
                current_chat,
            )

            await query.answer(
                "⏹️ متوقف شد."
                if result is not False
                else "❌ انجام نشد.",
            )

    except Exception:

        logger.exception(
            "Callback error"
        )

        try:
            await query.answer(
                "❌ عملیات انجام نشد.",
                show_alert=True,
            )
        except Exception:
            pass


# ============================================================
# Registration
# ============================================================

def register_handlers():
    global _handlers_registered

    if _handlers_registered:
        return

    if bot is None:
        logger.error(
            "Cannot register handlers: bot is None"
        )
        return

    # -------------------------
    # Private
    # -------------------------

    bot.add_handler(
        MessageHandler(
            cmd_start,
            filters.private
            & (
                filters.command("start")
                | filters.regex(r"^استارت$")
            ),
        )
    )

    # -------------------------
    # Group
    # -------------------------

    bot.add_handler(
        MessageHandler(
            cmd_robot,
            filters.group
            & filters.regex(r"^ربات$"),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_play,
            filters.group
            & filters.regex(
                r"^(?:پخش|/پخش)(?:\s+.*)?$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_pause,
            filters.group
            & filters.regex(
                r"^(?:مکث|/مکث)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_resume,
            filters.group
            & filters.regex(
                r"^(?:ادامه|/ادامه)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_stop,
            filters.group
            & filters.regex(
                r"^(?:اتمام|/اتمام)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_next,
            filters.group
            & filters.regex(
                r"^(?:بعدی|/بعدی)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_previous,
            filters.group
            & filters.regex(
                r"^(?:قبلی|/قبلی)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_forward,
            filters.group
            & filters.regex(
                r"^(?:جلو|/جلو)(?:\s+\d+)?$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_backward,
            filters.group
            & filters.regex(
                r"^(?:عقب|/عقب)(?:\s+\d+)?$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_volume,
            filters.group
            & filters.regex(
                r"^(?:صدا|/صدا)(?:\s+\d+)?$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_id,
            filters.group
            & filters.regex(
                r"^(?:آیدی|/آیدی)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_status,
            filters.group
            & filters.regex(
                r"^(?:وضعیت|/وضعیت)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_promote,
            filters.group
            & filters.regex(
                r"^(?:ترفیع موزیک|/ترفیع_موزیک)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_demote,
            filters.group
            & filters.regex(
                r"^(?:عزل موزیک|/عزل_موزیک)$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            cmd_music_owner,
            filters.group
            & filters.regex(
                r"^(?:مالک موزیک|/مالک_موزیک)$"
            ),
        )
    )

    # -------------------------
    # Callback buttons
    # -------------------------

    bot.add_handler(
        CallbackQueryHandler(
            callbacks,
            filters.regex(r"^music_"),
        )
    )

    _handlers_registered = True

    logger.info(
        "🟢 SILENT Persian music handlers registered successfully"
    )


# ============================================================
# Main.py integration
# ============================================================

def set_bot_instances(
    app,
    calls,
    music_player,
    stop_event=None,
):
    global bot
    global pytgcalls
    global player
    global shutdown_event

    bot = app
    pytgcalls = calls
    player = music_player
    shutdown_event = stop_event

    logger.info(
        "Handlers received bot instance"
    )

    # Critical:
    # main.py calls set_bot_instances().
    # We register handlers here automatically.
    register_handlers()
