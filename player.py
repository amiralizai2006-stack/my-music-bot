from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from player import TrackInfo

logger = logging.getLogger(__name__)

# =========================================================
# نمونه‌های اصلی
# =========================================================

bot: Optional[Client] = None
player: Any = None
pytgcalls: Any = None
shutdown_event: Any = None

SUPPORT_USERNAME = ""
REQUIRED_CHANNEL = ""

# =========================================================
# آمار و مدیریت
# =========================================================

user_stats: dict[int, dict[str, Any]] = {}
music_admins: set[int] = set()
music_owner_id: Optional[int] = None


# =========================================================
# آمار کاربران
# =========================================================

def _user_stats(user_id: int) -> dict[str, Any]:
    if user_id not in user_stats:
        user_stats[user_id] = {
            "plays": 0,
            "last_seen": None,
        }

    user_stats[user_id]["last_seen"] = datetime.utcnow()
    return user_stats[user_id]


def _increase_play(user_id: int):
    stats = _user_stats(user_id)
    stats["plays"] += 1


# =========================================================
# ثبت نمونه‌های اصلی
# =========================================================

def set_bot_instances(
    bot_instance: Client,
    player_instance: Any,
    pytgcalls_instance: Any = None,
    shutdown_event_instance: Any = None,
):
    global bot
    global player
    global pytgcalls
    global shutdown_event

    bot = bot_instance
    player = player_instance
    pytgcalls = pytgcalls_instance
    shutdown_event = shutdown_event_instance


# =========================================================
# کیبورد اصلی
# =========================================================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎵 موزیک",
                    callback_data="music_menu",
                ),
                InlineKeyboardButton(
                    "📊 وضعیت",
                    callback_data="music_status",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🆔 آیدی",
                    callback_data="show_id",
                ),
                InlineKeyboardButton(
                    "📈 آمار",
                    callback_data="show_stats",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔐 عضویت",
                    callback_data="membership",
                ),
                InlineKeyboardButton(
                    "👤 پشتیبانی",
                    callback_data="support",
                ),
            ],
        ]
    )


# =========================================================
# کیبورد موزیک
# =========================================================

def music_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏮ قبلی",
                    callback_data="music_previous",
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data="music_resume",
                ),
                InlineKeyboardButton(
                    "⏭ بعدی",
                    callback_data="music_next",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏪ 10",
                    callback_data="music_backward_10",
                ),
                InlineKeyboardButton(
                    "⏸ مکث",
                    callback_data="music_pause",
                ),
                InlineKeyboardButton(
                    "⏩ 10",
                    callback_data="music_forward_10",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏪ 30",
                    callback_data="music_backward_30",
                ),
                InlineKeyboardButton(
                    "⏩ 30",
                    callback_data="music_forward_30",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔊 صدا",
                    callback_data="music_volume",
                ),
                InlineKeyboardButton(
                    "⏹ اتمام",
                    callback_data="music_stop",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📊 وضعیت",
                    callback_data="music_status",
                ),
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="main_menu",
                ),
            ],
        ]
    )


# =========================================================
# اطلاعات آهنگ
# =========================================================

def _track_artist(track: Optional[TrackInfo]) -> str:
    if not track:
        return ""

    return (
        getattr(track, "artist", "")
        or getattr(track, "performer", "")
        or getattr(track, "uploader", "")
        or ""
    )


def _track_title(track: Optional[TrackInfo]) -> str:
    if not track:
        return "موزیک"

    return (
        getattr(track, "title", "")
        or "موزیک"
    )


def player_text(track: Optional[TrackInfo]) -> str:
    if not track:
        return "🎵 هیچ موزیکی در حال پخش نیست."

    title = _track_title(track)
    artist = _track_artist(track)

    text = f"🎵 **{title}**"

    if artist:
        text += f"\n👤 خواننده: **{artist}**"

    if getattr(track, "duration", 0):
        duration = int(track.duration)
        minutes = duration // 60
        seconds = duration % 60
        text += f"\n⏱ مدت: `{minutes}:{seconds:02d}`"

    return text


# =========================================================
# پیدا کردن فایل صوتی ریپلای
# =========================================================

def _get_reply_audio(message: Message):
    if not message.reply_to_message:
        return None

    reply = message.reply_to_message

    if reply.audio:
        return reply.audio

    if reply.voice:
        return reply.voice

    if reply.document:
        mime = reply.document.mime_type or ""

        if mime.startswith("audio/"):
            return reply.document

    return None


def _audio_title(media) -> str:
    if not media:
        return "موزیک"

    return (
        getattr(media, "title", None)
        or getattr(media, "file_name", None)
        or "موزیک"
    )


def _audio_artist(media) -> str:
    if not media:
        return ""

    return (
        getattr(media, "performer", None)
        or getattr(media, "artist", None)
        or ""
    )


# =========================================================
# وضعیت پلیر
# =========================================================

async def _get_status(chat_id: int):
    if not player:
        return {
            "playing": False,
            "paused": False,
            "track": None,
            "position": 0,
            "volume": 100,
            "queue_size": 0,
        }

    try:
        return await player.get_status(chat_id)
    except Exception:
        logger.exception("Could not get player status")

        return {
            "playing": False,
            "paused": False,
            "track": None,
            "position": 0,
            "volume": 100,
            "queue_size": 0,
        }


# =========================================================
# پخش / صف
# =========================================================

async def _download_and_play(
    chat_id: int,
    track: TrackInfo,
):
    if not player:
        return False, "❌ پلیر آماده نیست."

    try:
        # player.play در نسخه جدید خودش
        # اگر آهنگی در حال پخش باشد، آهنگ را وارد صف می‌کند.
        ok = await player.play(
            chat_id,
            track,
        )

        if not ok:
            return False, "❌ پخش موزیک انجام نشد."

        current = player.get_current(chat_id)

        if current is track:
            return True, "played"

        queue = player.get_queue(chat_id)

        if track in queue:
            return True, "queued"

        return True, "played"

    except Exception:
        logger.exception(
            "Could not play track in chat %s",
            chat_id,
        )

        return False, "❌ خطا هنگام پخش موزیک."


# =========================================================
# سازگاری برای فراخوانی متدهای پلیر
# =========================================================

async def _player_method(
    method: str,
    chat_id: int,
    *args,
    **kwargs,
):
    if not player:
        return None

    fn = getattr(
        player,
        method,
        None,
    )

    if not fn:
        return None

    try:
        return await fn(
            chat_id,
            *args,
            **kwargs,
        )

    except Exception:
        logger.exception(
            "Player method failed: %s",
            method,
        )

        return None


# =========================================================
# /start
# =========================================================

@Client.on_message(
    filters.command(
        "start",
        prefixes="/",
    )
)
async def start_handler(
    client: Client,
    message: Message,
):
    if message.from_user:
        _user_stats(
            message.from_user.id
        )

    text = (
        "🎵 **موزیک پلیر فارسی**\n\n"
        "برای پخش موزیک می‌توانید:\n\n"
        "• `پخش نام آهنگ`\n"
        "• روی یک آهنگ ریپلای کنید و `پخش` بزنید\n\n"
        "دستورات اصلی:\n"
        "▶️ پخش\n"
        "⏸ مکث\n"
        "▶️ ادامه\n"
        "⏭ بعدی\n"
        "⏮ قبلی\n"
        "⏹ اتمام\n"
        "📊 وضعیت\n"
        "🔊 صدا\n"
        "⏩ جلو\n"
        "⏪ عقب"
    )

    await message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# استارت
# =========================================================

@Client.on_message(
    filters.regex(r"^استارت$")
)
async def persian_start_handler(
    client: Client,
    message: Message,
):
    if message.from_user:
        _user_stats(
            message.from_user.id
        )

    await message.reply_text(
        "🎵 **موزیک پلیر آماده است.**\n\n"
        "برای پخش:\n"
        "`پخش نام آهنگ`\n\n"
        "یا روی فایل صوتی ریپلای کنید و `پخش` بزنید.",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# ربات
# =========================================================

@Client.on_message(
    filters.regex(r"^ربات$")
)
async def bot_handler(
    client: Client,
    message: Message,
):
    await message.reply_text(
        "🎵 **موزیک پلیر فعال است.**\n\n"
        "برای پخش موزیک بنویسید:\n"
        "`پخش نام آهنگ`"
    )


# =========================================================
# کمک
# =========================================================

@Client.on_message(
    filters.regex(r"^کمک$")
)
async def help_handler(
    client: Client,
    message: Message,
):
    await message.reply_text(
        "📚 **دستورات موزیک**\n\n"
        "🎵 `پخش آهنگ`\n"
        "↩️ ریپلای روی موزیک + `پخش`\n"
        "⏸ `مکث`\n"
        "▶️ `ادامه`\n"
        "⏭ `بعدی`\n"
        "⏮ `قبلی`\n"
        "⏹ `اتمام`\n"
        "⏩ `جلو 10`\n"
        "⏪ `عقب 10`\n"
        "🔊 `صدا 100`\n"
        "📋 `صف`\n"
        "📊 `وضعیت`\n"
        "🆔 `آیدی`"
    )


# =========================================================
# پخش
# =========================================================

@Client.on_message(
    filters.regex(r"^پخش(?:\s+(.+))?$")
)
async def play_handler(
    client: Client,
    message: Message,
):
    if not player:
        await message.reply_text(
            "❌ پلیر آماده نیست."
        )
        return

    query = None

    match = re.match(
        r"^پخش(?:\s+(.+))?$",
        message.text or "",
    )

    if match:
        query = match.group(1)

    # -----------------------------------------------------
    # ریپلای روی فایل صوتی
    # -----------------------------------------------------

    media = _get_reply_audio(message)

    if media:
        try:
            filepath = await client.download_media(
                message.reply_to_message,
                file_name="downloads/",
            )

            if not filepath:
                await message.reply_text(
                    "❌ دانلود موزیک انجام نشد."
                )
                return

            track = TrackInfo(
                title=_audio_title(media),
                performer=_audio_artist(media),
                artist=_audio_artist(media),
                filepath=filepath,
            )

            ok, result = await _download_and_play(
                message.chat.id,
                track,
            )

            if not ok:
                await message.reply_text(
                    result
                )
                return

            if result == "queued":
                queue_size = len(
                    player.get_queue(
                        message.chat.id
                    )
                )

                await message.reply_text(
                    f"➕ موزیک به صف اضافه شد.\n"
                    f"📋 جایگاه تقریبی در صف: `{queue_size}`\n\n"
                    f"{player_text(track)}"
                )

            else:
                await message.reply_text(
                    "▶️ **موزیک شروع شد.**\n\n"
                    + player_text(track),
                    reply_markup=music_keyboard(),
                )

            if message.from_user:
                _increase_play(
                    message.from_user.id
                )

            return

        except Exception:
            logger.exception(
                "Reply audio play failed"
            )

            await message.reply_text(
                "❌ خطا هنگام آماده‌سازی موزیک."
            )

            return

    # -----------------------------------------------------
    # پخش با نام آهنگ
    # -----------------------------------------------------

    if not query:
        await message.reply_text(
            "🎵 نام آهنگ را بعد از `پخش` بنویسید.\n\n"
            "مثال:\n"
            "`پخش محسن یگانه بهت قول میدم`"
        )
        return

    try:
        downloader = player.downloader

        track = await downloader.search(
            query,
            limit=1,
        )

        if not track:
            await message.reply_text(
                "❌ موزیکی پیدا نشد."
            )
            return

        ok, result = await _download_and_play(
            message.chat.id,
            track,
        )

        if not ok:
            await message.reply_text(
                result
            )
            return

        if result == "queued":
            queue_size = len(
                player.get_queue(
                    message.chat.id
                )
            )

            await message.reply_text(
                f"➕ **به صف اضافه شد.**\n"
                f"📋 تعداد صف: `{queue_size}`\n\n"
                + player_text(track)
            )

        else:
            await message.reply_text(
                "▶️ **موزیک شروع شد.**\n\n"
                + player_text(track),
                reply_markup=music_keyboard(),
            )

        if message.from_user:
            _increase_play(
                message.from_user.id
            )

    except Exception:
        logger.exception(
            "Play search failed"
        )

        await message.reply_text(
            "❌ خطا هنگام جست‌وجو یا پخش موزیک."
        )


# =========================================================
# صف
# =========================================================

@Client.on_message(
    filters.regex(r"^صف$")
)
async def queue_handler(
    client: Client,
    message: Message,
):
    if not player:
        await message.reply_text(
            "❌ پلیر آماده نیست."
        )
        return

    queue = player.get_queue(
        message.chat.id
    )

    if not queue:
        await message.reply_text(
            "📋 صف موزیک خالی است."
        )
        return

    lines = [
        "📋 **صف پخش موزیک**",
        "",
    ]

    for index, track in enumerate(
        queue[:20],
        start=1,
    ):
        artist = _track_artist(track)
        title = _track_title(track)

        if artist:
            lines.append(
                f"`{index}` — {artist} - {title}"
            )
        else:
            lines.append(
                f"`{index}` — {title}"
            )

    if len(queue) > 20:
        lines.append(
            f"\n... و {len(queue) - 20} موزیک دیگر"
        )

    await message.reply_text(
        "\n".join(lines)
    )


# =========================================================
# مکث
# =========================================================

@Client.on_message(
    filters.regex(r"^مکث$")
)
async def pause_handler(
    client: Client,
    message: Message,
):
    result = await _player_method(
        "pause",
        message.chat.id,
    )

    if result:
        await message.reply_text(
            "⏸ موزیک مکث شد."
        )
    else:
        await message.reply_text(
            "❌ موزیکی برای مکث وجود ندارد."
        )


# =========================================================
# ادامه
# =========================================================

@Client.on_message(
    filters.regex(r"^ادامه$")
)
async def resume_handler(
    client: Client,
    message: Message,
):
    result = await _player_method(
        "resume",
        message.chat.id,
    )

    if result:
        await message.reply_text(
            "▶️ موزیک ادامه پیدا کرد."
        )
    else:
        await message.reply_text(
            "❌ موزیک در حالت مکث نیست."
        )


# =========================================================
# اتمام
# =========================================================

@Client.on_message(
    filters.regex(r"^اتمام$")
)
async def stop_handler(
    client: Client,
    message: Message,
):
    result = await _player_method(
        "stop",
        message.chat.id,
    )

    if result:
        await message.reply_text(
            "⏹ پخش موزیک تمام شد و صف پاک شد."
        )
    else:
        await message.reply_text(
            "❌ توقف موزیک انجام نشد."
        )


# =========================================================
# بعدی
# =========================================================

@Client.on_message(
    filters.regex(r"^بعدی$")
)
async def next_handler(
    client: Client,
    message: Message,
):
    track = await _player_method(
        "next",
        message.chat.id,
    )

    if not track:
        await message.reply_text(
            "❌ موزیک دیگری در صف وجود ندارد."
        )
        return

    await message.reply_text(
        "⏭ **موزیک بعدی پخش شد.**\n\n"
        + player_text(track),
        reply_markup=music_keyboard(),
    )


# =========================================================
# قبلی
# =========================================================

@Client.on_message(
    filters.regex(r"^قبلی$")
)
async def previous_handler(
    client: Client,
    message: Message,
):
    track = await _player_method(
        "previous",
        message.chat.id,
    )

    if not track:
        await message.reply_text(
            "❌ موزیک قبلی موجود نیست."
        )
        return

    await message.reply_text(
        "⏮ **موزیک قبلی پخش شد.**\n\n"
        + player_text(track),
        reply_markup=music_keyboard(),
    )


# =========================================================
# جلو
# =========================================================

@Client.on_message(
    filters.regex(r"^جلو(?:\s+(\d+))?$")
)
async def forward_handler(
    client: Client,
    message: Message,
):
    match = re.match(
        r"^جلو(?:\s+(\d+))?$",
        message.text or "",
    )

    seconds = 10

    if match and match.group(1):
        seconds = int(
            match.group(1)
        )

    result = await _player_method(
        "forward",
        message.chat.id,
        seconds,
    )

    if result:
        await message.reply_text(
            f"⏩ `{seconds}` ثانیه جلو رفت."
        )
    else:
        await message.reply_text(
            "❌ جلو بردن موزیک پشتیبانی نمی‌شود."
        )


# =========================================================
# عقب
# =========================================================

@Client.on_message(
    filters.regex(r"^عقب(?:\s+(\d+))?$")
)
async def backward_handler(
    client: Client,
    message: Message,
):
    match = re.match(
        r"^عقب(?:\s+(\d+))?$",
        message.text or "",
    )

    seconds = 10

    if match and match.group(1):
        seconds = int(
            match.group(1)
        )

    result = await _player_method(
        "backward",
        message.chat.id,
        seconds,
    )

    if result:
        await message.reply_text(
            f"⏪ `{seconds}` ثانیه عقب رفت."
        )
    else:
        await message.reply_text(
            "❌ عقب بردن موزیک پشتیبانی نمی‌شود."
        )


# =========================================================
# صدا
# =========================================================

@Client.on_message(
    filters.regex(r"^صدا(?:\s+(\d+))?$")
)
async def volume_handler(
    client: Client,
    message: Message,
):
    match = re.match(
        r"^صدا(?:\s+(\d+))?$",
        message.text or "",
    )

    if not match or not match.group(1):
        try:
            status = await _get_status(
                message.chat.id
            )

            await message.reply_text(
                f"🔊 صدای فعلی: `{status['volume']}`"
            )

        except Exception:
            await message.reply_text(
                "🔊 صدای فعلی: `100`"
            )

        return

    volume = int(
        match.group(1)
    )

    volume = max(
        0,
        min(
            200,
            volume,
        ),
    )

    result = await _player_method(
        "set_volume",
        message.chat.id,
        volume,
    )

    if result:
        await message.reply_text(
            f"🔊 صدا روی `{volume}` تنظیم شد."
        )
    else:
        await message.reply_text(
            "❌ تغییر صدا انجام نشد."
        )


# =========================================================
# آیدی
# =========================================================

@Client.on_message(
    filters.regex(r"^آیدی$")
)
async def id_handler(
    client: Client,
    message: Message,
):
    user_id = (
        message.from_user.id
        if message.from_user
        else "نامشخص"
    )

    chat_id = message.chat.id

    await message.reply_text(
        f"🆔 **اطلاعات آیدی**\n\n"
        f"👤 آیدی شما:\n`{user_id}`\n\n"
        f"💬 آیدی چت:\n`{chat_id}`"
    )


# =========================================================
# وضعیت
# =========================================================

@Client.on_message(
    filters.regex(r"^وضعیت$")
)
async def status_handler(
    client: Client,
    message: Message,
):
    status = await _get_status(
        message.chat.id
    )

    track = status.get(
        "track"
    )

    if not track:
        await message.reply_text(
            "🎵 هیچ موزیکی در حال پخش نیست."
        )
        return

    position = int(
        status.get(
            "position",
            0,
        )
    )

    minutes = position // 60
    seconds = position % 60

    state = (
        "⏸ مکث"
        if status.get("paused")
        else "▶️ در حال پخش"
    )

    await message.reply_text(
        f"📊 **وضعیت پخش**\n\n"
        f"{player_text(track)}\n\n"
        f"وضعیت: {state}\n"
        f"⏱ موقعیت: `{minutes}:{seconds:02d}`\n"
        f"🔊 صدا: `{status.get('volume', 100)}`\n"
        f"📋 تعداد صف: `{status.get('queue_size', 0)}`",
        reply_markup=music_keyboard(),
    )


# =========================================================
# ترفیع موزیک
# =========================================================

@Client.on_message(
    filters.regex(r"^ترفیع موزیک$")
)
async def promote_music_admin(
    client: Client,
    message: Message,
):
    if not message.from_user:
        return

    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user

    if not target:
        await message.reply_text(
            "❌ برای ترفیع، روی پیام کاربر ریپلای کنید."
        )
        return

    music_admins.add(
        target.id
    )

    await message.reply_text(
        f"✅ کاربر `{target.id}` به مدیر موزیک اضافه شد."
    )


# =========================================================
# عزل موزیک
# =========================================================

@Client.on_message(
    filters.regex(r"^عزل موزیک$")
)
async def demote_music_admin(
    client: Client,
    message: Message,
):
    if not message.reply_to_message:
        await message.reply_text(
            "❌ روی پیام کاربر ریپلای کنید."
        )
        return

    target = (
        message.reply_to_message.from_user
    )

    if not target:
        await message.reply_text(
            "❌ کاربر پیدا نشد."
        )
        return

    music_admins.discard(
        target.id
    )

    await message.reply_text(
        f"✅ کاربر `{target.id}` از مدیران موزیک حذف شد."
    )


# =========================================================
# مالک موزیک
# =========================================================

@Client.on_message(
    filters.regex(r"^مالک موزیک$")
)
async def music_owner_handler(
    client: Client,
    message: Message,
):
    global music_owner_id

    if not message.from_user:
        return

    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user

    if target:
        music_owner_id = target.id

        await message.reply_text(
            f"👑 مالک موزیک روی `{target.id}` تنظیم شد."
        )
        return

    await message.reply_text(
        f"👑 مالک فعلی موزیک:\n"
        f"`{music_owner_id or 'تنظیم نشده'}`"
    )


# =========================================================
# شروع کال
# =========================================================

@Client.on_message(
    filters.regex(r"^شروع کال$")
)
async def start_call_handler(
    client: Client,
    message: Message,
):
    await message.reply_text(
        "❌ شروع کال هنوز به کنترل تماس صوتی متصل نشده است."
    )


# =========================================================
# پایان کال
# =========================================================

@Client.on_message(
    filters.regex(r"^پایان کال$")
)
async def end_call_handler(
    client: Client,
    message: Message,
):
    if player:
        result = await _player_method(
            "stop",
            message.chat.id,
        )

        if result:
            await message.reply_text(
                "⏹ پخش و اتصال فعلی متوقف شد."
            )
            return

    await message.reply_text(
        "❌ کنترل پایان کال به‌صورت مستقل متصل نشده است."
    )


# =========================================================
# کامنت کال فعال
# =========================================================

@Client.on_message(
    filters.regex(r"^کامنت کال فعال$")
)
async def enable_call_comments_handler(
    client: Client,
    message: Message,
):
    await message.reply_text(
        "❌ کنترل کامنت کال هنوز متصل نشده است."
    )


# =========================================================
# کامنت کال غیر فعال
# =========================================================

@Client.on_message(
    filters.regex(r"^کامنت کال غیر فعال$")
)
async def disable_call_comments_handler(
    client: Client,
    message: Message,
):
    await message.reply_text(
        "❌ کنترل کامنت کال هنوز متصل نشده است."
    )


# =========================================================
# Callback — منوی موزیک
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_menu$")
)
async def music_menu_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    await query.message.edit_text(
        "🎵 **کنترل موزیک**\n\n"
        "از دکمه‌های زیر استفاده کنید:",
        reply_markup=music_keyboard(),
    )


# =========================================================
# Callback — قبلی
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_previous$")
)
async def music_previous_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    track = await _player_method(
        "previous",
        query.message.chat.id,
    )

    if not track:
        await query.message.reply_text(
            "❌ موزیک قبلی موجود نیست."
        )
        return

    await query.message.edit_text(
        "⏮ **موزیک قبلی پخش شد.**\n\n"
        + player_text(track),
        reply_markup=music_keyboard(),
    )


# =========================================================
# Callback — ادامه
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_resume$")
)
async def music_resume_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "resume",
        query.message.chat.id,
    )

    if result:
        await query.message.edit_text(
            "▶️ **موزیک ادامه پیدا کرد.**",
            reply_markup=music_keyboard(),
        )
    else:
        await query.answer(
            "موزیک در حالت مکث نیست.",
            show_alert=True,
        )


# =========================================================
# Callback — بعدی
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_next$")
)
async def music_next_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    track = await _player_method(
        "next",
        query.message.chat.id,
    )

    if not track:
        await query.answer(
            "صف موزیک خالی است.",
            show_alert=True,
        )
        return

    await query.message.edit_text(
        "⏭ **موزیک بعدی پخش شد.**\n\n"
        + player_text(track),
        reply_markup=music_keyboard(),
    )


# =========================================================
# Callback — مکث
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_pause$")
)
async def music_pause_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "pause",
        query.message.chat.id,
    )

    if result:
        await query.message.edit_text(
            "⏸ **موزیک مکث شد.**",
            reply_markup=music_keyboard(),
        )
    else:
        await query.answer(
            "موزیکی برای مکث وجود ندارد.",
            show_alert=True,
        )


# =========================================================
# Callback — جلو 10
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_forward_10$")
)
async def music_forward_10_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "forward",
        query.message.chat.id,
        10,
    )

    if result:
        await query.answer(
            "⏩ ۱۰ ثانیه جلو رفت.",
        )
    else:
        await query.answer(
            "❌ جلو بردن پشتیبانی نمی‌شود.",
            show_alert=True,
        )


# =========================================================
# Callback — عقب 10
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_backward_10$")
)
async def music_backward_10_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "backward",
        query.message.chat.id,
        10,
    )

    if result:
        await query.answer(
            "⏪ ۱۰ ثانیه عقب رفت.",
        )
    else:
        await query.answer(
            "❌ عقب بردن پشتیبانی نمی‌شود.",
            show_alert=True,
        )


# =========================================================
# Callback — جلو 30
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_forward_30$")
)
async def music_forward_30_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "forward",
        query.message.chat.id,
        30,
    )

    if result:
        await query.answer(
            "⏩ ۳۰ ثانیه جلو رفت.",
        )
    else:
        await query.answer(
            "❌ جلو بردن پشتیبانی نمی‌شود.",
            show_alert=True,
        )


# =========================================================
# Callback — عقب 30
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_backward_30$")
)
async def music_backward_30_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "backward",
        query.message.chat.id,
        30,
    )

    if result:
        await query.answer(
            "⏪ ۳۰ ثانیه عقب رفت.",
        )
    else:
        await query.answer(
            "❌ عقب بردن پشتیبانی نمی‌شود.",
            show_alert=True,
        )


# =========================================================
# Callback — صدا
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_volume$")
)
async def music_volume_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    status = await _get_status(
        query.message.chat.id
    )

    await query.answer(
        f"🔊 صدا: {status.get('volume', 100)}",
        show_alert=True,
    )


# =========================================================
# Callback — اتمام
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_stop$")
)
async def music_stop_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    result = await _player_method(
        "stop",
        query.message.chat.id,
    )

    if result:
        await query.message.edit_text(
            "⏹ **پخش موزیک تمام شد.**",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await query.answer(
            "❌ توقف انجام نشد.",
            show_alert=True,
        )


# =========================================================
# Callback — وضعیت
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^music_status$")
)
async def music_status_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    status = await _get_status(
        query.message.chat.id
    )

    track = status.get(
        "track"
    )

    if not track:
        await query.message.edit_text(
            "🎵 هیچ موزیکی در حال پخش نیست.",
            reply_markup=music_keyboard(),
        )
        return

    position = int(
        status.get(
            "position",
            0,
        )
    )

    minutes = position // 60
    seconds = position % 60

    state = (
        "⏸ مکث"
        if status.get("paused")
        else "▶️ در حال پخش"
    )

    await query.message.edit_text(
        f"📊 **وضعیت پخش**\n\n"
        f"{player_text(track)}\n\n"
        f"وضعیت: {state}\n"
        f"⏱ موقعیت: `{minutes}:{seconds:02d}`\n"
        f"🔊 صدا: `{status.get('volume', 100)}`\n"
        f"📋 صف: `{status.get('queue_size', 0)}`",
        reply_markup=music_keyboard(),
    )


# =========================================================
# Callback — منوی اصلی
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^main_menu$")
)
async def main_menu_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    await query.message.edit_text(
        "🏠 **منوی اصلی موزیک پلیر**\n\n"
        "یک گزینه را انتخاب کنید:",
        reply_markup=main_menu_keyboard(),
    )


# =========================================================
# Callback — آیدی
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^show_id$")
)
async def show_id_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    user_id = (
        query.from_user.id
        if query.from_user
        else "نامشخص"
    )

    await query.message.reply_text(
        f"🆔 آیدی شما:\n`{user_id}`\n\n"
        f"💬 آیدی چت:\n`{query.message.chat.id}`"
    )


# =========================================================
# Callback — آمار
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^show_stats$")
)
async def show_stats_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    total_users = len(
        user_stats
    )

    total_plays = sum(
        int(
            data.get(
                "plays",
                0,
            )
        )
        for data in user_stats.values()
    )

    await query.message.reply_text(
        f"📊 **آمار ربات**\n\n"
        f"👤 کاربران ثبت‌شده: `{total_users}`\n"
        f"🎵 تعداد پخش ثبت‌شده: `{total_plays}`"
    )


# =========================================================
# Callback — عضویت
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^membership$")
)
async def membership_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    if REQUIRED_CHANNEL:
        text = (
            "🔐 **عضویت اجباری**\n\n"
            f"برای استفاده از ربات ابتدا در کانال زیر عضو شوید:\n"
            f"{REQUIRED_CHANNEL}"
        )
    else:
        text = (
            "🔐 **عضویت اجباری هنوز تنظیم نشده است.**"
        )

    await query.message.reply_text(
        text
    )


# =========================================================
# Callback — پشتیبانی
# =========================================================

@Client.on_callback_query(
    filters.regex(r"^support$")
)
async def support_callback(
    client: Client,
    query: CallbackQuery,
):
    await query.answer()

    if SUPPORT_USERNAME:
        await query.message.reply_text(
            f"👤 پشتیبانی:\n{SUPPORT_USERNAME}"
        )
    else:
        await query.message.reply_text(
            "👤 پشتیبانی هنوز تنظیم نشده است."
        )
