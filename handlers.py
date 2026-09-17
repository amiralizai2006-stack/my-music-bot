import logging
import os
import uuid
from pathlib import Path

from pyrogram import filters

from player import downloader, TrackInfo

logger = logging.getLogger(__name__)

app = None
pytgcalls_client = None
player = None
shutdown_event = None

_handlers_registered = False


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


def register_handlers():

    global _handlers_registered

    if _handlers_registered:
        return

    if app is None:
        raise RuntimeError(
            "Bot app has not been initialized"
        )

    # =========================
    # START
    # =========================

    @app.on_message(
        filters.command("start")
        & filters.private
    )
    async def start_handler(client, message):

        await message.reply(
            "🎵 سلام!\n\n"
            "به ربات موزیک خوش آمدید.\n\n"
            "🎧 دستورات:\n"
            "▶️ پخش نام آهنگ\n"
            "▶️ ریپلای روی آهنگ + پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "📋 صف\n"
            "🎵 الان\n"
            "🔊 صدا 100\n"
            "🆔 آیدی\n"
            "❓ کمک"
        )

    # =========================
    # HELP PRIVATE
    # =========================

    @app.on_message(
        filters.regex(r"^کمک$")
        & filters.private
    )
    async def private_help_handler(client, message):

        await message.reply(
            "🎵 راهنمای ربات\n\n"
            "▶️ پخش نام آهنگ\n"
            "▶️ ریپلای روی آهنگ + پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "📋 صف\n"
            "🎵 الان\n"
            "🔊 صدا 100\n"
            "🆔 آیدی"
        )

    # =========================
    # PLAY
    # =========================

    @app.on_message(
        filters.regex(r"^پخش(?:\s+(.+))?$")
        & filters.group
    )
    async def play_handler(client, message):

        query = message.matches[0].group(1)

        if player is None:
            await message.reply(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        if not player.is_voice_chat_available():
            await message.reply(
                "❌ سیستم پخش ویس‌چت آماده نیست."
            )
            return

        # =====================================
        # REPLY TO TELEGRAM AUDIO / MUSIC
        # =====================================

        reply = message.reply_to_message

        if reply and (
            reply.audio
            or reply.voice
            or reply.document
        ):

            media = (
                reply.audio
                or reply.voice
                or reply.document
            )

            # فقط فایل‌های صوتی را قبول کن
            mime_type = getattr(
                media,
                "mime_type",
                "",
            ) or ""

            file_name = getattr(
                media,
                "file_name",
                "",
            ) or ""

            is_audio = (
                reply.audio is not None
                or reply.voice is not None
                or mime_type.startswith("audio/")
                or file_name.lower().endswith(
                    (
                        ".mp3",
                        ".m4a",
                        ".aac",
                        ".ogg",
                        ".opus",
                        ".wav",
                        ".flac",
                        ".webm",
                    )
                )
            )

            if not is_audio:
                await message.reply(
                    "❌ فایل ریپلای‌شده صوتی نیست."
                )
                return

            status_message = await message.reply(
                "⬇️ در حال دریافت موزیک از تلگرام..."
            )

            try:

                downloads_dir = Path(
                    getattr(
                        downloader,
                        "downloads_dir",
                        "downloads",
                    )
                )

                downloads_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                file_id = uuid.uuid4().hex

                extension = ".audio"

                if file_name:
                    suffix = Path(file_name).suffix
                    if suffix:
                        extension = suffix

                output_file = (
                    downloads_dir
                    / f"telegram_{file_id}{extension}"
                )

                downloaded = await reply.download(
                    file_name=str(output_file)
                )

                if not downloaded:
                    await status_message.edit_text(
                        "❌ دریافت فایل از تلگرام انجام نشد."
                    )
                    return

                track_title = (
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
                    or "موزیک تلگرام"
                )

                track_uploader = (
                    getattr(
                        media,
                        "performer",
                        None,
                    )
                    or "Telegram"
                )

                duration = int(
                    getattr(
                        media,
                        "duration",
                        0,
                    )
                    or 0
                )

                track = TrackInfo(
                    title=track_title,
                    duration=duration,
                    url="",
                    webpage_url="",
                    thumbnail="",
                    uploader=track_uploader,
                    filepath=str(downloaded),
                )

                await status_message.edit_text(
                    f"🎧 در حال پخش:\n"
                    f"🎵 {track.title}"
                )

                success = await player.play(
                    message.chat.id,
                    track,
                )

                if success:

                    await status_message.edit_text(
                        "🎵 پخش شروع شد!\n\n"
                        f"🎤 {track.uploader}\n"
                        f"🎶 {track.title}"
                    )

                else:

                    await status_message.edit_text(
                        "❌ اتصال به ویس‌چت یا پخش موزیک انجام نشد."
                    )

            except Exception:

                logger.exception(
                    "Telegram audio playback failed"
                )

                await status_message.edit_text(
                    "❌ پخش فایل تلگرام انجام نشد."
                )

            return

        # =====================================
        # SEARCH / DOWNLOAD FROM INTERNET
        # =====================================

        if not query:

            await message.reply(
                "🎵 اسم آهنگ را بعد از «پخش» بنویس.\n\n"
                "مثال:\n"
                "پخش شادمهر تقدیر\n\n"
                "یا روی یک فایل صوتی ریپلای کن و فقط بنویس:\n"
                "پخش"
            )
            return

        status_message = await message.reply(
            f"🔎 در حال جستجو:\n{query}"
        )

        try:

            tracks = await downloader.search(
                query,
                limit=1,
            )

            if not tracks:

                await status_message.edit_text(
                    "❌ موزیک پیدا نشد."
                )
                return

            track = tracks[0]

            logger.info(
                "Selected track: title=%s url=%s webpage_url=%s",
                track.title,
                track.url,
                track.webpage_url,
            )

            await status_message.edit_text(
                f"⬇️ در حال دانلود:\n"
                f"🎵 {track.title}"
            )

            filepath = await downloader.download(
                track
            )

            if not filepath:

                logger.error(
                    "Downloader returned no filepath for: %s",
                    track.title,
                )

                await status_message.edit_text(
                    "❌ دانلود موزیک انجام نشد.\n\n"
                    "🔧 خطای دانلود در لاگ سرور ثبت شده است."
                )
                return

            track.filepath = filepath

            await status_message.edit_text(
                f"🎧 در حال ورود به ویس‌چت:\n"
                f"🎵 {track.title}"
            )

            success = await player.play(
                message.chat.id,
                track,
            )

            if success:

                await status_message.edit_text(
                    "🎵 پخش شروع شد!\n\n"
                    f"🎤 {track.uploader}\n"
                    f"🎶 {track.title}"
                )

            else:

                await status_message.edit_text(
                    "❌ اتصال به ویس‌چت یا پخش موزیک انجام نشد."
                )

        except Exception:

            logger.exception(
                "Play command failed"
            )

            await status_message.edit_text(
                "❌ هنگام پخش موزیک خطایی رخ داد."
            )

    # =========================
    # PAUSE
    # =========================

    @app.on_message(
        filters.regex(r"^مکث$")
        & filters.group
    )
    async def pause_handler(client, message):

        if player is None:
            return

        success = await player.pause(
            message.chat.id
        )

        if success:
            await message.reply(
                "⏸ پخش متوقف شد."
            )
        else:
            await message.reply(
                "❌ مکث انجام نشد."
            )

    # =========================
    # RESUME
    # =========================

    @app.on_message(
        filters.regex(r"^ادامه$")
        & filters.group
    )
    async def resume_handler(client, message):

        if player is None:
            return

        success = await player.resume(
            message.chat.id
        )

        if success:
            await message.reply(
                "▶️ پخش ادامه پیدا کرد."
            )
        else:
            await message.reply(
                "❌ ادامه پخش انجام نشد."
            )

    # =========================
    # STOP
    # =========================

    @app.on_message(
        filters.regex(r"^اتمام$")
        & filters.group
    )
    async def stop_handler(client, message):

        if player is None:
            return

        success = await player.stop(
            message.chat.id
        )

        if success:
            await message.reply(
                "⏹ پخش تمام شد."
            )
        else:
            await message.reply(
                "❌ موزیکی در حال پخش نیست."
            )

    # =========================
    # NEXT
    # =========================

    @app.on_message(
        filters.regex(r"^بعدی$")
        & filters.group
    )
    async def next_handler(client, message):

        await message.reply(
            "⏭ صف پخش هنوز فعال نشده است."
        )

    # =========================
    # QUEUE
    # =========================

    @app.on_message(
        filters.regex(r"^صف$")
        & filters.group
    )
    async def queue_handler(client, message):

        await message.reply(
            "📋 صف پخش فعلاً خالی است."
        )

    # =========================
    # NOW PLAYING
    # =========================

    @app.on_message(
        filters.regex(
            r"^(?:الان|در حال پخش)$"
        )
        & filters.group
    )
    async def now_playing_handler(client, message):

        if player is None:
            await message.reply(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        status = player.get_status()

        current = status.get(
            "current_track"
        )

        if current:

            await message.reply(
                f"🎵 در حال پخش:\n{current}"
            )

        else:

            await message.reply(
                "🎵 در حال حاضر موزیکی پخش نمی‌شود."
            )

    # =========================
    # VOLUME
    # =========================

    @app.on_message(
        filters.regex(
            r"^صدا(?:\s+(\d+))?$"
        )
        & filters.group
    )
    async def volume_handler(client, message):

        if player is None:
            return

        value = message.matches[0].group(1)

        if not value:

            await message.reply(
                f"🔊 صدا: {player.volume}"
            )
            return

        volume = int(value)

        if volume < 0 or volume > 200:

            await message.reply(
                "❌ میزان صدا باید بین ۰ تا ۲۰۰ باشد."
            )
            return

        success = await player.set_volume(
            message.chat.id,
            volume,
        )

        if success:

            await message.reply(
                f"🔊 صدا روی {volume} تنظیم شد."
            )

        else:

            await message.reply(
                "❌ تغییر صدا انجام نشد."
            )

    # =========================
    # ID
    # =========================

    @app.on_message(
        filters.regex(r"^آیدی$")
        & filters.group
    )
    async def id_handler(client, message):

        await message.reply(
            f"🆔 آیدی گروه:\n"
            f"`{message.chat.id}`"
        )

    # =========================
    # GROUP HELP
    # =========================

    @app.on_message(
        filters.regex(r"^کمک$")
        & filters.group
    )
    async def help_handler(client, message):

        await message.reply(
            "🎵 دستورات موزیک:\n\n"
            "▶️ پخش نام آهنگ\n"
            "▶️ ریپلای روی آهنگ + پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "📋 صف\n"
            "🎵 الان\n"
            "🔊 صدا 100\n"
            "🆔 آیدی"
        )

    _handlers_registered = True

    logger.info(
        "✅ Persian command handlers registered"
    )
