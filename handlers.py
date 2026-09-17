from __future__ import annotations

import inspect
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from player import TrackInfo

logger = logging.getLogger(__name__)


# ============================================================
# Runtime
# ============================================================

bot: Optional[Client] = None
pytgcalls = None
player = None
shutdown_event = None

_handlers_registered = False

_music_owner_id: Optional[int] = None
_music_admins: set[int] = set()
_player_deputies: set[int] = set()

_stats = {
    "plays": 0,
    "errors": 0,
    "started_at": time.time(),
}


# ============================================================
# Optional custom buttons
# ============================================================

try:
    from database import (
        get_custom_buttons,
        get_all_custom_buttons,
        add_custom_button,
        delete_custom_button,
    )
except Exception:
    get_custom_buttons = None
    get_all_custom_buttons = None
    add_custom_button = None
    delete_custom_button = None


# ============================================================
# Helpers
# ============================================================

def _env_int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_bot_owner_id() -> int:
    try:
        from config import config

        value = getattr(config, "owner_id", None)

        if value:
            return int(value)
    except Exception:
        pass

    return _env_int("OWNER_ID", 0)


def _get_music_owner_id() -> int:
    global _music_owner_id

    if _music_owner_id:
        return _music_owner_id

    _music_owner_id = _get_bot_owner_id()
    return _music_owner_id


def _is_bot_owner(user_id: int) -> bool:
    return bool(user_id and user_id == _get_bot_owner_id())


def _is_music_owner(user_id: int) -> bool:
    return bool(user_id and user_id == _get_music_owner_id())


def _is_music_admin(user_id: int) -> bool:
    return (
        _is_bot_owner(user_id)
        or _is_music_owner(user_id)
        or user_id in _music_admins
        or user_id in _player_deputies
    )


def _is_manager(user_id: int) -> bool:
    return _is_bot_owner(user_id) or _is_music_owner(user_id)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _reply(message, text: str, **kwargs):
    try:
        return await message.reply_text(
            text,
            quote=True,
            **kwargs,
        )
    except Exception:
        logger.exception("Telegram reply failed")
        return None


async def _edit(message, text: str, **kwargs):
    try:
        return await message.edit_text(
            text,
            **kwargs,
        )
    except Exception:
        logger.exception("Telegram edit failed")
        return None


async def _call_player(method_name: str, *args, **kwargs):
    if player is None:
        raise RuntimeError("MusicPlayer is not initialized")

    method = getattr(player, method_name, None)

    if not callable(method):
        raise AttributeError(
            f"MusicPlayer method '{method_name}' does not exist"
        )

    return await _maybe_await(method(*args, **kwargs))


def _chat_is_supported(message) -> bool:
    return bool(
        message
        and message.chat
        and message.chat.id
    )


# ============================================================
# Telegram media helpers
# ============================================================

def _reply_media(message):
    reply = getattr(message, "reply_to_message", None)

    if not reply:
        return None

    if (
        reply.audio
        or reply.voice
        or reply.video
        or reply.document
    ):
        return reply

    return None


def _media_object(message):
    if not message:
        return None

    return (
        message.audio
        or message.voice
        or message.video
        or message.document
    )


def _media_filename(message) -> str:
    media = _media_object(message)

    if not media:
        return "music"

    return (
        getattr(media, "file_name", None)
        or "music"
    )


def _media_title(message) -> str:
    if message.audio:
        return (
            message.audio.title
            or message.audio.file_name
            or "موزیک"
        )

    if message.voice:
        return "Voice"

    if message.video:
        return (
            message.video.file_name
            or "ویدیو"
        )

    if message.document:
        return (
            message.document.file_name
            or "موزیک"
        )

    return "موزیک"


def _media_performer(message) -> str:
    if message.audio:
        return message.audio.performer or ""

    return ""


def _media_duration(message) -> int:
    media = _media_object(message)

    try:
        return int(
            getattr(media, "duration", 0) or 0
        )
    except Exception:
        return 0


def _downloads_dir() -> Path:
    try:
        from config import config

        configured = getattr(
            config,
            "downloads_dir",
            None,
        )

        directory = (
            Path(configured)
            if configured
            else Path("downloads")
        )

    except Exception:
        directory = Path("downloads")

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


def _safe_name(value: str) -> str:
    value = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        value or "music",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value[:150] or "music"


async def _download_replied_media(
    media_message,
) -> Optional[str]:

    if bot is None:
        raise RuntimeError(
            "Bot client is not initialized"
        )

    media = _media_object(media_message)

    if media is None:
        return None

    original_name = _media_filename(
        media_message
    )

    extension = Path(
        original_name
    ).suffix.lower()

    if media_message.voice:
        extension = ".ogg"

    elif not extension:
        if media_message.audio:
            extension = ".mp3"
        elif media_message.video:
            extension = ".mp4"
        else:
            extension = ".bin"

    target_name = (
        f"{_safe_name(Path(original_name).stem)}"
        f"_{media_message.id}"
        f"{extension}"
    )

    target = (
        _downloads_dir()
        / target_name
    )

    if (
        target.exists()
        and target.stat().st_size > 0
    ):
        return str(target)

    downloaded = await bot.download_media(
        media_message,
        file_name=str(target),
    )

    if not downloaded:
        return None

    path = Path(downloaded)

    if (
        not path.exists()
        or path.stat().st_size <= 0
    ):
        return None

    return str(path)


def _make_track(
    path: str,
    media_message,
) -> TrackInfo:

    return TrackInfo(
        title=_media_title(
            media_message
        ),
        performer=_media_performer(
            media_message
        ),
        artist=_media_performer(
            media_message
        ),
        duration=_media_duration(
            media_message
        ),
        url="",
        source_url="",
        file_path=str(path),
        thumbnail="",
    )


# ============================================================
# PLAY — reply to Telegram audio/video/file
# ============================================================

async def _play_replied_media(message) -> bool:

    chat_id = message.chat.id

    media_message = _reply_media(message)

    if not media_message:
        await _reply(
            message,
            "🎵 روی فایل **موسیقی / Audio / Video** ریپلای کن "
            "و فقط «پخش» را بفرست."
        )
        return False

    preparing = await _reply(
        message,
        "⏳ فایل در حال آماده‌سازی است..."
    )

    try:
        path = await _download_replied_media(
            media_message
        )

        if not path:
            raise RuntimeError(
                "Telegram media download failed"
            )

        track = _make_track(
            path,
            media_message
        )

        # پلیر جدید
        result = await _call_player(
            "play",
            chat_id,
            track,
        )

        if result is False:
            raise RuntimeError(
                "MusicPlayer.play returned False"
            )

        _stats["plays"] += 1

        current = await _call_player(
            "get_current",
            chat_id,
        )

        # اگر آهنگ جدید به صف رفته
        if current is not None:
            current_title = getattr(
                current,
                "title",
                track.title,
            )

            if current_title != track.title:
                text = (
                    "➕ **به صف اضافه شد**\n\n"
                    f"🎵 {track.title}"
                )
            else:
                text = (
                    "🎵 **در حال پخش**\n\n"
                    f"🎧 **{track.title}**\n"
                    f"👤 {track.performer or 'نامشخص'}"
                )
        else:
            text = (
                "🎵 **در حال پخش**\n\n"
                f"🎧 **{track.title}**"
            )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⏸ مکث",
                    callback_data="music:pause"
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data="music:resume"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏭ بعدی",
                    callback_data="music:next"
                ),
                InlineKeyboardButton(
                    "⏹ اتمام",
                    callback_data="music:stop"
                ),
            ],
        ])

        if preparing:
            await _edit(
                preparing,
                text,
                reply_markup=keyboard,
            )
        else:
            await _reply(
                message,
                text,
                reply_markup=keyboard,
            )

        return True

    except Exception:
        _stats["errors"] += 1

        logger.exception(
            "Reply media playback failed"
        )

        error_text = (
            "❌ **پخش فایل انجام نشد.**\n\n"
            "مطمئن شو اکانت دستیار داخل ویس‌چت است "
            "و ویس‌چت گروه فعال است."
        )

        if preparing:
            await _edit(
                preparing,
                error_text,
            )
        else:
            await _reply(
                message,
                error_text,
            )

        return False


# ============================================================
# START
# ============================================================

def _start_keyboard(user_id: int):

    rows = []

    # Custom buttons
    if get_custom_buttons:
        try:
            buttons = get_custom_buttons(
                _get_bot_owner_id()
            )

            for button in buttons or []:
                try:
                    text = (
                        button.get("text")
                        if isinstance(button, dict)
                        else getattr(
                            button,
                            "text",
                            None,
                        )
                    )

                    url = (
                        button.get("url")
                        if isinstance(button, dict)
                        else getattr(
                            button,
                            "url",
                            None,
                        )
                    )

                    if text and url:
                        rows.append([
                            InlineKeyboardButton(
                                str(text),
                                url=str(url),
                            )
                        ])
                except Exception:
                    continue

        except Exception:
            logger.exception(
                "Custom start buttons failed"
            )

    rows.extend([
        [
            InlineKeyboardButton(
                "🎵 راهنمای پخش",
                callback_data="music:help",
            ),
            InlineKeyboardButton(
                "🆔 آیدی",
                callback_data="music:id",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎧 وضعیت ربات",
                callback_data="music:status",
            )
        ],
    ])

    if _is_bot_owner(user_id):
        rows.append([
            InlineKeyboardButton(
                "⚙️ مدیریت",
                callback_data="owner:menu",
            )
        ])

    return InlineKeyboardMarkup(rows)


async def start_handler(client, message):

    user_id = (
        message.from_user.id
        if message.from_user
        else 0
    )

    text = (
        "🎧 **SILENT PLAYER**\n\n"
        "به ربات موزیک پلیر سایلنت خوش آمدی 🎶\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎵 پخش آهنگ در ویس‌چت\n"
        "📂 پخش فایل با ریپلای\n"
        "📋 صف پخش\n"
        "⏸ مکث و ادامه\n"
        "⏭ آهنگ بعدی\n\n"
        "برای شروع در گروه:\n"
        "روی آهنگ ریپلای کن و بنویس:\n"
        "**پخش**"
    )

    # عکس پروفایل ربات را بفرست اگر قابل دریافت بود
    try:
        me = await client.get_me()

        if me.photo:
            photo = await client.download_media(
                me.photo.big_file_id,
                in_memory=True,
            )

            if photo:
                await message.reply_photo(
                    photo,
                    caption=text,
                    reply_markup=_start_keyboard(
                        user_id
                    ),
                )
                return

    except Exception:
        logger.exception(
            "Could not send bot profile photo"
        )

    await message.reply_text(
        text,
        reply_markup=_start_keyboard(
            user_id
        ),
    )


# ============================================================
# BASIC
# ============================================================

async def robot_handler(client, message):
    await _reply(
        message,
        "🟢 **SILENT PLAYER آنلاین است.**"
    )


# ============================================================
# PLAY BY SEARCH
# ============================================================

async def play_handler(client, message):

    if player is None:
        return await _reply(
            message,
            "❌ پلیر هنوز آماده نشده است."
        )

    if not _chat_is_supported(message):
        return

    # Reply to Telegram media
    if message.reply_to_message:
        return await _play_replied_media(
            message
        )

    text = message.text or ""

    query = re.sub(
        r"^/?پخش\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    if not query:
        return await _reply(
            message,
            "🎵 اسم آهنگ را بعد از «پخش» بنویس "
            "یا روی فایل آهنگ ریپلای کن."
        )

    preparing = await _reply(
        message,
        f"🔎 در حال جستجوی:\n**{query}**"
    )

    try:
        # API اصلی player جدید
        result = await _call_player(
            "play_query",
            message.chat.id,
            query,
        )

        if result is False:
            raise RuntimeError(
                "play_query returned False"
            )

        _stats["plays"] += 1

        track = None

        try:
            track = await _call_player(
                "get_current",
                message.chat.id,
            )
        except Exception:
            pass

        title = (
            getattr(
                track,
                "title",
                None,
            )
            or query
        )

        # اگر آهنگ اول باشد در حال پخش است.
        # اگر آهنگ دیگری در حال پخش باشد به صف رفته.
        queue_count = 0

        try:
            queue_count = await _call_player(
                "queue_count",
                message.chat.id,
            )
        except Exception:
            pass

        if track and getattr(
            track,
            "title",
            "",
        ) == title:

            text_result = (
                "🎵 **در حال پخش**\n\n"
                f"🎧 **{title}**\n"
                f"📋 تعداد در صف: {queue_count}"
            )

        else:
            text_result = (
                "➕ **به صف اضافه شد**\n\n"
                f"🎵 **{query}**\n"
                f"📋 تعداد در صف: {queue_count}"
            )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⏸ مکث",
                    callback_data="music:pause",
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data="music:resume",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏭ بعدی",
                    callback_data="music:next",
                ),
                InlineKeyboardButton(
                    "⏹ اتمام",
                    callback_data="music:stop",
                ),
            ],
        ])

        if preparing:
            await _edit(
                preparing,
                text_result,
                reply_markup=keyboard,
            )
        else:
            await _reply(
                message,
                text_result,
                reply_markup=keyboard,
            )

    except Exception:
        _stats["errors"] += 1

        logger.exception(
            "Search/play failed"
        )

        if preparing:
            await _edit(
                preparing,
                "❌ آهنگ پیدا یا پخش نشد."
            )
        else:
            await _reply(
                message,
                "❌ آهنگ پیدا یا پخش نشد."
            )


# ============================================================
# PLAYER CONTROLS
# ============================================================

async def pause_handler(client, message):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند مکث کند."
        )

    try:
        result = await _call_player(
            "pause",
            message.chat.id,
        )

        await _reply(
            message,
            "⏸️ موزیک مکث شد."
            if result is not False
            else "❌ مکث انجام نشد."
        )

    except Exception:
        logger.exception(
            "Pause failed"
        )
        await _reply(
            message,
            "❌ مکث انجام نشد."
        )


async def resume_handler(client, message):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند ادامه دهد."
        )

    try:
        result = await _call_player(
            "resume",
            message.chat.id,
        )

        await _reply(
            message,
            "▶️ پخش ادامه پیدا کرد."
            if result is not False
            else "❌ ادامه انجام نشد."
        )

    except Exception:
        logger.exception(
            "Resume failed"
        )
        await _reply(
            message,
            "❌ ادامه پخش انجام نشد."
        )


async def stop_handler(client, message):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند اتمام بزند."
        )

    try:
        await _call_player(
            "stop",
            message.chat.id,
        )

        await _reply(
            message,
            "⏹️ پخش متوقف شد و صف پاک شد."
        )

    except Exception:
        logger.exception(
            "Stop failed"
        )
        await _reply(
            message,
            "❌ توقف انجام نشد."
        )


async def next_handler(client, message):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند آهنگ بعدی را بزند."
        )

    try:
        result = await _call_player(
            "next",
            message.chat.id,
        )

        if result is False:
            await _reply(
                message,
                "❌ آهنگ بعدی وجود ندارد."
            )
            return

        track = await _call_player(
            "get_current",
            message.chat.id,
        )

        title = (
            getattr(
                track,
                "title",
                None,
            )
            if track
            else None
        )

        await _reply(
            message,
            (
                "⏭️ **آهنگ بعدی پخش شد.**\n\n"
                f"🎵 {title}"
                if title
                else "⏭️ آهنگ بعدی پخش شد."
            )
        )

    except Exception:
        logger.exception(
            "Next failed"
        )
        await _reply(
            message,
            "❌ رفتن به آهنگ بعدی انجام نشد."
        )


async def previous_handler(client, message):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند قبلی را بزند."
        )

    try:
        result = await _call_player(
            "previous",
            message.chat.id,
        )

        await _reply(
            message,
            "⏮️ آهنگ قبلی پخش شد."
            if result is not False
            else "❌ آهنگ قبلی موجود نیست."
        )

    except Exception:
        logger.exception(
            "Previous failed"
        )
        await _reply(
            message,
            "❌ آهنگ قبلی اجرا نشد."
        )


async def queue_handler(client, message):

    try:
        queue = await _call_player(
            "get_queue",
            message.chat.id,
        )

        if not queue:
            return await _reply(
                message,
                "📋 صف خالی است."
            )

        lines = [
            "📋 **صف پخش**",
            "",
        ]

        for index, track in enumerate(
            queue,
            start=1,
        ):
            title = getattr(
                track,
                "title",
                "موزیک",
            )

            lines.append(
                f"{index}. 🎵 {title}"
            )

        await _reply(
            message,
            "\n".join(lines)
        )

    except Exception:
        logger.exception(
            "Queue failed"
        )
        await _reply(
            message,
            "❌ دریافت صف انجام نشد."
        )


async def volume_handler(client, message):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند صدا را تغییر دهد."
        )

    parts = (
        message.text or ""
    ).split()

    try:
        value = int(
            parts[1]
        ) if len(parts) > 1 else 100
    except ValueError:
        value = 100

    value = max(
        1,
        min(200, value),
    )

    try:
        result = await _call_player(
            "set_volume",
            message.chat.id,
            value,
        )

        await _reply(
            message,
            (
                f"🔊 صدا روی **{value}%** تنظیم شد."
                if result is not False
                else "❌ تغییر صدا انجام نشد."
            )
        )

    except Exception:
        logger.exception(
            "Volume failed"
        )
        await _reply(
            message,
            "❌ تغییر صدا انجام نشد."
        )


# ============================================================
# SEEK
# ============================================================

async def seek_handler(
    client,
    message,
    forward: bool,
):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مدیر موزیک می‌تواند زمان آهنگ را تغییر دهد."
        )

    parts = (
        message.text or ""
    ).split()

    try:
        seconds = (
            int(parts[1])
            if len(parts) > 1
            else 10
        )
    except ValueError:
        seconds = 10

    seconds = max(
        1,
        min(300, seconds),
    )

    method = (
        "forward"
        if forward
        else "backward"
    )

    try:
        result = await _call_player(
            method,
            message.chat.id,
            seconds,
        )

        icon = (
            "⏩"
            if forward
            else "⏪"
        )

        word = (
            "جلو"
            if forward
            else "عقب"
        )

        await _reply(
            message,
            (
                f"{icon} **{seconds} ثانیه {word} رفت.**"
                if result is not False
                else "❌ جابه‌جایی انجام نشد."
            )
        )

    except Exception:
        logger.exception(
            "Seek failed"
        )
        await _reply(
            message,
            "❌ جابه‌جایی انجام نشد."
        )


async def forward_handler(client, message):
    await seek_handler(
        client,
        message,
        True,
    )


async def backward_handler(client, message):
    await seek_handler(
        client,
        message,
        False,
    )


# ============================================================
# INFO
# ============================================================

async def id_handler(client, message):

    user = message.from_user

    if not user:
        return

    if _is_bot_owner(user.id):
        role = "👑 مالک ربات"
    elif _is_music_owner(user.id):
        role = "👑 مالک موزیک"
    elif user.id in _music_admins:
        role = "🎵 مدیر موزیک"
    elif user.id in _player_deputies:
        role = "🛡 معاون پلیر"
    else:
        role = "👤 کاربر"

    await _reply(
        message,
        "🆔 **اطلاعات کاربر**\n\n"
        f"👤 نام: {user.first_name or 'نامشخص'}\n"
        f"🔢 آیدی: `{user.id}`\n"
        f"👑 نقش: {role}\n"
        f"🎵 پخش‌های موفق: {_stats['plays']}"
    )


async def status_handler(client, message):

    uptime = max(
        0,
        int(
            time.time()
            - _stats["started_at"]
        ),
    )

    hours, rem = divmod(
        uptime,
        3600,
    )

    minutes, seconds = divmod(
        rem,
        60,
    )

    await _reply(
        message,
        "🎧 **وضعیت SILENT PLAYER**\n\n"
        "🟢 آنلاین\n"
        f"⏱️ آپتایم: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
        f"🎵 پخش موفق: {_stats['plays']}\n"
        f"❌ خطا: {_stats['errors']}"
    )


# ============================================================
# ROLE MANAGEMENT
# ============================================================

def _target_user(message):
    reply = message.reply_to_message

    if not reply:
        return None

    return reply.from_user


async def promote_handler(client, message):

    user = message.from_user

    if not user or not _is_music_owner(
        user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مالک موزیک می‌تواند «ترفیع موزیک» انجام دهد."
        )

    target = _target_user(message)

    if not target:
        return await _reply(
            message,
            "👤 روی کاربر ریپلای کن و بنویس:\n"
            "**ترفیع موزیک**"
        )

    if _is_bot_owner(target.id):
        return await _reply(
            message,
            "👑 مالک ربات از قبل دسترسی کامل دارد."
        )

    _music_admins.add(
        target.id
    )

    _player_deputies.discard(
        target.id
    )

    await _reply(
        message,
        "👑 **ترفیع انجام شد.**\n\n"
        f"👤 {target.first_name or 'کاربر'}\n"
        "🎵 مدیر موزیک شد."
    )


async def demote_handler(client, message):

    user = message.from_user

    if not user or not _is_music_owner(
        user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مالک موزیک می‌تواند «عزل موزیک» انجام دهد."
        )

    target = _target_user(message)

    if not target:
        return await _reply(
            message,
            "👤 روی کاربر ریپلای کن و بنویس:\n"
            "**عزل موزیک**"
        )

    _music_admins.discard(
        target.id
    )

    _player_deputies.discard(
        target.id
    )

    await _reply(
        message,
        "👤 **عزل انجام شد.**\n\n"
        f"{target.first_name or 'کاربر'} "
        "دیگر مدیر موزیک نیست."
    )


async def music_owner_handler(
    client,
    message,
):

    global _music_owner_id

    user = message.from_user

    if not user or not _is_bot_owner(
        user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مالک اصلی ربات می‌تواند مالک موزیک را تعیین کند."
        )

    target = _target_user(message)

    if not target:
        return await _reply(
            message,
            "👤 روی کاربر ریپلای کن و بنویس:\n"
            "**مالک موزیک**"
        )

    _music_owner_id = target.id

    _music_admins.add(
        target.id
    )

    await _reply(
        message,
        "👑 **مالک موزیک تعیین شد.**\n\n"
        f"👤 {target.first_name or 'کاربر'}"
    )


# ============================================================
# DEPUTY
# ============================================================

async def deputy_promote_handler(
    client,
    message,
):

    user = message.from_user

    if not user or not _is_music_owner(
        user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مالک موزیک می‌تواند معاون پلیر تعیین کند."
        )

    target = _target_user(message)

    if not target:
        return await _reply(
            message,
            "👤 روی کاربر ریپلای کن و بنویس:\n"
            "**ارتقا معاون پلیر**"
        )

    _player_deputies.add(
        target.id
    )

    await _reply(
        message,
        "🛡 **معاون پلیر شد.**\n\n"
        f"👤 {target.first_name or 'کاربر'}"
    )


async def deputy_demote_handler(
    client,
    message,
):

    user = message.from_user

    if not user or not _is_music_owner(
        user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مالک موزیک می‌تواند معاون را حذف کند."
        )

    target = _target_user(message)

    if not target:
        return await _reply(
            message,
            "👤 روی کاربر ریپلای کن و بنویس:\n"
            "**حذف معاون پلیر**"
        )

    _player_deputies.discard(
        target.id
    )

    await _reply(
        message,
        "👤 معاون پلیر حذف شد."
    )


# ============================================================
# LEAVE GROUP / CHANNEL
# ============================================================

async def leave_handler(
    client,
    message,
):

    user = message.from_user

    if not user or not _is_bot_owner(
        user.id
    ):
        return await _reply(
            message,
            "⛔ فقط مالک اصلی ربات می‌تواند ربات را خارج کند."
        )

    chat_id = message.chat.id

    try:
        if player is not None:
            try:
                await _call_player(
                    "stop",
                    chat_id,
                )
            except Exception:
                pass

        await _reply(
            message,
            "👋 ربات از این گروه خارج می‌شود."
        )

        await client.leave_chat(
            chat_id
        )

    except Exception:
        logger.exception(
            "Leave chat failed"
        )

        await _reply(
            message,
            "❌ خروج ربات انجام نشد."
        )


# ============================================================
# VOICE CHAT
# ============================================================

async def call_start_handler(
    client,
    message,
):

    await _reply(
        message,
        "📞 **شروع کال**\n\n"
        "برای پخش موزیک، ویس‌چت گروه را فعال کن "
        "و مطمئن شو اکانت دستیار داخل کال حضور دارد."
    )


async def call_end_handler(
    client,
    message,
):

    if not _is_music_admin(
        message.from_user.id
    ):
        return await _reply(
            message,
            "⛔ دسترسی ندارید."
        )

    try:
        await _call_player(
            "stop",
            message.chat.id,
        )
    except Exception:
        logger.exception(
            "Call cleanup failed"
        )

    await _reply(
        message,
        "📞 پخش ویس‌چت متوقف شد."
    )


# ============================================================
# CALLBACK BUTTONS
# ============================================================

async def callback_handler(
    client,
    callback_query,
):

    data = (
        callback_query.data
        or ""
    )

    user = callback_query.from_user

    if not callback_query.message:
        return

    chat_id = (
        callback_query.message.chat.id
    )

    try:

        # -------------------------
        # HELP
        # -------------------------

        if data == "music:help":

            await callback_query.answer(
                "🎵 پخش آهنگ:\n"
                "پخش نام آهنگ\n\n"
                "📂 روی فایل ریپلای + پخش\n\n"
                "⏸ مکث\n"
                "▶️ ادامه\n"
                "⏭ بعدی\n"
                "⏹ اتمام\n"
                "📋 صف",
                show_alert=True,
            )

            return

        # -------------------------
        # ID
        # -------------------------

        if data == "music:id":

            await callback_query.answer(
                f"🆔 {user.id}",
                show_alert=True,
            )

            return

        # -------------------------
        # STATUS
        # -------------------------

        if data == "music:status":

            await callback_query.answer(
                "🟢 SILENT PLAYER آنلاین است.",
                show_alert=True,
            )

            return

        # -------------------------
        # OWNER MENU
        # -------------------------

        if data == "owner:menu":

            if not _is_bot_owner(
                user.id
            ):
                await callback_query.answer(
                    "⛔ دسترسی ندارید.",
                    show_alert=True,
                )
                return

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🎵 مدیریت موزیک",
                        callback_data="owner:music",
                    )
                ],
            ])

            await callback_query.message.reply_text(
                "⚙️ **پنل مدیریت مالک**",
                reply_markup=keyboard,
            )

            await callback_query.answer()
            return

        # -------------------------
        # MUSIC CONTROLS
        # -------------------------

        if data.startswith(
            "music:"
        ):

            if not _is_music_admin(
                user.id
            ):
                await callback_query.answer(
                    "⛔ فقط مدیر موزیک دسترسی دارد.",
                    show_alert=True,
                )
                return

            actions = {
                "music:pause": (
                    "pause",
                    "⏸️ مکث شد.",
                ),
                "music:resume": (
                    "resume",
                    "▶️ ادامه پیدا کرد.",
                ),
                "music:next": (
                    "next",
                    "⏭️ آهنگ بعدی.",
                ),
                "music:stop": (
                    "stop",
                    "⏹️ متوقف شد.",
                ),
            }

            item = actions.get(
                data
            )

            if not item:
                await callback_query.answer(
                    "❌ عملیات نامعتبر.",
                    show_alert=True,
                )
                return

            method, success_text = item

            result = await _call_player(
                method,
                chat_id,
            )

            await callback_query.answer(
                success_text
                if result is not False
                else "❌ عملیات انجام نشد.",
                show_alert=True,
            )

            return

        await callback_query.answer()

    except Exception:
        logger.exception(
            "Callback operation failed"
        )

        try:
            await callback_query.answer(
                "❌ عملیات انجام نشد.",
                show_alert=True,
            )
        except Exception:
            pass


# ============================================================
# REGISTRATION
# ============================================================

def register_handlers():

    global _handlers_registered

    if _handlers_registered:
        return

    if bot is None:
        raise RuntimeError(
            "Bot instance is not set"
        )

    # --------------------------------------------------------
    # PRIVATE START
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            start_handler,
            filters.private
            & (
                filters.command("start")
                | filters.regex(
                    r"^/?استارت$"
                )
            ),
        )
    )

    # --------------------------------------------------------
    # BASIC GROUP
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            robot_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?ربات$"
            ),
        )
    )

    # --------------------------------------------------------
    # PLAY
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            play_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?پخش(?:\s+.+)?$"
            ),
        )
    )

    # --------------------------------------------------------
    # PAUSE
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            pause_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?مکث$"
            ),
        )
    )

    # --------------------------------------------------------
    # RESUME
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            resume_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?ادامه$"
            ),
        )
    )

    # --------------------------------------------------------
    # STOP
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            stop_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?اتمام$"
            ),
        )
    )

    # --------------------------------------------------------
    # NEXT
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            next_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?بعدی$"
            ),
        )
    )

    # --------------------------------------------------------
    # PREVIOUS
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            previous_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?قبلی$"
            ),
        )
    )

    # --------------------------------------------------------
    # QUEUE
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            queue_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?صف$"
            ),
        )
    )

    # --------------------------------------------------------
    # SEEK
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            forward_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?جلو(?:\s+\d+)?$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            backward_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?عقب(?:\s+\d+)?$"
            ),
        )
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            volume_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?صدا(?:\s+\d+)?$"
            ),
        )
    )

    # --------------------------------------------------------
    # INFO
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            id_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?آیدی$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            status_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?وضعیت$"
            ),
        )
    )

    # --------------------------------------------------------
    # MUSIC MANAGEMENT
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            promote_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?ترفیع موزیک$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            demote_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?عزل موزیک$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            music_owner_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?مالک موزیک$"
            ),
        )
    )

    # --------------------------------------------------------
    # DEPUTY
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            deputy_promote_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?ارتقا معاون پلیر$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            deputy_demote_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?حذف معاون پلیر$"
            ),
        )
    )

    # --------------------------------------------------------
    # LEAVE
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            leave_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?خروج ربات از گروه$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            leave_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?خروج ربات از کانال$"
            ),
        )
    )

    # --------------------------------------------------------
    # VOICE CHAT
    # --------------------------------------------------------

    bot.add_handler(
        MessageHandler(
            call_start_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?شروع کال$"
            ),
        )
    )

    bot.add_handler(
        MessageHandler(
            call_end_handler,
            filters.group
            & filters.text
            & filters.regex(
                r"^/?پایان کال$"
            ),
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    bot.add_handler(
        CallbackQueryHandler(
            callback_handler,
            filters.regex(
                r"^(music|owner):"
            ),
        )
    )

    _handlers_registered = True

    logger.info(
        "🟢 SILENT Persian handlers registered successfully"
    )


# ============================================================
# MAIN RUNTIME INJECTION
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
        "🟢 Handlers connected to runtime"
    )

    register_handlers()
