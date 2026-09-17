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


# ============================================================
# Track
# ============================================================

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


# ============================================================
# Downloader
# ============================================================

class MusicDownloader:

    def __init__(
        self,
        download_dir: str = "downloads",
    ):
        self.download_dir = Path(
            download_dir
        )

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------------
    # Search YouTube
    # --------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 1,
    ) -> list[TrackInfo]:

        query = (
            query or ""
        ).strip()

        if not query:
            return []

        return await asyncio.to_thread(
            self._search_sync,
            query,
            limit,
        )

    def _search_sync(
        self,
        query: str,
        limit: int = 1,
    ) -> list[TrackInfo]:

        import yt_dlp

        if query.startswith(
            (
                "http://",
                "https://",
            )
        ):
            search_query = query
        else:
            search_query = (
                f"ytsearch{limit}:{query}"
            )

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                info = ydl.extract_info(
                    search_query,
                    download=False,
                )

                if not info:
                    return []

                entries = info.get(
                    "entries"
                )

                if entries is not None:
                    entries = [
                        item
                        for item in entries
                        if item
                    ]

                    if not entries:
                        return []

                    entries = entries[
                        :limit
                    ]

                else:
                    entries = [info]

                result = []

                for item in entries:
                    artist = (
                        item.get("artist")
                        or item.get("creator")
                        or item.get("uploader")
                        or ""
                    )

                    result.append(
                        TrackInfo(
                            title=(
                                item.get("title")
                                or "موزیک"
                            ),
                            performer=artist,
                            artist=artist,
                            duration=int(
                                item.get(
                                    "duration"
                                )
                                or 0
                            ),
                            url=(
                                item.get("url")
                                or ""
                            ),
                            webpage_url=(
                                item.get(
                                    "webpage_url"
                                )
                                or item.get(
                                    "original_url"
                                )
                                or ""
                            ),
                            thumbnail=(
                                item.get(
                                    "thumbnail"
                                )
                                or ""
                            ),
                            uploader=(
                                item.get(
                                    "uploader"
                                )
                                or ""
                            ),
                        )
                    )

                return result

        except Exception:
            logger.exception(
                "❌ YouTube search failed"
            )

            return []

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:

        import yt_dlp

        source = (
            track.webpage_url
            or track.url
        )

        if not source:
            logger.error(
                "❌ Track has no YouTube URL"
            )
            return None

        output_template = str(
            self.download_dir
            / "%(id)s.%(ext)s"
        )

        options = {
            "format": (
                "bestaudio[ext=m4a]/"
                "bestaudio/"
                "best"
            ),
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "overwrites": False,
        }

        try:
            loop = asyncio.get_running_loop()

            prepared = await loop.run_in_executor(
                None,
                self._download_sync,
                yt_dlp,
                options,
                source,
                track,
            )

            return prepared

        except Exception:
            logger.exception(
                "❌ Music download failed"
            )
            return None

    def _download_sync(
        self,
        yt_dlp,
        options,
        source,
        track,
    ):

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                source,
                download=True,
            )

            if not info:
                return None

            # ------------------------------------------------
            # اگر playlist بود، اولین مورد
            # ------------------------------------------------

            entries = info.get(
                "entries"
            )

            if entries:
                entries = [
                    item
                    for item in entries
                    if item
                ]

                if not entries:
                    return None

                info = entries[0]

            artist = (
                info.get("artist")
                or info.get("creator")
                or info.get("uploader")
                or track.performer
                or ""
            )

            prepared = TrackInfo(
                title=(
                    info.get("title")
                    or track.title
                    or "موزیک"
                ),
                performer=artist,
                artist=artist,
                duration=int(
                    info.get("duration")
                    or track.duration
                    or 0
                ),
                url=(
                    info.get("url")
                    or track.url
                    or ""
                ),
                webpage_url=(
                    info.get(
                        "webpage_url"
                    )
                    or track.webpage_url
                    or source
                ),
                thumbnail=(
                    info.get(
                        "thumbnail"
                    )
                    or track.thumbnail
                    or ""
                ),
                uploader=(
                    info.get(
                        "uploader"
                    )
                    or track.uploader
                    or ""
                ),
            )

            # ------------------------------------------------
            # پیدا کردن فایل واقعی
            # ------------------------------------------------

            filepath = None

            requested = (
                info.get(
                    "requested_downloads"
                )
                or []
            )

            if requested:
                for item in requested:
                    candidate = item.get(
                        "filepath"
                    )

                    if candidate:
                        filepath = candidate
                        break

            if not filepath:
                try:
                    filepath = (
                        ydl.prepare_filename(
                            info
                        )
                    )
                except Exception:
                    filepath = None

            # بعضی نسخه‌های yt-dlp مسیر واقعی
            # را از requested_downloads نمی‌دهند.
            if filepath:
                candidate = Path(
                    filepath
                )

                if candidate.exists():
                    prepared.filepath = str(
                        candidate.resolve()
                    )

            if not prepared.filepath:
                possible_files = sorted(
                    self.download_dir.glob(
                        "*"
                    ),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )

                for candidate in possible_files:
                    if (
                        candidate.is_file()
                        and candidate.stat().st_size
                        > 1024
                    ):
                        prepared.filepath = str(
                            candidate.resolve()
                        )
                        break

            if not prepared.filepath:
                logger.error(
                    "❌ Download finished but filepath was not found"
                )
                return None

            logger.info(
                "✅ Downloaded: %s",
                prepared.filepath,
            )

            return prepared

    # --------------------------------------------------------
    # Prepare
    # --------------------------------------------------------

    async def prepare(
        self,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:

        if (
            track.filepath
            and Path(
                track.filepath
            ).exists()
        ):
            return track

        return await self.download(
            track
        )


# ============================================================
# Music Player
# ============================================================

class MusicPlayer:

    def __init__(
        self,
        app: Any = None,
        call: Any = None,
        download_dir: str = "downloads",
    ):

        self.app = app
        self.call = call

        self.downloader = MusicDownloader(
            download_dir
        )

        self.current: dict[
            int,
            TrackInfo,
        ] = {}

        self.queues: dict[
            int,
            list[TrackInfo],
        ] = {}

        self.history: dict[
            int,
            list[TrackInfo],
        ] = {}

        self.paused: set[int] = set()

        self.started_at: dict[
            int,
            float,
        ] = {}

        self.offset: dict[
            int,
            float,
        ] = {}

        self.volume: dict[
            int,
            int,
        ] = {}

    # --------------------------------------------------------
    # Queue
    # --------------------------------------------------------

    def _queue(
        self,
        chat_id: int,
    ) -> list[TrackInfo]:

        return self.queues.setdefault(
            chat_id,
            [],
        )

    # --------------------------------------------------------
    # Play one track
    # --------------------------------------------------------

    async def play_track(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if self.call is None:
            logger.error(
                "❌ PyTgCalls client is None"
            )
            return False

        try:
            # --------------------------------------------
            # Prepare file
            # --------------------------------------------

            prepared = await self.downloader.prepare(
                track
            )

            if prepared is None:
                logger.error(
                    "❌ Track preparation failed"
                )
                return False

            if not prepared.filepath:
                logger.error(
                    "❌ Track has no filepath"
                )
                return False

            filepath = Path(
                prepared.filepath
            ).resolve()

            if not filepath.exists():
                logger.error(
                    "❌ Audio file does not exist: %s",
                    filepath,
                )
                return False

            if filepath.stat().st_size < 1024:
                logger.error(
                    "❌ Audio file is empty or invalid: %s",
                    filepath,
                )
                return False

            prepared.filepath = str(
                filepath
            )

            logger.info(
                "🎵 Preparing voice stream: %s",
                prepared.filepath,
            )

            # --------------------------------------------
            # Create MediaStream
            # --------------------------------------------

            try:
                stream = MediaStream(
                    prepared.filepath
                )

            except Exception:
                logger.exception(
                    "❌ MediaStream creation failed"
                )
                return False

            # --------------------------------------------
            # Start playback
            # --------------------------------------------

            try:
                await self.call.play(
                    chat_id,
                    stream,
                )

            except Exception as e:
                logger.exception(
                    "❌ PyTgCalls play() failed for chat %s: %s",
                    chat_id,
                    e,
                )

                return False

            # --------------------------------------------
            # Save state
            # --------------------------------------------

            old = self.current.get(
                chat_id
            )

            if old:
                self.history.setdefault(
                    chat_id,
                    [],
                ).append(old)

            self.current[
                chat_id
            ] = prepared

            self.started_at[
                chat_id
            ] = time.monotonic()

            self.offset[
                chat_id
            ] = 0

            self.paused.discard(
                chat_id
            )

            logger.info(
                "✅ NOW PLAYING | chat=%s | title=%s | file=%s",
                chat_id,
                prepared.title,
                prepared.filepath,
            )

            return True

        except Exception:
            logger.exception(
                "❌ Failed to play track"
            )

            return False

    # --------------------------------------------------------
    # Play / queue
    # --------------------------------------------------------

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if chat_id in self.current:
            self._queue(
                chat_id
            ).append(track)

            logger.info(
                "➕ Track added to queue: %s",
                track.title,
            )

            return True

        return await self.play_track(
            chat_id,
            track,
        )

    async def add_to_queue(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> int:

        queue = self._queue(
            chat_id
        )

        queue.append(track)

        return len(queue)

    # --------------------------------------------------------
    # Pause
    # --------------------------------------------------------

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        if self.call is None:
            return False

        if chat_id not in self.current:
            return False

        try:
            self.offset[
                chat_id
            ] = await self.get_position(
                chat_id
            )

            await self.call.pause(
                chat_id
            )

            self.paused.add(
                chat_id
            )

            return True

        except Exception:
            logger.exception(
                "❌ Pause failed"
            )
            return False

    # --------------------------------------------------------
    # Resume
    # --------------------------------------------------------

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        if self.call is None:
            return False

        if chat_id not in self.current:
            return False

        try:
            await self.call.resume(
                chat_id
            )

            self.paused.discard(
                chat_id
            )

            self.started_at[
                chat_id
            ] = time.monotonic()

            return True

        except Exception:
            logger.exception(
                "❌ Resume failed"
            )
            return False

    # --------------------------------------------------------
    # Stop
    # --------------------------------------------------------

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        if self.call is None:
            return False

        try:
            try:
                await self.call.leave_call(
                    chat_id
                )

            except Exception:
                await self.call.leave_group_call(
                    chat_id
                )

        except Exception:
            logger.exception(
                "❌ Could not leave voice chat"
            )

        self.current.pop(
            chat_id,
            None,
        )

        self.queues.pop(
            chat_id,
            None,
        )

        self.paused.discard(
            chat_id
        )

        self.started_at.pop(
            chat_id,
            None,
        )

        self.offset.pop(
            chat_id,
            None,
        )

        return True

    # --------------------------------------------------------
    # Next
    # --------------------------------------------------------

    async def next(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        queue = self._queue(
            chat_id
        )

        if not queue:
            await self.stop(
                chat_id
            )
            return None

        next_track = queue.pop(
            0
        )

        if await self.play_track(
            chat_id,
            next_track,
        ):
            return self.current.get(
                chat_id
            )

        return None

    # --------------------------------------------------------
    # Previous
    # --------------------------------------------------------

    async def previous(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        history = self.history.setdefault(
            chat_id,
            [],
        )

        if not history:
            return None

        previous_track = history.pop()

        if await self.play_track(
            chat_id,
            previous_track,
        ):
            return self.current.get(
                chat_id
            )

        return None

    # --------------------------------------------------------
    # Clear queue
    # --------------------------------------------------------

    async def clear_queue(
        self,
        chat_id: int,
    ) -> int:

        queue = self._queue(
            chat_id
        )

        count = len(queue)

        queue.clear()

        return count

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:

        if self.call is None:
            return False

        volume = max(
            1,
            min(
                200,
                int(volume),
            ),
        )

        try:
            await self.call.change_volume(
                chat_id,
                volume,
            )

            self.volume[
                chat_id
            ] = volume

            return True

        except Exception:
            logger.exception(
                "❌ Volume change failed"
            )
            return False

    # --------------------------------------------------------
    # Position
    # --------------------------------------------------------

    async def get_position(
        self,
        chat_id: int,
    ) -> int:

        if chat_id not in self.current:
            return 0

        if chat_id in self.paused:
            return int(
                self.offset.get(
                    chat_id,
                    0,
                )
            )

        started = self.started_at.get(
            chat_id
        )

        if started is None:
            return int(
                self.offset.get(
                    chat_id,
                    0,
                )
            )

        position = (
            self.offset.get(
                chat_id,
                0,
            )
            + time.monotonic()
            - started
        )

        return max(
            0,
            int(position),
        )

    # --------------------------------------------------------
    # Seek
    # --------------------------------------------------------

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

            self.offset[
                chat_id
            ] = int(seconds)

            self.started_at[
                chat_id
            ] = time.monotonic()

            return True

        except Exception:
            logger.exception(
                "❌ Seek failed"
            )
            return False

    # --------------------------------------------------------
    # Forward
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Backward
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    async def get_status(
        self,
        chat_id: int,
    ) -> dict:

        current = self.current.get(
            chat_id
        )

        return {
            "playing": current is not None,
            "paused": chat_id in self.paused,
            "current": current,
            "position": await self.get_position(
                chat_id
            ),
            "queue_size": len(
                self._queue(
                    chat_id
                )
            ),
            "volume": self.volume.get(
                chat_id,
                100,
            ),
        }

    # --------------------------------------------------------
    # Current / Queue
    # --------------------------------------------------------

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

        return list(
            self._queue(
                chat_id
            )
        )

    # --------------------------------------------------------
    # Cleanup files
    # --------------------------------------------------------

    async def cleanup_files(
        self,
    ) -> None:

        tracks = []

        for queue in self.queues.values():
            tracks.extend(queue)

        tracks.extend(
            self.current.values()
        )

        for track in tracks:
            if not track.filepath:
                continue

            try:
                Path(
                    track.filepath
                ).unlink(
                    missing_ok=True
                )

            except Exception:
                logger.exception(
                    "Could not remove file: %s",
                    track.filepath,
                )

    # --------------------------------------------------------
    # Cleanup chat
    # --------------------------------------------------------

    async def cleanup_chat(
        self,
        chat_id: int,
    ) -> None:

        current = self.current.pop(
            chat_id,
            None,
        )

        tracks = list(
            self._queue(
                chat_id
            )
        )

        if current:
            tracks.append(
                current
            )

        for track in tracks:
            if not track.filepath:
                continue

            try:
                Path(
                    track.filepath
                ).unlink(
                    missing_ok=True
                )

            except Exception:
                pass

        self.queues.pop(
            chat_id,
            None,
        )

        self.history.pop(
            chat_id,
            None,
        )

        self.paused.discard(
            chat_id
        )

        self.started_at.pop(
            chat_id,
            None,
        )

        self.offset.pop(
            chat_id,
            None,
        )

        self.volume.pop(
            chat_id,
            None,
        )
