import logging
import os
import tempfile
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message

from player import downloader, TrackInfo

logger = logging.getLogger(__name__)

bot = None
pytgcalls = None
player = None
shutdown_event = None


def set_bot_instances(
    bot_instance,
    pytgcalls_instance,
    player_instance,
    shutdown_event_instance=None,
):
    global bot, pytgcalls, player, shutdown_event

    bot = bot_instance
    pytgcalls = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown_event_instance

    register_handlers()

    logger.info("handlers - Persian command handlers registered")


def register_handlers():
    if bot is None:
        return

    @bot.on_message(filters.command("start"))
    async def start_handler(_, message: Message):
        await message.reply_text(
            "🎵 به ربات موزیک خوش آمدید.\n\n"
            "برای پخش موزیک:\n"
            "پخش نام آهنگ\n\n"
            "یا روی یک فایل آهنگ ریپلای کنید و بنویسید:\n"
            "پخش"
        )

    @bot.on_message(
        filters.text
        & filters.regex(r"^(?:پخش)(?:\s+(.+))?$")
    )
    async def play_handler(_, message: Message):

        if not message.chat:
            return

        if message.chat.type.value not in (
            "group",
            "supergroup",
        ):
            await message.reply_text(
                "❌ این دستور فقط داخل گروه قابل استفاده است."
            )
            return

        if player is None:
            await message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        query = None

        if message.text:
            parts = message.text.split(maxsplit=1)

            if len(parts) == 2:
                query = parts[1].strip()

        reply = message.reply_to_message

        # -------------------------------------------------
        # حالت اول: Reply به فایل موزیک
        # -------------------------------------------------

        if reply is not None:

            media = None
            suffix = ".mp3"

            if reply.audio:
                media = reply.audio

                if reply.audio.file_name:
                    suffix = Path(
                        reply.audio.file_name
                    ).suffix or ".mp3"

            elif reply.voice:
                media = reply.voice
                suffix = ".ogg"

            elif reply.document:
                mime = (
                    reply.document.mime_type or ""
                ).lower()

                if (
                    mime.startswith("audio/")
                    or mime in (
                        "application/ogg",
                        "application/octet-stream",
                    )
                ):
                    media = reply.document

                    if reply.document.file_name:
                        suffix = Path(
                            reply.document.file_name
                        ).suffix or ".mp3"

            if media is not None:

                status = await message.reply_text(
                    "⬇️ دریافت موزیک..."
                )

                temp_dir = tempfile.gettempdir()

                file_path = os.path.join(
                    temp_dir,
                    f"telegram_music_{message.id}{suffix}",
                )

                try:

                    downloaded = await reply.download(
                        file_name=file_path
                    )

                    if not downloaded:
                        await status.edit_text(
                            "❌ دریافت فایل موزیک انجام نشد."
                        )
                        return

                    track = TrackInfo(
                        title=(
                            getattr(
                                media,
                                "file_name",
                                None,
                            )
                            or "Telegram Music"
                        ),
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
                        uploader="Telegram",
                        filepath=str(downloaded),
                    )

                    logger.info(
                        "TELEGRAM FILE PLAY: %s",
                        downloaded,
                    )

                    await status.edit_text(
                        "🎵 در حال اتصال به ویس‌چت..."
                    )

                    try:

                        result = await player.play(
                            message.chat.id,
                            track,
                        )

                    except Exception as e:

                        logger.exception(
                            "PLAY ERROR FROM PLAYER"
                        )

                        await status.edit_text(
                            "❌ خطای واقعی پخش:\n\n"
                            f"{type(e).__name__}: {e}"
                        )
                        return

                    if result:

                        await status.edit_text(
                            f"▶️ در حال پخش:\n"
                            f"{track.title}"
                        )

                    else:

                        await status.edit_text(
                            "❌ پخش شروع نشد.\n\n"
                            "player.play مقدار False برگرداند."
                        )

                    return

                except Exception as e:

                    logger.exception(
                        "TELEGRAM FILE ERROR"
                    )

                    await status.edit_text(
                        "❌ خطای واقعی دریافت/پخش:\n\n"
                        f"{type(e).__name__}: {e}"
                    )

                    return

        # -------------------------------------------------
        # حالت دوم: پخش با اسم آهنگ
        # -------------------------------------------------

        if not query:

            await message.reply_text(
                "🎵 نام آهنگ را بنویس.\n\n"
                "مثال:\n"
                "پخش مهیار"
            )
            return

        status = await message.reply_text(
            f"🔎 جستجوی «{query}»..."
        )

        try:

            results = await downloader.search(
                query,
                limit=1,
            )

        except Exception as e:

            logger.exception(
                "SEARCH ERROR"
            )

            await status.edit_text(
                "❌ خطای واقعی جستجو:\n\n"
                f"{type(e).__name__}: {e}"
            )
            return

        if not results:

            await status.edit_text(
                "❌ موزیک پیدا نشد."
            )
            return

        track = results[0]

        await status.edit_text(
            f"⬇️ در حال دانلود:\n"
            f"{track.title}"
        )

        try:

            filepath = await downloader.download(
                track
            )

        except Exception as e:

            logger.exception(
                "DOWNLOAD ERROR FROM HANDLER"
            )

            await status.edit_text(
                "❌ خطای واقعی دانلود:\n\n"
                f"{type(e).__name__}: {e}"
            )
            return

        if not filepath:

            await status.edit_text(
                "❌ دانلود انجام نشد.\n\n"
                "جزئیات در لاگ Render ثبت شده است."
            )
            return

        track.filepath = filepath

        await status.edit_text(
            "🎵 فایل آماده شد.\n"
            "در حال اتصال به ویس‌چت..."
        )

        try:

            result = await player.play(
                message.chat.id,
                track,
            )

        except Exception as e:

            logger.exception(
                "PLAY ERROR FROM SEARCH"
            )

            await status.edit_text(
                "❌ خطای واقعی پخش:\n\n"
                f"{type(e).__name__}: {e}"
            )
            return

        if result:

            await status.edit_text(
                f"▶️ در حال پخش:\n"
                f"{track.title}"
            )

        else:

            await status.edit_text(
                "❌ پخش شروع نشد.\n\n"
                "player.play مقدار False برگرداند."
            )


    # -----------------------------------------------------
    # مکث
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^مکث$")
    )
    async def pause_handler(_, message: Message):

        try:

            result = await player.pause(
                message.chat.id
            )

            if result:
                await message.reply_text(
                    "⏸ موزیک مکث شد."
                )
            else:
                await message.reply_text(
                    "❌ امکان مکث وجود ندارد."
                )

        except Exception as e:

            logger.exception(
                "PAUSE ERROR"
            )

            await message.reply_text(
                "❌ خطای مکث:\n\n"
                f"{type(e).__name__}: {e}"
            )


    # -----------------------------------------------------
    # ادامه
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^ادامه$")
    )
    async def resume_handler(_, message: Message):

        try:

            result = await player.resume(
                message.chat.id
            )

            if result:
                await message.reply_text(
                    "▶️ موزیک ادامه پیدا کرد."
                )
            else:
                await message.reply_text(
                    "❌ امکان ادامه وجود ندارد."
                )

        except Exception as e:

            logger.exception(
                "RESUME ERROR"
            )

            await message.reply_text(
                "❌ خطای ادامه:\n\n"
                f"{type(e).__name__}: {e}"
            )


    # -----------------------------------------------------
    # اتمام
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^اتمام$")
    )
    async def stop_handler(_, message: Message):

        try:

            result = await player.stop(
                message.chat.id
            )

            if result:
                await message.reply_text(
                    "⏹ موزیک تمام شد و از ویس‌چت خارج شدم."
                )
            else:
                await message.reply_text(
                    "❌ موزیکی در حال پخش نیست."
                )

        except Exception as e:

            logger.exception(
                "STOP ERROR"
            )

            await message.reply_text(
                "❌ خطای اتمام:\n\n"
                f"{type(e).__name__}: {e}"
            )


    # -----------------------------------------------------
    # صدا
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^صدا(?:\s+(\d+))?$")
    )
    async def volume_handler(_, message: Message):

        try:

            parts = message.text.split()

            if len(parts) != 2:
                await message.reply_text(
                    "🔊 مثال:\n"
                    "صدا 80"
                )
                return

            volume = int(parts[1])

            if volume < 0 or volume > 200:
                await message.reply_text(
                    "❌ مقدار صدا باید بین 0 تا 200 باشد."
                )
                return

            result = await player.set_volume(
                message.chat.id,
                volume,
            )

            if result:
                await message.reply_text(
                    f"🔊 صدا روی {volume}% تنظیم شد."
                )
            else:
                await message.reply_text(
                    "❌ تغییر صدا انجام نشد."
                )

        except Exception as e:

            logger.exception(
                "VOLUME ERROR"
            )

            await message.reply_text(
                "❌ خطای صدا:\n\n"
                f"{type(e).__name__}: {e}"
            )


    # -----------------------------------------------------
    # الان
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^الان$")
    )
    async def now_handler(_, message: Message):

        try:

            status = player.get_status()

            current = status.get(
                "current_track"
            )

            if current:

                await message.reply_text(
                    f"🎵 در حال پخش:\n{current}"
                )

            else:

                await message.reply_text(
                    "🎵 در حال حاضر موزیکی پخش نمی‌شود."
                )

        except Exception as e:

            logger.exception(
                "NOW ERROR"
            )

            await message.reply_text(
                "❌ خطا:\n\n"
                f"{type(e).__name__}: {e}"
            )


    # -----------------------------------------------------
    # صف
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^صف$")
    )
    async def queue_handler(_, message: Message):

        await message.reply_text(
            "📋 فعلاً سیستم صف در حال تکمیل است."
        )


    # -----------------------------------------------------
    # بعدی
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^بعدی$")
    )
    async def next_handler(_, message: Message):

        await message.reply_text(
            "⏭ فعلاً آهنگ بعدی در صف وجود ندارد."
        )


    # -----------------------------------------------------
    # کمک
    # -----------------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^کمک$")
    )
    async def help_handler(_, message: Message):

        await message.reply_text(
            "🎵 راهنمای ربات موزیک\n\n"
            "▶️ پخش نام آهنگ\n"
            "▶️ Reply به موزیک + پخش\n"
            "⏸ مکث\n"
            "▶️ ادامه\n"
            "⏹ اتمام\n"
            "⏭ بعدی\n"
            "📋 صف\n"
            "🎵 الان\n"
            "🔊 صدا 80"
        )


logger.info(
    "Persian handlers module loaded"
)
