import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import yt_dlp

from config import config
from optional_deps import VOICE_CHAT_AVAILABLE

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    title: str
    duration: int
    url: str
    webpage_url: str
    thumbnail: str
    uploader: str
    filepath: Optional[str] = None


class MusicDownloader:

    def __init__(self):
        self.downloads_dir = Path(
            getattr(config, "downloads_dir", "downloads")
        )
        self.downloads_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _base_opts(self):
        return {
            "quiet": False,
            "no_warnings": False,
            "noplaylist": True,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
        }

    async def search(
        self,
        query: str,
        limit: int = 1,
    ) -> List[TrackInfo]:

        loop = asyncio.get_running_loop()

        def _search():

            opts = {
                **self._base_opts(),
                "extract_flat": True,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:

                info = ydl.extract_info(
                    f"ytsearch{limit}:{query}",
                    download=False,
                )

                if not info:
                    return []

                result = []

                for entry in info.get("entries") or []:

                    if not entry:
                        continue

                    webpage_url = (
                        entry.get("webpage_url")
                        or entry.get("original_url")
                        or entry.get("url")
                        or ""
                    )

                    result.append(
                        TrackInfo(
                            title=entry.get(
                                "title",
                                "Unknown",
                            ),
                            duration=int(
                                entry.get(
                                    "duration",
                                    0,
                                )
                                or 0
                            ),
                            url=entry.get(
                                "url",
                                "",
                            )
                            or "",
                            webpage_url=webpage_url,
                            thumbnail=entry.get(
                                "thumbnail",
                                "",
                            )
                            or "",
                            uploader=entry.get(
                                "uploader",
                                "Unknown",
                            )
                            or "Unknown",
                        )
                    )

                return result

        try:
            return await loop.run_in_executor(
                None,
                _search,
            )

        except Exception:
            logger.exception(
                "MUSIC SEARCH ERROR: %s",
                query,
            )
            return []

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[str]:

        loop = asyncio.get_running_loop()

        source = (
            track.webpage_url
            or track.url
        )

        if not source:
            logger.error(
                "No source URL for %s",
                track.title,
            )
            return None

        file_id = uuid.uuid4().hex

        output = (
            self.downloads_dir
            / f"{file_id}.%(ext)s"
        )

        def _download():

            logger.info(
                "DOWNLOAD START: %s | %s",
                track.title,
                source,
            )

            opts = {
                **self._base_opts(),

                # Download audio only.
                # No FFmpegExtractAudio postprocessor here.
                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best"
                ),

                "outtmpl": str(output),
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([source])

            files = list(
                self.downloads_dir.glob(
                    f"{file_id}.*"
                )
            )

            supported = {
                ".m4a",
                ".webm",
                ".opus",
                ".ogg",
                ".mp3",
                ".aac",
                ".wav",
            }

            for file in files:

                if (
                    file.is_file()
                    and file.suffix.lower()
                    in supported
                    and file.stat().st_size > 1024
                ):
                    return str(file)

            return None

        try:

            filepath = await loop.run_in_executor(
                None,
                _download,
            )

            if not filepath:

                logger.error(
                    "DOWNLOAD FINISHED BUT FILE NOT FOUND: %s",
                    track.title,
                )

                return None

            track.filepath = filepath

            logger.info(
                "DOWNLOAD SUCCESS: %s",
                filepath,
            )

            return filepath

        except Exception:

            logger.exception(
                "DOWNLOAD ERROR: %s",
                track.title,
            )

            return None


class MusicPlayer:

    def __init__(
        self,
        pytgcalls_client=None,
    ):

        self.client = pytgcalls_client

        self.current_track = None
        self.current_chat_id = None

        self.volume = getattr(
            config,
            "default_volume",
            100,
        )

        self.is_playing = False
        self.is_paused = False

        self._available = (
            VOICE_CHAT_AVAILABLE
            and self.client is not None
        )

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if not self._available:
            logger.error(
                "PyTgCalls is not available"
            )
            return False

        if not track.filepath:
            logger.error(
                "Track has no filepath"
            )
            return False

        path = Path(track.filepath)

        if not path.exists():
            logger.error(
                "File does not exist: %s",
                path,
            )
            return False

        if path.stat().st_size < 1024:
            logger.error(
                "File is too small: %s",
                path,
            )
            return False

        try:

            from pytgcalls.types import GroupCallConfig

            logger.info(
                "VOICE PLAY START: chat=%s file=%s",
                chat_id,
                path,
            )

            await asyncio.wait_for(
                self.client.play(
                    chat_id,
                    str(path),
                    config=GroupCallConfig(
                        auto_start=True
                    ),
                ),
                timeout=45,
            )

            self.current_track = track
            self.current_chat_id = chat_id
            self.is_playing = True
            self.is_paused = False

            logger.info(
                "VOICE PLAY SUCCESS: chat=%s title=%s",
                chat_id,
                track.title,
            )

            return True

        except asyncio.TimeoutError:

            logger.error(
                "VOICE PLAY TIMEOUT: chat=%s",
                chat_id,
            )
            return False

        except Exception:

            logger.exception(
                "VOICE PLAY ERROR: chat=%s",
                chat_id,
            )
            return False

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            await asyncio.wait_for(
                self.client.leave_call(
                    chat_id
                ),
                timeout=15,
            )

            self.current_track = None
            self.current_chat_id = None
            self.is_playing = False
            self.is_paused = False

            return True

        except Exception:

            logger.exception(
                "STOP ERROR: %s",
                chat_id,
            )
            return False

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            method = getattr(
                self.client,
                "pause",
                None,
            )

            if method is None:
                return False

            await method(chat_id)

            self.is_paused = True
            self.is_playing = False

            return True

        except Exception:

            logger.exception(
                "PAUSE ERROR"
            )
            return False

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            method = getattr(
                self.client,
                "resume",
                None,
            )

            if method is None:
                return False

            await method(chat_id)

            self.is_paused = False
            self.is_playing = True

            return True

        except Exception:

            logger.exception(
                "RESUME ERROR"
            )
            return False

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            volume = max(
                0,
                min(200, volume),
            )

            method = getattr(
                self.client,
                "change_volume_call",
                None,
            )

            if method is None:
                method = getattr(
                    self.client,
                    "change_volume",
                    None,
                )

            if method is None:
                return False

            await method(
                chat_id,
                volume,
            )

            self.volume = volume

            return True

        except Exception:

            logger.exception(
                "VOLUME ERROR"
            )
            return False

    def get_status(
        self,
    ) -> Dict[str, Any]:

        return {
            "available": self._available,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "current_track": (
                self.current_track.title
                if self.current_track
                else None
            ),
            "current_chat_id": (
                self.current_chat_id
            ),
            "volume": self.volume,
        }

    def is_voice_chat_available(
        self,
    ) -> bool:

        return self._available


downloader = MusicDownloader()
