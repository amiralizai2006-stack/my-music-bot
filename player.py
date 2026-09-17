from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from pytgcalls.types import MediaStream

logger = logging.getLogger("SILENT.player")


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
    webpage_url: str = ""
    thumbnail: str = ""
    uploader: str = ""

    filepath: str = ""

    requested_by: int = 0
    requested_name: str = ""

    def __post_init__(self):
        self.title = str(self.title or "موزیک").strip() or "موزیک"

        self.performer = str(
            self.performer or ""
        ).strip()

        self.artist = str(
            self.artist or ""
        ).strip()

        if not self.performer:
            self.performer = self.artist

        if not self.artist:
            self.artist = self.performer

        self.duration = max(
            0,
            int(self.duration or 0),
        )

    @property
    def display_artist(self) -> str:
        return (
            self.performer
            or self.artist
            or self.uploader
            or "ناشناخته"
        )

    @property
    def duration_text(self) -> str:
        seconds = max(0, int(self.duration or 0))

        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"


# ============================================================
# DOWNLOADER
# ============================================================

class MusicDownloader:

    YOUTUBE_CLIENTS = (
        ["android_vr"],
        ["web_safari"],
        ["web_music"],
        ["tv_simply"],
        ["web"],
    )

    USER_AGENT = (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )

    def __init__(
        self,
        download_dir: str = "downloads",
    ):
        self.download_dir = Path(download_dir)

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ========================================================
    # SEARCH
    # ========================================================

    async def search(
        self,
        query: str,
        limit: int = 1,
    ) -> list[TrackInfo]:

        query = str(query or "").strip()

        if not query:
            return []

        limit = max(
            1,
            min(int(limit), 10),
        )

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
            ("http://", "https://")
        ):
            return self._extract_url(
                yt_dlp,
                query,
                limit,
            )

        sources = (
            (
                "soundcloud",
                f"scsearch{limit}:{query}",
            ),
            (
                "youtube",
                f"ytsearch{limit}:{query}",
            ),
        )

        for source_name, source in sources:

            try:

                if source_name == "youtube":
                    results = self._youtube_search(
                        yt_dlp,
                        source,
                        limit,
                    )
                else:
                    results = self._generic_search(
                        yt_dlp,
                        source,
                        limit,
                    )

                if results:
                    logger.info(
                        "SEARCH OK | source=%s | query=%s",
                        source_name,
                        query,
                    )
                    return results

            except Exception:
                logger.exception(
                    "SEARCH ERROR | source=%s | query=%s",
                    source_name,
                    query,
                )

        logger.warning(
            "NO SEARCH RESULT | %s",
            query,
        )

        return []

    # ========================================================
    # GENERIC SEARCH
    # ========================================================

    def _generic_search(
        self,
        yt_dlp,
        source: str,
        limit: int,
    ) -> list[TrackInfo]:

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        try:

            with yt_dlp.YoutubeDL(options) as ydl:

                info = ydl.extract_info(
                    source,
                    download=False,
                )

            return self._info_to_tracks(
                info,
                limit,
            )

        except Exception as exc:

            logger.warning(
                "GENERIC SEARCH FAILED | %s",
                exc,
            )

            return []

    # ========================================================
    # YOUTUBE SEARCH
    # ========================================================

    def _youtube_search(
        self,
        yt_dlp,
        source: str,
        limit: int,
    ) -> list[TrackInfo]:

        for client in self.YOUTUBE_CLIENTS:

            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "extract_flat": False,

                "extractor_args": {
                    "youtube": {
                        "player_client": client,
                    }
                },

                "http_headers": {
                    "User-Agent": self.USER_AGENT,
                },
            }

            try:

                with yt_dlp.YoutubeDL(options) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=False,
                    )

                results = self._info_to_tracks(
                    info,
                    limit,
                )

                if results:
                    return results

            except Exception as exc:

                logger.warning(
                    "YOUTUBE SEARCH FAILED | client=%s | %s",
                    client,
                    exc,
                )

        return []

    # ========================================================
    # DIRECT URL
    # ========================================================

    def _extract_url(
        self,
        yt_dlp,
        source: str,
        limit: int,
    ) -> list[TrackInfo]:

        is_youtube = (
            "youtube.com" in source
            or "youtu.be" in source
        )

        if is_youtube:

            for client in self.YOUTUBE_CLIENTS:

                options = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "noplaylist": True,
                    "extract_flat": False,

                    "extractor_args": {
                        "youtube": {
                            "player_client": client,
                        }
                    },

                    "http_headers": {
                        "User-Agent": self.USER_AGENT,
                    },
                }

                try:

                    with yt_dlp.YoutubeDL(options) as ydl:

                        info = ydl.extract_info(
                            source,
                            download=False,
                        )

                    results = self._info_to_tracks(
                        info,
                        limit,
                    )

                    if results:
                        return results

                except Exception as exc:

                    logger.warning(
                        "DIRECT YOUTUBE FAILED | client=%s | %s",
                        client,
                        exc,
                    )

            return []

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        try:

            with yt_dlp.YoutubeDL(options) as ydl:

                info = ydl.extract_info(
                    source,
                    download=False,
                )

            return self._info_to_tracks(
                info,
                limit,
            )

        except Exception as exc:

            logger.warning(
                "DIRECT URL FAILED | %s",
                exc,
            )

            return []

    # ========================================================
    # INFO -> TRACKS
    # ========================================================

    def _info_to_tracks(
        self,
        info: Optional[dict],
        limit: int,
    ) -> list[TrackInfo]:

        if not info:
            return []

        entries = info.get("entries")

        if entries is None:
            entries = [info]
        else:
            entries = [
                item
                for item in entries
                if item
            ]

        results: list[TrackInfo] = []

        for item in entries[:limit]:

            artist = (
                item.get("artist")
                or item.get("creator")
                or item.get("uploader")
                or item.get("channel")
                or ""
            )

            results.append(
                TrackInfo(
                    title=item.get(
                        "title",
                        "موزیک",
                    ),

                    performer=artist,
                    artist=artist,

                    duration=int(
                        item.get(
                            "duration",
                            0,
                        )
                        or 0
                    ),

                    url=item.get(
                        "url",
                        "",
                    )
                    or "",

                    webpage_url=(
                        item.get(
                            "webpage_url",
                            "",
                        )
                        or item.get(
                            "original_url",
                            "",
                        )
                        or ""
                    ),

                    thumbnail=item.get(
                        "thumbnail",
                        "",
                    )
                    or "",

                    uploader=(
                        item.get(
                            "uploader",
                            "",
                        )
                        or item.get(
                            "channel",
                            "",
                        )
                        or ""
                    ),
                )
            )

        return results

    # ========================================================
    # DOWNLOAD
    # ========================================================

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:

        source = (
            track.webpage_url
            or track.url
        )

        if not source:
            logger.error(
                "DOWNLOAD FAILED | no source"
            )
            return None

        return await asyncio.to_thread(
            self._download_sync,
            source,
            track,
        )

    def _download_sync(
        self,
        source: str,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:

        import yt_dlp

        is_youtube = (
            "youtube.com" in source
            or "youtu.be" in source
        )

        clients = (
            self.YOUTUBE_CLIENTS
            if is_youtube
            else (None,)
        )

        for client in clients:

            output = str(
                self.download_dir
                / "%(id)s.%(ext)s"
            )

            options = {
                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best"
                ),

                "outtmpl": output,

                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "overwrites": False,

                "retries": 3,
                "fragment_retries": 3,
                "continuedl": True,

                "socket_timeout": 20,

                "http_headers": {
                    "User-Agent": self.USER_AGENT,
                },
            }

            if client:

                options["extractor_args"] = {
                    "youtube": {
                        "player_client": client,
                    }
                }

            try:

                logger.info(
                    "DOWNLOAD | source=%s | client=%s",
                    source,
                    client,
                )

                with yt_dlp.YoutubeDL(options) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=True,
                    )

                    if not info:
                        continue

                    entries = info.get("entries")

                    if entries:

                        entries = [
                            item
                            for item in entries
                            if item
                        ]

                        if not entries:
                            continue

                        info = entries[0]

                    filepath = None

                    requested = (
                        info.get(
                            "requested_downloads"
                        )
                        or []
                    )

                    for item in requested:

                        path = item.get(
                            "filepath"
                        )

                        if path:
                            filepath = path
                            break

                    if not filepath:

                        try:
                            filepath = ydl.prepare_filename(
                                info
                            )
                        except Exception:
                            filepath = None

                    if filepath:

                        path = Path(filepath)

                        if self._valid_file(path):

                            self._update_track(
                                track,
                                info,
                                path,
                            )

                            return track

                    newest = self._newest_file()

                    if newest:

                        self._update_track(
                            track,
                            info,
                            newest,
                        )

                        return track

            except Exception as exc:

                logger.warning(
                    "DOWNLOAD FAILED | client=%s | %s",
                    client,
                    exc,
                )

        logger.error(
            "ALL DOWNLOAD METHODS FAILED | %s",
            source,
        )

        return None

    # ========================================================
    # FILE HELPERS
    # ========================================================

    @staticmethod
    def _valid_file(
        path: Path,
    ) -> bool:

        try:
            return (
                path.exists()
                and path.is_file()
                and path.stat().st_size > 1024
            )
        except OSError:
            return False

    def _newest_file(self) -> Optional[Path]:

        try:

            files = [
                path
                for path in self.download_dir.iterdir()
                if self._valid_file(path)
            ]

        except OSError:
            return None

        if not files:
            return None

        return max(
            files,
            key=lambda p: p.stat().st_mtime,
        )

    # ========================================================
    # UPDATE TRACK
    # ========================================================

    def _update_track(
        self,
        track: TrackInfo,
        info: dict,
        path: Path,
    ):

        artist = (
            info.get("artist")
            or info.get("creator")
            or info.get("uploader")
            or info.get("channel")
            or track.performer
            or ""
        )

        track.title = (
            info.get("title")
            or track.title
            or "موزیک"
        )

        track.performer = artist
        track.artist = artist

        track.duration = int(
            info.get("duration")
            or track.duration
            or 0
        )

        track.url = (
            info.get("url")
            or track.url
            or ""
        )

        track.webpage_url = (
            info.get("webpage_url")
            or info.get("original_url")
            or track.webpage_url
            or ""
        )

        track.thumbnail = (
            info.get("thumbnail")
            or track.thumbnail
            or ""
        )

        track.uploader = (
            info.get("uploader")
            or info.get("channel")
            or track.uploader
            or ""
        )

        track.filepath = str(
            path.resolve()
        )

    # ========================================================
    # PREPARE
    # ========================================================

    async def prepare(
        self,
        track: TrackInfo,
    ) -> Optional[TrackInfo]:

        if track.filepath:

            path = Path(
                track.filepath
            )

            if self._valid_file(path):
                return track

        return await self.download(track)


# ============================================================
# MUSIC PLAYER
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

        self.current: dict[int, TrackInfo] = {}
        self.queues: dict[int, list[TrackInfo]] = {}
        self.history: dict[int, list[TrackInfo]] = {}

        self.paused: set[int] = set()

        self.started_at: dict[int, float] = {}
        self.offset: dict[int, int] = {}
        self.volume: dict[int, int] = {}

        self.locks: dict[int, asyncio.Lock] = {}

    # ========================================================
    # LOCK
    # ========================================================

    def _lock(
        self,
        chat_id: int,
    ) -> asyncio.Lock:

        return self.locks.setdefault(
            chat_id,
            asyncio.Lock(),
        )

    # ========================================================
    # QUEUE
    # ========================================================

    def _queue(
        self,
        chat_id: int,
    ) -> list[TrackInfo]:

        return self.queues.setdefault(
            chat_id,
            [],
        )

    # ========================================================
    # INTERNAL STREAM
    # ========================================================

    async def _play_file(
        self,
        chat_id: int,
        filepath: str,
    ) -> bool:

        if self.call is None:
            return False

        path = Path(filepath).resolve()

        if not self.downloader._valid_file(path):
            return False

        stream = MediaStream(
            str(path),
            video_flags=MediaStream.Flags.IGNORE,
        )

        await self.call.play(
            chat_id,
            stream,
        )

        return True

    # ========================================================
    # PLAY TRACK
    # ========================================================

    async def play_track(
        self,
        chat_id: int,
        track: TrackInfo,
        *,
        save_history: bool = True,
    ) -> bool:

        if self.call is None:
            logger.error(
                "PLAY FAILED | PyTgCalls unavailable"
            )
            return False

        if not track:
            return False

        async with self._lock(chat_id):

            try:

                prepared = await self.downloader.prepare(
                    track
                )

                if not prepared:
                    logger.error(
                        "PLAY FAILED | prepare returned None"
                    )
                    return False

                filepath = Path(
                    prepared.filepath
                ).resolve()

                if not self.downloader._valid_file(
                    filepath
                ):
                    logger.error(
                        "PLAY FAILED | invalid file=%s",
                        filepath,
                    )
                    return False

                prepared.filepath = str(filepath)

                old = self.current.get(chat_id)

                if (
                    old
                    and save_history
                    and old is not prepared
                ):

                    history = self.history.setdefault(
                        chat_id,
                        [],
                    )

                    history.append(old)

                    del history[:-20]

                if not await self._play_file(
                    chat_id,
                    prepared.filepath,
                ):
                    return False

                self.current[chat_id] = prepared

                self.started_at[chat_id] = time.monotonic()
                self.offset[chat_id] = 0

                self.paused.discard(chat_id)

                logger.info(
                    "🟢 NOW PLAYING | chat=%s | title=%s | artist=%s",
                    chat_id,
                    prepared.title,
                    prepared.display_artist,
                )

                return True

            except Exception:
                logger.exception(
                    "PLAY ERROR | chat=%s | title=%s",
                    chat_id,
                    getattr(
                        track,
                        "title",
                        "unknown",
                    ),
                )
                return False

    # ========================================================
    # PLAY / QUEUE
    # ========================================================

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if chat_id in self.current:
            return await self.add_to_queue(
                chat_id,
                track,
            ) > 0

        return await self.play_track(
            chat_id,
            track,
        )

    async def add_to_queue(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> int:

        queue = self._queue(chat_id)

        queue.append(track)

        logger.info(
            "➕ QUEUED | chat=%s | position=%s | title=%s",
            chat_id,
            len(queue),
            track.title,
        )

        return len(queue)

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        if (
            self.call is None
            or chat_id not in self.current
            or chat_id in self.paused
        ):
            return False

        try:

            self.offset[chat_id] = await self.get_position(
                chat_id
            )

            await self.call.pause(chat_id)

            self.paused.add(chat_id)

            logger.info(
                "⏸️ PAUSED | chat=%s | position=%s",
                chat_id,
                self.offset[chat_id],
            )

            return True

        except Exception:
            logger.exception(
                "PAUSE FAILED | chat=%s",
                chat_id,
            )
            return False

    # ========================================================
    # RESUME
    # ========================================================

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        if (
            self.call is None
            or chat_id not in self.current
            or chat_id not in self.paused
        ):
            return False

        try:

            await self.call.resume(chat_id)

            self.started_at[chat_id] = time.monotonic()

            self.paused.discard(chat_id)

            logger.info(
                "▶️ RESUMED | chat=%s",
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "RESUME FAILED | chat=%s",
                chat_id,
            )
            return False

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        if self.call is None:
            return False

        success = False

        try:

            await self.call.leave_call(chat_id)
            success = True

        except Exception:

            try:

                await self.call.leave_group_call(
                    chat_id
                )
                success = True

            except Exception:
                logger.warning(
                    "LEAVE CALL FAILED | chat=%s",
                    chat_id,
                    exc_info=True,
                )

        self.current.pop(chat_id, None)
        self.queues.pop(chat_id, None)
        self.paused.discard(chat_id)
        self.started_at.pop(chat_id, None)
        self.offset.pop(chat_id, None)

        logger.info(
            "⏹️ STOPPED | chat=%s",
            chat_id,
        )

        return success

    # ========================================================
    # NEXT
    # ========================================================

    async def next(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        queue = self._queue(chat_id)

        if not queue:
            await self.stop(chat_id)
            return None

        track = queue.pop(0)

        if await self.play_track(
            chat_id,
            track,
            save_history=True,
        ):
            return self.current.get(chat_id)

        # اگر پخش آهنگ بعدی شکست خورد،
        # بقیه صف را نگه می‌داریم.
        return None

    # ========================================================
    # PREVIOUS
    # ========================================================

    async def previous(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        history = self.history.get(
            chat_id,
            [],
        )

        if not history:
            return None

        track = history.pop()

        if await self.play_track(
            chat_id,
            track,
            save_history=False,
        ):
            return self.current.get(chat_id)

        history.append(track)

        return None

    # ========================================================
    # SEEK
    # ========================================================

    async def seek(
        self,
        chat_id: int,
        seconds: int,
    ) -> bool:

        """
        تغییر موقعیت پخش.

        PyTgCalls در این لایه API عمومی seek مستقیم ندارد،
        بنابراین برای جلوگیری از خراب شدن استریم، seek به شکل
        restart از ابتدای فایل انجام نمی‌شود و فقط زمانی
        فعال می‌شود که پیاده‌سازی call یک متد seek داشته باشد.
        """

        if (
            self.call is None
            or chat_id not in self.current
        ):
            return False

        seek_method = getattr(
            self.call,
            "seek",
            None,
        )

        if not callable(seek_method):
            return False

        try:

            current_position = await self.get_position(
                chat_id
            )

            target = max(
                0,
                current_position + int(seconds),
            )

            duration = self.current[
                chat_id
            ].duration

            if duration > 0:
                target = min(
                    target,
                    duration - 1,
                )

            result = seek_method(
                chat_id,
                target,
            )

            if asyncio.iscoroutine(result):
                await result

            self.offset[chat_id] = target
            self.started_at[chat_id] = time.monotonic()

            logger.info(
                "⏩ SEEK | chat=%s | target=%s",
                chat_id,
                target,
            )

            return True

        except Exception:
            logger.exception(
                "SEEK FAILED | chat=%s",
                chat_id,
            )
            return False

    # ========================================================
    # POSITION
    # ========================================================

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

        started = self.started_at.get(chat_id)

        if started is None:
            return 0

        position = (
            self.offset.get(
                chat_id,
                0,
            )
            + (
                time.monotonic()
                - started
            )
        )

        duration = int(
            self.current[
                chat_id
            ].duration
            or 0
        )

        if duration > 0:
            position = min(
                position,
                duration,
            )

        return max(
            0,
            int(position),
        )

    # ========================================================
    # VOLUME
    # ========================================================

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:

        if self.call is None:
            return False

        if chat_id not in self.current:
            return False

        try:

            volume = max(
                1,
                min(
                    200,
                    int(volume),
                ),
            )

            await self.call.change_volume(
                chat_id,
                volume,
            )

            self.volume[chat_id] = volume

            logger.info(
                "🔊 VOLUME | chat=%s | volume=%s",
                chat_id,
                volume,
            )

            return True

        except Exception:
            logger.exception(
                "VOLUME FAILED | chat=%s",
                chat_id,
            )
            return False

    def get_volume(
        self,
        chat_id: int,
    ) -> int:

        return self.volume.get(
            chat_id,
            100,
        )

    # ========================================================
    # CURRENT
    # ========================================================

    def get_current(
        self,
        chat_id: int,
    ) -> Optional[TrackInfo]:

        return self.current.get(chat_id)

    # ========================================================
    # QUEUE
    # ========================================================

    def get_queue(
        self,
        chat_id: int,
    ) -> list[TrackInfo]:

        return list(
            self.queues.get(
                chat_id,
                [],
            )
        )

    # ========================================================
    # STATE
    # ========================================================

    def is_playing(
        self,
        chat_id: int,
    ) -> bool:

        return (
            chat_id in self.current
            and chat_id not in self.paused
        )

    def is_paused(
        self,
        chat_id: int,
    ) -> bool:

        return (
            chat_id in self.current
            and chat_id in self.paused
        )

    def queue_count(
        self,
        chat_id: int,
    ) -> int:

        return len(
            self.queues.get(
                chat_id,
                [],
            )
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup_chat(
        self,
        chat_id: int,
    ):

        self.current.pop(chat_id, None)
        self.queues.pop(chat_id, None)
        self.history.pop(chat_id, None)

        self.paused.discard(chat_id)

        self.started_at.pop(chat_id, None)
        self.offset.pop(chat_id, None)
        self.volume.pop(chat_id, None)
        self.locks.pop(chat_id, None)

        logger.info(
            "🧹 CLEANUP | chat=%s",
            chat_id,
        )
