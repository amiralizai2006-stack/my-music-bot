import logging
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message

from player import TrackInfo

logger = logging.getLogger(__name__)

bot = None
player = None
pytgcalls = None
shutdown_event = None


def set_bot_instances(
    bot_instance,
    pytgcalls_instance,
    player_instance,
    shutdown,
):
    global bot, pytgcalls, player, shutdown_event

    bot = bot_instance
    pytgcalls = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown

    logger.info("Handlers received bot instance")


def _get_reply_audio(message: Message):
    reply = message.reply_to_message

    if reply is None:
        return None

    if reply.audio:
        return reply.audio

    if reply.voice:
        return reply.voice

    if reply.document:
        mime = reply.document.mime_type or ""
        if mime.startswith("audio/"):
            return reply.document

    return None


def _audio_title(audio):
    return (
        getattr(audio, "file_name", None)
        or getattr(audio, "title", None)
        or "موزیک"
    )


def _audio_artist(audio):
    return (
        getattr(audio, "performer", None)
        or "نامشخص"
    )


def register_handlers():

    if bot is None:
        raise RuntimeError(
            "Cannot register handlers: bot is None"
        )

    logger.info("REGISTERING TELEGRAM HANDLERS")

    # =====================================================
    # START
    # =====================================================

    @bot.on_message(
        filters.private & filters.command("start")
    )
    @bot.on_message(
        filters.group & filters.command("start")
    )
    async def start_handler(client, message):

        logger.info(
            "START RECEIVED | chat=%s | user=%s",
            message.chat.id,
            message.from_user.id if message.from_user else None,
        )

        await message.reply_text(
            "🎵 سلام!\n\n"
            "ربات موزیک پلیر آماده است.\n\n"
            "🎵 پخش نام آهنگ\n"
            "🎶 روی فایل موزیک ریپلای کن و بنویس: پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "🎵 الان\n"
            "📋 صف\n"
            "❓ کمک"
        )

    # =====================================================
    # HELP
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*کمک\s*$")
    )
    async def help_handler(client, message):

        logger.info(
            "HELP RECEIVED | chat=%s",
            message.chat.id,
        )

        await message.reply_text(
            "🎵 دستورات موزیک\n\n"
            "▶️ پخش نام آهنگ\n"
            "🎵 ریپلای روی موزیک + پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "⏮ قبلی\n"
            "⏪ عقب 10\n"
            "10 جلو\n"
            "⚡ سرعت\n"
            "🎵 الان\n"
            "📋 صف"
        )

    # =====================================================
    # PLAY
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*پخش(?:\s+(.+))?\s*$")
    )
    async def play_handler(client, message):

        logger.info(
            "PLAY RECEIVED | chat=%s | text=%r",
            message.chat.id,
            message.text,
        )

        try:

            text = (message.text or "").strip()
            parts = text.split(maxsplit=1)

            # -------------------------------------------------
            # Reply music
            # -------------------------------------------------

            audio = _get_reply_audio(message)

            if audio:

                await message.reply_text(
                    "⏳ در حال آماده‌سازی موزیک..."
                )

                filename = _audio_title(audio)

                safe_name = "".join(
                    char
                    for char in filename
                    if char.isalnum()
                    or char in " ._-"
                ).strip()

                if not safe_name:
                    safe_name = "music.mp3"

                download_dir = Path("downloads")
                download_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                destination = (
                    download_dir / safe_name
                )

                if destination.exists():

                    destination = (
                        download_dir
                        / f"{destination.stem}_{message.id}"
                        f"{destination.suffix}"
                    )

                downloaded = (
                    await message.reply_to_message.download(
                        file_name=str(destination)
                    )
                )

                if not downloaded:

                    await message.reply_text(
                        "❌ دانلود فایل انجام نشد."
                    )
                    return

                track = TrackInfo(
                    title=_audio_title(audio),
                    performer=_audio_artist(audio),
                    filepath=str(downloaded),
                )

                await player.play(
                    message.chat.id,
                    track,
                )

                await message.reply_text(
                    "🎵 در حال پخش\n\n"
                    f"🎶 آهنگ: {track.title}\n"
                    f"👤 خواننده: {track.performer}"
                )

                return

            # -------------------------------------------------
            # No song name
            # -------------------------------------------------

            if len(parts) < 2:

                await message.reply_text(
                    "🎵 اسم آهنگ را بعد از «پخش» بنویس.\n\n"
                    "مثال:\n"
                    "پخش مهیار"
                )
                return

            query = parts[1].strip()

            # -------------------------------------------------
            # Downloader
            # -------------------------------------------------

            if player is None:

                await message.reply_text(
                    "❌ Player آماده نیست."
                )
                return

            downloader = getattr(
                player,
                "downloader",
                None,
            )

            if downloader is None:

                await message.reply_text(
                    "❌ Downloader فعال نیست."
                )
                return

            await message.reply_text(
                f"🔎 در حال جستجوی:\n"
                f"🎵 {query}"
            )

            tracks = await downloader.search(
                query,
                limit=1,
            )

            if not tracks:

                await message.reply_text(
                    "❌ آهنگ پیدا نشد."
                )
                return

            track = tracks[0]

            await message.reply_text(
                "⬇️ آهنگ پیدا شد.\n\n"
                f"🎵 {track.title}\n"
                f"👤 {track.performer}\n\n"
                "⏳ در حال دانلود..."
            )

            downloaded = await downloader.download(
                track
            )

            if not downloaded:

                await message.reply_text(
                    "❌ دانلود آهنگ انجام نشد."
                )
                return

            await player.play(
                message.chat.id,
                track,
            )

            await message.reply_text(
                "🎵 در حال پخش\n\n"
                f"🎶 آهنگ: {track.title}\n"
                f"👤 خواننده: {track.performer}"
            )

        except Exception as error:

            logger.exception(
                "PLAY HANDLER ERROR"
            )

            await message.reply_text(
                "❌ خطای پخش:\n"
                f"`{type(error).__name__}: {error}`"
            )

    # =====================================================
    # PAUSE
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*مکث\s*$")
    )
    async def pause_handler(client, message):

        try:

            await player.pause(
                message.chat.id
            )

            await message.reply_text(
                "⏸ آهنگ مکث شد."
            )

        except Exception as error:

            await message.reply_text(
                f"❌ خطا:\n`{error}`"
            )

    # =====================================================
    # RESUME
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*ادامه\s*$")
    )
    async def resume_handler(client, message):

        try:

            await player.resume(
                message.chat.id
            )

            await message.reply_text(
                "▶️ آهنگ ادامه پیدا کرد."
            )

        except Exception as error:

            await message.reply_text(
                f"❌ خطا:\n`{error}`"
            )

    # =====================================================
    # STOP
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*اتمام\s*$")
    )
    async def stop_handler(client, message):

        try:

            await player.stop(
                message.chat.id
            )

            await message.reply_text(
                "⏹ آهنگ متوقف شد."
            )

        except Exception as error:

            await message.reply_text(
                f"❌ خطا:\n`{error}`"
            )

    # =====================================================
    # NOW
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*الان\s*$")
    )
    async def now_handler(client, message):

        try:

            status = player.get_status(
                message.chat.id
            )

            if not status:

                await message.reply_text(
                    "❌ در حال حاضر آهنگی پخش نمی‌شود."
                )
                return

            await message.reply_text(
                "🎵 در حال پخش:\n\n"
                f"🎶 {status.title}\n"
                f"👤 {status.performer}"
            )

        except Exception as error:

            await message.reply_text(
                f"❌ خطا:\n`{error}`"
            )

    # =====================================================
    # QUEUE
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*صف\s*$")
    )
    async def queue_handler(client, message):

        await message.reply_text(
            "📋 مدیریت صف در مرحله بعد فعال می‌شود."
        )

    # =====================================================
    # NEXT
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*بعدی\s*$")
    )
    async def next_handler(client, message):

        await message.reply_text(
            "⏭ مدیریت آهنگ بعدی در مرحله بعد فعال می‌شود."
        )

    # =====================================================
    # PREVIOUS
    # =====================================================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*قبلی\s*$")
    )
    async def previous_handler(client, message):

        await message.reply_text(
            "⏮ مدیریت آهنگ قبلی در مرحله بعد فعال می‌شود."
        )

    logger.info(
        "ALL TELEGRAM HANDLERS REGISTERED"
    )
