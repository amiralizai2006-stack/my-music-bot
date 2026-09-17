from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import yt_dlp

try:
    from pytgcalls.types import MediaStream
except Exception:
    MediaStream = None


logger = logging.getLogger("SILENT.player")


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TRACK
# ============================================================

@dataclass
class TrackInfo:
    title: str
    performer: str = ""
    artist: str = ""
    duration: int = 0
    url: str = ""
    source_url: str = ""
    file_path: str = ""
    thumbnail: str = ""

    def display_name(self) -> str:
        if self.performer:
            return f"{self.title} — {self.performer}"

        if self.artist:
            return f"{self.title} — {self.artist}"

        return self.title


# ============================================================
# YOUTUBE / AUDIO DOWNLOADER
# ============================================================

class MusicDownloader:
    YDL_SEARCH_OPTIONS = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": True,
        "default_search": "ytsearch",
    }

    YDL_INFO_OPTIONS = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    YDL_DOWNLOAD_OPTIONS = {
        "format": "bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "overwrites": False,
        "continuedl": True,
    }

    def __init__(self):
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_url(text: str) -> bool:
        try:
            parsed = urlparse(text.strip())
            return parsed.scheme in ("http", "https")
        except Exception:
            return False

    @staticmethod
    def _clean_query(query: str) -> str:
        return re.sub(
            r"\s+",
            " ",
            query or "",
        ).strip()

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = re.sub(
            r'[\\/:*?"<>|]+',
            "_",
            name,
        )
        name = re.sub(
            r"\s+",
            " ",
            name,
        ).strip()

        return name[:120] or "audio"

    def _search_sync(
        self,
        query: str,
    ) -> Optional[dict]:
        query = self._clean_query(query)

        if not query:
            return None

        if self._is_url(query):
            search_query = query
        else:
            search_query = f"ytsearch1:{query}"

        options = dict(
            self.YDL_SEARCH_OPTIONS
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                search_query,
                download=False,
            )

        if not info:
            return None

        if "entries" in info:
            entries = [
                item
                for item in info.get(
                    "entries",
                    [],
                )
                if item
            ]

            if not entries:
                return None

            return entries[0]

        return info

    def _download_sync(
        self,
        info: dict,
    ) -> Optional[Path]:
        video_id = str(
            info.get("id") or ""
        ).strip()

        title = str(
            info.get("title") or "audio"
        ).strip()

        if not video_id:
            return None

        # ----------------------------------------------------
        # Check existing downloaded file.
        # ----------------------------------------------------

        existing = list(
            DOWNLOAD_DIR.glob(
                f"{self._safe_filename(video_id)}.*"
            )
        )

        if existing:
            files = [
                item
                for item in existing
                if item.is_file()
            ]

            if files:
                files.sort(
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )

                return files[0]

        # ----------------------------------------------------
        # Source URL
        # ----------------------------------------------------

        source = (
            info.get("webpage_url")
            or info.get("original_url")
            or info.get("url")
        )

        if not source:
            logger.error(
                "No source URL for %s",
                title,
            )
            return None

        # ----------------------------------------------------
        # Download.
        # ----------------------------------------------------

        options = dict(
            self.YDL_DOWNLOAD_OPTIONS
        )

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                result = ydl.extract_info(
                    source,
                    download=True,
                )

                if not result:
                    return None

                prepared = ydl.prepare_filename(
                    result
                )

        except Exception:
            logger.exception(
                "yt-dlp download failed: %s",
                title,
            )
            return None

        # ----------------------------------------------------
        # Exact prepared file.
        # ----------------------------------------------------

        prepared_path = Path(
            prepared
        )

        if prepared_path.exists():
            return prepared_path

        # ----------------------------------------------------
        # Search by video ID.
        # ----------------------------------------------------

        candidates = list(
            DOWNLOAD_DIR.glob(
                f"{self._safe_filename(video_id)}.*"
            )
        )

        candidates = [
            item
            for item in candidates
            if item.is_file()
        ]

        if candidates:
            candidates.sort(
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            return candidates[0]

        # ----------------------------------------------------
        # Final fallback.
        # ----------------------------------------------------

        candidates = [
            item
            for item in DOWNLOAD_DIR.iterdir()
            if item.is_file()
            and video_id in item.name
        ]

        if candidates:
            candidates.sort(
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            return candidates[0]

        logger.warning(
            "Downloaded file not found: %s",
            title,
        )

        return None

    def _track_from_info(
        self,
        info: dict,
    ) -> TrackInfo:
        title = str(
            info.get("title")
            or "Unknown"
        )

        performer = str(
            info.get("uploader")
            or info.get("channel")
            or ""
        )

        artist = str(
            info.get("artist")
            or performer
            or ""
        )

        duration = info.get(
            "duration"
        ) or 0

        try:
            duration = int(
                float(duration)
            )
        except Exception:
            duration = 0

        webpage_url = str(
            info.get("webpage_url")
            or info.get("original_url")
            or ""
        )

        thumbnail = str(
            info.get("thumbnail")
            or ""
        )

        return TrackInfo(
            title=title,
            performer=performer,
            artist=artist,
            duration=duration,
            url=webpage_url,
            source_url=webpage_url,
            thumbnail=thumbnail,
        )

    async def search(
        self,
        query: str,
        limit: int = 1,
    ) -> list[TrackInfo]:
        query = self._clean_query(
            query
        )

        if not query:
            return []

        try:
            info = await asyncio.to_thread(
                self._search_sync,
                query,
            )

        except Exception:
            logger.exception(
                "YouTube search failed: %s",
                query,
            )
            return []

        if not info:
            return []

        return [
            self._track_from_info(info)
        ]

    async def prepare(
        self,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:
        """
        Resolve and download a TrackInfo.
        """

        # ----------------------------------------------------
        # Already downloaded.
        # ----------------------------------------------------

        if track.file_path:
            path = Path(
                track.file_path
            )

            if path.exists() and path.is_file():
                return track

        source = (
            track.source_url
            or track.url
        )

        if not source:
            logger.error(
                "Track has no source URL: %s",
                track.title,
            )
            return None

        async with self._lock:
            try:
                info = await asyncio.to_thread(
                    self._search_sync,
                    source,
                )

            except Exception:
                logger.exception(
                    "Could not resolve source: %s",
                    source,
                )
                return None

            if not info:
                return None

            try:
                file_path = await asyncio.to_thread(
                    self._download_sync,
                    info,
                )

            except Exception:
                logger.exception(
                    "Audio download failed: %s",
                    track.title,
                )
                return None

            if not file_path:
                return None

            resolved = self._track_from_info(
                info
            )

            resolved.file_path = str(
                file_path
            )

            return resolved


# ============================================================
# MUSIC PLAYER
# ============================================================

class MusicPlayer:
    def __init__(
        self,
        call: Any = None,
    ):
        self.call = call

        self.downloader = MusicDownloader()

        # ----------------------------------------------------
        # Current song per chat.
        # ----------------------------------------------------

        self.current: dict[
            int,
            TrackInfo,
        ] = {}

        # ----------------------------------------------------
        # Queue per chat.
        # ----------------------------------------------------

        self.queues: dict[
            int,
            list[TrackInfo],
        ] = {}

        # ----------------------------------------------------
        # Playback history.
        # ----------------------------------------------------

        self.history: dict[
            int,
            list[TrackInfo],
        ] = {}

        # ----------------------------------------------------
        # Pause state.
        # ----------------------------------------------------

        self.paused: dict[
            int,
            bool,
        ] = {}

        # ----------------------------------------------------
        # Timing.
        # ----------------------------------------------------

        self.started_at: dict[
            int,
            float,
        ] = {}

        self.paused_at: dict[
            int,
            float,
        ] = {}

        self.offset: dict[
            int,
            float,
        ] = {}

        # ----------------------------------------------------
        # Locks.
        # ----------------------------------------------------

        self._locks: dict[
            int,
            asyncio.Lock,
        ] = {}

        # ----------------------------------------------------
        # Prevent duplicate next().
        # ----------------------------------------------------

        self._advancing: set[int] = set()

        # ----------------------------------------------------
        # Active voice chats.
        # ----------------------------------------------------

        self.active_chat_ids: set[int] = set()


# ============================================================
# LOCK
# ============================================================

    def _get_lock(
        self,
        chat_id: int,
    ) -> asyncio.Lock:
        chat_id = int(chat_id)

        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()

        return self._locks[chat_id]


# ============================================================
# CALL PLAY
# ============================================================

    async def _call_play(
        self,
        chat_id: int,
        file_path: str,
    ):
        if not self.call:
            raise RuntimeError(
                "PyTgCalls is not available"
            )

        if MediaStream is None:
            raise RuntimeError(
                "MediaStream is unavailable"
            )

        path = Path(
            file_path
        )

        if not path.exists():
            raise FileNotFoundError(
                str(path)
            )

        stream = MediaStream(
            str(path),
            video_flags=MediaStream.Flags.IGNORE,
        )

        result = self.call.play(
            int(chat_id),
            stream,
        )

        if asyncio.iscoroutine(result):
            await result


# ============================================================
# CALL LEAVE
# ============================================================

    async def _call_leave(
        self,
        chat_id: int,
    ):
        if not self.call:
            return

        leave = getattr(
            self.call,
            "leave_call",
            None,
        )

        if not callable(leave):
            return

        try:
            result = leave(
                int(chat_id)
            )

            if asyncio.iscoroutine(result):
                await result

        except Exception:
            logger.exception(
                "Could not leave call %s",
                chat_id,
            )


# ============================================================
# RESOLVE
# ============================================================

    async def resolve(
        self,
        query: str,
    ) -> Optional[TrackInfo]:
        query = str(
            query or ""
        ).strip()

        if not query:
            return None

        results = await self.downloader.search(
            query,
            limit=1,
        )

        if not results:
            return None

        return results[0]


# ============================================================
# PREPARE TRACK
# ============================================================

    async def _prepare_track(
        self,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:
        return await self.downloader.prepare(
            track
        )


# ============================================================
# START TRACK
# ============================================================

    async def _start_track_locked(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> dict:
        prepared = await self._prepare_track(
            track
        )

        if not prepared:
            logger.error(
                "❌ Could not prepare: %s",
                track.display_name(),
            )

            return {
                "status": "error",
                "track": track,
                "error": "download_failed",
            }

        if not prepared.file_path:
            return {
                "status": "error",
                "track": prepared,
                "error": "file_missing",
            }

        try:
            await self._call_play(
                chat_id,
                prepared.file_path,
            )

        except Exception:
            logger.exception(
                "❌ Failed to play in chat %s",
                chat_id,
            )

            return {
                "status": "error",
                "track": prepared,
                "error": "play_failed",
            }

        # ----------------------------------------------------
        # Update current state.
        # ----------------------------------------------------

        self.current[chat_id] = prepared
        self.paused[chat_id] = False
        self.started_at[chat_id] = (
            time.monotonic()
        )
        self.paused_at[chat_id] = 0.0
        self.offset[chat_id] = 0.0

        self.active_chat_ids.add(
            chat_id
        )

        logger.info(
            "▶️ Playing | chat=%s | %s",
            chat_id,
            prepared.display_name(),
        )

        return {
            "status": "playing",
            "track": prepared,
            "queue_size": len(
                self.queues.get(
                    chat_id,
                    [],
                )
            ),
        }


# ============================================================
# PLAY
# ============================================================

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> dict:
        """
        If nothing is playing:
            start immediately.

        If something is playing:
            add the new track to queue.
        """

        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            # ------------------------------------------------
            # First song: play immediately.
            # ------------------------------------------------

            if chat_id not in self.current:
                return await self._start_track_locked(
                    chat_id,
                    track,
                )

            # ------------------------------------------------
            # Another song is already playing.
            # Put new song into queue.
            # ------------------------------------------------

            queue = self.queues.setdefault(
                chat_id,
                [],
            )

            queue.append(
                track
            )

            position = len(
                queue
            )

            logger.info(
                "➕ Queued #%s | chat=%s | %s",
                position,
                chat_id,
                track.display_name(),
            )

            return {
                "status": "queued",
                "track": track,
                "position": position,
                "queue_size": position,
            }


# ============================================================
# PLAY QUERY
# ============================================================

    async def play_query(
        self,
        chat_id: int,
        query: str,
    ) -> dict:
        track = await self.resolve(
            query
        )

        if not track:
            return {
                "status": "not_found",
                "track": None,
            }

        return await self.play(
            chat_id,
            track,
        )


# ============================================================
# ADD TO QUEUE
# ============================================================

    async def add_to_queue(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            queue = self.queues.setdefault(
                chat_id,
                [],
            )

            queue.append(
                track
            )

            position = len(
                queue
            )

            return {
                "status": "queued",
                "position": position,
                "queue_size": position,
                "track": track,
            }


# ============================================================
# NEXT
# ============================================================

    async def next(
        self,
        chat_id: int,
        automatic: bool = False,
    ) -> dict:
        """
        Skip current song and play the first song
        in the queue.

        If queue is empty, stop the call.
        """

        chat_id = int(
            chat_id
        )

        if chat_id in self._advancing:
            return {
                "status": "already_advancing"
            }

        self._advancing.add(
            chat_id
        )

        try:
            async with self._get_lock(
                chat_id
            ):
                old = self.current.get(
                    chat_id
                )

                queue = self.queues.setdefault(
                    chat_id,
                    [],
                )

                # --------------------------------------------
                # Save old track to history.
                # --------------------------------------------

                if old:
                    self.history.setdefault(
                        chat_id,
                        [],
                    ).append(
                        old
                    )

                # --------------------------------------------
                # Queue has another song.
                # --------------------------------------------

                if queue:
                    next_track = queue.pop(
                        0
                    )

                    result = await self._start_track_locked(
                        chat_id,
                        next_track,
                    )

                    result["automatic"] = automatic
                    result["remaining"] = len(
                        queue
                    )

                    logger.info(
                        "⏭️ Next | chat=%s | remaining=%s",
                        chat_id,
                        len(queue),
                    )

                    return result

                # --------------------------------------------
                # Queue empty.
                # --------------------------------------------

                self.current.pop(
                    chat_id,
                    None,
                )

                self.paused.pop(
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

                self.offset.pop(
                    chat_id,
                    None,
                )

                await self._call_leave(
                    chat_id
                )

                self.active_chat_ids.discard(
                    chat_id
                )

                logger.info(
                    "⏹️ Queue empty | chat=%s",
                    chat_id,
                )

                return {
                    "status": "empty",
                    "track": None,
                    "automatic": automatic,
                }

        finally:
            self._advancing.discard(
                chat_id
            )


# ============================================================
# STREAM END
# ============================================================

    async def on_stream_end(
        self,
        chat_id: int,
    ) -> dict:
        """
        Called by main.py after PyTgCalls reports
        that a stream has finished.
        """

        logger.info(
            "🎵 Stream ended | chat=%s",
            chat_id,
        )

        return await self.next(
            int(chat_id),
            automatic=True,
        )


    async def handle_stream_end(
        self,
        chat_id: int,
    ) -> dict:
        return await self.on_stream_end(
            chat_id
        )


# ============================================================
# PAUSE
# ============================================================

    async def pause(
        self,
        chat_id: int,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            track = self.current.get(
                chat_id
            )

            if not track:
                return {
                    "status": "nothing_playing"
                }

            if self.paused.get(
                chat_id,
                False,
            ):
                return {
                    "status": "already_paused",
                    "track": track,
                }

            pause_method = getattr(
                self.call,
                "pause",
                None,
            )

            if not callable(
                pause_method
            ):
                return {
                    "status": "unsupported"
                }

            try:
                result = pause_method(
                    chat_id
                )

                if asyncio.iscoroutine(result):
                    await result

            except Exception:
                logger.exception(
                    "Pause failed | chat=%s",
                    chat_id,
                )

                return {
                    "status": "error"
                }

            self.paused[chat_id] = True
            self.paused_at[chat_id] = (
                time.monotonic()
            )

            return {
                "status": "paused",
                "track": track,
            }


# ============================================================
# RESUME
# ============================================================

    async def resume(
        self,
        chat_id: int,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            track = self.current.get(
                chat_id
            )

            if not track:
                return {
                    "status": "nothing_playing"
                }

            if not self.paused.get(
                chat_id,
                False,
            ):
                return {
                    "status": "already_playing",
                    "track": track,
                }

            resume_method = getattr(
                self.call,
                "resume",
                None,
            )

            if not callable(
                resume_method
            ):
                return {
                    "status": "unsupported"
                }

            try:
                result = resume_method(
                    chat_id
                )

                if asyncio.iscoroutine(result):
                    await result

            except Exception:
                logger.exception(
                    "Resume failed | chat=%s",
                    chat_id,
                )

                return {
                    "status": "error"
                }

            # ------------------------------------------------
            # Adjust start time so paused duration does not
            # count as playback time.
            # ------------------------------------------------

            paused_at = self.paused_at.get(
                chat_id,
                0.0,
            )

            if paused_at:
                pause_duration = (
                    time.monotonic()
                    - paused_at
                )

                self.started_at[chat_id] += (
                    pause_duration
                )

            self.paused[chat_id] = False
            self.paused_at[chat_id] = 0.0

            return {
                "status": "resumed",
                "track": track,
            }


# ============================================================
# STOP / END
# ============================================================

    async def stop(
        self,
        chat_id: int,
        clear_queue: bool = True,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            current = self.current.get(
                chat_id
            )

            if clear_queue:
                self.queues.pop(
                    chat_id,
                    None,
                )

            self.current.pop(
                chat_id,
                None,
            )

            self.paused.pop(
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

            self.offset.pop(
                chat_id,
                None,
            )

            await self._call_leave(
                chat_id
            )

            self.active_chat_ids.discard(
                chat_id
            )

            logger.info(
                "⏹️ Stopped | chat=%s | queue_cleared=%s",
                chat_id,
                clear_queue,
            )

            return {
                "status": "stopped",
                "track": current,
                "queue_cleared": clear_queue,
            }


# ============================================================
# CLEAR QUEUE
# ============================================================

    async def clear_queue(
        self,
        chat_id: int,
    ) -> int:
        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            queue = self.queues.pop(
                chat_id,
                [],
            )

            count = len(
                queue
            )

            logger.info(
                "🗑️ Queue cleared | chat=%s | count=%s",
                chat_id,
                count,
            )

            return count


# ============================================================
# PREVIOUS
# ============================================================

    async def previous(
        self,
        chat_id: int,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        async with self._get_lock(
            chat_id
        ):
            history = self.history.setdefault(
                chat_id,
                [],
            )

            if not history:
                return {
                    "status": "no_history"
                }

            previous_track = history.pop()

            current = self.current.get(
                chat_id
            )

            if current:
                self.queues.setdefault(
                    chat_id,
                    [],
                ).insert(
                    0,
                    current,
                )

            result = await self._start_track_locked(
                chat_id,
                previous_track,
            )

            result["status"] = (
                "previous"
                if result.get("status") == "playing"
                else result.get("status")
            )

            return result


# ============================================================
# SEEK
# ============================================================

    async def seek(
        self,
        chat_id: int,
        seconds: int,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        seconds = max(
            0,
            int(seconds),
        )

        seek_method = getattr(
            self.call,
            "seek",
            None,
        )

        if not callable(
            seek_method
        ):
            return {
                "status": "unsupported"
            }

        try:
            result = seek_method(
                chat_id,
                seconds,
            )

            if asyncio.iscoroutine(result):
                await result

        except Exception:
            logger.exception(
                "Seek failed | chat=%s",
                chat_id,
            )

            return {
                "status": "error"
            }

        self.offset[chat_id] = float(
            seconds
        )

        self.started_at[chat_id] = (
            time.monotonic()
        )

        return {
            "status": "seeked",
            "seconds": seconds,
        }


# ============================================================
# POSITION
# ============================================================

    def get_position(
        self,
        chat_id: int,
    ) -> int:
        chat_id = int(
            chat_id
        )

        if chat_id not in self.current:
            return 0

        base = self.offset.get(
            chat_id,
            0.0,
        )

        if self.paused.get(
            chat_id,
            False,
        ):
            end = self.paused_at.get(
                chat_id,
                time.monotonic(),
            )

            start = self.started_at.get(
                chat_id,
                end,
            )

            return max(
                0,
                int(
                    base
                    + end
                    - start
                ),
            )

        started = self.started_at.get(
            chat_id,
            time.monotonic(),
        )

        return max(
            0,
            int(
                base
                + time.monotonic()
                - started
            ),
        )


# ============================================================
# VOLUME
# ============================================================

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> dict:
        chat_id = int(
            chat_id
        )

        volume = max(
            0,
            min(
                200,
                int(volume),
            ),
        )

        volume_method = getattr(
            self.call,
            "change_volume_call",
            None,
        )

        if not callable(
            volume_method
        ):
            volume_method = getattr(
                self.call,
                "set_volume",
                None,
            )

        if not callable(
            volume_method
        ):
            return {
                "status": "unsupported"
            }

        try:
            result = volume_method(
                chat_id,
                volume,
            )

            if asyncio.iscoroutine(result):
                await result

        except Exception:
            logger.exception(
                "Volume failed | chat=%s",
                chat_id,
            )

            return {
                "status": "error"
            }

        return {
            "status": "volume_changed",
            "volume": volume,
        }


# ============================================================
# CURRENT
# ============================================================

    def get_current(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:
        return self.current.get(
            int(chat_id)
        )


# ============================================================
# QUEUE
# ============================================================

    def get_queue(
        self,
        chat_id: int,
    ) -> list[TrackInfo]:
        return list(
            self.queues.get(
                int(chat_id),
                [],
            )
        )


    def queue_count(
        self,
        chat_id: int,
    ) -> int:
        return len(
            self.queues.get(
                int(chat_id),
                [],
            )
        )


# ============================================================
# STATE
# ============================================================

    def is_playing(
        self,
        chat_id: int,
    ) -> bool:
        return int(chat_id) in self.current


    def is_paused(
        self,
        chat_id: int,
    ) -> bool:
        return bool(
            self.paused.get(
                int(chat_id),
                False,
            )
        )


# ============================================================
# CLEANUP CHAT
# ============================================================

    async def cleanup_chat(
        self,
        chat_id: int,
    ):
        chat_id = int(
            chat_id
        )

        try:
            await self.stop(
                chat_id,
                clear_queue=True,
            )

        except Exception:
            logger.exception(
                "Cleanup failed | chat=%s",
                chat_id,
            )

        self.history.pop(
            chat_id,
            None,
        )

        self._advancing.discard(
            chat_id
        )

        self._locks.pop(
            chat_id,
            None,
        )


# ============================================================
# CLEANUP ALL
# ============================================================

    async def cleanup(self):
        chat_ids = set(
            self.active_chat_ids
        )

        chat_ids.update(
            self.current.keys()
        )

        chat_ids.update(
            self.queues.keys()
        )

        for chat_id in list(
            chat_ids
        ):
            try:
                await self.cleanup_chat(
                    chat_id
                )

            except Exception:
                logger.exception(
                    "Cleanup failed | chat=%s",
                    chat_id,
                )

        # ----------------------------------------------------
        # Do not delete downloads automatically here.
        #
        # Downloads can be reused by the next playback and
        # deleting them during normal shutdown is unnecessary.
        # ----------------------------------------------------


# ============================================================
# GLOBAL DOWNLOADER
# ============================================================

downloader = MusicDownloader()
