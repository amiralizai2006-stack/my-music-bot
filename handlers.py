import logging
import re
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
    pytgcalls_instance=None,
    player_instance=None,
    shutdown_event_instance=None,
):
    global bot, player, pytgcalls, shutdown_event

    bot = bot_instance
    pytgcalls = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown_event_instance

    logger.info("Handlers received bot instance")


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


async def _download_and_play(
    message: Message,
    track: TrackInfo,
):
    if player is None:
        await message.reply_text(
            "❌ پخش‌کننده آماده نیست."
        )
        return

    try:
        await message.reply_text(
            "⏳ در حال دانلود..."
        )

        logger.info(
            "DOWNLOAD REQUEST | title=%s | webpage=%s | url=%s",
            track.title,
            track.webpage_url,
            track.url,
        )

        downloader = getattr(
            player,
            "downloader",
            None,
        )

        if downloader is None:
            logger.error(
                "PLAYER DOWNLOADER IS NONE"
            )

            await message.reply_text(
                "❌ دانلودر آماده نیست."
            )
            return

        filepath = await downloader.download(
            track
        )

        if not filepath:
            logger.error(
                "DOWNLOAD RETURNED NONE | title=%s",
                track.title,
            )

            await message.reply_text(
                "❌ دانلود آهنگ انجام نشد."
            )
            return

        track.filepath = filepath

        logger.info(
            "DOWNLOAD COMPLETE | %s",
            filepath,
        )

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ پخش آهنگ انجام نشد."
            )
            return

        await message.reply_text(
            f"▶️ در حال پخش\n\n"
            f"🎵 {track.title}\n"
            f"👤 {track.artist}"
        )

    except Exception as e:
        logger.exception(
            "PLAY/DOWNLOAD ERROR | %s: %s",
            type(e).__name__,
            str(e),
        )

        await message.reply_text(
            f"❌ خطای پخش: "
            f"{type(e).__name__}: {e}"
        )


def register_handlers():

    if bot is None:
        raise RuntimeError(
            "Bot instance has not been set"
        )

    logger.info(
        "REGISTERING TELEGRAM HANDLERS"
    )

    # =========================
    # START
    # =========================

    @bot.on_message(
        filters.private & filters.command("start")
    )
    @bot.on_message(
        filters.group & filters.command("start")
    )
    async def start_handler(
        client,
        message,
    ):
        await message.reply_text(
            "🎵 سلام!\n\n"
            "به ربات موزیک پلیر خوش آمدید.\n\n"
            "برای پخش آهنگ:\n"
            "• پخش نام آهنگ\n"
            "• یا روی فایل آهنگ ریپلای کنید و بنویسید: پخش"
        )

    # =========================
    # HELP
    # =========================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*کمک\s*$")
    )
    async def help_handler(
        client,
        message,
    ):
        await message.reply_text(
            "🎵 دستورات موزیک:\n\n"
            "پخش نام آهنگ\n"
            "پخش ← روی آهنگ ریپلای شود\n"
            "مکث\n"
            "ادامه\n"
            "اتمام\n"
            "بعدی\n"
            "قبلی"
        )

    # =========================
    # PLAY
    # =========================

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*پخش(?:\s+(.+))?\s*$"
        )
    )
    async def play_handler(
        client,
        message,
    ):
        text = message.text or ""

        match = re.match(
            r"^\s*پخش(?:\s+(.+))?\s*$",
            text,
        )

        query = (
            match.group(1).strip()
            if match and match.group(1)
            else ""
        )

        logger.info(
            "PLAY RECEIVED | chat=%s | text=%r | query=%r",
            message.chat.id,
            text,
            query,
        )

        # -------------------------
        # REPLY TO AUDIO
        # -------------------------

        if not query:

            media = _get_reply_audio(
                message
            )

            if not media:
                await message.reply_text(
                    "❌ روی یک فایل آهنگ ریپلای کنید و «پخش» بزنید."
                )
                return

            await message.reply_text(
                "⏳ در حال آماده‌سازی آهنگ..."
            )

            try:

                file_name = (
                    getattr(
                        media,
                        "file_name",
                        None,
                    )
                    or f"audio_{message.id}.mp3"
                )

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

                filepath = await client.download_media(
                    message.reply_to_message,
                    file_name=str(
                        downloads_dir / file_name
                    ),
                )

                if not filepath:
                    await message.reply_text(
                        "❌ دریافت فایل آهنگ انجام نشد."
                    )
                    return

                track = TrackInfo(
                    title=_audio_title(media),
                    performer=_audio_artist(media),
                    filepath=filepath,
                )

                logger.info(
                    "REPLY AUDIO READY | title=%s | file=%s",
                    track.title,
                    filepath,
                )

                ok = await player.play(
                    message.chat.id,
                    track,
                )

                if not ok:
                    await message.reply_text(
                        "❌ پخش آهنگ انجام نشد."
                    )
                    return

                await message.reply_text(
                    f"▶️ در حال پخش\n\n"
                    f"🎵 {track.title}\n"
                    f"👤 {track.artist}"
                )

            except Exception as e:

                logger.exception(
                    "REPLY PLAY ERROR | %s: %s",
                    type(e).__name__,
                    str(e),
                )

                await message.reply_text(
                    f"❌ خطای پخش: "
                    f"{type(e).__name__}: {e}"
                )

            return

        # -------------------------
        # SEARCH BY NAME
        # -------------------------

        await message.reply_text(
            f"🔎 در حال جستجوی:\n"
            f"🎵 {query}"
        )

        try:

            results = await player.downloader.search(
                query,
                limit=1,
            )

            if not results:

                await message.reply_text(
                    "❌ آهنگی پیدا نشد."
                )
                return

            track = results[0]

            logger.info(
                "SEARCH RESULT SELECTED | title=%s | artist=%s | webpage=%s | url=%s",
                track.title,
                track.artist,
                track.webpage_url,
                track.url,
            )

            await message.reply_text(
                "⬇️ آهنگ پیدا شد.\n\n"
                f"🎵 {track.title}\n"
                f"👤 {track.artist}"
            )

            await _download_and_play(
                message,
                track,
            )

        except Exception as e:

            logger.exception(
                "SEARCH PLAY ERROR | %s: %s",
                type(e).__name__,
                str(e),
            )

            await message.reply_text(
                f"❌ خطای پخش: "
                f"{type(e).__name__}: {e}"
            )

    # =========================
    # PAUSE
    # =========================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*مکث\s*$")
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
            "⏸️ آهنگ مکث شد."
            if ok
            else "❌ مکث انجام نشد."
        )

    # =========================
    # RESUME
    # =========================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*ادامه\s*$")
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
            else "❌ ادامه پخش انجام نشد."
        )

    # =========================
    # STOP
    # =========================

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*اتمام\s*$")
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
            "⏹️ پخش متوقف شد."
            if ok
            else "❌ توقف انجام نشد."
        )

    logger.info(
        "ALL TELEGRAM HANDLERS REGISTERED"
    )
