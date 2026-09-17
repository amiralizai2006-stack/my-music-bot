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
    filepath: str = ""

    def __post_init__(self):
        if not self.performer and self.artist:
            self.performer = self.artist

        if not self.artist and self.performer:
            self.artist = self.performer


class MusicDownloader:
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, limit: int = 1) -> Optional[TrackInfo]:
        import yt_dlp

        search_query = query

        if not query.startswith(("http://", "https://")):
            search_query = f"ytsearch{limit}:{query}"

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(search_query, download=False)

                if not info:
                    return None

                if "entries" in info:
                    entries = info.get("entries") or []
                    if not entries:
                        return None
                    info = entries[0]

                return TrackInfo(
                    title=info.get("title") or "موزیک",
                    performer=info.get("artist")
                    or info.get("uploader")
                    or "",
                    artist=info.get("artist")
                    or info.get("uploader")
                    or "",
                    duration=int(info.get("duration") or 0),
                    url=info.get("url") or "",
                    webpage_url=info.get("webpage_url") or "",
                    thumbnail=info.get("thumbnail") or "",
                    uploader=info.get("uploader") or "",
                )

        except Exception:
            logger.exception("Music search failed")
            return None

    async def download(self, track: TrackInfo) -> Optional[TrackInfo]:
        import yt_dlp

        output_template = str(
            self.download_dir / "%(id)s.%(ext)s"
        )

        options = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        source = track.webpage_url or track.url

        if not source:
            return None

        try:
            loop = asyncio.get_running_loop()

            def do_download():
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(source, download=True)

                    prepared = TrackInfo(
                        title=info.get("title") or track.title,
                        performer=info.get("artist")
                        or info.get("uploader")
                        or track.performer,
                        artist=info.get("artist")
                        or info.get("uploader")
                        or track.artist,
                        duration=int(
                            info.get("duration")
                            or track.duration
                            or 0
                        ),
                        url=info.get("url") or track.url,
                        webpage_url=info.get("webpage_url")
                        or track.webpage_url,
                        thumbnail=info.get("thumbnail")
                        or track.thumbnail,
                        uploader=info.get("uploader")
                        or track.uploader,
                    )

                    requested = info.get("requested_downloads") or []

                    filepath = None

                    if requested:
                        filepath = requested[0].get("filepath")

                    if not filepath:
                        original = ydl.prepare_filename(info)
                        filepath = os.path.splitext(original)[0] + ".mp3"

                    prepared.filepath = filepath
                    return prepared

            return await loop.run_in_executor(None, do_download)

        except Exception:
            logger.exception("Music download failed")
            return None

    async def prepare(self, track: TrackInfo) -> Optional[TrackInfo]:
        if track.filepath and Path(track.filepath).exists():
            return track

        return await self.download(track)


class MusicPlayer:
    def __init__(
        self,
        app: Any = None,
        call: Any = None,
        download_dir: str = "downloads",
    ):
        self.app = app
        self.call = call

        self.downloader = MusicDownloader(download_dir)

        self.current: dict[int, TrackInfo] = {}
        self.queues: dict[int, list[TrackInfo]] = {}
        self.history: dict[int, list[TrackInfo]] = {}

        self.paused: set[int] = set()
        self.started_at: dict[int, float] = {}
        self.offset: dict[int, float] = {}
        self.volume: dict[int, int] = {}

    def _queue(self, chat_id: int) -> list[TrackInfo]:
        return self.queues.setdefault(chat_id, [])

    async def play_track(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:
        if self.call is None:
            logger.error("PyTgCalls client is not connected")
            return False

        try:
            prepared = await self.downloader.prepare(track)

            if prepared is None or not prepared.filepath:
                return False

            if not Path(prepared.filepath).exists():
                return False

            stream = MediaStream(prepared.filepath)

            await self.call.play(chat_id, stream)

            old = self.current.get(chat_id)

            if old:
                self.history.setdefault(chat_id, []).append(old)

            self.current[chat_id] = prepared
            self.started_at[chat_id] = time.monotonic()
            self.offset[chat_id] = 0
            self.paused.discard(chat_id)

            return True

        except Exception:
            logger.exception("Failed to play track")
            return False

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:
        if chat_id in self.current:
            self._queue(chat_id).append(track)
            return True

        return await self.play_track(chat_id, track)

    async def add_to_queue(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> int:
        queue = self._queue(chat_id)
        queue.append(track)
        return len(queue)

    async def pause(self, chat_id: int) -> bool:
        if self.call is None:
            return False

        if chat_id not in self.current:
            return False

        try:
            await self.call.pause(chat_id)
            self.paused.add(chat_id)
            return True
        except Exception:
            logger.exception("Pause failed")
            return False

    async def resume(self, chat_id: int) -> bool:
        if self.call is None:
            return False

        if chat_id not in self.current:
            return False

        try:
            await self.call.resume(chat_id)
            self.paused.discard(chat_id)
            return True
        except Exception:
            logger.exception("Resume failed")
            return False

    async def stop(self, chat_id: int) -> bool:
        if self.call is None:
            return False

        try:
            await self.call.leave_call(chat_id)
        except Exception:
            try:
                await self.call.leave_group_call(chat_id)
            except Exception:
                logger.exception("Could not leave voice chat")

        self.current.pop(chat_id, None)
        self.queues.pop(chat_id, None)
        self.paused.discard(chat_id)
        self.started_at.pop(chat_id, None)
        self.offset.pop(chat_id, None)

        return True

    async def next(self, chat_id: int) -> Optional[TrackInfo]:
        queue = self._queue(chat_id)

        if not queue:
            await self.stop(chat_id)
            return None

        next_track = queue.pop(0)

        if await self.play_track(chat_id, next_track):
            return self.current.get(chat_id)

        return None

    async def previous(self, chat_id: int) -> Optional[TrackInfo]:
        history = self.history.setdefault(chat_id, [])

        if not history:
            return None

        previous_track = history.pop()

        if await self.play_track(chat_id, previous_track):
            return self.current.get(chat_id)

        return None

    async def clear_queue(self, chat_id: int) -> int:
        queue = self._queue(chat_id)
        count = len(queue)
        queue.clear()
        return count

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:
        if self.call is None:
            return False

        volume = max(1, min(200, int(volume)))

        try:
            await self.call.change_volume(
                chat_id,
                volume,
            )

            self.volume[chat_id] = volume
            return True

        except Exception:
            logger.exception("Volume change failed")
            return False

    async def get_position(self, chat_id: int) -> int:
        if chat_id not in self.current:
            return 0

        if chat_id in self.paused:
            return int(self.offset.get(chat_id, 0))

        started = self.started_at.get(chat_id)

        if started is None:
            return int(self.offset.get(chat_id, 0))

        position = (
            self.offset.get(chat_id, 0)
            + time.monotonic()
            - started
        )

        return max(0, int(position))

    async def seek(
        self,
        chat_id: int,
        seconds: int,
    ) -> bool:
        if self.call is None:
            return False

        if chat_id not in self.current:
            return False

        try:
            await self.call.seek(
                chat_id,
                int(seconds),
            )

            self.offset[chat_id] = int(seconds)
            self.started_at[chat_id] = time.monotonic()

            return True

        except Exception:
            logger.exception("Seek failed")
            return False

    async def forward(
        self,
        chat_id: int,
        seconds: int = 10,
    ) -> bool:
        position = await self.get_position(chat_id)

        return await self.seek(
            chat_id,
            position + int(seconds),
        )

    async def backward(
        self,
        chat_id: int,
        seconds: int = 10,
    ) -> bool:
        position = await self.get_position(chat_id)

        return await self.seek(
            chat_id,
            max(0, position - int(seconds)),
        )

    async def get_status(self, chat_id: int) -> dict:
        current = self.current.get(chat_id)

        return {
            "playing": current is not None,
            "paused": chat_id in self.paused,
            "current": current,
            "position": await self.get_position(chat_id),
            "queue_size": len(self._queue(chat_id)),
            "volume": self.volume.get(chat_id, 100),
        }

    def get_current(self, chat_id: int) -> Optional[TrackInfo]:
        return self.current.get(chat_id)

    def get_queue(self, chat_id: int) -> list[TrackInfo]:
        return list(self._queue(chat_id))

    async def cleanup_files(self) -> None:
        for queue in self.queues.values():
            for track in queue:
                if track.filepath:
                    try:
                        Path(track.filepath).unlink(
                            missing_ok=True
                        )
                    except Exception:
                        pass

        for track in self.current.values():
            if track.filepath:
                try:
                    Path(track.filepath).unlink(
                        missing_ok=True
                    )
                except Exception:
                    pass

    async def cleanup_chat(self, chat_id: int) -> None:
        current = self.current.pop(chat_id, None)

        tracks = list(self._queue(chat_id))

        if current:
            tracks.append(current)

        for track in tracks:
            if track.filepath:
                try:
                    Path(track.filepath).unlink(
                        missing_ok=True
                    )
                except Exception:
                    pass

        self.queues.pop(chat_id, None)
        self.history.pop(chat_id, None)
        self.paused.discard(chat_id)
        self.started_at.pop(chat_id, None)
        self.offset.pop(chat_id, None)
        self.volume.pop(chat_id, None)
