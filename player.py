"""
Persian Telegram Music Downloader / Player
- Search by song name
- Download audio with yt-dlp
- Play through PyTgCalls
- Supports direct URLs
"""

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import yt_dlp

from config import config

from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    MediaStream,
)

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

    def _clean_filename(self, name: str) -> str:
        name = re.sub(r'[\\/*?:"<>|]', "_", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name[:150] or "music"

    def _base_opts(self):
        return {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 1,
            "socket_timeout": 30,
        }

    async def extract_info(
        self,
        query: str,
    ) -> Optional[TrackInfo]:

        loop = asyncio.get_running_loop()
        query = query.strip()

        if not query:
            return None

        try:

            def _extract():

                opts = {
                    **self._base_opts(),
                    "extract_flat": False,
                }

                with yt_dlp.YoutubeDL(opts) as ydl:

                    if query.startswith(
                        ("http://", "https://")
                    ):
                        info = ydl.extract_info(
                            query,
                            download=False,
                        )
                    else:
                        info = ydl.extract_info(
                            f"ytsearch1:{query}",
                            download=False,
                        )

                    if not info:
                        return None

                    if "entries" in info:
                        entries = info.get("entries") or []

                        if not entries:
                            return None

                        info = entries[0]

                    if not info:
                        return None

                    return {
                        "title": info.get(
                            "title",
                            "Unknown",
                        ),
                        "duration": int(
                            info.get(
                                "duration",
                                0,
                            ) or 0
                        ),
                        "url": info.get(
                            "url",
                            "",
                        ) or "",
                        "webpage_url": (
                            info.get(
                                "webpage_url",
                                "",
                            )
                            or info.get(
                                "original_url",
                                "",
                            )
                            or ""
                        ),
                        "thumbnail": info.get(
                            "thumbnail",
                            "",
                        ) or "",
                        "uploader": info.get(
                            "uploader",
                            "Unknown",
                        ) or "Unknown",
                    }

            info = await loop.run_in_executor(
                None,
                _extract,
            )

            if not info:
                logger.error(
                    "No music information found for: %s",
                    query,
                )
                return None

            return TrackInfo(**info)

        except Exception:
            logger.exception(
                "Extract info failed for: %s",
                query,
            )
            return None

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> List[TrackInfo]:

        loop = asyncio.get_running_loop()

        try:

            def _search():

                opts = {
                    **self._base_opts(),
                    "extract_flat": True,
                }

                with yt_dlp.YoutubeDL(opts) as ydl:

                    return ydl.extract_info(
                        f"ytsearch{limit}:{query}",
                        download=False,
                    )

            info = await loop.run_in_executor(
                None,
                _search,
            )

            tracks = []

            if not info:
                return tracks

            for entry in info.get("entries") or []:

                if not entry:
                    continue

                webpage_url = (
                    entry.get("webpage_url")
                    or entry.get("original_url")
                    or entry.get("url")
                    or ""
                )

                tracks.append(
                    TrackInfo(
                        title=entry.get(
                            "title",
                            "Unknown",
                        ),
                        duration=int(
                            entry.get(
                                "duration",
                                0,
                            ) or 0
                        ),
                        url=entry.get(
                            "url",
                            "",
                        ) or "",
                        webpage_url=webpage_url,
                        thumbnail=entry.get(
                            "thumbnail",
                            "",
                        ) or "",
                        uploader=entry.get(
                            "uploader",
                            "Unknown",
                        ) or "Unknown",
                    )
                )

            return tracks

        except Exception:
            logger.exception(
                "Music search failed: %s",
                query,
            )
            return []

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[str]:

        loop = asyncio.get_running_loop()

        try:

            source = (
                track.webpage_url
                or track.url
            )

            if not source:
                logger.error(
                    "No valid source URL for: %s",
                    track.title,
                )
                return None

            file_id = uuid.uuid4().hex

            output_template = str(
                self.downloads_dir
                / f"{file_id}.%(ext)s"
            )

            ydl_opts = {
                **self._base_opts(),

                # Prefer audio formats that do not require
                # unnecessary video processing.
                "format": (
                    "bestaudio[ext=m4a]/"
                    "bestaudio[ext=webm]/"
                    "bestaudio/best"
                ),

                "outtmpl": output_template,

                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            def _download():

                logger.info(
                    "Downloading music: %s",
                    track.title,
                )

                with yt_dlp.YoutubeDL(
                    ydl_opts
                ) as ydl:

                    result = ydl.download([source])

                    logger.info(
                        "yt-dlp result: %s",
                        result,
                    )

                # Find the file created for this request.
                candidates = list(
                    self.downloads_dir.glob(
                        f"{file_id}.*"
                    )
                )

                # FFmpeg normally produces .mp3.
                preferred = [
                    p for p in candidates
                    if p.suffix.lower() == ".mp3"
                ]

                if preferred:
                    return str(preferred[0])

                # Fallback if post-processing produced
                # another supported audio format.
                supported = {
                    ".m4a",
                    ".webm",
                    ".opus",
                    ".wav",
                    ".ogg",
                    ".mp3",
                }

                for file in candidates:
                    if file.suffix.lower() in supported:
                        return str(file)

                return None

            filepath = await loop.run_in_executor(
                None,
                _download,
            )

            if not filepath:
                logger.error(
                    "yt-dlp downloaded nothing for: %s",
                    track.title,
                )
                return None

            path = Path(filepath)

            if not path.exists():
                logger.error(
                    "Downloaded file does not exist: %s",
                    filepath,
                )
                return None

            if path.stat().st_size < 1024:
                logger.error(
                    "Downloaded file is too small: %s",
                    filepath,
                )
                try:
                    path.unlink()
                except Exception:
                    pass
                return None

            track.filepath = filepath

            logger.info(
                "Music downloaded successfully: %s",
                filepath,
            )

            return filepath

        except Exception:
            logger.exception(
                "DOWNLOAD ERROR - %s",
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
                "Voice chat is not available."
            )
            return False

        if not track.filepath:
            logger.error(
                "Track has no downloaded file."
            )
            return False

        path = Path(track.filepath)

        if not path.exists():
            logger.error(
                "Audio file does not exist: %s",
                track.filepath,
            )
            return False

        try:

            stream = MediaStream(
                str(path),
                video_flags=MediaStream.Flags.IGNORE,
            )

            await self.client.play(
                chat_id,
                stream,
            )

            self.current_track = track
            self.current_chat_id = chat_id
            self.is_playing = True
            self.is_paused = False

            logger.info(
                "Playing '%s' in chat %s",
                track.title,
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "PyTgCalls play failed"
            )
            return False

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            await self.client.leave_call(
                chat_id
            )

            self.current_track = None
            self.current_chat_id = None
            self.is_playing = False
            self.is_paused = False

            return True

        except Exception:
            logger.exception(
                "Stop failed"
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
                "Pause failed"
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
                "Resume failed"
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
                "Volume change failed"
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
