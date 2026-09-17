from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from pytgcalls.types import MediaStream

logger = logging.getLogger(__name__)


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

    def __post_init__(self):

        if not self.performer:
            self.performer = self.artist

        if not self.artist:
            self.artist = self.performer


# ============================================================
# DOWNLOADER
# ============================================================

class MusicDownloader:

    def __init__(self, download_dir="downloads"):

        self.download_dir = Path(
            download_dir
        )

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    # ========================================================
    # SEARCH
    # ========================================================

    async def search(
        self,
        query: str,
        limit: int = 1
    ):

        query = (
            query or ""
        ).strip()

        if not query:
            return []

        return await asyncio.to_thread(
            self._search_sync,
            query,
            limit
        )

    def _search_sync(
        self,
        query,
        limit=1
    ):

        import yt_dlp

        # ----------------------------------------------------
        # DIRECT URL
        # ----------------------------------------------------

        if query.startswith(
            ("http://", "https://")
        ):

            return self._extract_url(
                yt_dlp,
                query,
                limit
            )

        # ----------------------------------------------------
        # SEARCH SOURCES
        # ----------------------------------------------------
        #
        # اول SoundCloud
        # سپس YouTube
        #
        # اگر YouTube روی IP سرور Render
        # bot-check بدهد، SoundCloud همچنان
        # می‌تواند نتیجه بدهد.
        # ----------------------------------------------------

        sources = [
            (
                "soundcloud",
                f"scsearch{limit}:{query}"
            ),
            (
                "youtube",
                f"ytsearch{limit}:{query}"
            ),
        ]

        for source_name, source in sources:

            if source_name == "youtube":

                results = (
                    self._youtube_search(
                        yt_dlp,
                        source,
                        limit
                    )
                )

            else:

                results = (
                    self._generic_search(
                        yt_dlp,
                        source,
                        limit
                    )
                )

            if results:

                logger.info(
                    "SEARCH SUCCESS source=%s query=%s",
                    source_name,
                    query
                )

                return results

        logger.error(
            "ALL SEARCH SOURCES FAILED: %s",
            query
        )

        return []

    # ========================================================
    # GENERIC SEARCH
    # ========================================================

    def _generic_search(
        self,
        yt_dlp,
        source,
        limit
    ):

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        try:

            logger.info(
                "Searching generic source: %s",
                source
            )

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                info = ydl.extract_info(
                    source,
                    download=False
                )

            return self._info_to_tracks(
                info,
                limit
            )

        except Exception as e:

            logger.warning(
                "Generic search failed: %s",
                e
            )

            return []

    # ========================================================
    # YOUTUBE SEARCH
    # ========================================================

    def _youtube_search(
        self,
        yt_dlp,
        source,
        limit
    ):

        clients = [
            ["android_vr"],
            ["web_safari"],
            ["web_music"],
            ["tv_simply"],
            ["web"],
        ]

        for client in clients:

            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "extract_flat": False,

                "extractor_args": {
                    "youtube": {
                        "player_client": client
                    }
                },

                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(X11; Linux x86_64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/131.0 Safari/537.36"
                    )
                },
            }

            try:

                logger.info(
                    "YouTube search client=%s",
                    client
                )

                with yt_dlp.YoutubeDL(
                    options
                ) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=False
                    )

                results = self._info_to_tracks(
                    info,
                    limit
                )

                if results:
                    return results

            except Exception as e:

                logger.warning(
                    "YouTube client %s failed: %s",
                    client,
                    e
                )

        return []

    # ========================================================
    # DIRECT URL EXTRACT
    # ========================================================

    def _extract_url(
        self,
        yt_dlp,
        source,
        limit
    ):

        # اگر URL یوتیوب است، کلاینت‌های مختلف
        # امتحان شوند.
        if (
            "youtube.com" in source
            or "youtu.be" in source
        ):

            clients = [
                ["android_vr"],
                ["web_safari"],
                ["web_music"],
                ["tv_simply"],
                ["web"],
            ]

            for client in clients:

                options = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "noplaylist": True,
                    "extract_flat": False,

                    "extractor_args": {
                        "youtube": {
                            "player_client": client
                        }
                    },

                    "http_headers": {
                        "User-Agent": (
                            "Mozilla/5.0 "
                            "(X11; Linux x86_64) "
                            "AppleWebKit/537.36 "
                            "(KHTML, like Gecko) "
                            "Chrome/131.0 Safari/537.36"
                        )
                    },
                }

                try:

                    with yt_dlp.YoutubeDL(
                        options
                    ) as ydl:

                        info = ydl.extract_info(
                            source,
                            download=False
                        )

                    results = self._info_to_tracks(
                        info,
                        limit
                    )

                    if results:
                        return results

                except Exception as e:

                    logger.warning(
                        "Direct YouTube client %s failed: %s",
                        client,
                        e
                    )

            return []

        # ----------------------------------------------------
        # Other supported direct URLs
        # ----------------------------------------------------

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
                    source,
                    download=False
                )

            return self._info_to_tracks(
                info,
                limit
            )

        except Exception as e:

            logger.warning(
                "Direct URL extraction failed: %s",
                e
            )

            return []

    # ========================================================
    # INFO -> TRACKS
    # ========================================================

    def _info_to_tracks(
        self,
        info,
        limit
    ):

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

        else:

            entries = [info]

        if not entries:
            return []

        results = []

        for item in entries[:limit]:

            artist = (
                item.get("artist")
                or item.get("creator")
                or item.get("uploader")
                or item.get("channel")
                or ""
            )

            webpage_url = (
                item.get("webpage_url")
                or item.get("original_url")
                or ""
            )

            direct_url = (
                item.get("url")
                or ""
            )

            results.append(
                TrackInfo(
                    title=(
                        item.get("title")
                        or "موزیک"
                    ),

                    performer=artist,
                    artist=artist,

                    duration=int(
                        item.get("duration")
                        or 0
                    ),

                    url=direct_url,

                    webpage_url=webpage_url,

                    thumbnail=(
                        item.get("thumbnail")
                        or ""
                    ),

                    uploader=(
                        item.get("uploader")
                        or item.get("channel")
                        or ""
                    )
                )
            )

        return results

    # ========================================================
    # DOWNLOAD
    # ========================================================

    async def download(
        self,
        track: TrackInfo
    ):

        source = (
            track.webpage_url
            or track.url
        )

        if not source:

            logger.error(
                "DOWNLOAD FAILED: no source URL"
            )

            return None

        return await asyncio.to_thread(
            self._download_sync,
            source,
            track
        )

    def _download_sync(
        self,
        source,
        track
    ):

        import yt_dlp

        is_youtube = (
            "youtube.com" in source
            or "youtu.be" in source
        )

        if is_youtube:

            clients = [
                ["android_vr"],
                ["web_safari"],
                ["web_music"],
                ["tv_simply"],
                ["web"],
            ]

        else:

            clients = [None]

        for client in clients:

            output = str(
                self.download_dir
                / "%(id)s.%(ext)s"
            )

            options = {

                "format":
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best",

                "outtmpl": output,

                "noplaylist": True,

                "quiet": True,

                "no_warnings": True,

                "overwrites": False,

            }

            # فقط برای YouTube
            if client:

                options[
                    "extractor_args"
                ] = {
                    "youtube": {
                        "player_client": client
                    }
                }

                options[
                    "http_headers"
                ] = {
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(X11; Linux x86_64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/131.0 Safari/537.36"
                    )
                }

            try:

                logger.info(
                    "DOWNLOAD source=%s client=%s",
                    source,
                    client
                )

                with yt_dlp.YoutubeDL(
                    options
                ) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=True
                    )

                    if not info:
                        continue

                    entries = info.get(
                        "entries"
                    )

                    if entries:

                        entries = [
                            x
                            for x in entries
                            if x
                        ]

                        if not entries:
                            continue

                        info = entries[0]

                    # ----------------------------------------
                    # requested_downloads
                    # ----------------------------------------

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

                    # ----------------------------------------
                    # prepare_filename
                    # ----------------------------------------

                    if not filepath:

                        try:

                            filepath = (
                                ydl.prepare_filename(
                                    info
                                )
                            )

                        except Exception:

                            filepath = None

                    # ----------------------------------------
                    # FILE EXISTS
                    # ----------------------------------------

                    if filepath:

                        path = Path(
                            filepath
                        )

                        if (
                            path.exists()
                            and path.is_file()
                            and path.stat().st_size > 1024
                        ):

                            self._update_track(
                                track,
                                info,
                                path
                            )

                            logger.info(
                                "DOWNLOAD OK: %s",
                                path
                            )

                            return track

                    # ----------------------------------------
                    # FALLBACK
                    # ----------------------------------------

                    files = sorted(
                        self.download_dir.glob("*"),
                        key=lambda p: (
                            p.stat().st_mtime
                        ),
                        reverse=True
                    )

                    for path in files:

                        if (
                            path.is_file()
                            and path.stat().st_size > 1024
                        ):

                            self._update_track(
                                track,
                                info,
                                path
                            )

                            logger.info(
                                "DOWNLOAD FALLBACK OK: %s",
                                path
                            )

                            return track

            except Exception as e:

                logger.warning(
                    "DOWNLOAD FAILED "
                    "source=%s client=%s error=%s",
                    source,
                    client,
                    e
                )

        logger.error(
            "ALL DOWNLOAD METHODS FAILED: %s",
            source
        )

        return None

    # ========================================================
    # UPDATE TRACK
    # ========================================================

    def _update_track(
        self,
        track,
        info,
        path
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
        )

        track.performer = artist
        track.artist = artist

        track.duration = int(
            info.get("duration")
            or track.duration
            or 0
        )

        track.thumbnail = (
            info.get("thumbnail")
            or track.thumbnail
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
        track
    ):

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
# MUSIC PLAYER
# ============================================================

class MusicPlayer:

    def __init__(
        self,
        app: Any = None,
        call: Any = None,
        download_dir="downloads"
    ):

        self.app = app

        self.call = call

        self.downloader = MusicDownloader(
            download_dir
        )

        self.current = {}
        self.queues = {}
        self.history = {}

        self.paused = set()

        self.started_at = {}
        self.offset = {}

        self.volume = {}

    # ========================================================
    # QUEUE
    # ========================================================

    def _queue(
        self,
        chat_id
    ):

        return self.queues.setdefault(
            chat_id,
            []
        )

    # ========================================================
    # PLAY TRACK
    # ========================================================

    async def play_track(
        self,
        chat_id,
        track
    ):

        if self.call is None:

            logger.error(
                "PLAY FAILED: PyTgCalls is None"
            )

            return False

        try:

            # -----------------------------------------------
            # Prepare / download
            # -----------------------------------------------

            prepared = (
                await self.downloader.prepare(
                    track
                )
            )

            if not prepared:

                logger.error(
                    "PLAY FAILED: prepare returned None"
                )

                return False

            if not prepared.filepath:

                logger.error(
                    "PLAY FAILED: filepath is empty"
                )

                return False

            filepath = Path(
                prepared.filepath
            ).resolve()

            if not filepath.exists():

                logger.error(
                    "PLAY FAILED: file does not exist: %s",
                    filepath
                )

                return False

            if filepath.stat().st_size < 1024:

                logger.error(
                    "PLAY FAILED: file is too small: %s",
                    filepath
                )

                return False

            prepared.filepath = str(
                filepath
            )

            logger.info(
                "🎵 Preparing MediaStream: %s",
                filepath
            )

            # -----------------------------------------------
            # Audio-only MediaStream
            # -----------------------------------------------
            #
            # video_flags=IGNORE means Telegram voice chat
            # receives audio only.
            #
            # This is the official PyTgCalls pattern.
            # -----------------------------------------------

            stream = MediaStream(
                str(filepath),
                video_flags=(
                    MediaStream.Flags.IGNORE
                )
            )

            logger.info(
                "▶️ Calling PyTgCalls.play chat=%s file=%s",
                chat_id,
                filepath
            )

            # -----------------------------------------------
            # ACTUAL PLAY
            # -----------------------------------------------

            await self.call.play(
                chat_id,
                stream
            )

            # -----------------------------------------------
            # HISTORY
            # -----------------------------------------------

            old = self.current.get(
                chat_id
            )

            if old:

                self.history.setdefault(
                    chat_id,
                    []
                ).append(
                    old
                )

            # -----------------------------------------------
            # CURRENT
            # -----------------------------------------------

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
                "🟢 NOW PLAYING: %s",
                prepared.title
            )

            return True

        except Exception as e:

            logger.exception(
                "❌ REAL PLAY ERROR chat=%s: %s",
                chat_id,
                e
            )

            return False

    # ========================================================
    # PLAY
    # ========================================================

    async def play(
        self,
        chat_id,
        track
    ):

        if chat_id in self.current:

            self._queue(
                chat_id
            ).append(
                track
            )

            logger.info(
                "➕ Added to queue: %s",
                track.title
            )

            return True

        return await self.play_track(
            chat_id,
            track
        )

    # ========================================================
    # ADD QUEUE
    # ========================================================

    async def add_to_queue(
        self,
        chat_id,
        track
    ):

        queue = self._queue(
            chat_id
        )

        queue.append(
            track
        )

        return len(queue)

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id
    ):

        if (
            self.call is None
            or chat_id not in self.current
        ):

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

        except Exception as e:

            logger.exception(
                "Pause failed: %s",
                e
            )

            return False

    # ========================================================
    # RESUME
    # ========================================================

    async def resume(
        self,
        chat_id
    ):

        if (
            self.call is None
            or chat_id not in self.current
        ):

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

        except Exception as e:

            logger.exception(
                "Resume failed: %s",
                e
            )

            return False

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id
    ):

        if self.call is None:

            return False

        try:

            await self.call.leave_call(
                chat_id
            )

        except Exception:

            try:

                await self.call.leave_group_call(
                    chat_id
                )

            except Exception:

                logger.exception(
                    "Could not leave call"
                )

        self.current.pop(
            chat_id,
            None
        )

        self.queues.pop(
            chat_id,
            None
        )

        self.paused.discard(
            chat_id
        )

        self.started_at.pop(
            chat_id,
            None
        )

        self.offset.pop(
            chat_id,
            None
        )

        return True

    # ========================================================
    # NEXT
    # ========================================================

    async def next(
        self,
        chat_id
    ):

        queue = self._queue(
            chat_id
        )

        if not queue:

            await self.stop(
                chat_id
            )

            return None

        track = queue.pop(
            0
        )

        if await self.play_track(
            chat_id,
            track
        ):

            return self.current.get(
                chat_id
            )

        return None

    # ========================================================
    # PREVIOUS
    # ========================================================

    async def previous(
        self,
        chat_id
    ):

        history = self.history.setdefault(
            chat_id,
            []
        )

        if not history:

            return None

        track = history.pop()

        if await self.play_track(
            chat_id,
            track
        ):

            return self.current.get(
                chat_id
            )

        return None

    # ========================================================
    # POSITION
    # ========================================================

    async def get_position(
        self,
        chat_id
    ):

        if chat_id not in self.current:

            return 0

        if chat_id in self.paused:

            return int(
                self.offset.get(
                    chat_id,
                    0
                )
            )

        started = self.started_at.get(
            chat_id
        )

        if started is None:

            return 0

        return max(
            0,
            int(
                self.offset.get(
                    chat_id,
                    0
                )
                + time.monotonic()
                - started
            )
        )

    # ========================================================
    # VOLUME
    # ========================================================

    async def set_volume(
        self,
        chat_id,
        volume
    ):

        if self.call is None:

            return False

        try:

            volume = max(
                1,
                min(
                    200,
                    int(volume)
                )
            )

            await self.call.change_volume(
                chat_id,
                volume
            )

            self.volume[
                chat_id
            ] = volume

            return True

        except Exception as e:

            logger.exception(
                "Volume failed: %s",
                e
            )

            return False

    # ========================================================
    # CURRENT
    # ========================================================

    def get_current(
        self,
        chat_id
    ):

        return self.current.get(
            chat_id
        )

    # ========================================================
    # QUEUE
    # ========================================================

    def get_queue(
        self,
        chat_id
    ):

        return list(
            self._queue(
                chat_id
            )
        )
