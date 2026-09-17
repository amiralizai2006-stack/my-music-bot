"""
Telegram Music Downloader / Player
Compatible with modern PyTgCalls API.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import yt_dlp

from config import config

from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    MediaStream,
    AudioQuality,
    VideoQuality,
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
            config.downloads_dir
        )

        self.downloads_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._ydl_opts = {
            "format": config.ytdl_format,
            "outtmpl": str(
                self.downloads_dir / "%(title)s.%(ext)s"
            ),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

    async def extract_info(
        self,
        query: str,
    ) -> Optional[TrackInfo]:

        loop = asyncio.get_running_loop()

        try:
            def _extract():
                with yt_dlp.YoutubeDL({
                    **self._ydl_opts,
                    "extract_flat": True,
                }) as ydl:

                    if query.startswith(
                        ("http://", "https://")
                    ):
                        return ydl.extract_info(
                            query,
                            download=False,
                        )

                    return ydl.extract_info(
                        f"ytsearch1:{query}",
                        download=False,
                    )

            info = await loop.run_in_executor(
                None,
                _extract,
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

            return TrackInfo(
                title=info.get(
                    "title",
                    "Unknown",
                ),
                duration=info.get(
                    "duration",
                    0,
                ) or 0,
                url=info.get(
                    "url",
                    "",
                ),
                webpage_url=info.get(
                    "webpage_url",
                    "",
                ),
                thumbnail=info.get(
                    "thumbnail",
                    "",
                ),
                uploader=info.get(
                    "uploader",
                    "Unknown",
                ),
            )

        except Exception:
            logger.exception(
                "Error extracting track information"
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
                with yt_dlp.YoutubeDL({
                    **self._ydl_opts,
                    "extract_flat": True,
                }) as ydl:

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

            for entry in info.get(
                "entries",
                [],
            ):

                if not entry:
                    continue

                tracks.append(
                    TrackInfo(
                        title=entry.get(
                            "title",
                            "Unknown",
                        ),
                        duration=entry.get(
                            "duration",
                            0,
                        ) or 0,
                        url=entry.get(
                            "url",
                            "",
                        ),
                        webpage_url=entry.get(
                            "webpage_url",
                            "",
                        ),
                        thumbnail=entry.get(
                            "thumbnail",
                            "",
                        ),
                        uploader=entry.get(
                            "uploader",
                            "Unknown",
                        ),
                    )
                )

            return tracks

        except Exception:
            logger.exception(
                "Music search failed"
            )
            return []

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[str]:

        loop = asyncio.get_running_loop()

        try:

            output_template = str(
                self.downloads_dir
                / "%(id)s.%(ext)s"
            )

            ydl_opts = {
                **self._ydl_opts,
                "format": "bestaudio/best",
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

                with yt_dlp.YoutubeDL(
                    ydl_opts
                ) as ydl:

                    ydl.download([
                        track.webpage_url
                    ])

                    candidates = sorted(
                        self.downloads_dir.glob("*"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )

                    for file in candidates:

                        if file.suffix.lower() in (
                            ".mp3",
                            ".m4a",
                            ".webm",
                            ".opus",
                            ".wav",
                        ):
                            return str(file)

                    return None

            filepath = await loop.run_in_executor(
                None,
                _download,
            )

            if filepath and Path(filepath).exists():

                track.filepath = filepath

                logger.info(
                    "Downloaded: %s",
                    filepath,
                )

                return filepath

            return None

        except Exception:
            logger.exception(
                "Download failed: %s",
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

        if not Path(
            track.filepath
        ).exists():

            logger.error(
                "Audio file does not exist: %s",
                track.filepath,
            )
            return False

        try:

            stream = MediaStream(
                track.filepath,
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
                "🎵 Playing %s in %s",
                track.title,
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "❌ PyTgCalls play failed"
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
