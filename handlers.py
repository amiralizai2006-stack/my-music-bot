import logging
import os
import re
from pathlib import Path
from datetime import datetime

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from player import TrackInfo

from database import (
    init_db,
    add_user,
    increase_play_count,
    get_stats,
    set_owner,
    get_owner,
    is_owner,
    add_music_admin,
    remove_music_admin,
    is_music_admin,
    get_music_admins,
    activate_subscription,
    deactivate_subscription,
    is_subscription_active,
    subscription_days_left,
    get_subscription,
    get_required_channel,
    get_support_username,
)

logger = logging.getLogger(__name__)

# ============================================================
# DATABASE
# ============================================================

init_db()

# ============================================================
# اتصال‌ها
# ============================================================

bot = None
player = None
pytgcalls = None
shutdown_event = None

SUPPORT_USERNAME = ""
REQUIRED_CHANNEL = ""

user_stats = {}

# ============================================================
# مالک اولیه از Environment
# ============================================================

try:
    OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
except Exception:
    OWNER_ID = 0

if OWNER_ID:
    try:
        if not get_owner():
            set_owner(OWNER_ID)
            logger.info("Initial owner configured: %s", OWNER_ID)
    except Exception:
        logger.exception("Could not configure initial owner")


# ============================================================
# ابزار مالک و مدیر
# ============================================================

def _is_owner(user_id):
    try:
        return bool(is_owner(user_id))
    except Exception:
        return False


def _is_music_admin(user_id):
    try:
        return bool(is_music_admin(user_id))
    except Exception:
        return False


def _can_manage_music(user_id):
    return (
        _is_owner(user_id)
        or _is_music_admin(user_id)
    )


def _has_subscription_access(user_id):
    """
    مالک همیشه دسترسی دارد.
    کاربران عادی فقط با اشتراک فعال.
    """
    if _is_owner(user_id):
        return True

    try:
        return bool(
            is_subscription_active(user_id)
        )
    except Exception:
        return False


# ============================================================
# آمار
# ============================================================

def _get_user_stats(user_id):
    if user_id not in user_stats:
        user_stats[user_id] = {
            "messages": 0,
            "plays": 0,
            "pauses": 0,
            "joins": 0,
            "last_seen": None,
        }

    return user_stats[user_id]


def _register_activity(message):
    if not message.from_user:
        return

    user = message.from_user

    stats = _get_user_stats(
        user.id
    )

    stats["messages"] += 1
    stats["last_seen"] = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    try:
        add_user(
            user.id,
            username=user.username or "",
            first_name=user.first_name or "",
        )
    except Exception:
        logger.exception(
            "DATABASE USER REGISTER ERROR"
        )


def _user_name(user):
    if not user:
        return "کاربر"

    return (
        user.first_name
        or user.username
        or "کاربر"
    )


def _user_rank(user_id):
    if _is_owner(user_id):
        return "👑 مالک موزیک"

    if _is_music_admin(user_id):
        return "🎵 مدیر موزیک"

    return "👤 کاربر"


# ============================================================
# بررسی دسترسی
# ============================================================

async def _check_subscription(
    message,
    send_message=True,
):
    """
    بررسی اشتراک قبل از استفاده از امکانات موزیک.
    """

    if not message.from_user:
        return True

    user_id = message.from_user.id

    if _has_subscription_access(user_id):
        return True

    if send_message:
        await message.reply_text(
            "🔒 **اشتراک شما فعال نیست.**\n\n"
            "برای استفاده از موزیک پلیر باید اشتراک فعال داشته باشید.\n\n"
            "📅 مدت‌های قابل فعال‌سازی:\n"
            "• 10 روز\n"
            "• 30 روز\n"
            "• 60 روز\n"
            "• 90 روز\n"
            "• 180 روز\n\n"
            "🛟 برای فعال‌سازی با پشتیبانی تماس بگیرید."
        )

    return False


# ============================================================
# اتصال
# ============================================================

def set_bot_instances(
    bot_instance,
    pytgcalls_instance=None,
    player_instance=None,
    shutdown_event_instance=None,
):
    global bot
    global player
    global pytgcalls
    global shutdown_event

    bot = bot_instance
    pytgcalls = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown_event_instance

    logger.info(
        "Handlers received bot/player instances"
    )

    register_handlers()

    logger.info(
        "Telegram handlers registered successfully"
    )


# ============================================================
# منو اصلی
# ============================================================

def main_menu_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎵 موزیک",
                    callback_data="menu_music",
                ),
                InlineKeyboardButton(
                    "🎧 وضعیت",
                    callback_data="menu_status",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🆔 آیدی من",
                    callback_data="menu_id",
                ),
                InlineKeyboardButton(
                    "📊 آمار",
                    callback_data="menu_stats",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📢 عضویت اجباری",
                    callback_data="menu_force",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🛟 پشتیبانی",
                    callback_data="menu_support",
                ),
            ],
        ]
    )


def music_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏮️ قبلی",
                    callback_data="music_previous",
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data="music_resume",
                ),
                InlineKeyboardButton(
                    "⏭️ بعدی",
                    callback_data="music_next",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏪ عقب 10",
                    callback_data="music_backward_10",
                ),
                InlineKeyboardButton(
                    "⏸️ مکث",
                    callback_data="music_pause",
                ),
                InlineKeyboardButton(
                    "⏩ جلو 10",
                    callback_data="music_forward_10",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏪ عقب 30",
                    callback_data="music_backward_30",
                ),
                InlineKeyboardButton(
                    "⏩ جلو 30",
                    callback_data="music_forward_30",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔊 صدا",
                    callback_data="music_volume",
                ),
                InlineKeyboardButton(
                    "⏹️ اتمام",
                    callback_data="music_stop",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎧 وضعیت",
                    callback_data="music_status",
                ),
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="main_menu",
                ),
            ],
        ]
    )


# ============================================================
# TrackInfo
# ============================================================

def _track_artist(track):

    if not track:
        return "Unknown"

    return (
        getattr(track, "artist", None)
        or getattr(track, "performer", None)
        or getattr(track, "uploader", None)
        or "Unknown"
    )


def _track_title(track):

    if not track:
        return "موزیک"

    return (
        getattr(track, "title", None)
        or "موزیک"
    )


def player_text(
    track=None,
    position=0,
):

    if not track:

        return (
            "╭───────────────╮\n"
            "     🎵 𝗦𝗜𝗟𝗘𝗡𝗧 𝗠𝗨𝗦𝗜𝗖\n"
            "╰───────────────╯\n\n"
            "🎵 هیچ آهنگی در حال پخش نیست.\n\n"
            "🟢 ربات سایلنت همیشه آنلاین می‌باشد."
        )

    duration = (
        getattr(track, "duration", 0)
        or 0
    )

    position = max(
        0,
        min(
            int(position),
            duration if duration else int(position)
        )
    )

    return (
        "╭───────────────╮\n"
        "     🎵 𝗦𝗜𝗟𝗘𝗡𝗧 𝗠𝗨𝗦𝗜𝗖\n"
        "╰───────────────╯\n\n"
        f"🎵 {_track_title(track)}\n"
        f"👤 {_track_artist(track)}\n\n"
        f"▶️ زمان: {position}s"
        f" / {duration}s\n\n"
        "🟢 ربات سایلنت همیشه آنلاین می‌باشد."
    )


# ============================================================
# فایل صوتی ریپلای
# ============================================================

def _get_reply_audio(message):

    if not message.reply_to_message:
        return None

    reply = message.reply_to_message

    if reply.audio:
        return reply.audio

    if reply.voice:
        return reply.voice

    if reply.document:

        mime = (
            reply.document.mime_type
            or ""
        )

        if mime.startswith("audio/"):
            return reply.document

    return None


def _audio_title(media):

    return (
        getattr(media, "title", None)
        or getattr(media, "file_name", None)
        or "آهنگ"
    )


def _audio_artist(media):

    return (
        getattr(media, "performer", None)
        or getattr(media, "artist", None)
        or "Unknown"
    )


# ============================================================
# وضعیت پلیر
# ============================================================

async def _get_status(chat_id):

    if not player:
        return None

    try:
        return await player.get_status(
            chat_id
        )

    except TypeError:

        try:
            return await player.get_status(
                chat_id=chat_id
            )

        except Exception:
            return None

    except Exception:
        logger.exception(
            "GET STATUS ERROR"
        )
        return None


# ============================================================
# پخش
# ============================================================

async def _download_and_play(
    message,
    track,
):

    if player is None:

        await message.reply_text(
            "❌ پخش‌کننده آماده نیست."
        )

        return

    downloader = getattr(
        player,
        "downloader",
        None
    )

    if downloader is None:

        await message.reply_text(
            "❌ دانلودر آماده نیست."
        )

        return

    try:

        await message.reply_text(
            "⏳ در حال آماده‌سازی آهنگ..."
        )

        filepath = await downloader.prepare(
            track
        )

        if not filepath:

            await message.reply_text(
                "❌ دانلود آهنگ انجام نشد."
            )

            return

        track.filepath = filepath

        chat_id = message.chat.id

        was_playing = (
            player.get_current(chat_id)
            is not None
        )

        ok = await player.play(
            chat_id,
            track
        )

        if not ok:

            await message.reply_text(
                "❌ آهنگ پخش نشد."
            )

            return

        if message.from_user:

            stats = _get_user_stats(
                message.from_user.id
            )

            stats["plays"] += 1

            try:
                increase_play_count(
                    message.from_user.id
                )
            except Exception:
                logger.exception(
                    "PLAY COUNT ERROR"
                )

        if was_playing:

            queue = player.get_queue(
                chat_id
            )

            await message.reply_text(
                "➕ آهنگ به صف اضافه شد.\n\n"
                f"🎵 {_track_title(track)}\n"
                f"👤 {_track_artist(track)}\n\n"
                f"📋 جایگاه در صف: {len(queue)}\n\n"
                "🎧 آهنگ فعلی بدون قطع شدن ادامه دارد."
            )

            return

        position = await player.get_position(
            chat_id
        )

        await message.reply_text(
            player_text(
                track,
                position
            ),
            reply_markup=music_keyboard()
        )

    except Exception as e:

        logger.exception(
            "DOWNLOAD PLAY ERROR"
        )

        await message.reply_text(
            f"❌ خطای پخش:\n"
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# اجرای متد پلیر
# ============================================================

async def _player_method(
    method_name,
    chat_id,
    *args,
):

    if player is None:
        return None

    method = getattr(
        player,
        method_name,
        None
    )

    if method is None:

        logger.warning(
            "PLAYER METHOD NOT AVAILABLE: %s",
            method_name
        )

        return None

    try:

        return await method(
            chat_id,
            *args
        )

    except Exception:

        logger.exception(
            "PLAYER METHOD ERROR: %s",
            method_name
        )

        return None


# ============================================================
# ثبت Handlerها
# ============================================================

def register_handlers():

    if bot is None:
        raise RuntimeError(
            "Bot instance has not been set"
        )

    logger.info(
        "REGISTERING TELEGRAM HANDLERS"
    )


    # ========================================================
    # START
    # ========================================================

    @bot.on_message(
        filters.private
        & filters.command("start")
    )
    async def start_command(
        client,
        message
    ):

        _register_activity(message)

        await message.reply_text(
            "╭───────────────╮\n"
            "     🎵 𝗦𝗜𝗟𝗘𝗡𝗧 𝗠𝗨𝗦𝗜𝗖\n"
            "╰───────────────╯\n\n"
            "🟢 ربات سایلنت همیشه آنلاین می‌باشد.\n\n"
            "🎧 موزیک پلیر آماده است.\n"
            "از منوی زیر استفاده کن:",
            reply_markup=main_menu_keyboard()
        )


    # ========================================================
    # استارت
    # ========================================================

    @bot.on_message(
        filters.private
        & filters.text
        & filters.regex(
            r"^\s*استارت\s*$"
        )
    )
    async def start_farsi(
        client,
        message
    ):

        _register_activity(message)

        await message.reply_text(
            "╭───────────────╮\n"
            "     🎵 𝗦𝗜𝗟𝗘𝗡𝗧 𝗠𝗨𝗦𝗜𝗖\n"
            "╰───────────────╯\n\n"
            "🟢 ربات سایلنت همیش.\n\n"
            "🎧 موزیک پلیر آماده است.",
            reply_markup=main_menu_keyboard()
        )


    # ========================================================
    # ربات
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*ربات\s*$"
        )
    )
    async def bot_status(
        client,
        message
    ):

        _register_activity(message)

        await message.reply_text(
            "🟢 ربات سایلنت همیشه آنلاین می‌باشد."
        )


    # ========================================================
    # کمک
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*کمک\s*$"
        )
    )
    async def help_handler(
        client,
        message
    ):

        _register_activity(message)

        await message.reply_text(
            "🎵 دستورات ربات سایلنت\n\n"

            "🎵 پخش نام آهنگ\n"
            "🎵 پخش ← روی فایل ریپلای\n\n"

            "⏸️ مکث\n"
            "▶️ ادامه\n"
            "⏹️ اتمام\n"
            "⏭️ بعدی\n"
            "⏮️ قبلی\n"
            "📋 صف\n"
            "⏩ جلو 30\n"
            "⏪ عقب 30\n"
            "🔊 صدا 80\n\n"

            "🆔 آیدی\n"
            "🎧 وضعیت\n"
            "📅 اشتراک\n\n"

            "👑 ترفیع موزیک\n"
            "👤 عزل موزیک\n"
            "👑 مالک موزیک\n\n"

            "💳 شارژ 10\n"
            "💳 شارژ 30\n"
            "💳 شارژ 60\n"
            "💳 شارژ 90\n"
            "💳 شارژ 180\n\n"

            "📞 شروع کال\n"
            "📞 پایان کال\n"
            "💬 کامنت کال فعال\n"
            "💬 کامنت کال غیر فعال"
        )


    # ========================================================
    # پخش
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*پخش(?:\s+(.+))?\s*$"
        )
    )
    async def play_handler(
        client,
        message
    ):

        _register_activity(message)

        # بررسی اشتراک
        if not await _check_subscription(
            message
        ):
            return

        text = message.text or ""

        match = re.match(
            r"^\s*پخش(?:\s+(.+))?\s*$",
            text
        )

        query = ""

        if match and match.group(1):
            query = match.group(1).strip()


        # ----------------------------------------------------
        # ریپلای فایل صوتی
        # ----------------------------------------------------

        if not query:

            media = _get_reply_audio(
                message
            )

            if not media:

                await message.reply_text(
                    "❌ برای پخش آهنگ:\n\n"
                    "• پخش اسم آهنگ\n\n"
                    "یا روی فایل صوتی ریپلای کن و بنویس:\n"
                    "پخش"
                )

                return

            if player is None:

                await message.reply_text(
                    "❌ پخش‌کننده آماده نیست."
                )

                return

            await message.reply_text(
                "⏳ در حال دریافت فایل..."
            )

            try:

                downloads_dir = Path(
                    getattr(
                        player.downloader,
                        "download_dir",
                        "downloads"
                    )
                )

                downloads_dir.mkdir(
                    parents=True,
                    exist_ok=True
                )

                file_name = (
                    getattr(
                        media,
                        "file_name",
                        None
                    )
                    or f"audio_{message.id}.mp3"
                )

                file_name = Path(
                    file_name
                ).name

                filepath = (
                    await client.download_media(
                        message.reply_to_message,
                        file_name=str(
                            downloads_dir
                            / file_name
                        )
                    )
                )

                if not filepath:

                    await message.reply_text(
                        "❌ دریافت فایل انجام نشد."
                    )

                    return

                track = TrackInfo(
                    title=_audio_title(
                        media
                    ),
                    performer=_audio_artist(
                        media
                    ),
                    artist=_audio_artist(
                        media
                    ),
                    filepath=filepath,
                )

                chat_id = message.chat.id

                was_playing = (
                    player.get_current(
                        chat_id
                    )
                    is not None
                )

                ok = await player.play(
                    chat_id,
                    track
                )

                if not ok:

                    await message.reply_text(
                        "❌ پخش آهنگ انجام نشد."
                    )

                    return

                if message.from_user:

                    stats = _get_user_stats(
                        message.from_user.id
                    )

                    stats["plays"] += 1

                    try:
                        increase_play_count(
                            message.from_user.id
                        )
                    except Exception:
                        logger.exception(
                            "PLAY COUNT ERROR"
                        )

                if was_playing:

                    queue = player.get_queue(
                        chat_id
                    )

                    await message.reply_text(
                        "➕ آهنگ به صف اضافه شد.\n\n"
                        f"🎵 {_track_title(track)}\n"
                        f"👤 {_track_artist(track)}\n\n"
                        f"📋 جایگاه در صف: {len(queue)}\n\n"
                        "🎧 آهنگ فعلی بدون قطع شدن ادامه دارد."
                    )

                else:

                    position = (
                        await player.get_position(
                            chat_id
                        )
                    )

                    await message.reply_text(
                        player_text(
                            track,
                            position
                        ),
                        reply_markup=music_keyboard()
                    )

            except Exception as e:

                logger.exception(
                    "REPLY PLAY ERROR"
                )

                await message.reply_text(
                    f"❌ خطای پخش:\n"
                    f"{type(e).__name__}: {e}"
                )

            return


        # ----------------------------------------------------
        # جستجو
        # ----------------------------------------------------

        if player is None:

            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )

            return

        downloader = getattr(
            player,
            "downloader",
            None
        )

        if downloader is None:

            await message.reply_text(
                "❌ دانلودر آماده نیست."
            )

            return

        await message.reply_text(
            f"🔎 در حال جستجو...\n\n"
            f"🎵 {query}"
        )

        try:

            result = await downloader.search(
                query,
                limit=1
            )

            if not result:

                await message.reply_text(
                    "❌ آهنگی پیدا نشد."
                )

                return

            track = result

            await _download_and_play(
                message,
                track
            )

        except Exception as e:

            logger.exception(
                "SEARCH PLAY ERROR"
            )

            await message.reply_text(
                f"❌ خطای جستجو/پخش:\n"
                f"{type(e).__name__}: {e}"
            )


    # ========================================================
    # صف
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*صف\s*$"
        )
    )
    async def queue_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        if not player:

            await message.reply_text(
                "❌ پلیر آماده نیست."
            )

            return

        chat_id = message.chat.id

        current = player.get_current(
            chat_id
        )

        queue = player.get_queue(
            chat_id
        )

        lines = [
            "📋 صف پخش 𝗦𝗜𝗟𝗘𝗡𝗧",
            ""
        ]

        if current:

            lines.extend(
                [
                    "▶️ در حال پخش:",
                    f"🎵 {_track_title(current)}",
                    f"👤 {_track_artist(current)}",
                    ""
                ]
            )

        if not queue:

            lines.append(
                "📭 صف خالی است."
            )

        else:

            lines.append(
                f"🎧 آهنگ‌های منتظر: {len(queue)}"
            )
            lines.append("")

            for index, track in enumerate(
                queue,
                start=1
            ):

                lines.append(
                    f"{index}. "
                    f"{_track_title(track)}"
                    f" — "
                    f"{_track_artist(track)}"
                )

        await message.reply_text(
            "\n".join(lines),
            reply_markup=music_keyboard()
        )


    # ========================================================
    # مکث
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*مکث\s*$"
        )
    )
    async def pause_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "pause",
            message.chat.id
        )

        if message.from_user:

            _get_user_stats(
                message.from_user.id
            )["pauses"] += 1

        await message.reply_text(
            "⏸️ موزیک مکث شد."
            if ok
            else "❌ مکث انجام نشد."
        )


    # ========================================================
    # ادامه
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*ادامه\s*$"
        )
    )
    async def resume_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "resume",
            message.chat.id
        )

        await message.reply_text(
            "▶️ پخش ادامه پیدا کرد."
            if ok
            else "❌ ادامه پخش انجام نشد."
        )


    # ========================================================
    # اتمام
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*اتمام\s*$"
        )
    )
    async def stop_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "stop",
            message.chat.id
        )

        await message.reply_text(
            "⏹️ پخش متوقف شد."
            if ok
            else "❌ توقف انجام نشد."
        )


    # ========================================================
    # بعدی
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*بعدی\s*$"
        )
    )
    async def next_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        if not player:

            await message.reply_text(
                "❌ پلیر آماده نیست."
            )

            return

        chat_id = message.chat.id

        queue = player.get_queue(
            chat_id
        )

        if not queue:

            await message.reply_text(
                "📭 آهنگ دیگری در صف نیست."
            )

            return

        track = await _player_method(
            "next",
            chat_id
        )

        if not track:

            await message.reply_text(
                "❌ پخش آهنگ بعدی انجام نشد."
            )

            return

        await message.reply_text(
            "⏭️ آهنگ بعدی پخش شد.\n\n"
            f"🎵 {_track_title(track)}\n"
            f"👤 {_track_artist(track)}",
            reply_markup=music_keyboard()
        )


    # ========================================================
    # قبلی
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*قبلی\s*$"
        )
    )
    async def previous_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        track = await _player_method(
            "previous",
            message.chat.id
        )

        if not track:

            await message.reply_text(
                "❌ آهنگ قبلی موجود نیست."
            )

            return

        await message.reply_text(
            "⏮️ آهنگ قبلی پخش شد.\n\n"
            f"🎵 {_track_title(track)}\n"
            f"👤 {_track_artist(track)}",
            reply_markup=music_keyboard()
        )


    # ========================================================
    # جلو
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*جلو\s+(\d+)\s*$"
        )
    )
    async def forward_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        match = re.match(
            r"^\s*جلو\s+(\d+)\s*$",
            message.text or ""
        )

        seconds = int(
            match.group(1)
        )

        seconds = max(
            1,
            min(100, seconds)
        )

        ok = await _player_method(
            "forward",
            message.chat.id,
            seconds
        )

        await message.reply_text(
            f"⏩ {seconds} ثانیه جلو رفت."
            if ok
            else "❌ جلو بردن انجام نشد."
        )


    # ========================================================
    # عقب
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*عقب\s+(\d+)\s*$"
        )
    )
    async def backward_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        match = re.match(
            r"^\s*عقب\s+(\d+)\s*$",
            message.text or ""
        )

        seconds = int(
            match.group(1)
        )

        seconds = max(
            1,
            min(100, seconds)
        )

        ok = await _player_method(
            "backward",
            message.chat.id,
            seconds
        )

        await message.reply_text(
            f"⏪ {seconds} ثانیه عقب رفت."
            if ok
            else "❌ عقب بردن انجام نشد."
        )


    # ========================================================
    # صدا
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*صدا(?:\s+(\d{1,3}))?\s*$"
        )
    )
    async def volume_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        match = re.match(
            r"^\s*صدا(?:\s+(\d{1,3}))?\s*$",
            message.text or ""
        )

        volume = 100

        if match and match.group(1):
            volume = int(
                match.group(1)
            )

        volume = max(
            0,
            min(200, volume)
        )

        ok = await _player_method(
            "set_volume",
            message.chat.id,
            volume
        )

        await message.reply_text(
            f"🔊 صدا روی {volume}% تنظیم شد."
            if ok
            else "❌ تغییر صدا انجام نشد."
        )


    # ========================================================
    # آیدی
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*آیدی\s*$"
        )
    )
    async def id_handler(
        client,
        message
    ):

        _register_activity(message)

        user = message.from_user

        if not user:
            return

        stats = _get_user_stats(
            user.id
        )

        username = (
            f"@{user.username}"
            if user.username
            else "ندارد"
        )

        subscription_text = "❌ فعال نیست"

        try:
            if is_subscription_active(
                user.id
            ):
                days = subscription_days_left(
                    user.id
                )
                subscription_text = (
                    f"✅ فعال — {days} روز باقی‌مانده"
                )
        except Exception:
            pass

        await message.reply_text(
            "╭──── 👤 اطلاعات کاربر ────╮\n\n"
            f"📛 نام: {_user_name(user)}\n"
            f"🔗 یوزرنیم: {username}\n"
            f"🆔 آیدی عددی: {user.id}\n"
            f"👑 مقام: {_user_rank(user.id)}\n"
            f"📅 اشتراک: {subscription_text}\n\n"
            "📊 آمار فعالیت\n"
            f"💬 پیام‌ها: {stats['messages']}\n"
            f"🎵 پخش‌ها: {stats['plays']}\n"
            f"⏸️ مکث‌ها: {stats['pauses']}\n"
            f"🕐 آخرین فعالیت: "
            f"{stats['last_seen'] or 'ثبت نشده'}"
        )


    # ========================================================
    # اشتراک
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*(?:اشتراک|وضعیت اشتراک)\s*$"
        )
    )
    async def subscription_status_handler(
        client,
        message
    ):

        _register_activity(message)

        if not message.from_user:
            return

        user_id = message.from_user.id

        if _is_owner(user_id):

            await message.reply_text(
                "👑 شما مالک ربات هستید.\n\n"
                "♾️ دسترسی شما بدون محدودیت اشتراک است."
            )

            return

        try:

            if not is_subscription_active(
                user_id
            ):

                await message.reply_text(
                    "❌ اشتراک شما فعال نیست."
                )

                return

            days = subscription_days_left(
                user_id
            )

            row = get_subscription(
                user_id
            )

            expires = "نامشخص"

            if row:

                value = row["expires_at"]

                if value:

                    try:
                        expires = datetime.fromisoformat(
                            value
                        ).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                    except Exception:
                        expires = str(value)

            await message.reply_text(
                "📅 **وضعیت اشتراک**\n\n"
                "🟢 وضعیت: فعال\n"
                f"⏳ روز باقی‌مانده: {days}\n"
                f"📆 تاریخ انقضا: {expires}"
            )

        except Exception as e:

            logger.exception(
                "SUBSCRIPTION STATUS ERROR"
            )

            await message.reply_text(
                f"❌ خطا در دریافت اشتراک:\n{e}"
            )


    # ========================================================
    # شارژ
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*شارژ\s+(10|30|60|90|180)\s*$"
        )
    )
    async def charge_handler(
        client,
        message
    ):

        _register_activity(message)

        if not message.from_user:
            return

        # فقط مالک
        if not _is_owner(
            message.from_user.id
        ):

            await message.reply_text(
                "❌ فقط مالک ربات می‌تواند شارژ انجام دهد."
            )

            return

        # باید روی کاربر ریپلای شود
        if not message.reply_to_message:

            await message.reply_text(
                "❌ ابتدا روی پیام کاربر ریپلای کن.\n\n"
                "مثال:\n"
                "روی پیام کاربر → `شارژ 30`"
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

        match = re.match(
            r"^\s*شارژ\s+(10|30|60|90|180)\s*$",
            message.text or ""
        )

        if not match:
            return

        days = int(
            match.group(1)
        )

        try:

            add_user(
                target.id,
                username=target.username or "",
                first_name=target.first_name or "",
            )

            expires = activate_subscription(
                target.id,
                days
            )

            if hasattr(expires, "strftime"):

                expires_text = expires.strftime(
                    "%Y-%m-%d %H:%M"
                )

            else:

                expires_text = str(expires)

            await message.reply_text(
                "╭──── 💳 شارژ اشتراک ────╮\n\n"
                "✅ اشتراک با موفقیت فعال شد.\n\n"
                f"👤 کاربر: {_user_name(target)}\n"
                f"🆔 آیدی: `{target.id}`\n"
                f"⏳ مدت: {days} روز\n"
                f"📆 انقضا: {expires_text}"
            )

        except Exception as e:

            logger.exception(
                "CHARGE ERROR"
            )

            await message.reply_text(
                f"❌ شارژ انجام نشد:\n"
                f"{type(e).__name__}: {e}"
            )


    # ========================================================
    # لغو اشتراک
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*لغو اشتراک\s*$"
        )
    )
    async def cancel_subscription_handler(
        client,
        message
    ):

        _register_activity(message)

        if not message.from_user:
            return

        if not _is_owner(
            message.from_user.id
        ):

            await message.reply_text(
                "❌ فقط مالک ربات می‌تواند اشتراک را لغو کند."
            )

            return

        if not message.reply_to_message:

            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )

            return

        target = (
            message.reply_to_message.from_user
        )

        if not target:
            return

        try:

            deactivate_subscription(
                target.id
            )

            await message.reply_text(
                f"✅ اشتراک {_user_name(target)} لغو شد."
            )

        except Exception as e:

            logger.exception(
                "CANCEL SUBSCRIPTION ERROR"
            )

            await message.reply_text(
                f"❌ خطا:\n{e}"
            )


    # ========================================================
    # ترفیع موزیک
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*ترفیع موزیک\s*$"
        )
    )
    async def promote_handler(
        client,
        message
    ):

        _register_activity(message)

        if not message.from_user:
            return

        if not _is_owner(
            message.from_user.id
        ):

            await message.reply_text(
                "❌ فقط مالک ربات می‌تواند مدیر موزیک تعیین کند."
            )

            return

        if not message.reply_to_message:

            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )

            return

        user = (
            message
            .reply_to_message
            .from_user
        )

        if not user:
            return

        try:

            add_music_admin(
                user.id
            )

            await message.reply_text(
                f"👑 {_user_name(user)}\n\n"
                "🎵 مدیر موزیک شد."
            )

        except Exception as e:

            logger.exception(
                "PROMOTE ERROR"
            )

            await message.reply_text(
                f"❌ خطا:\n{e}"
            )


    # ========================================================
    # عزل موزیک
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*عزل موزیک\s*$"
        )
    )
    async def demote_handler(
        client,
        message
    ):

        _register_activity(message)

        if not message.from_user:
            return

        if not _is_owner(
            message.from_user.id
        ):

            await message.reply_text(
                "❌ فقط مالک ربات می‌تواند مدیر موزیک را عزل کند."
            )

            return

        if not message.reply_to_message:

            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )

            return

        user = (
            message
            .reply_to_message
            .from_user
        )

        if not user:
            return

        try:

            remove_music_admin(
                user.id
            )

            await message.reply_text(
                f"👤 {_user_name(user)}\n\n"
                "از مدیران موزیک عزل شد."
            )

        except Exception as e:

            logger.exception(
                "DEMOTE ERROR"
            )

            await message.reply_text(
                f"❌ خطا:\n{e}"
            )


    # ========================================================
    # مالک موزیک
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*مالک موزیک\s*$"
        )
    )
    async def owner_handler(
        client,
        message
    ):

        _register_activity(message)

        if not message.from_user:
            return

        current_owner = get_owner()

        # اگر مالک قبلی وجود دارد فقط همان مالک اجازه دارد
        if current_owner:

            if message.from_user.id != current_owner:

                await message.reply_text(
                    "❌ فقط مالک فعلی می‌تواند مالک موزیک را تغییر دهد."
                )

                return

        else:

            # اگر مالک هنوز تنظیم نشده
            if OWNER_ID:

                if message.from_user.id != OWNER_ID:

                    await message.reply_text(
                        "❌ شما اجازه تعیین مالک را ندارید."
                    )

                    return

            else:

                # اولین اجرا: خود فرستنده مالک شود
                set_owner(
                    message.from_user.id
                )

        if not message.reply_to_message:

            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )

            return

        user = (
            message
            .reply_to_message
            .from_user
        )

        if not user:
            return

        try:

            set_owner(
                user.id
            )

            await message.reply_text(
                f"👑 {_user_name(user)}\n\n"
                "مالک موزیک شد."
            )

        except Exception as e:

            logger.exception(
                "OWNER ERROR"
            )

            await message.reply_text(
                f"❌ خطا:\n{e}"
            )


    # ========================================================
    # شروع کال
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*شروع کال\s*$"
        )
    )
    async def start_call_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "start_call",
            message.chat.id
        )

        await message.reply_text(
            "📞 کال شروع شد."
            if ok
            else "❌ کنترل شروع کال هنوز به پلیر متصل نشده."
        )


    # ========================================================
    # پایان کال
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*پایان کال\s*$"
        )
    )
    async def end_call_handler(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "end_call",
            message.chat.id
        )

        if not ok:

            ok = await _player_method(
                "stop",
                message.chat.id
            )

        await message.reply_text(
            "📞 کال پایان یافت."
            if ok
            else "❌ پایان کال انجام نشد."
        )


    # ========================================================
    # کامنت کال فعال
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*کامنت کال فعال\s*$"
        )
    )
    async def comments_on(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "enable_call_comments",
            message.chat.id
        )

        await message.reply_text(
            "💬 کامنت کال فعال شد."
            if ok
            else "❌ کنترل کامنت کال هنوز به Assistant متصل نشده."
        )


    # ========================================================
    # کامنت کال غیر فعال
    # ========================================================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*کامنت کال غیر فعال\s*$"
        )
    )
    async def comments_off(
        client,
        message
    ):

        _register_activity(message)

        if not await _check_subscription(
            message
        ):
            return

        ok = await _player_method(
            "disable_call_comments",
            message.chat.id
        )

        await message.reply_text(
            "💬 کامنت کال غیر فعال شد."
            if ok
            else "❌ کنترل کامنت کال هنوز به Assistant متصل نشده."
        )


    # ========================================================
    # CALLBACK موزیک
    # ========================================================

    @bot.on_callback_query(
        filters.regex(
            r"^music_.+"
        )
    )
    async def music_callbacks(
        client,
        callback
    ):

        if not callback.message:
            return

        data = callback.data
        chat_id = callback.message.chat.id

        await callback.answer()

        if not await _check_subscription(
            callback.message,
            send_message=False
        ):

            await callback.message.reply_text(
                "🔒 اشتراک شما فعال نیست."
            )

            return


        if data == "music_pause":

            ok = await _player_method(
                "pause",
                chat_id
            )

            await callback.message.reply_text(
                "⏸️ مکث شد."
                if ok
                else "❌ مکث انجام نشد."
            )


        elif data == "music_resume":

            ok = await _player_method(
                "resume",
                chat_id
            )

            await callback.message.reply_text(
                "▶️ ادامه پیدا کرد."
                if ok
                else "❌ ادامه انجام نشد."
            )


        elif data == "music_stop":

            ok = await _player_method(
                "stop",
                chat_id
            )

            await callback.message.reply_text(
                "⏹️ اتمام شد."
                if ok
                else "❌ توقف انجام نشد."
            )


        elif data == "music_next":

            track = await _player_method(
                "next",
                chat_id
            )

            if track:

                await callback.message.reply_text(
                    "⏭️ آهنگ بعدی پخش شد.\n\n"
                    f"🎵 {_track_title(track)}\n"
                    f"👤 {_track_artist(track)}"
                )

            else:

                await callback.message.reply_text(
                    "📭 آهنگ دیگری در صف نیست."
                )


        elif data == "music_previous":

            track = await _player_method(
                "previous",
                chat_id
            )

            await callback.message.reply_text(
                "⏮️ آهنگ قبلی پخش شد."
                if track
                else "❌ آهنگ قبلی موجود نیست."
            )


        elif data == "music_forward_10":

            ok = await _player_method(
                "forward",
                chat_id,
                10
            )

            await callback.message.reply_text(
                "⏩ ۱۰ ثانیه جلو رفت."
                if ok
                else "❌ جلو بردن فعال نیست."
            )


        elif data == "music_backward_10":

            ok = await _player_method(
                "backward",
                chat_id,
                10
            )

            await callback.message.reply_text(
                "⏪ ۱۰ ثانیه عقب رفت."
                if ok
                else "❌ عقب بردن فعال نیست."
            )


        elif data == "music_forward_30":

            ok = await _player_method(
                "forward",
                chat_id,
                30
            )

            await callback.message.reply_text(
                "⏩ ۳۰ ثانیه جلو رفت."
                if ok
                else "❌ جلو بردن فعال نیست."
            )


        elif data == "music_backward_30":

            ok = await _player_method(
                "backward",
                chat_id,
                30
            )

            await callback.message.reply_text(
                "⏪ ۳۰ ثانیه عقب رفت."
                if ok
                else "❌ عقب بردن فعال نیست."
            )


        elif data == "music_volume":

            status = await _get_status(
                chat_id
            )

            current = (
                status.get("volume", 100)
                if status
                else 100
            )

            await callback.message.reply_text(
                f"🔊 صدای فعلی: {current}%\n\n"
                "برای تغییر بنویس:\n"
                "صدا 80"
            )


        elif data == "music_status":

            status = await _get_status(
                chat_id
            )

            if not status:

                await callback.message.reply_text(
                    "❌ دریافت وضعیت انجام نشد."
                )

                return

            track = status.get(
                "track"
            )

            state = (
                "⏸️ مکث"
                if status.get("paused")
                else "▶️ در حال پخش"
                if status.get("playing")
                else "⏹️ متوقف"
            )

            await callback.message.reply_text(
                "🎧 وضعیت موزیک\n\n"
                f"🎵 {_track_title(track)}\n"
                f"👤 {_track_artist(track)}\n"
                f"📡 {state}\n"
                f"🔊 {status.get('volume', 100)}%\n"
                f"📋 صف: {status.get('queue_size', 0)}\n\n"
                "🟢 ربات سایلنت همیشه آنلاین می‌باشد.",
                reply_markup=music_keyboard()
            )


    # ========================================================
    # CALLBACK منوی اصلی
    # ========================================================

    @bot.on_callback_query(
        filters.regex(
            r"^menu_.+|^main_menu$"
        )
    )
    async def menu_callbacks(
        client,
        callback
    ):

        data = callback.data

        await callback.answer()

        if data == "main_menu":

            await callback.message.edit_text(
                "🟢 ربات سایلنت همیشه آنلاین می‌باشد.\n\n"
                "🎵 منوی اصلی:",
                reply_markup=main_menu_keyboard()
            )

            return


        if data == "menu_music":

            if not await _check_subscription(
                callback.message,
                send_message=False
            ):

                await callback.message.edit_text(
                    "🔒 اشتراک شما فعال نیست.\n\n"
                    "برای استفاده از موزیک پلیر ابتدا اشتراک فعال کنید.",
                    reply_markup=main_menu_keyboard()
                )

                return

            await callback.message.edit_text(
                "🎵 کنترل موزیک\n\n"
                "برای پخش بنویس:\n"
                "پخش نام آهنگ\n\n"
                "یا روی فایل صوتی ریپلای کن و بنویس:\n"
                "پخش\n\n"
                "برای دیدن صف:\n"
                "صف",
                reply_markup=music_keyboard()
            )

            return


        if data == "menu_status":

            status = await _get_status(
                callback.message.chat.id
            )

            if not status:

                await callback.message.edit_text(
                    "❌ دریافت وضعیت انجام نشد.",
                    reply_markup=main_menu_keyboard()
                )

                return

            track = status.get(
                "track"
            )

            state = (
                "⏸️ مکث"
                if status.get("paused")
                else "▶️ در حال پخش"
                if status.get("playing")
                else "⏹️ متوقف"
            )

            await callback.message.edit_text(
                "🎧 وضعیت موزیک\n\n"
                f"🎵 {_track_title(track)}\n"
                f"👤 {_track_artist(track)}\n"
                f"📡 {state}\n"
                f"🔊 {status.get('volume', 100)}%\n"
                f"📋 صف: {status.get('queue_size', 0)}\n\n"
                "🟢 ربات سایلنت همیشه آنلاین می‌باشد.",
                reply_markup=music_keyboard()
            )

            return


        if data == "menu_id":

            user = callback.from_user

            stats = _get_user_stats(
                user.id
            )

            username = (
                f"@{user.username}"
                if user.username
                else "ندارد"
            )

            await callback.message.reply_text(
                "╭──── 👤 اطلاعات شما ────╮\n\n"
                f"📛 نام: {_user_name(user)}\n"
                f"🔗 یوزرنیم: {username}\n"
                f"🆔 آیدی عددی: `{user.id}`\n"
                f"👑 مقام: {_user_rank(user.id)}\n\n"
                "📊 آمار\n"
                f"💬 پیام: {stats['messages']}\n"
                f"🎵 پخش: {stats['plays']}\n"
                f"⏸️ مکث: {stats['pauses']}\n\n"
                "🟢 ربات سایلنت همیشه آنلاین می‌باشد."
            )

            return


        if data == "menu_stats":

            user = callback.from_user

            stats = _get_user_stats(
                user.id
            )

            await callback.message.reply_text(
                "📊 آمار فعالیت شما\n\n"
                f"💬 پیام: {stats['messages']}\n"
                f"🎵 پخش: {stats['plays']}\n"
                f"⏸️ مکث: {stats['pauses']}\n"
                f"🕐 آخرین فعالیت: "
                f"{stats['last_seen'] or 'ثبت نشده'}"
            )

            return


        if data == "menu_force":

            channel = REQUIRED_CHANNEL

            try:
                db_channel = get_required_channel()

                if db_channel:
                    channel = db_channel
            except Exception:
                pass

            if channel:

                await callback.message.reply_text(
                    "📢 عضویت اجباری\n\n"
                    f"📢 کانال موردنظر:\n{channel}"
                )

            else:

                await callback.message.reply_text(
                    "📢 عضویت اجباری\n\n"
                    "⚙️ کانال هنوز تنظیم نشده است."
                )

            return


        if data == "menu_support":

            username = SUPPORT_USERNAME

            try:
                db_support = get_support_username()

                if db_support:
                    username = db_support
            except Exception:
                pass

            if username:

                if not username.startswith("@"):
                    username = "@" + username

                await callback.message.reply_text(
                    "🛟 پشتیبانی\n\n"
                    "برای ارتباط با پشتیبانی:\n"
                    f"{username}"
                )

            else:

                await callback.message.reply_text(
                    "🛟 پشتیبانی\n\n"
                    "⚙️ آیدی پشتیبانی هنوز تنظیم نشده است."
                )

            return


    logger.info(
        "ALL TELEGRAM HANDLERS REGISTERED"
    )
