# ============================================================
# Telegram Persian Music Bot - handlers.py
# نسخه یکپارچه:
# - پخش اسم آهنگ
# - پخش ریپلای
# - لینک
# - دکمه‌های کنترل
# - عضویت اجباری
# - بررسی شارژ
# - ظاهر مدرن مشکی/سفید
# ============================================================

import logging
import re
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
# Global instances
# ============================================================

app = None
pytgcalls_client = None
player = None
shutdown_event = None

_handlers_registered = False

# پیام Now Playing هر چت
_now_playing_messages = {}


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


def _register_activity(message: Message):
    return None


# ============================================================
# Access control
# ============================================================

async def _check_subscription(message: Message) -> bool:
    """
    قبل از هر نوع پخش:
    1. شارژ گروه/کانال بررسی می‌شود.
    2. عضویت اجباری بررسی می‌شود.

    اگر هیچ‌کدام تنظیم نشده باشند، پخش طبق وضعیت شارژ انجام می‌شود.
    """

    chat_id = message.chat.id

    # --------------------------------------------------------
    # شارژ
    # --------------------------------------------------------

    if not is_chat_active(chat_id):
        await message.reply_text(
            "╭───────────────╮\n"
            "      ⛔ دسترسی غیرفعال\n"
            "╰───────────────╯\n\n"
            "این گروه/کانال هنوز فعال نشده است.\n"
            "برای استفاده از موزیک پلیر، ابتدا باید شارژ شود.\n\n"
            "مدت‌های قابل فعال‌سازی:\n"
            "• ۳۰ روز\n"
            "• ۶۰ روز\n"
            "• ۹۰ روز"
        )
        return False

    # --------------------------------------------------------
    # عضویت اجباری
    # --------------------------------------------------------

    channel = get_forced_channel(chat_id)

    if channel:
        username = channel["username"]

        try:
            member = await app.get_chat_member(
                username,
                message.from_user.id,
            )

            if member.status in (
                "left",
                "kicked",
            ):
                keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📢 عضویت در کانال",
                                url=f"https://t.me/{username}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "✅ بررسی عضویت",
                                callback_data=f"checksub:{chat_id}",
                            )
                        ],
                    ]
                )

                await message.reply_text(
                    "╭───────────────╮\n"
                    "      🔒 عضویت الزامی\n"
                    "╰───────────────╯\n\n"
                    "برای استفاده از موزیک پلیر ابتدا باید "
                    "در کانال مشخص‌شده عضو شوید.",
                    reply_markup=keyboard,
                )
                return False

        except Exception:
            logger.exception(
                "FORCED SUBSCRIPTION CHECK ERROR"
            )

            await message.reply_text(
                "❌ بررسی عضویت انجام نشد.\n"
                "مطمئن شو ربات در کانال دسترسی لازم را دارد."
            )
            return False

    return True


# ============================================================
# Track helpers
# ============================================================

def _track_title(track):
    return (
        getattr(track, "title", None)
        or "آهنگ بدون نام"
    )


def _track_artist(track):
    return (
        getattr(track, "uploader", None)
        or getattr(track, "performer", None)
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
        return "نامشخص"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining = seconds % 60

    if hours:
        return f"{hours}:{minutes:02d}:{remaining:02d}"

    return f"{minutes}:{remaining:02d}"


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
        x for x in [
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        ]
        if x
    ).strip()

    return name or getattr(
        user,
        "username",
        None,
    ) or "کاربر"


# ============================================================
# Modern player keyboard
# ============================================================

def _player_keyboard(chat_id: int):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏮ قبلی",
                    callback_data=f"music:prev:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏸ مکث",
                    callback_data=f"music:pause:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏭ بعدی",
                    callback_data=f"music:next:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏪ ۳۰",
                    callback_data=f"music:back30:{chat_id}",
                ),
                InlineKeyboardButton(
                    "📋 صف",
                    callback_data=f"music:queue:{chat_id}",
                ),
                InlineKeyboardButton(
                    "۳۰ ⏩",
                    callback_data=f"music:forward30:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔊 صدا +",
                    callback_data=f"music:volup:{chat_id}",
                ),
                InlineKeyboardButton(
                    "🔉 صدا −",
                    callback_data=f"music:voldown:{chat_id}",
                ),
                InlineKeyboardButton(
                    "⏹ پایان",
                    callback_data=f"music:stop:{chat_id}",
                ),
            ],
        ]
    )


# ============================================================
# Modern Now Playing
# ============================================================

def _now_playing_text(track, requested_by=None):
    title = _track_title(track)
    artist = _track_artist(track)
    duration = _format_duration(
        getattr(track, "duration", 0)
    )

    requester = _user_display_name(
        requested_by
    )

    return (
        "╭───────────────╮\n"
        "       🎧 𝗦𝗜𝗟𝗘𝗡𝗧 𝗣𝗟𝗔𝗬𝗘𝗥\n"
        "╰───────────────╯\n\n"
        f"♫ 𝗧𝗿𝗮𝗰𝗸 : {title}\n"
        f"♬ 𝗔𝗿𝘁𝗶𝘀𝘁 : {artist}\n"
        f"⏱ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 : {duration}\n"
        f"👤 𝗥𝗲𝗾𝘂𝗲𝘀𝘁 : {requester}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "● 𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚\n"
        "━━━━━━━━━━━━━━━━━━"
    )


async def _send_now_playing(
    message,
    track,
    requested_by=None,
):
    text = _now_playing_text(
        track,
        requested_by,
    )

    keyboard = _player_keyboard(
        message.chat.id
    )

    thumbnail = _track_thumbnail(track)

    try:
        if thumbnail:
            sent = await message.reply_photo(
                thumbnail,
                caption=text,
                reply_markup=keyboard,
            )
        else:
            sent = await message.reply_text(
                text,
                reply_markup=keyboard,
            )

        _now_playing_messages[
            message.chat.id
        ] = sent.id

        return sent

    except Exception:
        logger.exception(
            "NOW PLAYING MESSAGE ERROR"
        )

        return await message.reply_text(
            text,
            reply_markup=keyboard,
        )


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

    if reply.document:
        mime = (
            getattr(
                reply.document,
                "mime_type",
                None,
            )
            or ""
        )

        if (
            mime.startswith("audio/")
            or mime.startswith("video/")
        ):
            return reply.document

    if reply.video:
        return reply.video

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
        return Path(file_name).stem

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


async def _play_local_reply_file(
    client,
    message,
    media,
):
    """
    مسیر قبلی ریپلای عمداً حفظ شده است:
    Telegram file -> download -> TrackInfo -> player.play()
    """

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

        await message.reply_text(
            "⏳ فایل ریپلای‌شده در حال آماده‌سازی است..."
        )

        downloaded = await client.download_media(
            reply,
            file_name=str(filepath),
        )

        if not downloaded:
            await message.reply_text(
                "❌ دانلود فایل انجام نشد."
            )
            return

        filepath = Path(
            downloaded
        ).resolve()

        if not filepath.exists():
            await message.reply_text(
                "❌ فایل دانلودشده پیدا نشد."
            )
            return

        if filepath.stat().st_size < 1024:
            await message.reply_text(
                "❌ فایل صوتی معتبر نیست."
            )
            return

        title = _get_media_title(media)
        artist = _get_media_artist(media)

        # TrackInfo واقعی player.py
        # باید با فیلدهای dataclass هماهنگ باشد.
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
            filepath=str(filepath),
        )

        await message.reply_text(
            "▶️ فایل آماده شد؛ دستیار در حال شروع پخش است..."
        )

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ فایل دانلود شد ولی پخش نشد.\n\n"
                "ویس‌چت را فعال کن و مطمئن شو دستیار "
                "دسترسی لازم برای مدیریت Voice Chat دارد."
            )
            return

        await _send_now_playing(
            message,
            track,
            message.from_user,
        )

    except Exception as e:
        logger.exception(
            "REPLY AUDIO PLAY ERROR"
        )

        await message.reply_text(
            "❌ خطا در پخش فایل ریپلای‌شده:\n"
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# Search + download
# ============================================================

async def _download_track(query):
    if player is None:
        return None

    downloader = player.downloader

    if _is_url(query):
        track = TrackInfo(
            title="در حال دریافت آهنگ",
            duration=0,
            url=query,
            webpage_url=query,
            thumbnail="",
            uploader="ناشناخته",
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


async def _search_and_play(
    message,
    query,
):
    """
    مسیر اسم آهنگ و لینک.
    این مسیر و مسیر ریپلای در نهایت هر دو
    به player.play() می‌رسند.
    """

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
            "پخش مهیار"
        )
        return

    try:
        if _is_url(query):
            await message.reply_text(
                "🔗 لینک دریافت شد.\n"
                "⬇️ در حال آماده‌سازی..."
            )
        else:
            await message.reply_text(
                "╭───────────────╮\n"
                "       🔎 جست‌وجوی موزیک\n"
                "╰───────────────╯\n\n"
                f"🎵 {query}\n\n"
                "⏳ در حال پیدا کردن و آماده‌سازی..."
            )

        track = await _download_track(
            query
        )

        if track is None:
            await message.reply_text(
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
            await message.reply_text(
                "❌ فایل آهنگ ساخته نشد."
            )
            return

        filepath = Path(
            filepath
        ).resolve()

        if not filepath.exists():
            await message.reply_text(
                "❌ فایل دانلودشده روی سرور پیدا نشد."
            )
            return

        if filepath.stat().st_size < 1024:
            await message.reply_text(
                "❌ فایل دانلودشده معتبر نیست."
            )
            return

        track.filepath = str(
            filepath
        )

        await message.reply_text(
            "🎧 آهنگ آماده شد.\n"
            "📞 در حال اتصال دستیار به Voice Chat..."
        )

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ آهنگ آماده شد اما پخش شروع نشد.\n\n"
                "ویس‌چت گروه را فعال کن و دسترسی دستیار "
                "را بررسی کن."
            )
            return

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
# Play command
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
        _register_activity(message)

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

        # ====================================================
        # اول ریپلای
        # ====================================================

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

        # ====================================================
        # اسم آهنگ / لینک
        # ====================================================

        if query:
            await _search_and_play(
                message,
                query,
            )
            return

        # ====================================================
        # لینک داخل پیام ریپلای
        # ====================================================

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
            "╭───────────────╮\n"
            "       🎵 راهنمای پخش\n"
            "╰───────────────╯\n\n"
            "• پخش نام آهنگ\n"
            "  مثال: پخش مهیار\n\n"
            "• روی فایل آهنگ ریپلای کن و بنویس:\n"
            "  پخش\n\n"
            "• روی لینک ریپلای کن و بنویس:\n"
            "  پخش"
        )


# ============================================================
# Pause / Resume / Stop
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
        if player is None:
            return

        ok = await player.pause(
            message.chat.id
        )

        await message.reply_text(
            "⏸ مکث انجام شد."
            if ok
            else
            "❌ آهنگی برای مکث وجود ندارد."
        )


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


def _register_stop_handler():
    @app.on_message(
        filters.text
        & filters.regex(
            r"^\s*(اتمام|توقف|stop)\s*$",
            flags=re.IGNORECASE,
        )
    )
    async def stop_handler(
        client,
        message,
    ):
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
        if player is None:
            return

        track = player.current_track

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

        status = player.get_status()

        available = (
            "فعال"
            if status.get("available")
            else "غیرفعال"
        )

        playing = (
            "در حال پخش"
            if status.get("is_playing")
            else "متوقف"
        )

        current = (
            status.get("current_track")
            or "هیچ آهنگی"
        )

        await message.reply_text(
            "╭───────────────╮\n"
            "       📊 وضعیت پلیر\n"
            "╰───────────────╯\n\n"
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
            "╭───────────────╮\n"
            "       🎵 𝗦𝗜𝗟𝗘𝗡𝗧 𝗣𝗟𝗔𝗬𝗘𝗥\n"
            "╰───────────────╯\n\n"
            "▶️ پخش نام آهنگ\n"
            "🎧 ریپلای فایل + پخش\n"
            "🔗 پخش لینک\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏭ بعدی\n"
            "⏹ اتمام\n"
            "📋 صف\n"
            "🎵 الان\n"
            "📊 وضعیت"
        )


# ============================================================
# Start
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
                    )
                ],
                [
                    InlineKeyboardButton(
                        "➕ افزودن به گروه",
                        url="https://t.me/Silent_musicplayerbot?startgroup=true",
                    )
                ],
            ]
        )

        await message.reply_text(
            "╭───────────────╮\n"
            "       🎧 𝗦𝗜𝗟𝗘𝗡𝗧 𝗣𝗟𝗔𝗬𝗘𝗥\n"
            "╰───────────────╯\n\n"
            "سلام 👋\n"
            "موزیک پلیر فارسی آماده است.\n\n"
            "برای پخش آهنگ در گروه:\n"
            "«پخش نام آهنگ»\n\n"
            "برای فایل تلگرام:\n"
            "روی فایل ریپلای کن و «پخش» بزن.",
            reply_markup=keyboard,
        )


# ============================================================
# Callback controls
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

        data = callback.data.split(":")

        if len(data) != 3:
            await callback.answer(
                "دکمه نامعتبر است.",
                show_alert=True,
            )
            return

        action = data[1]

        try:
            chat_id = int(data[2])
        except ValueError:
            await callback.answer(
                "شناسه چت نامعتبر است.",
                show_alert=True,
            )
            return

        if callback.from_user is None:
            await callback.answer()
            return

        if action == "pause":
            ok = await player.pause(chat_id)
            await callback.answer(
                "⏸ مکث شد."
                if ok
                else
                "❌ امکان مکث نیست."
            )
            return

        if action == "stop":
            ok = await player.stop(chat_id)
            await callback.answer(
                "⏹ پایان یافت."
                if ok
                else
                "❌ چیزی برای توقف نیست."
            )
            return

        if action == "next":
            method = getattr(
                player,
                "next",
                None,
            )

            if method is None:
                await callback.answer(
                    "⏭ قابلیت بعدی هنوز در پلیر متصل نشده.",
                    show_alert=True,
                )
                return

            ok = await method(chat_id)

            await callback.answer(
                "⏭ آهنگ بعدی."
                if ok
                else
                "❌ آهنگ بعدی وجود ندارد."
            )
            return

        if action == "prev":
            method = getattr(
                player,
                "previous",
                None,
            )

            if method is None:
                await callback.answer(
                    "⏮ قابلیت قبلی هنوز متصل نشده.",
                    show_alert=True,
                )
                return

            ok = await method(chat_id)

            await callback.answer(
                "⏮ آهنگ قبلی."
                if ok
                else
                "❌ آهنگ قبلی وجود ندارد."
            )
            return

        if action == "queue":
            queue = getattr(
                player,
                "queue",
                None,
            )

            if not queue:
                await callback.answer(
                    "📋 صف خالی است.",
                    show_alert=True,
                )
                return

            lines = [
                "╭───────────────╮",
                "       📋 صف پخش",
                "╰───────────────╯",
                "",
            ]

            for index, item in enumerate(
                list(queue)[:30],
                start=1,
            ):
                lines.append(
                    f"{index}. {_track_title(item)}"
                )

            await callback.message.reply_text(
                "\n".join(lines)
            )

            await callback.answer()
            return

        if action in (
            "back30",
            "forward30",
        ):
            await callback.answer(
                "این دکمه برای رد کردن ۳۰ ثانیه از زمان آهنگ نیست؛ "
                "برای صف باید به موتور صف متصل شود.",
                show_alert=True,
            )
            return

        if action in (
            "volup",
            "voldown",
        ):
            method = getattr(
                player,
                "set_volume",
                None,
            )

            if method is None:
                await callback.answer(
                    "کنترل صدا هنوز به پلیر متصل نشده.",
                    show_alert=True,
                )
                return

            status = player.get_status()
            current = int(
                status.get(
                    "volume",
                    100,
                )
                or 100
            )

            if action == "volup":
                volume = min(
                    200,
                    current + 10,
                )
            else:
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
                f"🔊 صدا: {volume}"
                if ok
                else
                "❌ تغییر صدا انجام نشد."
            )
            return

        await callback.answer(
            "دستور ناشناخته.",
            show_alert=True,
        )


# ============================================================
# Subscription callback
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

            if member.status not in (
                "left",
                "kicked",
            ):
                await callback.answer(
                    "✅ عضویت تأیید شد.",
                    show_alert=True,
                )
            else:
                await callback.answer(
                    "❌ هنوز عضو کانال نیستید.",
                    show_alert=True,
                )

        except Exception:
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
            "🎵 برای پخش:\n\n"
            "پخش نام آهنگ\n\n"
            "یا روی فایل صوتی ریپلای کن و بنویس:\n"
            "پخش"
        )

        await callback.answer()


# ============================================================
# Register
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

    _handlers_registered = True

    logger.info(
        "✅ Persian music handlers registered"
    )
