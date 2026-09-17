import logging
import re
from pyrogram import filters

logger = logging.getLogger(__name__)

app = None
pytgcalls_client = None
player = None
shutdown_event = None

_handlers_registered = False


def set_bot_instances(bot_app, pytgcalls, music_player, event):
    global app, pytgcalls_client, player, shutdown_event

    app = bot_app
    pytgcalls_client = pytgcalls
    player = music_player
    shutdown_event = event

    register_handlers()

    logger.info("✅ Persian command handlers registered")


def register_handlers():
    global _handlers_registered

    if _handlers_registered:
        return

    if app is None:
        raise RuntimeError("Bot app has not been initialized")

    @app.on_message(filters.regex(r"^پخش(?:\s+(.+))?$") & filters.group)
    async def play_handler(client, message):
        query = message.matches[0].group(1)

        if not query and message.reply_to_message:
            if message.reply_to_message.audio:
                await message.reply("🎵 دریافت موزیک از پیام در حال انجام است...")
                return

        if not query:
            await message.reply("🎵 اسم آهنگ یا لینک موزیک را بنویس.")
            return

        if player is None:
            await message.reply("❌ پخش‌کننده آماده نیست.")
            return

        try:
            await message.reply(f"🔎 در حال جستجو: {query}")

            track = await player.search(query)

            if not track:
                await message.reply("❌ موزیک پیدا نشد.")
                return

        except Exception as e:
            logger.exception("Play command error")
            await message.reply("❌ هنگام جستجوی موزیک خطایی رخ داد.")

    @app.on_message(filters.regex(r"^مکث$") & filters.group)
    async def pause_handler(client, message):
        if player is None:
            return

        try:
            success = await player.pause(message.chat.id)

            if success:
                await message.reply("⏸ پخش موزیک متوقف شد.")
            else:
                await message.reply("❌ موزیکی در حال پخش نیست.")
        except Exception:
            logger.exception("Pause command error")
            await message.reply("❌ خطا در مکث موزیک.")

    @app.on_message(filters.regex(r"^ادامه$") & filters.group)
    async def resume_handler(client, message):
        if player is None:
            return

        try:
            success = await player.resume(message.chat.id)

            if success:
                await message.reply("▶️ پخش ادامه پیدا کرد.")
            else:
                await message.reply("❌ موزیکی برای ادامه وجود ندارد.")
        except Exception:
            logger.exception("Resume command error")
            await message.reply("❌ خطا در ادامه پخش.")

    @app.on_message(filters.regex(r"^اتمام$") & filters.group)
    async def stop_handler(client, message):
        if player is None:
            return

        try:
            success = await player.stop(message.chat.id)

            if success:
                await message.reply("⏹ پخش موزیک تمام شد.")
            else:
                await message.reply("❌ موزیکی در حال پخش نیست.")
        except Exception:
            logger.exception("Stop command error")
            await message.reply("❌ خطا در اتمام موزیک.")

    @app.on_message(filters.regex(r"^بعدی$") & filters.group)
    async def next_handler(client, message):
        await message.reply("⏭ آهنگ بعدی در نسخه فعلی صف‌بندی می‌شود.")

    @app.on_message(filters.regex(r"^صف$") & filters.group)
    async def queue_handler(client, message):
        await message.reply("📋 صف پخش فعلاً خالی است.")

    @app.on_message(
        filters.regex(r"^(?:الان|در حال پخش)$") & filters.group
    )
    async def now_playing_handler(client, message):
        if player is None:
            await message.reply("❌ پخش‌کننده آماده نیست.")
            return

        status = player.get_status()
        current = status.get("current_track")

        if current:
            await message.reply(f"🎵 در حال پخش:\n{current}")
        else:
            await message.reply("🎵 در حال حاضر موزیکی پخش نمی‌شود.")

    @app.on_message(filters.regex(r"^صدا(?:\s+(\d+))?$") & filters.group)
    async def volume_handler(client, message):
        if player is None:
            return

        match = message.matches[0]
        value = match.group(1)

        if not value:
            await message.reply(f"🔊 صدا: {player.volume}")
            return

        try:
            volume = int(value)

            if volume < 0 or volume > 200:
                await message.reply("❌ میزان صدا باید بین ۰ تا ۲۰۰ باشد.")
                return

            success = await player.set_volume(message.chat.id, volume)

            if success:
                await message.reply(f"🔊 صدا روی {volume} تنظیم شد.")
            else:
                await message.reply("❌ تغییر صدا انجام نشد.")
        except Exception:
            await message.reply("❌ مقدار صدا نامعتبر است.")

    @app.on_message(filters.regex(r"^آیدی$") & filters.group)
    async def id_handler(client, message):
        await message.reply(
            f"🆔 آیدی این گروه:\n`{message.chat.id}`"
        )

    @app.on_message(filters.regex(r"^کمک$") & filters.group)
    async def help_handler(client, message):
        await message.reply(
            "🎵 دستورات موزیک:\n\n"
            "▶️ پخش نام آهنگ\n"
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

    _handlers_registered = True
