import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

import yt_dlp

from config import config
from optional_deps import VOICE_CHAT_AVAILABLE

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    title: str
    duration: int = 0
    url: str = ""
    webpage_url: str = ""
    thumbnail: str = ""
    uploader: str = "Unknown"
    filepath: Optional[str] = None
    performer: str = ""

    @property
    def artist(self) -> str:
        return self.performer or self.uploader or "Unknown"


class MusicDownloader:

    def __init__(self):
        self.downloads_dir = Path(
            getattr(config, "downloads_dir", "downloads")
        )

        self.downloads_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def _base_opts(self):
        return {
            "quiet": False,
            "no_warnings": False,
            "noplaylist": True,
            "nocheckcertificate": True,
            "ignoreerrors": False,

            "retries": 10,
            "fragment_retries": 10,

            "socket_timeout": 60,

            "geo_bypass": True,
            "geo_bypass_country": "US",

            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0.0.0 "
                    "Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        }

    async def search(
        self,
        query: str,
        limit: int = 1
    ) -> List[TrackInfo]:

        loop = asyncio.get_running_loop()

        def _search():

            logger.info(
                "MUSIC SEARCH START | query=%s",
                query
            )

            opts = {
                **self._base_opts(),
                "extract_flat": True,
            }

            try:

                with yt_dlp.YoutubeDL(opts) as ydl:

                    info = ydl.extract_info(
                        f"ytsearch{limit}:{query}",
                        download=False
                    )

                if not info:

                    logger.error(
                        "SEARCH RETURNED NOTHING | query=%s",
                        query
                    )

                    return []

                results = []

                for entry in info.get("entries") or []:

                    if not entry:
                        continue

                    webpage_url = (
                        entry.get("webpage_url")
                        or entry.get("original_url")
                        or ""
                    )

                    video_id = (
                        entry.get("id")
                        or ""
                    )

                    if not webpage_url and video_id:

                        webpage_url = (
                            "https://www.youtube.com/watch?v="
                            + video_id
                        )

                    uploader = (
                        entry.get("uploader")
                        or entry.get("channel")
                        or "Unknown"
                    )

                    performer = (
                        entry.get("artist")
                        or entry.get("creator")
                        or uploader
                        or "Unknown"
                    )

                    track = TrackInfo(
                        title=entry.get(
                            "title",
                            "Unknown"
                        ),
                        duration=int(
                            entry.get(
                                "duration",
                                0
                            ) or 0
                        ),
                        url=entry.get(
                            "url",
                            ""
                        ) or "",
                        webpage_url=webpage_url,
                        thumbnail=entry.get(
                            "thumbnail",
                            ""
                        ) or "",
                        uploader=uploader,
                        performer=performer
                    )

                    results.append(track)

                    logger.info(
                        "SEARCH RESULT | title=%s | url=%s",
                        track.title,
                        track.webpage_url
                    )

                logger.info(
                    "MUSIC SEARCH SUCCESS | results=%s",
                    len(results)
                )

                return results

            except Exception as e:

                logger.exception(
                    "MUSIC SEARCH ERROR | %s: %s",
                    type(e).__name__,
                    str(e)
                )

                return []

        return await loop.run_in_executor(
            None,
            _search
        )

    async def download(
        self,
        track: TrackInfo
    ) -> Optional[str]:

        loop = asyncio.get_running_loop()

        source = (
            track.webpage_url
            or track.url
        )

        logger.info(
            "========== YOUTUBE DOWNLOAD START =========="
        )

        logger.info(
            "DOWNLOAD TITLE | %s",
            track.title
        )

        logger.info(
            "DOWNLOAD SOURCE | %s",
            source
        )

        if not source:

            logger.error(
                "DOWNLOAD ABORTED | NO SOURCE"
            )

            return None

        file_id = uuid.uuid4().hex

        output = (
            self.downloads_dir
            / f"{file_id}.%(ext)s"
        )

        def _download():

            logger.info(
                "YTDLP EXTRACT START | %s",
                source
            )

            opts = {
                **self._base_opts(),

                # Download the best available audio.
                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best"
                ),

                "outtmpl": str(output),

                "noplaylist": True,

                "concurrent_fragment_downloads": 1,

                # Do not require FFmpeg for the download itself.
                "postprocessors": [],

                # Try multiple clients/formats when YouTube changes.
                "extractor_args": {
                    "youtube": {
                        "player_client": [
                            "android",
                            "web"
                        ]
                    }
                },
            }

            try:

                with yt_dlp.YoutubeDL(opts) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=True
                    )

                if not info:

                    logger.error(
                        "YTDLP RETURNED NO INFO"
                    )

                    return None

                logger.info(
                    "YTDLP DOWNLOAD FINISHED | id=%s",
                    info.get("id")
                )

            except Exception as e:

                logger.exception(
                    "YTDLP DOWNLOAD ERROR | %s: %s",
                    type(e).__name__,
                    str(e)
                )

                return None

            logger.info(
                "SEARCHING DOWNLOADED FILE | pattern=%s.*",
                file_id
            )

            files = list(
                self.downloads_dir.glob(
                    f"{file_id}.*"
                )
            )

            logger.info(
                "DOWNLOADED FILE COUNT | %s",
                len(files)
            )

            supported = {
                ".m4a",
                ".webm",
                ".opus",
                ".ogg",
                ".mp3",
                ".aac",
                ".wav",
                ".mp4",
                ".flac"
            }

            for file in files:

                if not file.is_file():
                    continue

                logger.info(
                    "DOWNLOADED FILE FOUND | %s",
                    file
                )

                if file.suffix.lower() not in supported:

                    logger.warning(
                        "UNSUPPORTED FILE TYPE | %s",
                        file
                    )

                    continue

                try:
                    size = file.stat().st_size
                except Exception as e:

                    logger.error(
                        "FILE STAT ERROR | %s",
                        e
                    )

                    continue

                logger.info(
                    "FILE SIZE | %s bytes",
                    size
                )

                if size <= 1024:

                    logger.error(
                        "FILE TOO SMALL | %s",
                        file
                    )

                    continue

                logger.info(
                    "DOWNLOAD SUCCESS | file=%s | size=%s",
                    file,
                    size
                )

                return str(file)

            logger.error(
                "DOWNLOAD FILE NOT FOUND | id=%s",
                file_id
            )

            return None

        filepath = await loop.run_in_executor(
            None,
            _download
        )

        if filepath:

            track.filepath = filepath

            logger.info(
                "TRACK FILEPATH SET | %s",
                filepath
            )

        logger.info(
            "========== YOUTUBE DOWNLOAD END =========="
        )

        return filepath


# Global downloader
downloader = MusicDownloader()


class MusicPlayer:

    def __init__(
        self,
        pytgcalls_client=None
    ):

        self.client = pytgcalls_client

        self.downloader = downloader

        self.current_track = None
        self.current_chat_id = None

        self.volume = getattr(
            config,
            "default_volume",
            100
        )

        self.is_playing = False
        self.is_paused = False

        self._available = (
            VOICE_CHAT_AVAILABLE
            and self.client is not None
        )

        logger.info(
            "MusicPlayer initialized | "
            "voice_available=%s | "
            "client=%s | "
            "downloader=%s",
            VOICE_CHAT_AVAILABLE,
            self.client is not None,
            self.downloader is not None
        )

    async def play(
        self,
        chat_id: int,
        track: TrackInfo
    ) -> bool:

        if not self._available:

            logger.error(
                "VOICE PLAYER UNAVAILABLE"
            )

            return False

        if not track.filepath:

            logger.error(
                "TRACK HAS NO FILEPATH | %s",
                track.title
            )

            return False

        path = Path(track.filepath)

        if not path.exists():

            logger.error(
                "FILE DOES NOT EXIST | %s",
                path
            )

            return False

        if path.stat().st_size < 1024:

            logger.error(
                "FILE TOO SMALL | %s",
                path
            )

            return False

        logger.info(
            "VOICE PLAY START | chat=%s | file=%s",
            chat_id,
            path
        )

        try:

            from pytgcalls.types import GroupCallConfig

            config_obj = GroupCallConfig(
                auto_start=True
            )

            result = await asyncio.wait_for(
                self.client.play(
                    chat_id,
                    str(path),
                    config=config_obj
                ),
                timeout=45
            )

            logger.info(
                "PyTgCalls.play returned | %r",
                result
            )

            self.current_track = track
            self.current_chat_id = chat_id

            self.is_playing = True
            self.is_paused = False

            logger.info(
                "VOICE PLAY SUCCESS | chat=%s | title=%s",
                chat_id,
                track.title
            )

            return True

        except asyncio.TimeoutError:

            logger.error(
                "VOICE PLAY TIMEOUT | chat=%s",
                chat_id
            )

            return False

        except Exception as e:

            logger.exception(
                "VOICE PLAY ERROR | %s: %s",
                type(e).__name__,
                str(e)
            )

            return False

    async def stop(
        self,
        chat_id: int
    ) -> bool:

        if not self._available:
            return False

        try:

            await asyncio.wait_for(
                self.client.leave_call(
                    chat_id
                ),
                timeout=15
            )

            self.current_track = None
            self.current_chat_id = None

            self.is_playing = False
            self.is_paused = False

            logger.info(
                "VOICE STOP SUCCESS | %s",
                chat_id
            )

            return True

        except Exception as e:

            logger.exception(
                "STOP ERROR | %s: %s",
                type(e).__name__,
                str(e)
            )

            return False

    async def pause(
        self,
        chat_id: int
    ) -> bool:

        if not self._available:
            return False

        try:

            method = getattr(
                self.client,
                "pause",
                None
            )

            if method is None:

                logger.error(
                    "PAUSE METHOD NOT AVAILABLE"
                )

                return False

            await method(chat_id)

            self.is_paused = True
            self.is_playing = False

            logger.info(
                "PAUSE SUCCESS | chat=%s",
                chat_id
            )

            return True

        except Exception as e:

            logger.exception(
                "PAUSE ERROR | %s: %s",
                type(e).__name__,
                str(e)
            )

            return False

    async def resume(
        self,
        chat_id: int
    ) -> bool:

        if not self._available:
            return False

        try:

            method = getattr(
                self.client,
                "resume",
                None
            )

            if method is None:

                logger.error(
                    "RESUME METHOD NOT AVAILABLE"
                )

                return False

            await method(chat_id)

            self.is_paused = False
            self.is_playing = True

            logger.info(
                "RESUME SUCCESS | chat=%s",
                chat_id
            )

            return True

        except Exception as e:

            logger.exception(
                "RESUME ERROR | %s: %s",
                type(e).__name__,
                str(e)
            )

            return False

    async def set_volume(
        self,
        chat_id: int,
        volume: int
    ) -> bool:

        if not self._available:
            return False

        try:

            volume = max(
                0,
                min(200, volume)
            )

            method = getattr(
                self.client,
                "change_volume_call",
                None
            )

            if method is None:

                method = getattr(
                    self.client,
                    "change_volume",
                    None
                )

            if method is None:

                logger.error(
                    "VOLUME METHOD NOT AVAILABLE"
                )

                return False

            await method(
                chat_id,
                volume
            )

            self.volume = volume

            logger.info(
                "VOLUME CHANGED | chat=%s | volume=%s",
                chat_id,
                volume
            )

            return True

        except Exception as e:

            logger.exception(
                "VOLUME ERROR | %s: %s",
                type(e).__name__,
                str(e)
            )

            return False

    def get_status(self) -> Dict[str, Any]:

        return {
            "available": self._available,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "current_track": (
                self.current_track.title
                if self.current_track
                else None
            ),
            "current_chat_id": self.current_chat_id,
            "volume": self.volume
        }

    def is_voice_chat_available(self) -> bool:
        return self._available
