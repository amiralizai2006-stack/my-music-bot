"""
Command handlers for Telegram Music Bot.
Works with or without PyTgCalls (voice chat).
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import config, VOICE_CHAT_AVAILABLE
from database import db, QueueItem
from player import downloader, MusicPlayer, TrackInfo
from optional_deps import (
    PyTgCalls, Update, AudioVideoPiped, AudioPiped, 
    NoActiveGroupCall, GroupCallNotFound, pytgcalls
)

logger = logging.getLogger(__name__)

# Command prefix
PREFIX = config.command_prefix

# Global instances (set by main.py)
app: Optional[Client] = None
pytgcalls_client: Optional[PyTgCalls] = None
player: Optional[MusicPlayer] = None
shutdown_event: Optional[asyncio.Event] = None


def set_bot_instances(
    app_instance: Client,
    pytgcalls_instance,
    player_instance: MusicPlayer,
    shutdown_evt: asyncio.Event
):
    """Set global instances from main.py."""
    global app, pytgcalls_client, player, shutdown_event
    app = app_instance
    pytgcalls_client = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown_evt


# Helper functions
def is_admin(user_id: int) -> bool:
    return user_id in config.admin_ids or config.admin_ids == []


async def get_queue_text(chat_id: int) -> str:
    queue = await db.get_queue(chat_id)
    if not queue:
        return "📭 صف پخش خالی است."
    
    text = "📋 **صف پخش:**\n\n"
    for i, item in enumerate(queue[:10], 1):
        duration_str = f"{item.duration // 60}:{item.duration % 60:02d}" if item.duration > 0 else "??:??"
        text += f"{i}. **{item.title}** (`{duration_str}`) — @{item.requested_by}\n"
    
    if len(queue) > 10:
        text += f"\n... و {len(queue) - 10} موزیک دیگر"
    
    return text


async def play_next(chat_id: int):
    """Play next track in queue."""
    if not VOICE_CHAT_AVAILABLE or not player:
        logger.warning(f"play_next called but voice chat not available")
        return
    
    next_item = await db.get_next_in_queue(chat_id)
    if not next_item:
        # Queue empty, schedule auto-leave
        settings = await db.get_chat_settings(chat_id)
        player._schedule_auto_leave(chat_id, settings.get("auto_leave_timeout", config.auto_leave_timeout))
        return
    
    # Download if not already
    if not next_item.filepath or not Path(next_item.filepath).exists():
        track = TrackInfo(
            title=next_item.title,
            duration=next_item.duration,
            url=next_item.url,
            webpage_url=next_item.url,
            thumbnail="",
            uploader=next_item.requested_by,
            filepath=next_item.filepath
        )
        filepath = await downloader.download(track)
        if filepath:
            next_item.filepath = filepath
    
    if next_item.filepath:
        success = await player.play(chat_id, TrackInfo(
            title=next_item.title,
            duration=next_item.duration,
            url=next_item.url,
            webpage_url=next_item.url,
            thumbnail="",
            uploader=next_item.requested_by,
            filepath=next_item.filepath
        ))
        if success:
            await db.remove_from_queue(next_item.id)
            await db.reorder_queue(chat_id)
        else:
            # Failed to play, remove and try next
            await db.remove_from_queue(next_item.id)
            await db.reorder_queue(chat_id)
            await play_next(chat_id)
    else:
        # Download failed, remove and try next
        await db.remove_from_queue(next_item.id)
        await db.reorder_queue(chat_id)
        await play_next(chat_id)


# PyTgCalls event handlers (only register if available)
if VOICE_CHAT_AVAILABLE and pytgcalls_client:
    @pytgcalls_client.on_stream_end()
    async def on_stream_end(client: PyTgCalls, update: Update):
        """Handle stream end - play next in queue."""
        chat_id = update.chat_id
        settings = await db.get_chat_settings(chat_id)
        repeat_mode = settings.get("repeat_mode", "off")
        
        if repeat_mode == "one" and player.current_track:
            # Replay current track
            await player.play(chat_id, player.current_track)
        elif repeat_mode == "all":
            # Add current track back to queue end
            if player.current_track:
                queue = await db.get_queue(chat_id)
                position = len(queue) + 1
                item = QueueItem(
                    id=None,
                    chat_id=chat_id,
                    user_id=0,
                    title=player.current_track.title,
                    duration=player.current_track.duration,
                    url=player.current_track.url,
                    filepath=player.current_track.filepath,
                    requested_by="auto-repeat",
                    added_at=datetime.now(),
                    position=position
                )
                await db.add_to_queue(item)
            await play_next(chat_id)
        else:
            # Normal: play next
            await play_next(chat_id)

    @pytgcalls_client.on_kicked()
    async def on_kicked(client: PyTgCalls, chat_id: int):
        """Bot was kicked from call."""
        if player:
            player.current_chat_id = None
            player.current_track = None
            player.is_playing = False
        logger.info(f"Kicked from chat {chat_id}")

    @pytgcalls_client.on_left()
    async def on_left(client: PyTgCalls, chat_id: int):
        """Bot left call."""
        if player:
            player.current_chat_id = None
            player.current_track = None
            player.is_playing = False
        logger.info(f"Left chat {chat_id}")


# Command handlers
@app.on_message(filters.command("start", prefixes=PREFIX) & filters.private)
async def start_cmd(client: Client, message: Message):
    if VOICE_CHAT_AVAILABLE:
        text = """
🎵 **ربات موزیک تلگرام** 🎵

این ربات می‌تواند در ویس کال‌های گروهی آهنگ پخش کند.

**دستورات اصلی:**
• `/play <نام یا لینک>` - اضافه کردن به صف و پخش
• `/queue` - نمایش صف پخش
• `/skip` - رد کردن آهنگ فعلی
• `/pause` - توقف موقت
• `/resume` - ادامه پخش
• `/stop` - توقف و خروج از کال
• `/volume <0-200>` - تنظیم صدا
• `/now` - آهنگ در حال پخش
• `/help` - راهنمای کامل

**نکات:**
• ربات باید ادمین گروه باشد
• برای ویس کال گروهی، ربات را به گروه اضافه کنید و ادمین کنید
• لینک‌های یوتیوب، ساوندکلاود و جستجوی متنی پشتیبانی می‌شود
"""
    else:
        text = """
🎵 **ربات موزیک تلگرام** (حالت محدود) 🎵

⚠️ **ویس چت در این پلتفرم پشتیبانی نمی‌شود** (Android/Termux)
فقط قابلیت دانلود موزیک فعال است.

**دستورات موجود:**
• `/play <نام یا لینک>` - جستجو و دانلود موزیک
• `/queue` - نمایش صف دانلود
• `/help` - راهنمای کامل

**نکات:**
• فایل‌های دانلود شده در پوشه `downloads/` ذخیره می‌شوند
• برای پخش در ویس کال، ربات را روی سرور لینوکس/ویندوز/مک اجرا کنید
"""
    await message.reply(text)


@app.on_message(filters.command("help", prefixes=PREFIX))
async def help_cmd(client: Client, message: Message):
    if VOICE_CHAT_AVAILABLE:
        text = """
🎵 **راهنمای کامل ربات موزیک**

**دستورات پخش:**
• `/play <لینک/متن>` - جستجو و اضافه کردن به صف
• `/play <لینک یوتیوب>` - پخش مستقیم از یوتیوب

**کنترل صف:**
• `/queue` - نمایش صف پخش
• `/clear` - پاک کردن صف (ادمین)
• `/shuffle` - شافل کردن صف (ادمین)
• `/remove <شماره>` - حذف از صف

**کنترل پخش:**
• `/skip` - رد کردن آهنگ فعلی
• `/pause` - توقف موقت
• `/resume` - ادامه پخش
• `/stop` - توقف کامل و خروج
• `/restart` - پخش مجدد آهنگ فعلی

**تنظیمات:**
• `/volume <0-200>` - تنظیم میزان صدا
• `/repeat <off/one/all>` - تکرار (آدمن)
• `/autoleave <ثانیه>` - خروج خودکار بعد از بی‌فعالیتی

**اطلاعات:**
• `/now` - اطلاعات آهنگ در حال پخش

**ادمین‌ها:**
• `/leave` - اجبار به خروج (ادمین)
• `/ban <یوزر>` - بن کردن کاربر از استفاده (ادمین)
• `/unban <یوزر>` - آنبن کردن (ادمین)

**نحوه استفاده:**
1. ربات را به گروه اضافه کنید
2. ربات را ادمین گروه کنید (حداقل مدیریت ویس کال)
3. به ویس کال گروهی بپیوندید
4. از `/play` برای اضافه کردن موزیک استفاده کنید
"""
    else:
        text = """
🎵 **راهنمای ربات موزیک (حالت محدود - Termux/Android)**

⚠️ **ویس چت پشتیبانی نمی‌شود** - فقط دانلود موزیک فعال است

**دستورات موجود:**
• `/play <نام یا لینک>` - جستجو و دانلود موزیک
• `/queue` - نمایش صف دانلود
• `/clear` - پاک کردن صف (ادمین)

**فایل‌های دانلود شده:**
موزیک‌ها در پوشه `downloads/` به فرمت MP3 ذخیره می‌شوند.

**برای استفاده کامل (ویس کال):**
ربات را روی سرور لینوکس/ویندوز/مک اجرا کنید:
```bash
git clone https://github.com/mehrshadharry/tg-music-bot.git
cd tg-music-bot
cp config.example.py config.py
# ویرایش config.py
./run.sh
```
"""
    await message.reply(text)


@app.on_message(filters.command("play", prefixes=PREFIX) & filters.group)
async def play_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ لطفاً نام آهنگ یا لینک را وارد کنید.\nمثال: `/play shape of you` یا `/play https://youtube.com/...`")
        return
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    user = message.from_user
    
    # Send searching message
    status_msg = await message.reply("🔍 در حال جستجو...")
    
    # Extract info
    track = await downloader.extract_info(query)
    if not track:
        await status_msg.edit("❌ موزیکی یافت نشد. لینک یا نام دیگری امتحان کنید.")
        return
    
    # Download
    await status_msg.edit(f"⬇️ در حال دانلود: **{track.title}**...")
    filepath = await downloader.download(track)
    if not filepath:
        await status_msg.edit("❌ خطا در دانلود موزیک.")
        return
    
    # Add to queue
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
        requested_by=user.username or user.first_name,
        added_at=datetime.now(),
        position=position
    )
    
    await db.add_to_queue(item)
    
    if VOICE_CHAT_AVAILABLE:
        # If nothing playing, start playback
        if not player.is_playing or player.current_chat_id != chat_id:
            await status_msg.edit(f"▶️ در حال پخش: **{track.title}**")
            await play_next(chat_id)
        else:
            await status_msg.edit(f"✅ به صف اضافه شد: **{track.title}** (موقعیت: {position})")
    else:
        await status_msg.edit(f"✅ دانلود شد: **{track.title}**\n📁 ذخیره شده در: `{filepath}`\n⚠️ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")


@app.on_message(filters.command("queue", prefixes=PREFIX) & filters.group)
async def queue_cmd(client: Client, message: Message):
    text = await get_queue_text(message.chat.id)
    
    # Add inline buttons for queue control
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 شافل", callback_data="queue_shuffle"),
         InlineKeyboardButton("🗑 پاک کردن", callback_data="queue_clear")],
        [InlineKeyboardButton("⏭ رد کردن", callback_data="queue_skip"),
         InlineKeyboardButton("⏸ توقف", callback_data="queue_pause")]
    ])
    
    if not VOICE_CHAT_AVAILABLE:
        # Remove voice chat buttons in limited mode
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 پاک کردن", callback_data="queue_clear")]
        ])
    
    await message.reply(text, reply_markup=keyboard)


@app.on_message(filters.command("skip", prefixes=PREFIX) & filters.group)
async def skip_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")
        return
    
    chat_id = message.chat.id
    if not player or player.current_chat_id != chat_id or not player.is_playing:
        await message.reply("❌ هیچ موزیکی در حال پخش نیست.")
        return
    
    # Just trigger next track by stopping current
    await pytgcalls_client.change_stream(chat_id, AudioVideoPiped(""))
    await message.reply("⏭ رد شد. در حال پخش موزیک بعدی...")


@app.on_message(filters.command("pause", prefixes=PREFIX) & filters.group)
async def pause_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")
        return
    
    chat_id = message.chat.id
    if not player or player.current_chat_id != chat_id or not player.is_playing:
        await message.reply("❌ هیچ موزیکی در حال پخش نیست.")
        return
    
    if player.is_paused:
        await message.reply("❌ موزیک قبلاً متوقف شده.")
        return
    
    success = await player.pause(chat_id)
    if success:
        await message.reply("⏸ موزیک متوقف شد.")
    else:
        await message.reply("❌ خطا در توقف موزیک.")


@app.on_message(filters.command("resume", prefixes=PREFIX) & filters.group)
async def resume_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")
        return
    
    chat_id = message.chat.id
    if not player or player.current_chat_id != chat_id or not player.is_paused:
        await message.reply("❌ موزیکی متوقف شده برای ادامه وجود ندارد.")
        return
    
    success = await player.resume(chat_id)
    if success:
        await message.reply("▶️ موزیک ادامه یافت.")
    else:
        await message.reply("❌ خطا در ادامه موزیک.")


@app.on_message(filters.command("stop", prefixes=PREFIX) & filters.group)
async def stop_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")
        return
    
    chat_id = message.chat.id
    if not player or player.current_chat_id != chat_id:
        await message.reply("❌ ربات در این گروه در کال نیست.")
        return
    
    success = await player.stop(chat_id)
    await db.clear_queue(chat_id)
    
    if success:
        await message.reply("⏹ موزیک متوقف شد و ربات از کال خارج شد. صف هم پاک شد.")
    else:
        await message.reply("❌ خطا در توقف.")


@app.on_message(filters.command("now", prefixes=PREFIX) & filters.group)
async def now_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE or not player or not player.current_track or player.current_chat_id != message.chat.id:
        await message.reply("❌ هیچ موزیکی در حال پخش نیست.")
        return
    
    track = player.current_track
    status = player.get_status()
    
    duration_str = f"{track.duration // 60}:{track.duration % 60:02d}" if track.duration > 0 else "??:??"
    
    text = f"""
🎵 **در حال پخش:**
**{track.title}**
⏱ مدت: `{duration_str}`
🔊 صدا: `{status['volume']}%`
🔁 تکرار: `{status['repeat_mode']}`
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ رد", callback_data="queue_skip"),
         InlineKeyboardButton("⏸ توقف", callback_data="queue_pause")],
        [InlineKeyboardButton("🔊 صدا +", callback_data="vol_up"),
         InlineKeyboardButton("🔉 صدا -", callback_data="vol_down")]
    ])
    
    await message.reply(text, reply_markup=keyboard)


@app.on_message(filters.command("volume", prefixes=PREFIX) & filters.group)
async def volume_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")
        return
    
    if len(message.command) < 2:
        await message.reply(f"🔊 صدا فعلی: `{player.volume}%`\nاستفاده: `/volume <0-200>`")
        return
    
    try:
        vol = int(message.command[1])
        vol = max(0, min(200, vol))
    except ValueError:
        await message.reply("❌ عدد نامعتبر. از 0 تا 200 وارد کنید.")
        return
    
    chat_id = message.chat.id
    if not player or player.current_chat_id != chat_id:
        await message.reply("❌ ربات در این گروه در کال نیست.")
        return
    
    success = await player.set_volume(chat_id, vol)
    await db.update_chat_settings(chat_id, volume=vol)
    
    if success:
        await message.reply(f"🔊 صدا روی `{vol}%` تنظیم شد.")
    else:
        await message.reply("❌ خطا در تنظیم صدا.")


@app.on_message(filters.command("repeat", prefixes=PREFIX) & filters.group)
async def repeat_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ فقط ادمین‌ها می‌توانند تکرار را تغییر دهند.")
        return
    
    if len(message.command) < 2:
        settings = await db.get_chat_settings(message.chat.id)
        await message.reply(f"🔁 حالت تکرار فعلی: `{settings.get('repeat_mode', 'off')}`\nاستفاده: `/repeat <off|one|all>`")
        return
    
    mode = message.command[1].lower()
    if mode not in ["off", "one", "all"]:
        await message.reply("❌ حالت نامعتبر. گزینه‌ها: `off`, `one`, `all`")
        return
    
    if player:
        player.repeat_mode = mode
    await db.update_chat_settings(message.chat.id, repeat_mode=mode)
    await message.reply(f"🔁 حالت تکرار روی `{mode}` تنظیم شد.")


@app.on_message(filters.command("clear", prefixes=PREFIX) & filters.group)
async def clear_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ فقط ادمین‌ها می‌توانند صف را پاک کنند.")
        return
    
    count = await db.clear_queue(message.chat.id)
    await message.reply(f"🗑 صف پاک شد ({count} آیتم حذف شد).")


@app.on_message(filters.command("leave", prefixes=PREFIX) & filters.group)
async def leave_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        await message.reply("❌ فقط ادمین‌ها می‌توانند ربات را خارج کنند.")
        return
    
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.")
        return
    
    chat_id = message.chat.id
    if not player or player.current_chat_id != chat_id:
        await message.reply("❌ ربات در این گروه در کال نیست.")
        return
    
    await player.stop(chat_id)
    await db.clear_queue(chat_id)
    await message.reply("👋 ربات از کال خارج شد و صف پاک شد.")


# Callback query handlers
@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    if not VOICE_CHAT_AVAILABLE and query.data != "queue_clear":
        await query.answer("❌ ویس چت در این پلتفرم پشتیبانی نمی‌شود.", show_alert=True)
        return
    
    chat_id = query.message.chat.id
    data = query.data
    
    if data == "queue_skip":
        if player and player.current_chat_id == chat_id and player.is_playing:
            await pytgcalls_client.change_stream(chat_id, AudioVideoPiped(""))
            await query.answer("⏭ رد شد")
        else:
            await query.answer("❌ موزیکی در حال پخش نیست", show_alert=True)
    
    elif data == "queue_pause":
        if player and player.current_chat_id == chat_id and player.is_playing:
            await player.pause(chat_id)
            await query.answer("⏸ متوقف شد")
        elif player and player.current_chat_id == chat_id and player.is_paused:
            await player.resume(chat_id)
            await query.answer("▶️ ادامه یافت")
        else:
            await query.answer("❌ موزیکی در حال پخش نیست", show_alert=True)
    
    elif data == "queue_clear":
        if is_admin(query.from_user.id):
            count = await db.clear_queue(chat_id)
            await query.answer(f"🗑 صف پاک شد ({count} آیتم)")
            await query.message.edit_text(await get_queue_text(chat_id), reply_markup=query.message.reply_markup)
        else:
            await query.answer("❌ فقط ادمین‌ها", show_alert=True)
    
    elif data == "queue_shuffle":
        if is_admin(query.from_user.id):
            await query.answer("🔀 شافل شد (نیاز به پیاده‌سازی)")
        else:
            await query.answer("❌ فقط ادمین‌ها", show_alert=True)
    
    elif data == "vol_up":
        if player and player.current_chat_id == chat_id:
            new_vol = min(200, player.volume + 10)
            await player.set_volume(chat_id, new_vol)
            await db.update_chat_settings(chat_id, volume=new_vol)
            await query.answer(f"🔊 صدا: {new_vol}%")
    
    elif data == "vol_down":
        if player and player.current_chat_id == chat_id:
            new_vol = max(0, player.volume - 10)
            await player.set_volume(chat_id, new_vol)
            await db.update_chat_settings(chat_id, volume=new_vol)
            await query.answer(f"🔉 صدا: {new_vol}%")