# ============================================================
# Telegram Persian Music Bot - handlers.py
# نسخه اصلاح‌شده
# ============================================================

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from pyrogram import filters
from pyrogram.types import Message

from player import TrackInfo


logger = logging.getLogger(__name__)


# ============================================================
# Global instances
# ============================================================

app = None
pytgcalls_client = None
player = None
shutdown_event = None

_handlers_registered = False


# ============================================================
# Runtime helpers
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


async def _check_subscription(message: Message) -> bool:
    """
    فعلاً پخش را مسدود نمی‌کند.
    مدیریت اشتراک می‌تواند بعداً روی همین تابع اضافه شود.
    """
    return True


# ============================================================
# Text / Track helpers
# ============================================================

def _track_title(track):
    return (
        getattr(track, "title", None)
        or "آهنگ بدون نام"
    )


def _track_artist(track):
    performer = getattr(
        track,
        "performer",
        None,
    )

    if performer:
        return performer

    uploader = getattr(
        track,
        "uploader",
        None,
    )

    return uploader or "ناشناخته"


def _format_duration(seconds):
    try:
        seconds = int(seconds or 0)
    except Exception:
        seconds = 0

    if seconds <= 0:
        return "نامشخص"

    minutes = seconds // 60
    remaining = seconds % 60

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
    performer = getattr(
        media,
        "performer",
        None,
    )

    if performer:
        return performer

    return "ناشناخته"


async def _send_now_playing(
    message,
    track,
):
    title = _track_title(track)
    artist = _track_artist(track)

    duration = _format_duration(
        getattr(
            track,
            "duration",
            0,
        )
    )

    await message.reply_text(
        "🎵 پخش شد\n\n"
        f"🎶 {title}\n"
        f"👤 {artist}\n"
        f"⏱ {duration}"
    )


# ============================================================
# Reply audio
# ============================================================

async def _play_local_reply_file(
    client,
    message,
    media,
):
    """
    فایل صوتی ریپلای‌شده را دانلود و پخش می‌کند.
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

        if not safe_name:
            safe_name = (
                f"reply_{reply.id}.audio"
            )

        # نام یکتا تا دو فایل هم‌نام روی هم نوشته نشوند.
        filepath = (
            downloads_dir
            / f"reply_{reply.id}_{message.id}_{safe_name}"
        )

        await message.reply_text(
            "⏳ فایل ریپلای‌شده در حال دانلود است..."
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
            performer=artist,
            filepath=str(filepath),
        )

        chat_id = message.chat.id

        await message.reply_text(
            "▶️ در حال پخش فایل..."
        )

        ok = await player.play(
            chat_id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ فایل دانلود شد ولی پخش نشد.\n\n"
                "مطمئن شو ویس‌چت گروه فعال است."
            )
            return

        await _send_now_playing(
            message,
            track,
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
# YouTube
# ============================================================

async def _download_youtube_track(
    query,
):
    """
    جست‌وجو یا دریافت لینک YouTube
    و سپس دانلود واقعی فایل.
    """

    downloader = player.downloader

    # --------------------------------------------------------
    # لینک مستقیم YouTube
    # --------------------------------------------------------

    if _is_url(query):
        track = TrackInfo(
            title="YouTube",
            webpage_url=query,
            performer="YouTube",
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
    # جست‌وجوی YouTube
    # --------------------------------------------------------

    results = await downloader.search(
        query,
        1,
    )

    if not results:
        return None

    track = results[0]

    # --------------------------------------------------------
    # دانلود
    # --------------------------------------------------------

    filepath = await downloader.download(
        track
    )

    if not filepath:
        return None

    track.filepath = str(
        Path(filepath).resolve()
    )

    return track


async def _search_youtube_and_play(
    message,
    query,
):
    """
    جست‌وجو / دانلود / پخش YouTube.
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
            "پخش شادمهر تقدیر"
        )
        return

    try:
        if _is_url(query):
            await message.reply_text(
                "🔗 لینک YouTube دریافت شد.\n"
                "⬇️ در حال دانلود..."
            )
        else:
            await message.reply_text(
                "🔎 در حال جست‌وجوی YouTube...\n\n"
                f"🎵 {query}"
            )

        # نکته مهم:
        # search در player.py خودش async است.
        # بنابراین نباید داخل asyncio.to_thread قرار بگیرد.
        track = await _download_youtube_track(
            query
        )

        if track is None:
            await message.reply_text(
                "❌ آهنگ پیدا یا دانلود نشد.\n\n"
                "اسم آهنگ را دقیق‌تر بنویس "
                "یا لینک مستقیم YouTube بده."
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
            "▶️ آهنگ دانلود شد.\n"
            "🎧 در حال شروع پخش..."
        )

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ آهنگ دانلود شد اما پخش نشد.\n\n"
                "ویس‌چت گروه را بررسی کن."
            )
            return

        await _send_now_playing(
            message,
            track,
        )

    except Exception as e:
        logger.exception(
            "YOUTUBE PLAY ERROR"
        )

        await message.reply_text(
            "❌ خطا هنگام جست‌وجو یا دانلود YouTube:\n"
            f"{type(e).__name__}: {e}"
        )


# ============================================================
# Main play handler
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

        text = (
            message.text or ""
        )

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
        # پخش اسم آهنگ یا لینک
        # ----------------------------------------------------

        if query:
            await _search_youtube_and_play(
                message,
                query,
            )
            return

        # ----------------------------------------------------
        # پخش فایل ریپلای‌شده
        # ----------------------------------------------------

        media = _get_reply_media(
            message
        )

        if media:
            await _play_local_reply_file(
                client,
                message,
                media,
            )
            return

        # ----------------------------------------------------
        # ریپلای روی پیام دارای لینک
        # ----------------------------------------------------

        reply = (
            message.reply_to_message
        )

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
                await _search_youtube_and_play(
                    message,
                    urls[0],
                )
                return

        await message.reply_text(
            "❌ چیزی برای پخش پیدا نشد.\n\n"
            "🎵 روش اول:\n"
            "پخش اسم آهنگ\n\n"
            "مثال:\n"
            "پخش شادمهر تقدیر\n\n"
            "🎧 روش دوم:\n"
            "روی فایل آهنگ ریپلای کن و بنویس:\n"
            "پخش\n\n"
            "🔗 روش سوم:\n"
            "روی لینک YouTube ریپلای کن و بنویس:\n"
            "پخش"
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
        if player is None:
            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        ok = await player.pause(
            message.chat.id
        )

        if ok:
            await message.reply_text(
                "⏸ پخش متوقف موقت شد."
            )
        else:
            await message.reply_text(
                "❌ امکان مکث وجود ندارد."
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
        if player is None:
            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        ok = await player.resume(
            message.chat.id
        )

        if ok:
            await message.reply_text(
                "▶️ پخش ادامه پیدا کرد."
            )
        else:
            await message.reply_text(
                "❌ امکان ادامه پخش وجود ندارد."
            )


# ============================================================
# Stop
# ============================================================

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
            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        ok = await player.stop(
            message.chat.id
        )

        if ok:
            await message.reply_text(
                "⏹ پخش آهنگ تمام شد."
            )
        else:
            await message.reply_text(
                "❌ چیزی برای توقف پیدا نشد."
            )


# ============================================================
# Current song
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
            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        track = (
            player.current_track
        )

        if not track:
            await message.reply_text(
                "🎵 در حال حاضر آهنگی در حال پخش نیست."
            )
            return

        await _send_now_playing(
            message,
            track,
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
            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
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
            "📊 وضعیت موزیک پلیر\n\n"
            f"🎧 ویس‌چت: {available}\n"
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
            "🎵 راهنمای موزیک پلیر\n\n"
            "▶️ پخش اسم آهنگ\n"
            "مثال: پخش شادمهر تقدیر\n\n"
            "🔗 پخش لینک YouTube\n"
            "پخش https://youtube.com/...\n\n"
            "🎧 ریپلای روی فایل صوتی + پخش\n"
            "همان فایل را در ویس‌چت پخش می‌کند.\n\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
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
        await message.reply_text(
            "🎵 سلام!\n\n"
            "من موزیک پلیر فارسی هستم.\n\n"
            "برای پخش آهنگ بنویس:\n"
            "پخش اسم آهنگ\n\n"
            "مثال:\n"
            "پخش شادمهر تقدیر\n\n"
            "یا روی یک فایل صوتی ریپلای کن و بنویس:\n"
            "پخش"
        )


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

    _handlers_registered = True

    logger.info(
        "✅ All Telegram handlers registered successfully"
    )
