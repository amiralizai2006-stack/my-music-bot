import logging
import re
from pathlib import Path

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from player import TrackInfo

logger = logging.getLogger(__name__)

bot = None
player = None
pytgcalls = None
shutdown_event = None

# نقش‌های موقت تا وقتی سیستم مدیریت کاربران/دیتابیس را
# در مرحله بعد اضافه کنیم.
music_admins = set()
music_owner_id = None

# --------------------------------------------------
# اتصال نمونه‌های اصلی پروژه
# --------------------------------------------------

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


# --------------------------------------------------
# ابزارها
# --------------------------------------------------

def _user_name(user):
    if not user:
        return "کاربر"

    return (
        user.first_name
        or user.username
        or "کاربر"
    )


def _user_rank(user_id: int) -> str:
    if music_owner_id == user_id:
        return "👑 مالک موزیک"

    if user_id in music_admins:
        return "🎵 مدیر موزیک"

    return "👤 کاربر"


def _player_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏸️ مکث",
                    callback_data="music_pause",
                ),
                InlineKeyboardButton(
                    "▶️ ادامه",
                    callback_data="music_resume",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏮️ قبلی",
                    callback_data="music_previous",
                ),
                InlineKeyboardButton(
                    "⏭️ بعدی",
                    callback_data="music_next",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏩ جلو 10",
                    callback_data="music_forward_10",
                ),
                InlineKeyboardButton(
                    "⏪ عقب 10",
                    callback_data="music_backward_10",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏹️ اتمام",
                    callback_data="music_stop",
                ),
                InlineKeyboardButton(
                    "🔊 صدا",
                    callback_data="music_volume",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎧 وضعیت",
                    callback_data="music_status",
                ),
            ],
        ]
    )


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


async def _call_player_method(
    method_name,
    chat_id,
    *args,
):
    if player is None:
        return False

    method = getattr(
        player,
        method_name,
        None,
    )

    if method is None:
        logger.warning(
            "PLAYER METHOD NOT AVAILABLE | %s",
            method_name,
        )
        return False

    try:
        return await method(
            chat_id,
            *args,
        )

    except Exception:
        logger.exception(
            "PLAYER METHOD ERROR | %s",
            method_name,
        )
        return False


# --------------------------------------------------
# دانلود و پخش
# --------------------------------------------------

async def _download_and_play(
    message: Message,
    track: TrackInfo,
):

    logger.info(
        "========== DOWNLOAD PIPELINE START =========="
    )

    if player is None:
        await message.reply_text(
            "❌ پخش‌کننده آماده نیست."
        )
        return

    downloader = getattr(
        player,
        "downloader",
        None,
    )

    if downloader is None:
        await message.reply_text(
            "❌ دانلودر آماده نیست."
        )
        return

    await message.reply_text(
        "⏳ در حال دانلود..."
    )

    try:
        logger.info(
            "CALLING DOWNLOADER.DOWNLOAD | title=%s",
            track.title,
        )

        filepath = await downloader.download(
            track
        )

        logger.info(
            "DOWNLOADER RETURNED | filepath=%r",
            filepath,
        )

        if not filepath:
            await message.reply_text(
                "❌ دانلود انجام نشد.\n\n"
                "جزئیات خطا در Logs ثبت شد."
            )
            return

        track.filepath = filepath

        ok = await player.play(
            message.chat.id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ آهنگ دانلود شد ولی پخش نشد."
            )
            return

        await message.reply_text(
            f"▶️ در حال پخش\n\n"
            f"🎵 {track.title}\n"
            f"👤 {track.artist}",
            reply_markup=_player_keyboard(),
        )

        logger.info(
            "========== DOWNLOAD PIPELINE SUCCESS =========="
        )

    except Exception as e:
        logger.exception(
            "DOWNLOAD PIPELINE ERROR | %s: %s",
            type(e).__name__,
            str(e),
        )

        await message.reply_text(
            f"❌ خطای پخش:\n"
            f"{type(e).__name__}: {e}"
        )


# --------------------------------------------------
# ثبت دستورات
# --------------------------------------------------

def register_handlers():

    if bot is None:
        raise RuntimeError(
            "Bot instance has not been set"
        )

    logger.info(
        "REGISTERING TELEGRAM HANDLERS"
    )

    # ----------------------------------------------
    # شروع
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*شروع\s*$")
    )
    async def start_farsi(client, message):

        await message.reply_text(
            "🎵 سلام!\n\n"
            "به تیم موزیک سایلنت خوش آمدید.\n\n"
            "🎧 برای پخش:\n"
            "پخش نام آهنگ\n\n"
            "یا روی فایل صوتی ریپلای کن و بنویس:\n"
            "پخش"
        )

    # ----------------------------------------------
    # کمک
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*کمک\s*$")
    )
    async def help_handler(client, message):

        await message.reply_text(
            "🎵 راهنمای ربات موزیک\n\n"

            "🎵 پخش نام آهنگ\n"
            "⏸️ مکث\n"
            "▶️ ادامه\n"
            "⏹️ اتمام\n"
            "⏭️ بعدی\n"
            "⏮️ قبلی\n"
            "⏩ جلو 10\n"
            "⏪ عقب 10\n"
            "🔊 صدا\n\n"

            "📞 شروع کال\n"
            "📞 پایان کال\n"
            "💬 کامنت کال فعال\n"
            "💬 کامنت کال غیر فعال\n\n"

            "🆔 آیدی\n"
            "🎧 وضعیت"
        )

    # ----------------------------------------------
    # پخش
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*پخش(?:\s+(.+))?\s*$"
        )
    )
    async def play_handler(client, message):

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
            "PLAY RECEIVED | chat=%s | query=%r",
            message.chat.id,
            query,
        )

        # پخش فایل ریپلای‌شده
        if not query:

            media = _get_reply_audio(
                message
            )

            if not media:
                await message.reply_text(
                    "❌ روی فایل آهنگ ریپلای کن و «پخش» بنویس."
                )
                return

            await message.reply_text(
                "⏳ در حال آماده‌سازی آهنگ..."
            )

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

                file_name = (
                    getattr(
                        media,
                        "file_name",
                        None,
                    )
                    or f"audio_{message.id}.mp3"
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
                    f"👤 {track.artist}",
                    reply_markup=_player_keyboard(),
                )

            except Exception as e:

                logger.exception(
                    "REPLY PLAY ERROR | %s: %s",
                    type(e).__name__,
                    str(e),
                )

                await message.reply_text(
                    f"❌ خطای پخش:\n"
                    f"{type(e).__name__}: {e}"
                )

            return

        # جستجوی آهنگ
        await message.reply_text(
            f"🔎 در حال جستجو...\n"
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
                f"❌ خطای پخش:\n"
                f"{type(e).__name__}: {e}"
            )

    # ----------------------------------------------
    # مکث
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*مکث\s*$")
    )
    async def pause_handler(client, message):

        ok = await _call_player_method(
            "pause",
            message.chat.id,
        )

        await message.reply_text(
            "⏸️ پخش مکث شد."
            if ok
            else "❌ مکث انجام نشد."
        )

    # ----------------------------------------------
    # ادامه
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*ادامه\s*$")
    )
    async def resume_handler(client, message):

        ok = await _call_player_method(
            "resume",
            message.chat.id,
        )

        await message.reply_text(
            "▶️ پخش ادامه پیدا کرد."
            if ok
            else "❌ ادامه پخش انجام نشد."
        )

    # ----------------------------------------------
    # اتمام
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*اتمام\s*$")
    )
    async def stop_handler(client, message):

        ok = await _call_player_method(
            "stop",
            message.chat.id,
        )

        await message.reply_text(
            "⏹️ پخش متوقف شد."
            if ok
            else "❌ توقف انجام نشد."
        )

    # ----------------------------------------------
    # صدا
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*صدا(?:\s+(\d{1,3}))?\s*$"
        )
    )
    async def volume_handler(client, message):

        match = re.match(
            r"^\s*صدا(?:\s+(\d{1,3}))?\s*$",
            message.text or "",
        )

        volume = 100

        if match and match.group(1):
            volume = int(match.group(1))

        ok = await _call_player_method(
            "set_volume",
            message.chat.id,
            volume,
        )

        await message.reply_text(
            f"🔊 صدا روی {volume}% تنظیم شد."
            if ok
            else "❌ تغییر صدا انجام نشد."
        )

    # ----------------------------------------------
    # جلو / عقب
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*جلو\s+(\d+)\s*$"
        )
    )
    async def forward_handler(client, message):

        match = re.match(
            r"^\s*جلو\s+(\d+)\s*$",
            message.text or "",
        )

        seconds = int(match.group(1))

        ok = await _call_player_method(
            "forward",
            message.chat.id,
            seconds,
        )

        await message.reply_text(
            f"⏩ {seconds} ثانیه جلو رفت."
            if ok
            else "❌ جلو بردن فعلاً آماده نیست."
        )

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*عقب\s+(\d+)\s*$"
        )
    )
    async def backward_handler(client, message):

        match = re.match(
            r"^\s*عقب\s+(\d+)\s*$",
            message.text or "",
        )

        seconds = int(match.group(1))

        ok = await _call_player_method(
            "backward",
            message.chat.id,
            seconds,
        )

        await message.reply_text(
            f"⏪ {seconds} ثانیه عقب رفت."
            if ok
            else "❌ عقب بردن فعلاً آماده نیست."
        )

    # ----------------------------------------------
    # بعدی / قبلی
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*بعدی\s*$")
    )
    async def next_handler(client, message):

        ok = await _call_player_method(
            "next",
            message.chat.id,
        )

        await message.reply_text(
            "⏭️ آهنگ بعدی."
            if ok
            else "❌ آهنگ بعدی فعلاً آماده نیست."
        )

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*قبلی\s*$")
    )
    async def previous_handler(client, message):

        ok = await _call_player_method(
            "previous",
            message.chat.id,
        )

        await message.reply_text(
            "⏮️ آهنگ قبلی."
            if ok
            else "❌ آهنگ قبلی فعلاً آماده نیست."
        )

    # ----------------------------------------------
    # آیدی
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*آیدی\s*$")
    )
    async def id_handler(client, message):

        user = message.from_user

        if not user:
            return

        rank = _user_rank(
            user.id
        )

        status = "❌ خارج از ویس کال"

        if player:
            try:
                current_chat = (
                    player.current_chat_id
                )

                if current_chat == message.chat.id:
                    status = "🎧 در ویس کال"

            except Exception:
                pass

        username = (
            f"@{user.username}"
            if user.username
            else "ندارد"
        )

        text = (
            "👤 اطلاعات شما\n\n"
            f"📛 نام: {_user_name(user)}\n"
            f"🔗 یوزرنیم: {username}\n"
            f"🆔 آیدی عددی: {user.id}\n"
            f"👑 رتبه: {rank}\n"
            f"🎧 وضعیت: {status}\n\n"
            "🟢 تیم سایلنت همیشه آنلاین می‌باشد."
        )

        try:
            if user.photo:
                await client.send_photo(
                    message.chat.id,
                    user.photo.big_file_id,
                    caption=text,
                )
                return
        except Exception:
            logger.exception(
                "PROFILE PHOTO SEND ERROR"
            )

        await message.reply_text(
            text
        )

    # ----------------------------------------------
    # وضعیت
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(r"^\s*وضعیت\s*$")
    )
    async def status_handler(client, message):

        if player is None:
            await message.reply_text(
                "🔴 پخش‌کننده آماده نیست."
            )
            return

        try:
            status = player.get_status()

            track = (
                status.get("current_track")
                or "هیچ آهنگی"
            )

            playing = (
                "▶️ در حال پخش"
                if status.get("is_playing")
                else "⏸️ متوقف/مکث"
            )

            await message.reply_text(
                "🎧 وضعیت موزیک\n\n"
                f"🎵 آهنگ: {track}\n"
                f"📡 وضعیت: {playing}\n"
                f"🔊 صدا: {status.get('volume', 100)}%\n\n"
                "🟢 تیم سایلنت همیشه آنلاین می‌باشد.",
                reply_markup=_player_keyboard(),
            )

        except Exception:
            logger.exception(
                "STATUS ERROR"
            )

            await message.reply_text(
                "❌ دریافت وضعیت انجام نشد."
            )

    # ----------------------------------------------
    # ترفیع موزیک
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*ترفیع موزیک\s*$"
        )
    )
    async def promote_music(client, message):

        if not message.reply_to_message:
            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )
            return

        user = (
            message.reply_to_message.from_user
        )

        if not user:
            await message.reply_text(
                "❌ کاربر پیدا نشد."
            )
            return

        music_admins.add(
            user.id
        )

        await message.reply_text(
            f"👑 {_user_name(user)}\n\n"
            "🎵 به مدیر موزیک ارتقا پیدا کرد."
        )

    # ----------------------------------------------
    # عزل موزیک
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*عزل موزیک\s*$"
        )
    )
    async def demote_music(client, message):

        if not message.reply_to_message:
            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )
            return

        user = (
            message.reply_to_message.from_user
        )

        if not user:
            return

        music_admins.discard(
            user.id
        )

        await message.reply_text(
            f"👤 {_user_name(user)}\n\n"
            "از مدیران موزیک عزل شد."
        )

    # ----------------------------------------------
    # مالک موزیک
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*مالک موزیک\s*$"
        )
    )
    async def owner_music(client, message):

        global music_owner_id

        if not message.reply_to_message:
            await message.reply_text(
                "❌ روی پیام کاربر ریپلای کن."
            )
            return

        user = (
            message.reply_to_message.from_user
        )

        if not user:
            return

        music_owner_id = user.id

        await message.reply_text(
            f"👑 {_user_name(user)}\n\n"
            "مالک موزیک شد."
        )

    # ----------------------------------------------
    # شروع کال
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*شروع کال\s*$"
        )
    )
    async def start_call_handler(client, message):

        ok = await _call_player_method(
            "start_call",
            message.chat.id,
        )

        await message.reply_text(
            "📞 شروع کال انجام شد."
            if ok
            else "❌ شروع کال فعلاً به کنترل کال متصل نشده است."
        )

    # ----------------------------------------------
    # پایان کال
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*پایان کال\s*$"
        )
    )
    async def end_call_handler(client, message):

        ok = await _call_player_method(
            "end_call",
            message.chat.id,
        )

        if not ok:
            ok = await _call_player_method(
                "stop",
                message.chat.id,
            )

        await message.reply_text(
            "📞 کال پایان یافت."
            if ok
            else "❌ پایان کال انجام نشد."
        )

    # ----------------------------------------------
    # کامنت کال
    # ----------------------------------------------

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*کامنت کال فعال\s*$"
        )
    )
    async def call_comment_on(client, message):

        ok = await _call_player_method(
            "enable_call_comments",
            message.chat.id,
        )

        await message.reply_text(
            "💬 کامنت کال فعال شد."
            if ok
            else "💬 دستور ثبت شد؛ کنترل کامنت کال هنوز به پلیر متصل نشده است."
        )

    @bot.on_message(
        filters.text
        & filters.regex(
            r"^\s*کامنت کال غیر فعال\s*$"
        )
    )
    async def call_comment_off(client, message):

        ok = await _call_player_method(
            "disable_call_comments",
            message.chat.id,
        )

        await message.reply_text(
            "💬 کامنت کال غیر فعال شد."
            if ok
            else "💬 دستور ثبت شد؛ کنترل کامنت کال هنوز به پلیر متصل نشده است."
        )

    # ----------------------------------------------
    # Callback دکمه‌های پلیر
    # ----------------------------------------------

    @bot.on_callback_query(
        filters.regex(
            r"^music_(.+)$"
        )
    )
    async def player_callback(
        client,
        callback: CallbackQuery,
    ):

        data = callback.data

        await callback.answer()

        if player is None:
            await callback.message.reply_text(
                "❌ پخش‌کننده آماده نیست."
            )
            return

        chat_id = callback.message.chat.id

        if data == "music_pause":

            ok = await _call_player_method(
                "pause",
                chat_id,
            )

            await callback.message.edit_text(
                "⏸️ موزیک مکث شد."
                if ok
                else "❌ مکث انجام نشد.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_resume":

            ok = await _call_player_method(
                "resume",
                chat_id,
            )

            await callback.message.edit_text(
                "▶️ پخش ادامه پیدا کرد."
                if ok
                else "❌ ادامه پخش انجام نشد.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_stop":

            ok = await _call_player_method(
                "stop",
                chat_id,
            )

            await callback.message.edit_text(
                "⏹️ پخش اتمام یافت."
                if ok
                else "❌ توقف انجام نشد.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_next":

            ok = await _call_player_method(
                "next",
                chat_id,
            )

            await callback.message.edit_text(
                "⏭️ رفتن به آهنگ بعدی."
                if ok
                else "❌ آهنگ بعدی هنوز به صف پخش متصل نیست.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_previous":

            ok = await _call_player_method(
                "previous",
                chat_id,
            )

            await callback.message.edit_text(
                "⏮️ برگشت به آهنگ قبلی."
                if ok
                else "❌ آهنگ قبلی هنوز به صف پخش متصل نیست.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_forward_10":

            ok = await _call_player_method(
                "forward",
                chat_id,
                10,
            )

            await callback.message.edit_text(
                "⏩ ۱۰ ثانیه جلو رفت."
                if ok
                else "❌ جلو بردن هنوز به پلیر متصل نیست.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_backward_10":

            ok = await _call_player_method(
                "backward",
                chat_id,
                10,
            )

            await callback.message.edit_text(
                "⏪ ۱۰ ثانیه عقب رفت."
                if ok
                else "❌ عقب بردن هنوز به پلیر متصل نیست.",
                reply_markup=_player_keyboard(),
            )

        elif data == "music_volume":

            status = player.get_status()

            volume = status.get(
                "volume",
                100,
            )

            await callback.message.reply_text(
                f"🔊 صدای فعلی: {volume}%\n\n"
                "برای تغییر بنویس:\n"
                "صدا 80"
            )

        elif data == "music_status":

            status = player.get_status()

            track = (
                status.get(
                    "current_track"
                )
                or "هیچ آهنگی"
            )

            playing = (
                "▶️ در حال پخش"
                if status.get("is_playing")
                else "⏸️ مکث/متوقف"
            )

            await callback.message.reply_text(
                "🎧 وضعیت پلیر\n\n"
                f"🎵 {track}\n"
                f"📡 {playing}\n"
                f"🔊 {status.get('volume', 100)}%\n\n"
                "🟢 تیم سایلنت همیشه آنلاین می‌باشد.",
                reply_markup=_player_keyboard(),
            )

    logger.info(
        "ALL TELEGRAM HANDLERS REGISTERED"
    )
