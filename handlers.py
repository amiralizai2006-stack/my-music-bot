
# Persian command aliases
# =========================

@app.on_message(filters.regex(r"^پخش(?:\s+(.+))?$") & filters.group)
async def persian_play_cmd(client: Client, message: Message):
    query = message.matches[0].group(1)

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

    await status_msg.edit(f"⬇️ در حال دانلود:\n**{track.title}**")

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
        requested_by=user.username or user.first_name,
        added_at=datetime.now(),
        position=position
    )

    await db.add_to_queue(item)

    if VOICE_CHAT_AVAILABLE:
        if not player.is_playing or player.current_chat_id != chat_id:
            await status_msg.edit(f"▶️ در حال پخش:\n**{track.title}**")
            await play_next(chat_id)
        else:
            await status_msg.edit(
                f"✅ به صف اضافه شد:\n**{track.title}**\n"
                f"📋 شماره صف: `{position}`"
            )
    else:
        await status_msg.edit(
            f"✅ دانلود شد:\n**{track.title}**\n\n"
            "⚠️ ویس‌چت در هاست فعلی فعال نیست."
        )


@app.on_message(filters.regex(r"^مکث$") & filters.group)
async def persian_pause_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if not player or player.current_chat_id != chat_id or not player.is_playing:
        await message.reply("❌ موزیکی در حال پخش نیست.")
        return

    if player.is_paused:
        await message.reply("⏸ موزیک از قبل متوقف است.")
        return

    if await player.pause(chat_id):
        await message.reply("⏸ موزیک مکث شد.")
    else:
        await message.reply("❌ خطا در مکث موزیک.")


@app.on_message(filters.regex(r"^(ادامه|ادامه پخش)$") & filters.group)
async def persian_resume_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if not player or player.current_chat_id != chat_id or not player.is_paused:
        await message.reply("❌ موزیک متوقف‌شده‌ای برای ادامه وجود ندارد.")
        return

    if await player.resume(chat_id):
        await message.reply("▶️ پخش ادامه یافت.")
    else:
        await message.reply("❌ خطا در ادامه پخش.")


@app.on_message(filters.regex(r"^اتمام$") & filters.group)
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


@app.on_message(filters.regex(r"^بعدی$") & filters.group)
async def persian_skip_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    chat_id = message.chat.id

    if not player or player.current_chat_id != chat_id or not player.is_playing:
        await message.reply("❌ موزیکی در حال پخش نیست.")
        return

    await pytgcalls_client.change_stream(
        chat_id,
        AudioVideoPiped("")
    )

    await message.reply("⏭ آهنگ بعدی در حال پخش است...")


@app.on_message(filters.regex(r"^صف$") & filters.group)
async def persian_queue_cmd(client: Client, message: Message):
    text = await get_queue_text(message.chat.id)
    await message.reply(text)


@app.on_message(filters.regex(r"^(الان|در حال پخش)$") & filters.group)
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
        f"⏱ مدت: `{duration_str}`"
    )


@app.on_message(filters.regex(r"^صدا(?:\s+(\d+))?$") & filters.group)
async def persian_volume_cmd(client: Client, message: Message):
    if not VOICE_CHAT_AVAILABLE:
        await message.reply("❌ ویس‌چت در هاست فعلی فعال نیست.")
        return

    value = message.matches[0].group(1)

    if not value:
        await message.reply(f"🔊 صدای فعلی: `{player.volume}%`")
        return

    vol = max(0, min(200, int(value)))
    chat_id = message.chat.id

    if not player or player.current_chat_id != chat_id:
        await message.reply("❌ ربات در ویس‌چت این گروه نیست.")
        return

    success = await player.set_volume(chat_id, vol)
    await db.update_chat_settings(chat_id, volume=vol)

    if success:
        await message.reply(f"🔊 صدا روی `{vol}%` تنظیم شد.")
    else:
        await message.reply("❌ خطا در تنظیم صدا.")


@app.on_message(filters.regex(r"^آیدی$") & filters.group)
async def persian_id_cmd(client: Client, message: Message):
    await message.reply(
        f"🆔 **آیدی گروه:** `{message.chat.id}`\n"
        f"👤 **آیدی شما:** `{message.from_user.id}`"
    )


@app.on_message(filters.regex(r"^کمک$"))
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
