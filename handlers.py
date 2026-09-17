# ============================================================
# SILENT MUSIC PLAYER - handlers.py
# Persian Telegram Music Player
#
# امکانات:
# - پخش اسم آهنگ
# - پخش فایل با ریپلای
# - پخش لینک
# - کارت Now Playing مدرن
# - عکس پروفایل خود ربات
# - دکمه‌های متعدد کنترل موزیک
# - صف پخش
# - قبلی / بعدی
# - مکث / ادامه
# - پایان
# - کنترل صدا
# - عضویت اجباری
# - بررسی فعال بودن چت
# ============================================================

import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from player import TrackInfo
from database import (
    is_chat_active,
    get_forced_channel,
)


logger = logging.getLogger(__name__)


# ============================================================
# Global runtime instances
# ============================================================

app = None
pytgcalls_client = None
player = None
shutdown_event = None

_handlers_registered = False

_now_playing_messages = {}
_bot_profile_photo = None


# ============================================================
# Runtime
# ============================================================

def set_bot_instances(
    bot_app,
    pytgcalls,
    music_player,
    event,
):
    global app
    global pytgcalls_client
    global player
    global shutdown_event

    app = bot_app
    pytgcalls_client = pytgcalls
    player = music_player
    shutdown_event = event

    register_handlers()


# ============================================================
# Activity
# ============================================================

def _register_activity(message: Message):
    return None


# ============================================================
# Basic helpers
# ============================================================

def _track_title(track):
    return (
        getattr(track, "title", None)
        or "آهنگ بدون نام"
    )


def _track_artist(track):
    return (
        getattr(track, "performer", None)
        or getattr(track, "artist", None)
        or getattr(track, "uploader", None)
        or "ناشناخته"
    )


def _track_thumbnail(track):
    return (
        getattr(track, "thumbnail", None)
        or None
    )


def _format_duration(seconds):
    try:
        seconds = int(seconds or 0)
    except Exception:
        seconds = 0

    if seconds <= 0:
        return "00:00"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def _is_url(text):
    if not text:
        return False

    try:
        parsed = urlparse(text.strip())

        return parsed.scheme in (
            "http",
            "https",
        )

    except Exception:
        return False


def _user_display_name(user):
    if not user:
        return "کاربر"

    name = " ".join(
        x
        for x in [
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        ]
        if x
    ).strip()

    return (
        name
        or getattr(user, "username", None)
        or "کاربر"
    )


# ============================================================
# Current track compatibility
# ============================================================

def _get_current_track(chat_id):
    """
    با ساختارهای مختلف player.py سازگار است.
    """

    if player is None:
        return None

    # ساختار رایج
    try:
        current = getattr(
            player,
            "current",
            None,
        )

        if isinstance(current, dict):
            return current.get(chat_id)

    except Exception:
        pass

    # property
    try:
        current_track = getattr(
            player,
            "current_track",
            None,
        )

        if current_track:
            return current_track

    except Exception:
        pass

    # متد
    try:
        method = getattr(
            player,
            "get_current",
            None,
        )

        if method:
            return method(chat_id)

    except Exception:
        pass

    return None


# ============================================================
# Bot profile photo
# ============================================================

async def _get_bot_profile_photo(client):
    """
    عکس پروفایل فعلی خود ربات را یک‌بار دریافت می‌کند.
    """

    global _bot_profile_photo

    if _bot_profile_photo:
        return _bot_profile_photo

    try:
        me = await client.get_me()

        if not me or not me.photo:
            logger.warning(
                "Bot has no profile photo."
            )
            return None

        profile_path = await client.download_media(
            me.photo.big_file_id,
            file_name="data/bot_profile.jpg",
        )

        if profile_path:
            _bot_profile_photo = str(
                Path(profile_path).resolve()
            )

            return _bot_profile_photo

    except Exception:
        logger.exception(
            "BOT PROFILE PHOTO ERROR"
        )

    return None


# ============================================================
# Subscription / activation
# ============================================================

async def _check_subscription(message: Message) -> bool:

    if app is None:
        return False

    if message.chat is None:
        return False

    chat_id = message.chat.id

    # --------------------------------------------------------
    # Chat activation
    # --------------------------------------------------------

    if not is_chat_active(chat_id):

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💳 خرید / فعال‌سازی ربات",
                        callback_data="system:activation",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "👑 ارتباط با مالک",
                        callback_data="system:owner",
                    )
                ],
            ]
        )

        await message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "       🔒 دسترسی غیرفعال\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            "این گروه یا کانال هنوز توسط مالک فعال نشده است.\n\n"
            "برای استفاده از موزیک پلیر، ابتدا باید "
            "اشتراک این چت فعال شود.",
            reply_markup=keyboard,
        )

        return False

    # --------------------------------------------------------
    # Forced subscription
    # --------------------------------------------------------

    channel = get_forced_channel(chat_id)

    if not channel:
        return True

    if not message.from_user:
        return True

    username = (
        channel["username"]
        or ""
    ).strip().lstrip("@")

    if not username:
        return True

    try:
        member = await app.get_chat_member(
            username,
            message.from_user.id,
        )

        status = str(
            getattr(
                member,
                "status",
                "",
            )
        ).lower()

        if status in (
            "left",
            "kicked",
            "banned",
        ):

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔵 عضویت در کانال",
                            url=f"https://t.me/{username}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔄 بررسی عضویت",
                            callback_data=f"checksub:{chat_id}",
                        )
                    ],
                ]
            )

            await message.reply_text(
                "╭━━━━━━━━━━━━━━━━━━╮\n"
                "        🔐 عضویت الزامی\n"
                "╰━━━━━━━━━━━━━━━━━━╯\n\n"
                "برای استفاده از موزیک پلیر باید ابتدا "
                "در کانال مشخص‌شده عضو شوید.",
                reply_markup=keyboard,
            )

            return False

    except Exception:
        logger.exception(
            "FORCED SUBSCRIPTION CHECK ERROR"
        )

        await message.reply_text(
            "❌ بررسی عضویت انجام نشد.\n\n"
            "لطفاً مطمئن شوید ربات در کانال دسترسی لازم را دارد."
        )

        return False

    return True


# ============================================================
# Player keyboard
# ============================================================

def _player_keyboard(chat_id: int):
    """
    چیدمان کنترل شبیه پلیر موبایل.
    """

    return InlineKeyboardMarkup(
        [

            # ------------------------------------------------
            # Seek
            # ------------------------------------------------
            [
                InlineKeyboardButton(
                    "⏪ ۳۰ ثانیه",
                    callback_data=f"music:back30:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏩ ۳۰ ثانیه",
                    callback_data=f"music:forward30:{chat_id}",
                ),
            ],

            # ------------------------------------------------
            # Main controls
            # ------------------------------------------------
            [
                InlineKeyboardButton(
                    "⏮",
                    callback_data=f"music:prev:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏸ مکث",
                    callback_data=f"music:pause:{chat_id}",
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data=f"music:resume:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏭",
                    callback_data=f"music:next:{chat_id}",
                ),
            ],

            # ------------------------------------------------
            # Queue / stop
            # ------------------------------------------------
            [
                InlineKeyboardButton(
                    "📋 صف پخش",
                    callback_data=f"music:queue:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏹ پایان",
                    callback_data=f"music:stop:{chat_id}",
                ),
            ],

            # ------------------------------------------------
            # Volume
            # ------------------------------------------------
            [
                InlineKeyboardButton(
                    "🔉 صدا −",
                    callback_data=f"music:voldown:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🔊 صدا +",
                    callback_data=f"music:volup:{chat_id}",
                ),
            ],

            # ------------------------------------------------
            # Information
            # ------------------------------------------------
            [
                InlineKeyboardButton(
                    "🎵 آهنگ فعلی",
                    callback_data=f"music:current:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data=f"music:refresh:{chat_id}",
                ),
            ],
        ]
    )


# ============================================================
# Progress bar
# ============================================================

def _progress_bar(position, duration, length=18):
    """
    نوار پیشرفت شبیه موزیک پلیر.
    """

    try:
        position = max(
            0,
            int(position or 0),
        )

        duration = max(
            0,
            int(duration or 0),
        )

    except Exception:
        position = 0
        duration = 0

    if duration <= 0:
        return "━━━━━━━━━━━━━━━━━━"

    ratio = min(
        1,
        max(
            0,
            position / duration,
        ),
    )

    filled = int(
        ratio * length
    )

    empty = length - filled

    return (
        "━" * filled
        + "🔵"
        + "━" * max(
            0,
            empty - 1,
        )
    )


# ============================================================
# Now Playing text
# ============================================================

def _now_playing_text(
    track,
    requested_by=None,
    position=0,
):

    title = _track_title(track)
    artist = _track_artist(track)

    duration_seconds = int(
        getattr(
            track,
            "duration",
            0,
        )
        or 0
    )

    duration = _format_duration(
        duration_seconds
    )

    current_position = _format_duration(
        position
    )

    requester = _user_display_name(
        requested_by
    )

    bar = _progress_bar(
        position,
        duration_seconds,
    )

    return (
        "╭━━━━━━━━━━━━━━━━━━━━╮\n"
        "       🎧 𝗦𝗜𝗟𝗘𝗡𝗧 𝗣𝗟𝗔𝗬𝗘𝗥\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"

        f"🎵  {title}\n"
        f"🎤  {artist}\n\n"

        f"⏱  {current_position}  /  {duration}\n"
        f"{bar}\n\n"

        f"👤 درخواست‌کننده: {requester}\n\n"

        "🔵  در حال پخش\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


# ============================================================
# Send Now Playing
# ============================================================

async def _send_now_playing(
    message,
    track,
    requested_by=None,
):

    if track is None:
        return None

    position = 0

    try:
        if player:
            get_position = getattr(
                player,
                "get_position",
                None,
            )

            if get_position:
                result = get_position(
                    message.chat.id
                )

                if hasattr(
                    result,
                    "__await__",
                ):
                    result = await result

                position = int(
                    result or 0
                )

    except Exception:
        position = 0

    text = _now_playing_text(
        track,
        requested_by,
        position,
    )

    keyboard = _player_keyboard(
        message.chat.id
    )

    # --------------------------------------------------------
    # اول عکس پروفایل ربات
    # --------------------------------------------------------

    profile_photo = await _get_bot_profile_photo(
        app
    )

    # اگر ربات عکس داشته باشد،
    # همان عکس بالای Now Playing قرار می‌گیرد.
    if profile_photo:

        try:
            sent = await message.reply_photo(
                profile_photo,
                caption=text,
                reply_markup=keyboard,
            )

            _now_playing_messages[
                message.chat.id
            ] = sent.id

            return sent

        except Exception:
            logger.exception(
                "BOT PROFILE PHOTO SEND ERROR"
            )

    # --------------------------------------------------------
    # اگر عکس پروفایل موجود نبود،
    # thumbnail آهنگ امتحان می‌شود.
    # --------------------------------------------------------

    thumbnail = _track_thumbnail(
        track
    )

    if thumbnail:

        try:
            sent = await message.reply_photo(
                thumbnail,
                caption=text,
                reply_markup=keyboard,
            )

            _now_playing_messages[
                message.chat.id
            ] = sent.id

            return sent

        except Exception:
            logger.exception(
                "TRACK THUMBNAIL SEND ERROR"
            )

    # --------------------------------------------------------
    # fallback
    # --------------------------------------------------------

    sent = await message.reply_text(
        text,
        reply_markup=keyboard,
    )

    _now_playing_messages[
        message.chat.id
    ] = sent.id

    return sent


# ============================================================
# Reply media
# ============================================================

def _get_reply_media(message):

    reply = message.reply_to_message

    if not reply:
        return None

    if reply.audio:
        return reply.audio

    if reply.voice:
        return reply.voice

    if reply.video:
        return reply.video

    if reply.document:

        mime = (
            getattr(
                reply.document,
                "mime_type",
                None,
            )
            or ""
        ).lower()

        if (
            mime.startswith("audio/")
            or mime.startswith("video/")
        ):
            return reply.document

    return None


def _get_media_title(media):

    title = getattr(
        media,
        "title",
        None,
    )

    if title:
        return title

    file_name = getattr(
        media,
        "file_name",
        None,
    )

    if file_name:
        return Path(
            file_name
        ).stem

    return "آهنگ ریپلای‌شده"


def _get_media_artist(media):

    return (
        getattr(
            media,
            "performer",
            None,
        )
        or "ناشناخته"
    )


# ============================================================
# Play replied Telegram media
# ============================================================

async def _play_local_reply_file(
    client,
    message,
    media,
):

    if player is None:
        await message.reply_text(
            "❌ پخش‌کننده آماده نیست."
        )
        return

    reply = message.reply_to_message

    if reply is None:
        await message.reply_text(
            "❌ پیام ریپلای‌شده پیدا نشد."
        )
        return

    try:

        downloads_dir = Path(
            getattr(
                player.downloader,
                "downloads_dir",
                "downloads",
            )
        )

        downloads_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        original_name = (
            getattr(
                media,
                "file_name",
                None,
            )
            or getattr(
                media,
                "title",
                None,
            )
            or f"reply_{reply.id}.audio"
        )

        safe_name = Path(
            original_name
        ).name

        filepath = (
            downloads_dir
            / f"reply_{reply.id}_{message.id}_{safe_name}"
        )

        status_message = await message.reply_text(
            "⏳ فایل دریافت شد.\n"
            "⬇️ در حال آماده‌سازی موزیک..."
        )

        downloaded = await client.download_media(
            reply,
            file_name=str(filepath),
        )

        if not downloaded:

            await status_message.edit_text(
                "❌ دانلود فایل انجام نشد."
            )

            return

        filepath = Path(
            downloaded
        ).resolve()

        if not filepath.exists():

            await status_message.edit_text(
                "❌ فایل دانلودشده پیدا نشد."
            )

            return

        if filepath.stat().st_size < 1024:

            await status_message.edit_text(
                "❌ فایل معتبر نیست."
            )

            return

        title = _get_media_title(
            media
        )

        artist = _get_media_artist(
            media
        )

        track = TrackInfo(
            title=title,
            duration=int(
                getattr(
                    media,
                    "duration",
                    0,
                )
                or 0
            ),
            url="",
            webpage_url="",
            thumbnail="",
            uploader=artist,
            performer=artist,
            artist=artist,
            filepath=str(filepath),
            requested_by=(
                message.from_user.id
                if message.from_user
                else 0
            ),
            requested_name=(
                _user_display_name(
                    message.from_user
                )
                if message.from_user
                else "کاربر"
            ),
        )

        await status_message.edit_text(
            "🎧 فایل آماده شد.\n"
            "📞 در حال اتصال به Voice Chat..."
        )

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:

            await status_message.edit_text(
                "❌ پخش شروع نشد.\n\n"
                "ویس‌چت گروه را فعال کن و دسترسی "
                "اکانت دستیار را بررسی کن."
            )

            return

        try:
            await status_message.delete()
        except Exception:
            pass

        await _send_now_playing(
            message,
            track,
            message.from_user,
        )

    except Exception as e:

        logger.exception(
            "REPLY MEDIA PLAY ERROR"
        )

        await message.reply_text(
            "❌ خطا در پخش فایل:\n"
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# Download/search
# ============================================================

async def _download_track(query):

    if player is None:
        return None

    downloader = player.downloader

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    if _is_url(query):

        track = TrackInfo(
            title="در حال دریافت آهنگ",
            duration=0,
            url=query,
            webpage_url=query,
            thumbnail="",
            uploader="ناشناخته",
            performer="ناشناخته",
            artist="ناشناخته",
        )

        filepath = await downloader.download(
            track
        )

        if not filepath:
            return None

        track.filepath = str(
            Path(filepath).resolve()
        )

        return track

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    results = await downloader.search(
        query,
        1,
    )

    if not results:
        return None

    track = results[0]

    filepath = await downloader.download(
        track
    )

    if not filepath:
        return None

    track.filepath = str(
        Path(filepath).resolve()
    )

    return track


# ============================================================
# Search and play
# ============================================================

async def _search_and_play(
    message,
    query,
):

    if player is None:
        await message.reply_text(
            "❌ پخش‌کننده آماده نیست."
        )
        return

    query = (
        query or ""
    ).strip()

    if not query:

        await message.reply_text(
            "❌ اسم آهنگ را بنویس.\n\n"
            "مثال:\n"
            "پخش اسم آهنگ"
        )

        return

    try:

        if _is_url(query):

            status = await message.reply_text(
                "🔗 لینک دریافت شد.\n"
                "⬇️ در حال آماده‌سازی..."
            )

        else:

            status = await message.reply_text(
                "╭━━━━━━━━━━━━━━━━━━╮\n"
                "       🔎 جست‌وجوی موزیک\n"
                "╰━━━━━━━━━━━━━━━━━━╯\n\n"
                f"🎵 {query}\n\n"
                "⏳ در حال پیدا کردن آهنگ..."
            )

        track = await _download_track(
            query
        )

        if track is None:

            await status.edit_text(
                "❌ آهنگ پیدا یا دانلود نشد.\n\n"
                "اسم آهنگ و خواننده را دقیق‌تر بنویس."
            )

            return

        filepath = getattr(
            track,
            "filepath",
            None,
        )

        if not filepath:

            await status.edit_text(
                "❌ فایل آهنگ ساخته نشد."
            )

            return

        filepath = Path(
            filepath
        ).resolve()

        if not filepath.exists():

            await status.edit_text(
                "❌ فایل دانلودشده پیدا نشد."
            )

            return

        if filepath.stat().st_size < 1024:

            await status.edit_text(
                "❌ فایل دانلودشده معتبر نیست."
            )

            return

        track.filepath = str(
            filepath
        )

        track.requested_by = (
            message.from_user.id
            if message.from_user
            else 0
        )

        track.requested_name = (
            _user_display_name(
                message.from_user
            )
            if message.from_user
            else "کاربر"
        )

        await status.edit_text(
            "🎧 آهنگ آماده شد.\n"
            "📞 در حال اتصال دستیار به Voice Chat..."
        )

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:

            await status.edit_text(
                "❌ آهنگ آماده شد اما پخش شروع نشد.\n\n"
                "ویس‌چت را فعال کن و دسترسی اکانت دستیار "
                "را بررسی کن."
            )

            return

        try:
            await status.delete()
        except Exception:
            pass

        await _send_now_playing(
            message,
            track,
            message.from_user,
        )

    except Exception as e:

        logger.exception(
            "SEARCH PLAY ERROR"
        )

        await message.reply_text(
            "❌ خطا هنگام آماده‌سازی آهنگ:\n"
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# PLAY command
# ============================================================

def _register_play_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*پخش(?:\s+(.+))?\s*$"
        )
    )
    async def play_handler(
        client,
        message,
    ):

        _register_activity(
            message
        )

        if not await _check_subscription(
            message
        ):
            return

        text = message.text or ""

        match = re.match(
            r"^\s*پخش(?:\s+(.+))?\s*$",
            text,
        )

        query = ""

        if match:

            query = (
                match.group(1)
                or ""
            ).strip()

        # ----------------------------------------------------
        # Reply media first
        # ----------------------------------------------------

        media = _get_reply_media(
            message
        )

        if media and not query:

            await _play_local_reply_file(
                client,
                message,
                media,
            )

            return

        # ----------------------------------------------------
        # Name / URL
        # ----------------------------------------------------

        if query:

            await _search_and_play(
                message,
                query,
            )

            return

        # ----------------------------------------------------
        # URL inside replied message
        # ----------------------------------------------------

        reply = message.reply_to_message

        if reply:

            reply_text = (
                reply.text
                or reply.caption
                or ""
            )

            urls = re.findall(
                r"https?://[^\s]+",
                reply_text,
            )

            if urls:

                await _search_and_play(
                    message,
                    urls[0],
                )

                return

        await message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "        🎵 راهنمای پخش\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            "🎧 پخش نام آهنگ\n"
            "مثال: پخش آهنگ موردنظر\n\n"
            "📁 پخش فایل تلگرام\n"
            "روی فایل ریپلای کن و «پخش» بزن.\n\n"
            "🔗 پخش لینک\n"
            "روی لینک ریپلای کن و «پخش» بزن."
        )


# ============================================================
# Pause
# ============================================================

def _register_pause_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(مکث|pause)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def pause_handler(
        client,
        message,
    ):

        if not await _check_subscription(
            message
        ):
            return

        if player is None:
            return

        ok = await player.pause(
            message.chat.id
        )

        await message.reply_text(
            "⏸ پخش مکث شد."
            if ok
            else
            "❌ آهنگی برای مکث وجود ندارد."
        )


# ============================================================
# Resume
# ============================================================

def _register_resume_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(ادامه|resume)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def resume_handler(
        client,
        message,
    ):

        if not await _check_subscription(
            message
        ):
            return

        if player is None:
            return

        ok = await player.resume(
            message.chat.id
        )

        await message.reply_text(
            "▶️ پخش ادامه پیدا کرد."
            if ok
            else
            "❌ امکان ادامه پخش وجود ندارد."
        )


# ============================================================
# Stop
# ============================================================

def _register_stop_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(اتمام|توقف|پایان|stop)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def stop_handler(
        client,
        message,
    ):

        if not await _check_subscription(
            message
        ):
            return

        if player is None:
            return

        ok = await player.stop(
            message.chat.id
        )

        await message.reply_text(
            "⏹ پخش پایان یافت."
            if ok
            else
            "❌ چیزی برای توقف وجود ندارد."
        )


# ============================================================
# Current
# ============================================================

def _register_current_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(الان|آهنگ فعلی|current)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def current_handler(
        client,
        message,
    ):

        if not await _check_subscription(
            message
        ):
            return

        track = _get_current_track(
            message.chat.id
        )

        if not track:

            await message.reply_text(
                "🎵 در حال حاضر آهنگی در حال پخش نیست."
            )

            return

        await _send_now_playing(
            message,
            track,
            message.from_user,
        )


# ============================================================
# Status
# ============================================================

def _register_status_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(وضعیت|status)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def status_handler(
        client,
        message,
    ):

        if player is None:
            return

        try:

            status = player.get_status()

            if hasattr(
                status,
                "__await__",
            ):
                status = await status

        except Exception:

            status = {}

        available = (
            "فعال"
            if status.get(
                "available",
                False,
            )
            else
            "غیرفعال"
        )

        playing = (
            "در حال پخش"
            if status.get(
                "is_playing",
                False,
            )
            else
            "متوقف"
        )

        current = (
            status.get(
                "current_track"
            )
            or "هیچ آهنگی"
        )

        await message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "        📊 وضعیت پلیر\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"
            f"🎧 Voice Chat: {available}\n"
            f"▶️ وضعیت: {playing}\n"
            f"🎵 آهنگ: {current}\n"
            f"🔊 صدا: {status.get('volume', 100)}"
        )


# ============================================================
# Help
# ============================================================

def _register_help_handler():

    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(راهنما|کمک|help)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def help_handler(
        client,
        message,
    ):

        await message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "       🎧 𝗦𝗜𝗟𝗘𝗡𝗧 𝗣𝗟𝗔𝗬𝗘𝗥\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"

            "🎵 پخش نام آهنگ\n"
            "📁 ریپلای فایل + پخش\n"
            "🔗 پخش لینک\n\n"

            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏭ بعدی\n"
            "⏮ قبلی\n"
            "⏹ اتمام\n"
            "📋 صف\n"
            "🔊 کنترل صدا\n\n"

            "🎧 الان\n"
            "📊 وضعیت"
        )


# ============================================================
# START
# ============================================================

def _register_start_handler():

    @app.on_message(
        filters.command(
            "start",
            prefixes="/",
        )
    )
    async def start_handler(
        client,
        message,
    ):

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎵 راهنمای موزیک",
                        callback_data="start:help",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "➕ افزودن به گروه",
                        url=(
                            "https://t.me/"
                            "Silent_musicplayerbot"
                            "?startgroup=true"
                        ),
                    ),
                ],
            ]
        )

        await message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "       🎧 𝗦𝗜𝗟𝗘𝗡𝗧 𝗣𝗟𝗔𝗬𝗘𝗥\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"

            "سلام 👋\n\n"
            "🎶 ربات سایلنت همیشه آنلاین می‌باشد.\n\n"

            "برای پخش آهنگ در گروه:\n"
            "🎵 پخش نام آهنگ\n\n"

            "برای فایل تلگرام:\n"
            "📁 روی فایل ریپلای کن و «پخش» بزن.",
            reply_markup=keyboard,
        )


# ============================================================
# Music callbacks
# ============================================================

def _register_callback_handler():

    @app.on_callback_query(
        filters.regex(
            r"^music:"
        )
    )
    async def music_callback(
        client,
        callback: CallbackQuery,
    ):

        if player is None:

            await callback.answer(
                "پخش‌کننده آماده نیست.",
                show_alert=True,
            )

            return

        data = (
            callback.data
            or ""
        ).split(":")

        if len(data) != 3:

            await callback.answer(
                "دکمه نامعتبر است.",
                show_alert=True,
            )

            return

        action = data[1]

        try:

            chat_id = int(
                data[2]
            )

        except ValueError:

            await callback.answer(
                "شناسه چت نامعتبر است.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # امنیت: دکمه باید متعلق به همان چت باشد
        # ----------------------------------------------------

        if not callback.message:
            await callback.answer()
            return

        if callback.message.chat.id != chat_id:

            await callback.answer(
                "❌ این دکمه مربوط به چت دیگری است.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # Pause
        # ----------------------------------------------------

        if action == "pause":

            ok = await player.pause(
                chat_id
            )

            await callback.answer(
                "⏸ مکث شد."
                if ok
                else
                "❌ امکان مکث نیست."
            )

            return

        # ----------------------------------------------------
        # Resume
        # ----------------------------------------------------

        if action == "resume":

            ok = await player.resume(
                chat_id
            )

            await callback.answer(
                "▶️ ادامه پخش."
                if ok
                else
                "❌ امکان ادامه وجود ندارد."
            )

            return

        # ----------------------------------------------------
        # Stop
        # ----------------------------------------------------

        if action == "stop":

            ok = await player.stop(
                chat_id
            )

            await callback.answer(
                "⏹ پخش پایان یافت."
                if ok
                else
                "❌ چیزی برای توقف نیست."
            )

            return

        # ----------------------------------------------------
        # Next
        # ----------------------------------------------------

        if action == "next":

            method = getattr(
                player,
                "next",
                None,
            )

            if method is None:

                await callback.answer(
                    "⏭ قابلیت بعدی متصل نیست.",
                    show_alert=True,
                )

                return

            ok = await method(
                chat_id
            )

            await callback.answer(
                "⏭ آهنگ بعدی."
                if ok
                else
                "❌ آهنگ بعدی وجود ندارد."
            )

            return

        # ----------------------------------------------------
        # Previous
        # ----------------------------------------------------

        if action == "prev":

            method = getattr(
                player,
                "previous",
                None,
            )

            if method is None:

                await callback.answer(
                    "⏮ قابلیت قبلی متصل نیست.",
                    show_alert=True,
                )

                return

            ok = await method(
                chat_id
            )

            await callback.answer(
                "⏮ آهنگ قبلی."
                if ok
                else
                "❌ آهنگ قبلی وجود ندارد."
            )

            return

        # ----------------------------------------------------
        # Queue
        # ----------------------------------------------------

        if action == "queue":

            queue = None

            try:

                queues = getattr(
                    player,
                    "queues",
                    None,
                )

                if isinstance(
                    queues,
                    dict,
                ):
                    queue = queues.get(
                        chat_id,
                        [],
                    )

                elif queues:
                    queue = queues

            except Exception:
                queue = []

            if not queue:

                await callback.answer(
                    "📋 صف پخش خالی است.",
                    show_alert=True,
                )

                return

            lines = [
                "╭━━━━━━━━━━━━━━━━━━╮",
                "          📋 صف پخش",
                "╰━━━━━━━━━━━━━━━━━━╯",
                "",
            ]

            for index, item in enumerate(
                list(queue)[:30],
                start=1,
            ):

                lines.append(
                    f"{index} • {_track_title(item)}"
                )

            await callback.message.reply_text(
                "\n".join(lines)
            )

            await callback.answer()

            return

        # ----------------------------------------------------
        # Current
        # ----------------------------------------------------

        if action == "current":

            track = _get_current_track(
                chat_id
            )

            if not track:

                await callback.answer(
                    "🎵 آهنگی در حال پخش نیست.",
                    show_alert=True,
                )

                return

            await _send_now_playing(
                callback.message,
                track,
                callback.from_user,
            )

            await callback.answer()

            return

        # ----------------------------------------------------
        # Refresh
        # ----------------------------------------------------

        if action == "refresh":

            track = _get_current_track(
                chat_id
            )

            if not track:

                await callback.answer(
                    "🎵 آهنگی در حال پخش نیست.",
                    show_alert=True,
                )

                return

            try:

                await callback.message.edit_caption(
                    caption=_now_playing_text(
                        track,
                        callback.from_user,
                        0,
                    ),
                    reply_markup=_player_keyboard(
                        chat_id
                    ),
                )

            except Exception:

                try:

                    await callback.message.edit_text(
                        _now_playing_text(
                            track,
                            callback.from_user,
                            0,
                        ),
                        reply_markup=_player_keyboard(
                            chat_id
                        ),
                    )

                except Exception:
                    pass

            await callback.answer(
                "🔄 بروزرسانی شد."
            )

            return

        # ----------------------------------------------------
        # Volume up
        # ----------------------------------------------------

        if action == "volup":

            method = getattr(
                player,
                "set_volume",
                None,
            )

            if method is None:

                await callback.answer(
                    "کنترل صدا متصل نیست.",
                    show_alert=True,
                )

                return

            try:

                status = player.get_status()

                if hasattr(
                    status,
                    "__await__",
                ):
                    status = await status

            except Exception:
                status = {}

            current = int(
                status.get(
                    "volume",
                    100,
                )
                or 100
            )

            volume = min(
                200,
                current + 10,
            )

            try:

                ok = await method(
                    chat_id,
                    volume,
                )

            except TypeError:

                ok = await method(
                    chat_id,
                    volume,
                )

            await callback.answer(
                f"🔊 صدا: {volume}"
                if ok
                else
                "❌ تغییر صدا انجام نشد."
            )

            return

        # ----------------------------------------------------
        # Volume down
        # ----------------------------------------------------

        if action == "voldown":

            method = getattr(
                player,
                "set_volume",
                None,
            )

            if method is None:

                await callback.answer(
                    "کنترل صدا متصل نیست.",
                    show_alert=True,
                )

                return

            try:

                status = player.get_status()

                if hasattr(
                    status,
                    "__await__",
                ):
                    status = await status

            except Exception:
                status = {}

            current = int(
                status.get(
                    "volume",
                    100,
                )
                or 100
            )

            volume = max(
                0,
                current - 10,
            )

            try:

                ok = await method(
                    chat_id,
                    volume,
                )

            except TypeError:

                ok = await method(
                    chat_id,
                    volume,
                )

            await callback.answer(
                f"🔉 صدا: {volume}"
                if ok
                else
                "❌ تغییر صدا انجام نشد."
            )

            return

        # ----------------------------------------------------
        # Seek
        #
        # player.py فعلی هنوز seek واقعی ندارد.
        # دکمه‌ها فعلاً امن هستند و پیام مناسب می‌دهند.
        # ----------------------------------------------------

        if action == "back30":

            method = getattr(
                player,
                "seek",
                None,
            )

            if method:

                try:

                    position = player.get_position(
                        chat_id
                    )

                    if hasattr(
                        position,
                        "__await__",
                    ):
                        position = await position

                    new_position = max(
                        0,
                        int(position or 0) - 30,
                    )

                    ok = await method(
                        chat_id,
                        new_position,
                    )

                    await callback.answer(
                        "⏪ ۳۰ ثانیه عقب رفت."
                        if ok
                        else
                        "❌ جابه‌جایی انجام نشد."
                    )

                    return

                except Exception:
                    pass

            await callback.answer(
                "⏪ کنترل ۳۰ ثانیه هنوز به موتور پخش متصل نشده.",
                show_alert=True,
            )

            return

        if action == "forward30":

            method = getattr(
                player,
                "seek",
                None,
            )

            if method:

                try:

                    position = player.get_position(
                        chat_id
                    )

                    if hasattr(
                        position,
                        "__await__",
                    ):
                        position = await position

                    track = _get_current_track(
                        chat_id
                    )

                    duration = int(
                        getattr(
                            track,
                            "duration",
                            0,
                        )
                        or 0
                    )

                    new_position = int(
                        position or 0
                    ) + 30

                    if duration > 0:
                        new_position = min(
                            duration,
                            new_position,
                        )

                    ok = await method(
                        chat_id,
                        new_position,
                    )

                    await callback.answer(
                        "⏩ ۳۰ ثانیه جلو رفت."
                        if ok
                        else
                        "❌ جابه‌جایی انجام نشد."
                    )

                    return

                except Exception:
                    pass

            await callback.answer(
                "⏩ کنترل ۳۰ ثانیه هنوز به موتور پخش متصل نشده.",
                show_alert=True,
            )

            return

        await callback.answer(
            "دستور ناشناخته.",
            show_alert=True,
        )


# ============================================================
# Forced subscription callback
# ============================================================

def _register_subscription_callback():

    @app.on_callback_query(
        filters.regex(
            r"^checksub:"
        )
    )
    async def subscription_callback(
        client,
        callback: CallbackQuery,
    ):

        try:

            chat_id = int(
                callback.data.split(":")[1]
            )

        except Exception:

            await callback.answer(
                "خطا.",
                show_alert=True,
            )

            return

        channel = get_forced_channel(
            chat_id
        )

        if not channel:

            await callback.answer(
                "عضویت اجباری تنظیم نشده است.",
                show_alert=True,
            )

            return

        try:

            member = await client.get_chat_member(
                channel["username"],
                callback.from_user.id,
            )

            status = str(
                getattr(
                    member,
                    "status",
                    "",
                )
            ).lower()

            if status not in (
                "left",
                "kicked",
                "banned",
            ):

                await callback.answer(
                    "✅ عضویت شما تأیید شد.",
                    show_alert=True,
                )

            else:

                await callback.answer(
                    "❌ هنوز عضو کانال نیستید.",
                    show_alert=True,
                )

        except Exception:

            logger.exception(
                "SUBSCRIPTION CALLBACK ERROR"
            )

            await callback.answer(
                "❌ بررسی عضویت ناموفق بود.",
                show_alert=True,
            )


# ============================================================
# Start callback
# ============================================================

def _register_start_callback():

    @app.on_callback_query(
        filters.regex(
            r"^start:help$"
        )
    )
    async def start_help_callback(
        client,
        callback: CallbackQuery,
    ):

        await callback.message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━╮\n"
            "       🎧 راهنمای سایلنت\n"
            "╰━━━━━━━━━━━━━━━━━━╯\n\n"

            "🎵 پخش آهنگ:\n"
            "پخش نام آهنگ\n\n"

            "📁 فایل تلگرام:\n"
            "روی فایل ریپلای کن و بنویس «پخش»\n\n"

            "🔗 لینک:\n"
            "روی لینک ریپلای کن و «پخش» بزن.\n\n"

            "🎛 کنترل‌ها از طریق دکمه‌های زیر کارت آهنگ انجام می‌شوند."
        )

        await callback.answer()


# ============================================================
# System callbacks
# ============================================================

def _register_system_callbacks():

    @app.on_callback_query(
        filters.regex(
            r"^system:"
        )
    )
    async def system_callback(
        client,
        callback: CallbackQuery,
    ):

        action = (
            callback.data.split(":")[1]
            if ":" in callback.data
            else ""
        )

        if action == "activation":

            await callback.answer(
                "💳 فعال‌سازی چت توسط مالک انجام می‌شود.",
                show_alert=True,
            )

            return

        if action == "owner":

            await callback.answer(
                "👑 برای ارتباط با مالک از بخش پشتیبانی ربات استفاده کنید.",
                show_alert=True,
            )

            return

        await callback.answer()


# ============================================================
# Register all handlers
# ============================================================

def register_handlers():

    global _handlers_registered

    if _handlers_registered:
        return

    if app is None:
        raise RuntimeError(
            "Bot app has not been initialized"
        )

    _register_start_handler()

    _register_help_handler()

    _register_play_handler()

    _register_pause_handler()

    _register_resume_handler()

    _register_stop_handler()

    _register_current_handler()

    _register_status_handler()

    _register_callback_handler()

    _register_subscription_callback()

    _register_start_callback()

    _register_system_callbacks()

    _handlers_registered = True

    logger.info(
        "✅ SILENT Persian music handlers registered successfully"
    )
