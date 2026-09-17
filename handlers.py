# handlers.py
# Persian Music Player handlers

import logging
import os
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message

from player import TrackInfo

logger = logging.getLogger(__name__)

bot = None
player = None
pytgcalls = None
shutdown_event = None


def set_bot_instances(bot_instance, pytgcalls_instance, player_instance, shutdown):
    global bot, pytgcalls, player, shutdown_event

    bot = bot_instance
    pytgcalls = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown

    logger.info("handlers - Persian command handlers registered")


def _get_reply_audio(message: Message):
    reply = message.reply_to_message

    if not reply:
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
        or "Unknown"
    )


def _audio_artist(audio):
    return (
        getattr(audio, "performer", None)
        or "Unknown"
    )


# ============================================================
# START
# ============================================================

def register_handlers():

    @bot.on_message(filters.command("start"))
    async def start_handler(client, message):
        await message.reply_text(
            "🎵 به ربات موزیک پلیر فارسی خوش آمدید.\n\n"
            "برای پخش آهنگ:\n"
            "• پخش نام آهنگ\n"
            "• یا روی فایل موزیک ریپلای کن و بنویس پخش"
        )


    # ========================================================
    # پخش
    # ========================================================

    @bot.on_message(
        filters.text &
        filters.regex(r"^پخش(?:\s+(.+))?$")
    )
    async def play_handler(client, message):

        try:
            text = message.text.strip()
            parts = text.split(maxsplit=1)

            # ------------------------------------------------
            # حالت 1: پخش روی فایل ریپلای‌شده
            # ------------------------------------------------

            if message.reply_to_message:

                audio = _get_reply_audio(message)

                if audio:

                    await message.reply_text("⏳ در حال آماده‌سازی موزیک...")

                    filename = _audio_title(audio)

                    safe_name = "".join(
                        c for c in filename
                        if c.isalnum() or c in " ._-"
                    ).strip()

                    if not safe_name:
                        safe_name = "music"

                    download_dir = Path("downloads")
                    download_dir.mkdir(
                        parents=True,
                        exist_ok=True
                    )

                    destination = download_dir / safe_name

                    # اگر فایل قبلاً وجود داشت، اسم جدید
                    if destination.exists():
                        stem = destination.stem
                        suffix = destination.suffix
                        destination = (
                            download_dir /
                            f"{stem}_{message.id}{suffix}"
                        )

                    downloaded = await message.reply_to_message.download(
                        file_name=str(destination)
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
                        track
                    )

                    await message.reply_text(
                        f"🎵 **در حال پخش**\n\n"
                        f"🎶 آهنگ: {track.title}\n"
                        f"👤 خواننده: {track.performer}"
                    )

                    return

            # ------------------------------------------------
            # حالت 2: پخش نام آهنگ
            # ------------------------------------------------

            if len(parts) < 2 or not parts[1].strip():

                await message.reply_text(
                    "🎵 نام آهنگ را بعد از پخش بنویس.\n\n"
                    "مثال:\n"
                    "پخش مهیار"
                )
                return

            query = parts[1].strip()

            await message.reply_text(
                f"🔎 در حال جستجوی «{query}»..."
            )

            # Downloader موجود در player
            downloader = getattr(player, "downloader", None)

            if downloader is None:
                await message.reply_text(
                    "❌ Downloader در ربات فعال نیست."
                )
                return

            # ------------------------------------------------
            # جستجو
            # ------------------------------------------------

            tracks = await downloader.search(
                query,
                limit=1
            )

            if not tracks:

                await message.reply_text(
                    "❌ آهنگ پیدا نشد.\n\n"
                    f"🔎 جستجو: {query}"
                )
                return

            track = tracks[0]

            await message.reply_text(
                f"⬇️ آهنگ پیدا شد:\n"
                f"🎵 {track.title}\n"
                f"👤 {track.performer}\n\n"
                f"⏳ در حال دانلود..."
            )

            # ------------------------------------------------
            # دانلود
            # ------------------------------------------------

            downloaded = await downloader.download(track)

            if not downloaded:

                logger.error(
                    "DOWNLOAD ERROR | query=%s | track=%s",
                    query,
                    track
                )

                await message.reply_text(
                    "❌ دانلود آهنگ انجام نشد.\n\n"
                    f"🔎 آهنگ: {query}\n"
                    "لطفاً دوباره امتحان کن."
                )
                return

            # ------------------------------------------------
            # پخش
            # ------------------------------------------------

            await player.play(
                message.chat.id,
                track
            )

            await message.reply_text(
                f"🎵 **در حال پخش**\n\n"
                f"🎶 آهنگ: {track.title}\n"
                f"👤 خواننده: {track.performer}"
            )

        except Exception as e:

            logger.exception(
                "PLAY HANDLER ERROR | %s: %s",
                type(e).__name__,
                str(e)
            )

            await message.reply_text(
                "❌ خطای پخش:\n"
                f"`{type(e).__name__}: {str(e)}`"
            )


    # ========================================================
    # مکث
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^مکث$"))
    async def pause_handler(client, message):

        try:
            await player.pause(message.chat.id)

            await message.reply_text(
                "⏸ آهنگ مکث شد."
            )

        except Exception as e:
            await message.reply_text(
                f"❌ خطا: `{type(e).__name__}: {e}`"
            )


    # ========================================================
    # ادامه
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^ادامه$"))
    async def resume_handler(client, message):

        try:
            await player.resume(message.chat.id)

            await message.reply_text(
                "▶️ آهنگ ادامه پیدا کرد."
            )

        except Exception as e:
            await message.reply_text(
                f"❌ خطا: `{type(e).__name__}: {e}`"
            )


    # ========================================================
    # اتمام
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^اتمام$"))
    async def stop_handler(client, message):

        try:
            await player.stop(message.chat.id)

            await message.reply_text(
                "⏹ آهنگ متوقف شد."
            )

        except Exception as e:
            await message.reply_text(
                f"❌ خطا: `{type(e).__name__}: {e}`"
            )


    # ========================================================
    # وضعیت آهنگ
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^الان$"))
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
                f"🎵 آهنگ در حال پخش:\n\n"
                f"🎶 {status.title}\n"
                f"👤 {status.performer}"
            )

        except Exception as e:
            await message.reply_text(
                f"❌ خطا: `{type(e).__name__}: {e}`"
            )


    # ========================================================
    # صف
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^صف$"))
    async def queue_handler(client, message):

        await message.reply_text(
            "🎵 مدیریت صف در حال آماده‌سازی است."
        )


    # ========================================================
    # بعدی
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^بعدی$"))
    async def next_handler(client, message):

        await message.reply_text(
            "⏭ مدیریت آهنگ بعدی در حال آماده‌سازی است."
        )


    # ========================================================
    # کمک
    # ========================================================

    @bot.on_message(filters.text & filters.regex(r"^کمک$"))
    async def help_handler(client, message):

        await message.reply_text(
            "🎵 **دستورات موزیک**\n\n"
            "▶️ پخش نام آهنگ\n"
            "🎵 ریپلای روی موزیک + پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "🎶 الان\n"
            "📋 صف"
        )

    logger.info("Bot handlers registered")
