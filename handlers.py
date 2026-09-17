"""
Telegram Music Bot handlers.
Persian commands + English aliases.
"""

import logging
from datetime import datetime
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message

from database import db, QueueItem
from player import downloader, MusicPlayer, TrackInfo
from optional_deps import VOICE_CHAT_AVAILABLE

logger = logging.getLogger(__name__)

# These are injected from main.py by set_bot_instances()
app: Optional[Client] = None
pytgcalls_client = None
player: Optional[MusicPlayer] = None
shutdown_event = None


def set_bot_instances(bot_app, pytgcalls, music_player, event):
    """Receive initialized objects from main.py."""
    global app, pytgcalls_client, player, shutdown_event

    app = bot_app
    pytgcalls_client = pytgcalls
    player = music_player
    shutdown_event = event

    logger.info("✅ Handler instances initialized")


async def get_queue_text(chat_id: int) -> str:
    queue = await db.get_queue(chat_id)

    if not queue:
        return "📋 صف موزیک خالی است."

    lines = ["📋 **صف موزیک:**", ""]

    for index, item in enumerate(queue, 1):
        duration = (
            f"{item.duration // 60}:{item.duration % 60:02d}"
            if item.duration
            else "??:??"
        )

        lines.append(
            f"{index}. 🎵 **{item.title}**\n"
            f"   ⏱ `{duration}` | 👤 {item.requested_by}"
        )

    return "\n".join(lines)


async def play_queue_item(item: QueueItem) -> bool:
    """Convert a queue item into TrackInfo and play it."""
    if not player or not VOICE_CHAT_AVAILABLE:
        return False

    track = TrackInfo(
        title=item.title,
        duration=item.duration,
        url=item.url,
        webpage_url=item.url,
        thumbnail="",
        uploader="",
        filepath=item.filepath,
    )

    return await player.play(item.chat_id, track)


async def play_next(chat_id: int) -> bool:
    """Play the first item in the queue."""
    if not player or not VOICE_CHAT_AVAILABLE:
        return False

    item = await db.get_next_in_queue(chat_id)

    if not item:
        player.current_track = None
        player.is_playing = False
        return False

    if not item.filepath:
        await db.remove_from_queue(item.id)
        await db.reorder_queue(chat_id)
        return await play_next(chat_id)

    success = await play_queue_item(item)

    if success:
        await db.remove_from_queue(item.id)
        await db.reorder_queue(chat_id)
        return True

    return False


# ============================================================
# Persian commands
# ============================================================


@app.on_message(
    filters.regex(r"^(?:پخش|play)(?:\s+(.+))?$") & filters.group
)
async def persian_play_cmd(client: Client, message: Message):
    query = message.matches[0].group(1)

    # Reply-to-audio/music support
    if not query and message.reply_to_message:
        replied = message.reply_to_message

        if replied.audio or replied.voice or replied.video:
            await message.reply(
                "⚠️ پخش مستقیم فایل ریپلای‌شده در این نسخه هنوز فعال نیست.\n"
                "لطفاً نام آهنگ را بعد از «پخش» بنویس."
            )
            return

    if not query:
        await message.reply(
            "🎵 برای پخش، نام آهنگ را بعد از «پخش» بنویس.\n\n"
            "مثال:\n"
            "پخش محسن یگانه\n"
            "پخش Shape of You"
        )
        return

    chat_id = message.chat.id
    user = message.from_user

    status_msg = await message.reply("🔍 در حال جستجوی موزیک...")

    track = await downloader.extract_info(query)

    if not track:
        await status_msg.edit("❌ موزیکی پیدا نشد.")
        return

    await status_msg.edit(
        f"🎵 **{track.title}**\n"
        f"👤 {track.uploader}\n\n"
        "⬇️ در حال دانلود..."
    )

    filepath = await downloader.download(track)

    if not filepath:
        await status_msg.edit("❌ دانلود موزیک ناموفق بود.")
        return

    queue = await db.get_queue(chat_id)
    position = len(queue) + 1

    item = QueueItem(
        id=None,
        chat_id=chat_id,
        user_id=user.id,
        title=track.title,
        duration=track.duration,
        url=track.webpage_url,
        filepath=filepath,
        requested_by=user.username or user.first_name or str(user.id),
        added_at=datetime.now(),
        position=position,
    )

    await db.add_to_queue(item)

    if not VOICE_CHAT_AVAILABLE:
        await status_msg.edit(
            f"✅ **{track.title}** دانلود شد.\n\n"
            "⚠️ قابلیت ویس‌چت در هاست فعلی در دسترس نیست."
        )
        return

    if not player.is_playing or player.current_chat_id != chat_id:
        success = await play_next(chat_id)

        if success:
            await status_msg.edit(
                f"▶️ **در حال پخش:**\n"
                f"🎵 {track.title}\n"
                f"👤 {track.uploader}"
            )
        else:
            await status_msg.edit(
                f"❌ پخش **{track.title}** شروع نشد."
            )
    else:
        await status_msg.edit(
            f"✅ به صف اضافه شد:\n"
            f"🎵 **{track.title}**\n"
            f"📋 شماره صف: `{position}`"
        )


@app.on_message(
    filters.regex(r"^(?:مکث|pause)$") & filters.group
)
async def persian_pause_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if (
        not player
        or player.current_chat_id != chat_id
        or not player.is_playing
    ):
        await message.reply("❌ موزیکی در حال پخش نیست.")
        return

    if player.is_paused:
        await message.reply("⏸ موزیک از قبل مکث شده است.")
        return

    if await player.pause(chat_id):
        await message.reply("⏸ موزیک مکث شد.")
    else:
        await message.reply("❌ خطا در مکث موزیک.")


@app.on_message(
    filters.regex(r"^(?:ادامه|ادامه پخش|resume)$") & filters.group
)
async def persian_resume_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if (
        not player
        or player.current_chat_id != chat_id
        or not player.is_paused
    ):
        await message.reply(
            "❌ موزیک متوقف‌شده‌ای برای ادامه وجود ندارد."
        )
        return

    if await player.resume(chat_id):
        await message.reply("▶️ پخش ادامه یافت.")
    else:
        await message.reply("❌ خطا در ادامه پخش.")


@app.on_message(
    filters.regex(r"^(?:اتمام|stop)$") & filters.group
)
async def persian_stop_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if not player or player.current_chat_id != chat_id:
        await message.reply("❌ ربات در ویس‌چت نیست.")
        return

    success = await player.stop(chat_id)
    await db.clear_queue(chat_id)

    if success:
        await message.reply("⏹ پخش تمام شد و صف پاک شد.")
    else:
        await message.reply("❌ خطا در اتمام پخش.")


@app.on_message(
    filters.regex(r"^(?:بعدی|skip|next)$") & filters.group
)
async def persian_skip_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if (
        not player
        or player.current_chat_id != chat_id
        or not player.is_playing
    ):
        await message.reply("❌ موزیکی در حال پخش نیست.")
        return

    success = await play_next(chat_id)

    if success:
        await message.reply("⏭ آهنگ بعدی در حال پخش است.")
    else:
        await message.reply("⏭ آهنگ دیگری در صف وجود ندارد.")


@app.on_message(
    filters.regex(r"^(?:صف|queue)$") & filters.group
)
async def persian_queue_cmd(client: Client, message: Message):
    text = await get_queue_text(message.chat.id)
    await message.reply(text)


@app.on_message(
    filters.regex(r"^(?:الان|در حال پخش|now)$") & filters.group
)
async def persian_now_cmd(client: Client, message: Message):
    if (
        not VOICE_CHAT_AVAILABLE
        or not player
        or not player.current_track
        or player.current_chat_id != message.chat.id
    ):
        await message.reply("❌ هیچ موزیکی در حال پخش نیست.")
        return

    track = player.current_track

    duration_str = (
        f"{track.duration // 60}:{track.duration % 60:02d}"
        if track.duration > 0
        else "??:??"
    )

    await message.reply(
        f"🎵 **در حال پخش:**\n"
        f"**{track.title}**\n"
        f"👤 {track.uploader or 'نامشخص'}\n"
        f"⏱ مدت: `{duration_str}`"
    )


@app.on_message(
    filters.regex(r"^(?:صدا|volume)(?:\s+(\d+))?$") & filters.group
)
async def persian_volume_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    if not player:
        await message.reply("❌ پخش‌کننده آماده نیست.")
        return

    value = message.matches[0].group(1)

    if not value:
        await message.reply(
            f"🔊 صدای فعلی: `{player.volume}%`"
        )
        return

    vol = max(0, min(200, int(value)))
    chat_id = message.chat.id

    if player.current_chat_id != chat_id:
        await message.reply(
            "❌ ربات در ویس‌چت این گروه نیست."
        )
        return

    success = await player.set_volume(chat_id, vol)

    if success:
        await db.update_chat_settings(
            chat_id,
            volume=vol
        )
        await message.reply(
            f"🔊 صدا روی `{vol}%` تنظیم شد."
        )
    else:
        await message.reply(
            "❌ خطا در تنظیم صدا."
        )


@app.on_message(
    filters.regex(r"^(?:آیدی|id)$") & filters.group
)
async def persian_id_cmd(client: Client, message: Message):
    await message.reply(
        f"🆔 **آیدی گروه:** `{message.chat.id}`\n"
        f"👤 **آیدی شما:** `{message.from_user.id}`"
    )


@app.on_message(
    filters.regex(r"^(?:کمک|help)$")
)
async def persian_help_cmd(client: Client, message: Message):
    await message.reply(
        "🎵 **راهنمای ربات موزیک**\n\n"
        "▶️ `پخش نام آهنگ` — جستجو و پخش\n"
        "⏸ `مکث` — توقف موقت\n"
        "▶️ `ادامه` — ادامه پخش\n"
        "⏹ `اتمام` — پایان پخش\n"
        "⏭ `بعدی` — آهنگ بعدی\n"
        "📋 `صف` — نمایش صف\n"
        "🎵 `الان` — آهنگ فعلی\n"
        "🔊 `صدا 100` — تنظیم صدا\n"
        "🆔 `آیدی` — نمایش آیدی\n"
        "❓ `کمک` — نمایش راهنما"
    )


# ============================================================
# English aliases
# ============================================================


@app.on_message(
    filters.command("start")
)
async def start_cmd(client: Client, message: Message):
    await message.reply(
        "🎵 **ربات موزیک آماده است.**\n\n"
        "برای شروع بنویس:\n"
        "`پخش نام آهنگ`\n\n"
        "برای دیدن دستورات:\n"
        "`کمک`"
    )


logger.info("✅ Persian music handlers loaded")
