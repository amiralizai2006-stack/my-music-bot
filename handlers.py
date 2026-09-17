# ============================================================
# پخش از YouTube + ریپلای فایل صوتی
# ============================================================

async def _play_local_reply_file(client, message, media):
    """
    فایل صوتی ریپلای‌شده را دانلود می‌کند و مستقیماً به MusicPlayer می‌دهد.
    """

    if player is None:
        await message.reply_text("❌ پخش‌کننده آماده نیست.")
        return

    try:
        downloads_dir = Path(
            getattr(
                player.downloader,
                "download_dir",
                "downloads",
            )
        )

        downloads_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        original_name = (
            getattr(media, "file_name", None)
            or getattr(media, "title", None)
            or f"reply_{message.reply_to_message.id}.mp3"
        )

        safe_name = Path(original_name).name

        if not safe_name.lower().endswith(
            (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".webm", ".mp4")
        ):
            safe_name += ".mp3"

        filepath = downloads_dir / safe_name

        await message.reply_text(
            "⏳ فایل ریپلای‌شده در حال آماده‌سازی است..."
        )

        downloaded = await client.download_media(
            message.reply_to_message,
            file_name=str(filepath),
        )

        if not downloaded:
            await message.reply_text(
                "❌ دانلود فایل ریپلای‌شده انجام نشد."
            )
            return

        filepath = Path(downloaded)

        title = _audio_title(media)
        artist = _audio_artist(media)

        track = TrackInfo(
            title=title,
            performer=artist,
            artist=artist,
            duration=int(
                getattr(media, "duration", 0) or 0
            ),
            filepath=str(filepath),
        )

        chat_id = message.chat.id

        was_playing = (
            player.get_current(chat_id) is not None
        )

        ok = await player.play(
            chat_id,
            track,
        )

        if not ok:
            await message.reply_text(
                "❌ فایل دانلود شد ولی در ویس پخش نشد."
            )
            return

        if message.from_user:
            try:
                _get_user_stats(
                    message.from_user.id
                )["plays"] += 1

                increase_play_count(
                    message.from_user.id
                )
            except Exception:
                logger.exception(
                    "REPLY PLAY COUNT ERROR"
                )

        if was_playing:
            queue = player.get_queue(chat_id)

            await message.reply_text(
                "➕ آهنگ به صف اضافه شد.\n\n"
                f"🎵 {title}\n"
                f"👤 {artist}\n\n"
                f"📋 جایگاه: {len(queue)}"
            )
            return

        await message.reply_text(
            player_text(
                track,
                await player.get_position(chat_id),
            ),
            reply_markup=music_keyboard(),
        )

    except Exception as e:
        logger.exception(
            "REPLY AUDIO PLAY ERROR"
        )

        await message.reply_text(
            "❌ خطا در پخش فایل ریپلای‌شده:\n"
            f"{type(e).__name__}: {e}"
        )


async def _search_youtube_and_play(
    message,
    query,
):
    """
    جست‌وجوی مستقیم YouTube با yt-dlp.
    """

    if player is None:
        await message.reply_text(
            "❌ پخش‌کننده آماده نیست."
        )
        return

    query = query.strip()

    if not query:
        await message.reply_text(
            "❌ اسم آهنگ را بنویس.\n\n"
            "مثال:\n"
            "پخش شادمهر تقدیر"
        )
        return

    try:
        await message.reply_text(
            f"🔎 در حال جست‌وجوی YouTube برای:\n"
            f"🎵 {query}"
        )

        downloader = player.downloader

        # جست‌وجوی مستقیم YouTube
        track = await asyncio.to_thread(
            downloader.search,
            query,
            1,
        )

        if not track:
            await message.reply_text(
                "❌ آهنگی با این نام پیدا نشد.\n\n"
                "اسم آهنگ یا نام خواننده را دقیق‌تر بنویس."
            )
            return

        await message.reply_text(
            "⬇️ آهنگ پیدا شد.\n"
            f"🎵 {_track_title(track)}\n"
            f"👤 {_track_artist(track)}\n\n"
            "⏳ در حال دانلود و آماده‌سازی..."
        )

        # دانلود واقعی از YouTube
        prepared = await downloader.prepare(track)

        if not prepared:
            await message.reply_text(
                "❌ دانلود آهنگ از YouTube انجام نشد."
            )
            return

        if not prepared.filepath:
            await message.reply_text(
                "❌ فایل دانلود شد ولی مسیر فایل پیدا نشد."
            )
            return

        if not Path(
            prepared.filepath
        ).exists():
            await message.reply_text(
                "❌ فایل دانلودشده وجود ندارد."
            )
            return

        prepared.filepath = str(
            Path(prepared.filepath).resolve()
        )

        chat_id = message.chat.id

        was_playing = (
            player.get_current(chat_id) is not None
        )

        # پخش یا اضافه‌کردن به صف
        ok = await player.play(
            chat_id,
            prepared,
        )

        if not ok:
            await message.reply_text(
                "❌ آهنگ دانلود شد اما پخش نشد.\n"
                "ویس‌چت گروه را بررسی کن."
            )
            return

        if message.from_user:
            try:
                _get_user_stats(
                    message.from_user.id
                )["plays"] += 1

                increase_play_count(
                    message.from_user.id
                )
            except Exception:
                logger.exception(
                    "YOUTUBE PLAY COUNT ERROR"
                )

        if was_playing:
            queue = player.get_queue(chat_id)

            await message.reply_text(
                "➕ آهنگ به صف اضافه شد.\n\n"
                f"🎵 {_track_title(prepared)}\n"
                f"👤 {_track_artist(prepared)}\n\n"
                f"📋 جایگاه در صف: {len(queue)}",
            )
            return

        await message.reply_text(
            player_text(
                prepared,
                await player.get_position(chat_id),
            ),
            reply_markup=music_keyboard(),
        )

    except Exception as e:
        logger.exception(
            "YOUTUBE SEARCH PLAY ERROR"
        )

        await message.reply_text(
            "❌ خطا هنگام جست‌وجو یا دانلود YouTube:\n"
            f"{type(e).__name__}: {e}"
        )


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
    """
    حالت‌های پخش:

    پخش شادمهر تقدیر
    پخش محسن یگانه
    پخش https://youtube.com/...

    یا:

    روی آهنگ ریپلای کن
    پخش
    """

    _register_activity(message)

    # --------------------------------------------------------
    # اشتراک
    # --------------------------------------------------------

    if not await _check_subscription(message):
        return

    text = message.text or ""

    match = re.match(
        r"^\s*پخش(?:\s+(.+))?\s*$",
        text,
    )

    query = ""

    if match and match.group(1):
        query = match.group(1).strip()

    # --------------------------------------------------------
    # حالت ۱:
    # ریپلای روی فایل صوتی / ویس / سند صوتی
    # --------------------------------------------------------

    if not query:
        media = _get_reply_audio(message)

        if media:
            await _play_local_reply_file(
                client,
                message,
                media,
            )
            return

        # ----------------------------------------------------
        # ریپلای روی پیام متنی دارای لینک YouTube
        # ----------------------------------------------------

        reply = message.reply_to_message

        if reply and reply.text:
            urls = re.findall(
                r"https?://[^\s]+",
                reply.text,
            )

            if urls:
                await _search_youtube_and_play(
                    message,
                    urls[0],
                )
                return

        await message.reply_text(
            "❌ چیزی برای پخش پیدا نشد.\n\n"
            "روش اول:\n"
            "پخش اسم آهنگ\n\n"
            "مثال:\n"
            "پخش شادمهر تقدیر\n\n"
            "روش دوم:\n"
            "روی فایل آهنگ ریپلای کن و بنویس:\n"
            "پخش\n\n"
            "روش سوم:\n"
            "روی لینک YouTube ریپلای کن و بنویس:\n"
            "پخش"
        )

        return

    # --------------------------------------------------------
    # حالت ۲:
    # پخش اسم آهنگ / خواننده / لینک YouTube
    # --------------------------------------------------------

    await _search_youtube_and_play(
        message,
        query,
    )
