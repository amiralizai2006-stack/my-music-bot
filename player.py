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

            logger.info(
                "MUSIC SEARCH START: %s",
                query,
            )

            with yt_dlp.YoutubeDL(opts) as ydl:

                info = ydl.extract_info(
                    f"ytsearch{limit}:{query}",
                    download=False,
                )

                if not info:
                    logger.error(
                        "SEARCH RETURNED NOTHING: %s",
                        query,
                    )
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
                            uploader=uploader,
                            performer=performer,
                        )
                    )

                logger.info(
                    "MUSIC SEARCH SUCCESS: %s result(s)",
                    len(result),
                )

                return result

        try:

            return await loop.run_in_executor(
                None,
                _search,
            )

        except Exception as e:

            logger.exception(
                "MUSIC SEARCH ERROR: %s: %s",
                type(e).__name__,
                str(e),
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
                "NO SOURCE URL: %s",
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

                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio[ext=opus]/"
                    "bestaudio/best"
                ),

                "outtmpl": str(output),

                "postprocessors": [],
            }

            try:

                with yt_dlp.YoutubeDL(opts) as ydl:

                    ydl.download(
                        [source]
                    )

            except Exception as e:

                logger.exception(
                    "YTDLP DOWNLOAD ERROR: %s: %s",
                    type(e).__name__,
                    str(e),
                )

                return None

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
                ".mp4",
            }

            for file in files:

                if (
                    file.is_file()
                    and file.suffix.lower()
                    in supported
                    and file.stat().st_size > 1024
                ):

                    logger.info(
                        "DOWNLOAD SUCCESS: %s",
                        file,
                    )

                    return str(file)

            logger.error(
                "DOWNLOAD FILE NOT FOUND: %s",
                track.title,
            )

            return None

        try:

            filepath = await loop.run_in_executor(
                None,
                _download,
            )

            if not filepath:
                return None

            track.filepath = filepath

            return filepath

        except Exception as e:

            logger.exception(
                "DOWNLOAD ERROR: %s: %s",
                type(e).__name__,
                str(e),
            )

            return None


# Downloader مشترک
downloader = MusicDownloader()


class MusicPlayer:

    def __init__(
        self,
        pytgcalls_client=None,
    ):

        self.client = pytgcalls_client

        # مهم: handlers.py از این استفاده می‌کند
        self.downloader = downloader

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

        logger.info(
            "MusicPlayer initialized | voice_available=%s | client=%s | downloader=%s",
            VOICE_CHAT_AVAILABLE,
            self.client is not None,
            self.downloader is not None,
        )


    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if not self._available:

            logger.error(
                "VOICE PLAYER UNAVAILABLE | VOICE_CHAT_AVAILABLE=%s | CLIENT=%s",
                VOICE_CHAT_AVAILABLE,
                self.client is not None,
            )

            return False

        if not track.filepath:

            logger.error(
                "TRACK HAS NO FILEPATH: %s",
                track.title,
            )

            return False

        path = Path(
            track.filepath
        )

        if not path.exists():

            logger.error(
                "FILE DOES NOT EXIST: %s",
                path,
            )

            return False

        if path.stat().st_size < 1024:

            logger.error(
                "FILE TOO SMALL: %s",
                path,
            )

            return False

        logger.info(
            "VOICE PLAY START | chat=%s | file=%s | size=%s",
            chat_id,
            path,
            path.stat().st_size,
        )

        try:

            from pytgcalls.types import GroupCallConfig

            logger.info(
                "GroupCallConfig imported successfully"
            )

            config_obj = GroupCallConfig(
                auto_start=True
            )

            logger.info(
                "Calling PyTgCalls.play..."
            )

            result = await asyncio.wait_for(
                self.client.play(
                    chat_id,
                    str(path),
                    config=config_obj,
                ),
                timeout=45,
            )

            logger.info(
                "PyTgCalls.play returned: %r",
                result,
            )

            self.current_track = track
            self.current_chat_id = chat_id
            self.is_playing = True
            self.is_paused = False

            logger.info(
                "VOICE PLAY SUCCESS | chat=%s | title=%s",
                chat_id,
                track.title,
            )

            return True

        except asyncio.TimeoutError as e:

            logger.error(
                "VOICE PLAY TIMEOUT | chat=%s | %s: %s",
                chat_id,
                type(e).__name__,
                str(e),
            )

            return False

        except Exception as e:

            logger.exception(
                "VOICE PLAY ERROR | chat=%s | %s: %s",
                chat_id,
                type(e).__name__,
                str(e),
            )

            raise


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

            logger.info(
                "VOICE STOP SUCCESS: %s",
                chat_id,
            )

            return True

        except Exception as e:

            logger.exception(
                "STOP ERROR: %s: %s",
                type(e).__name__,
                str(e),
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

                logger.error(
                    "PyTgCalls pause method not available"
                )

                return False

            await method(chat_id)

            self.is_paused = True
            self.is_playing = False

            return True

        except Exception as e:

            logger.exception(
                "PAUSE ERROR: %s: %s",
                type(e).__name__,
                str(e),
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

                logger.error(
                    "PyTgCalls resume method not available"
                )

                return False

            await method(chat_id)

            self.is_paused = False
            self.is_playing = True

            return True

        except Exception as e:

            logger.exception(
                "RESUME ERROR: %s: %s",
                type(e).__name__,
                str(e),
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

                logger.error(
                    "PyTgCalls volume method not available"
                )

                return False

            await method(
                chat_id,
                volume,
            )

            self.volume = volume

            return True

        except Exception as e:

            logger.exception(
                "VOLUME ERROR: %s: %s",
                type(e).__name__,
                str(e),
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
