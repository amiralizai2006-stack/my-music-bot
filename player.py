from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from pytgcalls.types import MediaStream

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
        if not self.performer:
            self.performer = self.artist
        if not self.artist:
            self.artist = self.performer


class MusicDownloader:

    def __init__(self, download_dir="downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # YOUTUBE SEARCH
    # -------------------------

    async def search(self, query: str, limit: int = 1):
        query = (query or "").strip()

        if not query:
            return []

        return await asyncio.to_thread(
            self._search_sync,
            query,
            limit
        )

    def _search_sync(self, query, limit=1):

        import yt_dlp

        source = (
            query
            if query.startswith(("http://", "https://"))
            else f"ytsearch{limit}:{query}"
        )

        clients = [
            ["android_vr"],
            ["web_safari"],
            ["web_music"],
            ["tv_simply"],
            ["web"],
        ]

        for clients_list in clients:

            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "extract_flat": False,

                "extractor_args": {
                    "youtube": {
                        "player_client": clients_list
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
                    "YouTube search using client=%s",
                    clients_list
                )

                with yt_dlp.YoutubeDL(options) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=False
                    )

                if not info:
                    continue

                entries = info.get("entries")

                if entries is not None:
                    entries = [
                        x for x in entries
                        if x
                    ]
                else:
                    entries = [info]

                if not entries:
                    continue

                result = []

                for item in entries[:limit]:

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
                                item.get("duration")
                                or 0
                            ),

                            url=(
                                item.get("url")
                                or ""
                            ),

                            webpage_url=(
                                item.get("webpage_url")
                                or item.get("original_url")
                                or ""
                            ),

                            thumbnail=(
                                item.get("thumbnail")
                                or ""
                            ),

                            uploader=(
                                item.get("uploader")
                                or ""
                            )
                        )
                    )

                if result:
                    return result

            except Exception as e:

                logger.warning(
                    "YouTube client %s failed: %s",
                    clients_list,
                    e
                )

        logger.error(
            "All YouTube clients failed for: %s",
            query
        )

        return []

    # -------------------------
    # YOUTUBE DOWNLOAD
    # -------------------------

    async def download(self, track: TrackInfo):

        import yt_dlp

        source = (
            track.webpage_url
            or track.url
        )

        if not source:
            logger.error(
                "No source URL"
            )
            return None

        return await asyncio.to_thread(
            self._download_sync,
            source,
            track
        )

    def _download_sync(self, source, track):

        import yt_dlp

        clients = [
            ["android_vr"],
            ["web_safari"],
            ["web_music"],
            ["tv_simply"],
            ["web"],
        ]

        for clients_list in clients:

            output = str(
                self.download_dir /
                "%(id)s.%(ext)s"
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

                "extractor_args": {
                    "youtube": {
                        "player_client": clients_list
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
                    "YouTube download client=%s",
                    clients_list
                )

                with yt_dlp.YoutubeDL(options) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=True
                    )

                if not info:
                    continue

                entries = info.get("entries")

                if entries:
                    entries = [
                        x for x in entries
                        if x
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
                        filepath = (
                            ydl.prepare_filename(
                                info
                            )
                        )
                    except Exception:
                        filepath = None

                if filepath:

                    path = Path(filepath)

                    if path.exists():

                        artist = (
                            info.get("artist")
                            or info.get("creator")
                            or info.get("uploader")
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

                        logger.info(
                            "DOWNLOAD OK: %s",
                            track.filepath
                        )

                        return track

                # fallback: newest file
                files = sorted(
                    self.download_dir.glob("*"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )

                for path in files:

                    if (
                        path.is_file()
                        and path.stat().st_size > 1024
                    ):

                        track.filepath = str(
                            path.resolve()
                        )

                        logger.info(
                            "DOWNLOAD FALLBACK OK: %s",
                            track.filepath
                        )

                        return track

            except Exception as e:

                logger.warning(
                    "Download failed with %s: %s",
                    clients_list,
                    e
                )

        logger.error(
            "ALL YOUTUBE DOWNLOAD CLIENTS FAILED"
        )

        return None

    # -------------------------
    # PREPARE
    # -------------------------

    async def prepare(self, track):

        if (
            track.filepath
            and Path(track.filepath).exists()
        ):
            return track

        return await self.download(track)


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

    def _queue(self, chat_id):
        return self.queues.setdefault(
            chat_id,
            []
        )

    # -------------------------
    # PLAY
    # -------------------------

    async def play_track(
        self,
        chat_id,
        track
    ):

        if self.call is None:

            logger.error(
                "PyTgCalls client is None"
            )

            return False

        try:

            prepared = await self.downloader.prepare(
                track
            )

            if not prepared:
                return False

            if not prepared.filepath:
                return False

            filepath = Path(
                prepared.filepath
            ).resolve()

            if not filepath.exists():
                return False

            if filepath.stat().st_size < 1024:
                return False

            prepared.filepath = str(
                filepath
            )

            logger.info(
                "Creating MediaStream: %s",
                filepath
            )

            stream = MediaStream(
                str(filepath),
                video_flags=MediaStream.Flags.IGNORE
            )

            logger.info(
                "Calling PyTgCalls.play chat=%s",
                chat_id
            )

            await self.call.play(
                chat_id,
                stream
            )

            old = self.current.get(
                chat_id
            )

            if old:
                self.history.setdefault(
                    chat_id,
                    []
                ).append(old)

            self.current[chat_id] = prepared

            self.started_at[chat_id] = (
                time.monotonic()
            )

            self.offset[chat_id] = 0

            self.paused.discard(
                chat_id
            )

            logger.info(
                "NOW PLAYING: %s",
                prepared.title
            )

            return True

        except Exception as e:

            logger.exception(
                "REAL PLAY ERROR: %s",
                e
            )

            return False

    async def play(
        self,
        chat_id,
        track
    ):

        if chat_id in self.current:

            self._queue(chat_id).append(
                track
            )

            return True

        return await self.play_track(
            chat_id,
            track
        )

    async def add_to_queue(
        self,
        chat_id,
        track
    ):

        queue = self._queue(chat_id)

        queue.append(track)

        return len(queue)

    async def pause(self, chat_id):

        if (
            self.call is None
            or chat_id not in self.current
        ):
            return False

        try:

            self.offset[chat_id] = (
                await self.get_position(
                    chat_id
                )
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
                "Pause failed"
            )
            return False

    async def resume(self, chat_id):

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

            self.started_at[chat_id] = (
                time.monotonic()
            )

            return True

        except Exception:
            logger.exception(
                "Resume failed"
            )
            return False

    async def stop(self, chat_id):

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
                pass

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

    async def next(self, chat_id):

        queue = self._queue(
            chat_id
        )

        if not queue:

            await self.stop(
                chat_id
            )

            return None

        track = queue.pop(0)

        if await self.play_track(
            chat_id,
            track
        ):
            return self.current.get(
                chat_id
            )

        return None

    async def previous(self, chat_id):

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

    async def get_position(self, chat_id):

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

            self.volume[chat_id] = volume

            return True

        except Exception:
            logger.exception(
                "Volume failed"
            )
            return False

    def get_current(self, chat_id):
        return self.current.get(
            chat_id
        )

    def get_queue(self, chat_id):
        return list(
            self._queue(chat_id)
        )
