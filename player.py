from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from optional_deps import MediaStream

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    title: str
    performer: str = ""
    artist: str = ""
    duration: int = 0
    url: str = ""
    webpage_url: str = ""
    thumbnail: str = ""
    uploader: str = ""
    filepath: Optional[str] = None

    def __post_init__(self):
        # سازگاری بین artist و performer
        if not self.performer and self.artist:
            self.performer = self.artist

        if not self.artist and self.performer:
            self.artist = self.performer


class MusicDownloader:
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def search(
        self,
        query: str,
        limit: int = 1,
    ) -> Optional[TrackInfo]:

        try:
            import yt_dlp

            query = query.strip()

            if not query:
                return None

            if query.startswith(("http://", "https://")):
                search_query = query
            else:
                search_query = (
                    f"ytsearch{max(1, int(limit))}:{query}"
                )

            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
            }

            def extract():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(
                        search_query,
                        download=False,
                    )

            info = await asyncio.to_thread(extract)

            if not info:
                return None

            if "entries" in info:
                entries = [
                    entry
                    for entry in (info.get("entries") or [])
                    if entry
                ]

                if not entries:
                    return None

                info = entries[0]

            title = info.get("title") or "موزیک"

            artist = (
                info.get("artist")
                or info.get("creator")
                or info.get("uploader")
                or info.get("channel")
                or ""
            )

            return TrackInfo(
                title=title,
                performer=artist,
                artist=artist,
                duration=int(
                    info.get("duration") or 0
                ),
                url=info.get("url") or "",
                webpage_url=(
                    info.get("webpage_url") or ""
                ),
                thumbnail=(
                    info.get("thumbnail") or ""
                ),
                uploader=(
                    info.get("uploader")
                    or info.get("channel")
                    or ""
                ),
            )

        except Exception:
            logger.exception(
                "Music search failed"
            )
            return None

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[str]:

        try:
            import yt_dlp

            source = (
                track.webpage_url
                or track.url
            )

            if not source:
                return None

            output = (
                self.download_dir
                / "%(id)s.%(ext)s"
            )

            options = {
                "format": "bestaudio/best",
                "outtmpl": str(output),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            def extract():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(
                        source,
                        download=True,
                    )

            info = await asyncio.to_thread(extract)

            if not info:
                return None

            video_id = info.get("id")

            if video_id:

                mp3_file = (
                    self.download_dir
                    / f"{video_id}.mp3"
                )

                if mp3_file.exists():
                    return str(mp3_file)

                for file in self.download_dir.glob(
                    f"{video_id}.*"
                ):
                    if file.is_file():
                        return str(file)

            return None

        except Exception:
            logger.exception(
                "Music download failed"
            )
            return None

    async def prepare(
        self,
        track: TrackInfo,
    ) -> Optional[str]:

        if (
            track.filepath
            and os.path.exists(track.filepath)
        ):
            return track.filepath

        return await self.download(track)


class MusicPlayer:

    def __init__(
        self,
        pytgcalls: Any = None,
    ):
        self.pytgcalls = pytgcalls

        self.downloader = MusicDownloader()

        # صف هر چت
        self.queues: dict[
            int,
            list[TrackInfo]
        ] = {}

        # آهنگ فعلی
        self.current: dict[
            int,
            TrackInfo
        ] = {}

        self.started_at: dict[
            int,
            float
        ] = {}

        self.paused_at: dict[
            int,
            float
        ] = {}

        self.paused: set[int] = set()

        self.volumes: dict[
            int,
            int
        ] = {}

        self.history: dict[
            int,
            list[TrackInfo]
        ] = {}

        self.history_index: dict[
            int,
            int
        ] = {}

        self.locks: dict[
            int,
            asyncio.Lock
        ] = {}

    def _lock(
        self,
        chat_id: int,
    ) -> asyncio.Lock:

        if chat_id not in self.locks:
            self.locks[chat_id] = (
                asyncio.Lock()
            )

        return self.locks[chat_id]

    async def call_method(
        self,
        method: str,
        *args,
        **kwargs,
    ):

        if not self.pytgcalls:
            raise RuntimeError(
                "PyTgCalls is not available"
            )

        fn = getattr(
            self.pytgcalls,
            method,
            None,
        )

        if not fn:
            raise RuntimeError(
                f"PyTgCalls method not found: {method}"
            )

        return await fn(
            *args,
            **kwargs,
        )

    async def _make_stream(
        self,
        filepath: str,
    ):

        try:
            return MediaStream(filepath)

        except TypeError:
            return MediaStream(
                filepath=filepath
            )

    async def prepare_local_file(
        self,
        filepath: str,
        title: str = "موزیک",
        performer: str = "",
    ) -> TrackInfo:

        return TrackInfo(
            title=title,
            performer=performer,
            artist=performer,
            filepath=filepath,
        )

    async def play_track(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        async with self._lock(chat_id):

            try:

                filepath = (
                    await self.downloader.prepare(
                        track
                    )
                )

                if not filepath:
                    logger.error(
                        "Could not prepare track"
                    )
                    return False

                track.filepath = filepath

                stream = await self._make_stream(
                    filepath
                )

                await self.call_method(
                    "play",
                    chat_id,
                    stream,
                )

                self.current[chat_id] = track

                self.started_at[chat_id] = (
                    time.time()
                )

                self.paused_at.pop(
                    chat_id,
                    None,
                )

                self.paused.discard(
                    chat_id
                )

                self.volumes.setdefault(
                    chat_id,
                    100,
                )

                history = self.history.setdefault(
                    chat_id,
                    [],
                )

                # جلوگیری از ثبت تکراری
                # ولی اجازه می‌دهیم آهنگ بعدی دوباره پخش شود
                if not history or (
                    history[-1].webpage_url
                    != track.webpage_url
                    or not track.webpage_url
                ):
                    history.append(track)

                self.history_index[chat_id] = (
                    len(history) - 1
                )

                logger.info(
                    "▶️ Playing: %s - %s",
                    track.artist
                    or track.performer,
                    track.title,
                )

                return True

            except Exception:

                logger.exception(
                    "Failed to play track in chat %s",
                    chat_id,
                )

                return False

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        # اگر آهنگی در حال پخش است،
        # آهنگ جدید باید برود داخل صف
        if chat_id in self.current:

            await self.add_to_queue(
                chat_id,
                track,
            )

            logger.info(
                "➕ Added to queue: %s",
                track.title,
            )

            return True

        # اگر چیزی پخش نمی‌شود،
        # مستقیم پخش کن
        return await self.play_track(
            chat_id,
            track,
        )

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        try:

            await self.call_method(
                "pause",
                chat_id,
            )

            self.paused.add(
                chat_id
            )

            self.paused_at[chat_id] = (
                time.time()
            )

            return True

        except Exception:

            logger.exception(
                "Pause failed"
            )

            return False

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        try:

            await self.call_method(
                "resume",
                chat_id,
            )

            self.paused.discard(
                chat_id
            )

            paused_time = (
                self.paused_at.pop(
                    chat_id,
                    None,
                )
            )

            if (
                paused_time
                and chat_id in self.started_at
            ):
                self.started_at[chat_id] += (
                    time.time()
                    - paused_time
                )

            return True

        except Exception:

            logger.exception(
                "Resume failed"
            )

            return False

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        try:

            try:
                await self.call_method(
                    "leave_call",
                    chat_id,
                )

            except Exception:

                try:
                    await self.call_method(
                        "stop",
                        chat_id,
                    )
                except Exception:
                    pass

            self.current.pop(
                chat_id,
                None,
            )

            # با اتمام، صف هم پاک شود
            self.queues.pop(
                chat_id,
                None,
            )

            self.started_at.pop(
                chat_id,
                None,
            )

            self.paused_at.pop(
                chat_id,
                None,
            )

            self.paused.discard(
                chat_id
            )

            return True

        except Exception:

            logger.exception(
                "Stop failed"
            )

            return False

    async def next(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        queue = self.queues.get(
            chat_id,
            [],
        )

        if not queue:
            return None

        # آهنگ اول صف را بردار
        track = queue.pop(0)

        # اگر صف خالی شد، دیکشنری را تمیز کن
        if not queue:
            self.queues.pop(
                chat_id,
                None,
            )

        # آهنگ قبلی را جایگزین کن
        if await self.play_track(
            chat_id,
            track,
        ):
            return track

        return None

    async def previous(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        history = self.history.get(
            chat_id,
            [],
        )

        if len(history) < 2:
            return None

        index = self.history_index.get(
            chat_id,
            len(history) - 1,
        )

        if index <= 0:
            return None

        index -= 1

        self.history_index[chat_id] = (
            index
        )

        track = history[index]

        if await self.play_track(
            chat_id,
            track,
        ):
            return track

        return None

    async def add_to_queue(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> int:

        queue = self.queues.setdefault(
            chat_id,
            [],
        )

        queue.append(track)

        return len(queue)

    async def clear_queue(
        self,
        chat_id: int,
    ):

        self.queues.pop(
            chat_id,
            None,
        )

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:

        volume = max(
            0,
            min(
                200,
                int(volume),
            ),
        )

        try:

            await self.call_method(
                "change_volume",
                chat_id,
                volume,
            )

            self.volumes[chat_id] = volume

            return True

        except Exception:

            logger.exception(
                "Volume change failed"
            )

            return False

    async def get_position(
        self,
        chat_id: int,
    ) -> int:

        if chat_id not in self.started_at:
            return 0

        if chat_id in self.paused:

            paused_at = self.paused_at.get(
                chat_id
            )

            if paused_at:

                return max(
                    0,
                    int(
                        paused_at
                        - self.started_at[
                            chat_id
                        ]
                    ),
                )

        return max(
            0,
            int(
                time.time()
                - self.started_at[
                    chat_id
                ]
            ),
        )

    async def seek(
        self,
        chat_id: int,
        seconds: int,
    ) -> bool:

        try:

            await self.call_method(
                "seek",
                chat_id,
                int(seconds),
            )

            return True

        except Exception:

            logger.warning(
                "Seek is not supported"
            )

            return False

    async def forward(
        self,
        chat_id: int,
        seconds: int = 10,
    ) -> bool:

        position = await self.get_position(
            chat_id
        )

        return await self.seek(
            chat_id,
            position + int(seconds),
        )

    async def backward(
        self,
        chat_id: int,
        seconds: int = 10,
    ) -> bool:

        position = await self.get_position(
            chat_id
        )

        return await self.seek(
            chat_id,
            max(
                0,
                position - int(seconds),
            ),
        )

    async def get_status(
        self,
        chat_id: int,
    ) -> dict:

        track = self.current.get(
            chat_id
        )

        return {
            "playing": (
                track is not None
                and chat_id not in self.paused
            ),
            "paused": (
                chat_id in self.paused
            ),
            "track": track,
            "position": await self.get_position(
                chat_id
            ),
            "volume": self.volumes.get(
                chat_id,
                100,
            ),
            "queue_size": len(
                self.queues.get(
                    chat_id,
                    [],
                )
            ),
        }

    def get_current(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        return self.current.get(
            chat_id
        )

    def get_queue(
        self,
        chat_id: int,
    ) -> list[TrackInfo]:

        return self.queues.get(
            chat_id,
            [],
        )

    async def cleanup_files(self):

        try:

            for file in (
                self.downloader
                .download_dir
                .iterdir()
            ):

                if file.is_file():

                    try:
                        file.unlink()

                    except Exception:

                        logger.warning(
                            "Could not remove %s",
                            file,
                        )

        except Exception:

            logger.exception(
                "Cleanup failed"
            )

    async def cleanup_chat(
        self,
        chat_id: int,
    ):

        self.queues.pop(
            chat_id,
            None,
        )

        self.current.pop(
            chat_id,
            None,
        )

        self.started_at.pop(
            chat_id,
            None,
        )

        self.paused_at.pop(
            chat_id,
            None,
        )

        self.paused.discard(
            chat_id
        )

        self.volumes.pop(
            chat_id,
            None,
        )

        self.history.pop(
            chat_id,
            None,
        )

        self.history_index.pop(
            chat_id,
            None,
        )

        self.locks.pop(
            chat_id,
            None
        )
