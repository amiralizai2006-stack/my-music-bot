"""
SILENT Telegram Music Player
Downloader + Voice Chat Player

این فایل با main.py فعلی پروژه سازگار است.
هیچ Secret یا API credential داخل این فایل قرار نده.
"""

import asyncio
import inspect
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

import yt_dlp

from config import config

try:
    from optional_deps import (
        VOICE_CHAT_AVAILABLE,
        MediaStream,
    )
except Exception:
    VOICE_CHAT_AVAILABLE = False
    MediaStream = None


logger = logging.getLogger(__name__)


# =========================================================
# Track
# =========================================================

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


# =========================================================
# Helpers
# =========================================================

async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _clean_filename(name: str) -> str:
    name = name or "audio"
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:150] or "audio"


def _duration(value) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


# =========================================================
# Downloader
# =========================================================

class MusicDownloader:
    def __init__(self):
        downloads_dir = getattr(
            config,
            "downloads_dir",
            "./downloads",
        )

        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.base_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 30,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Linux; Android 12) "
                    "AppleWebKit/537.36 "
                    "Chrome/131.0 Mobile Safari/537.36"
                )
            },
        }

    # -----------------------------------------------------
    # Extract information
    # -----------------------------------------------------

    async def extract_info(
        self,
        query: str,
    ) -> Optional[TrackInfo]:

        if not query:
            return None

        query = query.strip()

        loop = asyncio.get_running_loop()

        def _extract():
            opts = {
                **self.base_opts,
                "extract_flat": False,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:

                if query.startswith(
                    (
                        "http://",
                        "https://",
                    )
                ):
                    return ydl.extract_info(
                        query,
                        download=False,
                    )

                return ydl.extract_info(
                    f"ytsearch1:{query}",
                    download=False,
                )

        try:
            info = await loop.run_in_executor(
                None,
                _extract,
            )

            if not info:
                return None

            if info.get("entries"):
                entries = [
                    x
                    for x in info.get("entries", [])
                    if x
                ]

                if not entries:
                    return None

                info = entries[0]

            if not info:
                return None

            webpage_url = (
                info.get("webpage_url")
                or info.get("original_url")
                or ""
            )

            return TrackInfo(
                title=(
                    info.get("title")
                    or "Unknown"
                ),
                duration=_duration(
                    info.get("duration")
                ),
                url=(
                    info.get("url")
                    or ""
                ),
                webpage_url=webpage_url,
                thumbnail=(
                    info.get("thumbnail")
                    or ""
                ),
                uploader=(
                    info.get("uploader")
                    or info.get("channel")
                    or "Unknown"
                ),
                performer=(
                    info.get("artist")
                    or info.get("creator")
                    or ""
                ),
            )

        except Exception:
            logger.exception(
                "❌ Extract information failed: %s",
                query,
            )
            return None

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> List[TrackInfo]:

        if not query:
            return []

        limit = max(
            1,
            min(10, int(limit)),
        )

        loop = asyncio.get_running_loop()

        def _search():
            opts = {
                **self.base_opts,
                "extract_flat": True,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(
                    f"ytsearch{limit}:{query}",
                    download=False,
                )

        try:
            info = await loop.run_in_executor(
                None,
                _search,
            )

            if not info:
                return []

            results = []

            for entry in info.get(
                "entries",
                [],
            ):

                if not entry:
                    continue

                results.append(
                    TrackInfo(
                        title=(
                            entry.get("title")
                            or "Unknown"
                        ),
                        duration=_duration(
                            entry.get("duration")
                        ),
                        url=(
                            entry.get("url")
                            or ""
                        ),
                        webpage_url=(
                            entry.get("webpage_url")
                            or entry.get("url")
                            or ""
                        ),
                        thumbnail=(
                            entry.get("thumbnail")
                            or ""
                        ),
                        uploader=(
                            entry.get("uploader")
                            or entry.get("channel")
                            or "Unknown"
                        ),
                        performer=(
                            entry.get("artist")
                            or ""
                        ),
                    )
                )

            return results

        except Exception:
            logger.exception(
                "❌ Music search failed: %s",
                query,
            )
            return []

    # -----------------------------------------------------
    # Download
    # -----------------------------------------------------

    async def download(
        self,
        track: TrackInfo,
    ) -> Optional[str]:

        if not track:
            return None

        # اگر قبلاً دانلود شده
        if track.filepath:
            path = Path(track.filepath)

            if path.exists() and path.stat().st_size > 0:
                return str(path)

        source = (
            track.webpage_url
            or track.url
        )

        if not source:
            logger.error(
                "❌ Track has no source URL: %s",
                track.title,
            )
            return None

        loop = asyncio.get_running_loop()

        safe_title = _clean_filename(
            track.title
        )

        output_template = str(
            self.downloads_dir
            / f"{safe_title}.%(ext)s"
        )

        def _download():

            # اول تلاش: MP3 با FFmpeg
            mp3_opts = {
                **self.base_opts,
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

            try:

                with yt_dlp.YoutubeDL(
                    mp3_opts
                ) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=True,
                    )

                    if not info:
                        return None

            except Exception:

                logger.exception(
                    "⚠️ MP3 download failed, trying original audio"
                )

                # تلاش دوم بدون postprocessor
                fallback_template = str(
                    self.downloads_dir
                    / f"{safe_title}.%(ext)s"
                )

                fallback_opts = {
                    **self.base_opts,
                    "format": (
                        "bestaudio[ext=m4a]/"
                        "bestaudio[ext=webm]/"
                        "bestaudio/best"
                    ),
                    "outtmpl": fallback_template,
                }

                with yt_dlp.YoutubeDL(
                    fallback_opts
                ) as ydl:

                    info = ydl.extract_info(
                        source,
                        download=True,
                    )

                    if not info:
                        return None

            # پیدا کردن فایل واقعی
            candidates = []

            for path in self.downloads_dir.iterdir():

                if not path.is_file():
                    continue

                if path.stat().st_size <= 0:
                    continue

                if path.suffix.lower() not in {
                    ".mp3",
                    ".m4a",
                    ".webm",
                    ".opus",
                    ".ogg",
                    ".wav",
                    ".aac",
                    ".flac",
                }:
                    continue

                candidates.append(path)

            if not candidates:
                return None

            # جدیدترین فایل
            candidates.sort(
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            return str(candidates[0])

        try:

            filepath = await loop.run_in_executor(
                None,
                _download,
            )

            if not filepath:
                logger.error(
                    "❌ No downloaded audio file found"
                )
                return None

            path = Path(filepath)

            if not path.exists():
                logger.error(
                    "❌ Downloaded file does not exist: %s",
                    filepath,
                )
                return None

            if path.stat().st_size <= 0:
                logger.error(
                    "❌ Downloaded file is empty: %s",
                    filepath,
                )
                return None

            track.filepath = str(path)

            logger.info(
                "✅ Download completed: %s",
                filepath,
            )

            return str(path)

        except Exception:

            logger.exception(
                "❌ Download failed: %s",
                track.title,
            )

            return None

    # -----------------------------------------------------
    # Download Telegram audio
    # -----------------------------------------------------

    async def prepare_local_file(
        self,
        filepath: str,
        title: str = "Telegram Audio",
        uploader: str = "Telegram",
    ) -> Optional[TrackInfo]:

        if not filepath:
            return None

        path = Path(filepath)

        if not path.exists():
            return None

        if path.stat().st_size <= 0:
            return None

        return TrackInfo(
            title=title or "Telegram Audio",
            duration=0,
            url="",
            webpage_url="",
            thumbnail="",
            uploader=uploader or "Telegram",
            filepath=str(path),
        )


# =========================================================
# Music Player
# =========================================================

class MusicPlayer:

    def __init__(
        self,
        pytgcalls_client=None,
    ):

        self.client = pytgcalls_client

        self.current_track: Optional[
            TrackInfo
        ] = None

        self.current_chat_id = None

        self.volume = int(
            getattr(
                config,
                "default_volume",
                100,
            )
        )

        self.volume = max(
            0,
            min(200, self.volume),
        )

        self.is_playing = False
        self.is_paused = False

        self.started_at = None
        self.paused_at = None
        self.position = 0

        self.queue: List[
            TrackInfo
        ] = []

        self.history: List[
            TrackInfo
        ] = []

        self._lock = asyncio.Lock()

        self._available = bool(
            VOICE_CHAT_AVAILABLE
            and self.client is not None
            and MediaStream is not None
        )

        self.downloader = MusicDownloader()

        logger.info(
            "MusicPlayer initialized | voice=%s",
            self._available,
        )

    # -----------------------------------------------------
    # Availability
    # -----------------------------------------------------

    def is_voice_chat_available(
        self,
    ) -> bool:

        return self._available

    # -----------------------------------------------------
    # Internal client call
    # -----------------------------------------------------

    async def _call(
        self,
        method_name: str,
        *args,
        **kwargs,
    ):

        if not self.client:
            return None

        method = getattr(
            self.client,
            method_name,
            None,
        )

        if not callable(method):
            return None

        return await _maybe_await(
            method(
                *args,
                **kwargs,
            )
        )

    # -----------------------------------------------------
    # Play
    # -----------------------------------------------------

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if not self._available:
            logger.error(
                "❌ Voice chat is not available"
            )
            return False

        if not track:
            logger.error(
                "❌ No track supplied"
            )
            return False

        if not track.filepath:
            logger.error(
                "❌ Track has no filepath: %s",
                track.title,
            )
            return False

        path = Path(
            track.filepath
        )

        if not path.exists():
            logger.error(
                "❌ Audio file does not exist: %s",
                path,
            )
            return False

        if path.stat().st_size <= 0:
            logger.error(
                "❌ Audio file is empty: %s",
                path,
            )
            return False

        async with self._lock:

            try:

                # اگر در یک چت دیگر در حال پخش است
                if (
                    self.current_chat_id
                    and self.current_chat_id != chat_id
                ):
                    try:
                        await self._call(
                            "leave_call",
                            self.current_chat_id,
                        )
                    except Exception:
                        logger.exception(
                            "Could not leave previous call"
                        )

                # ساخت MediaStream
                stream = MediaStream(
                    str(path),
                    video_flags=MediaStream.Flags.IGNORE,
                )

                logger.info(
                    "▶️ Starting PyTgCalls playback | chat=%s | file=%s",
                    chat_id,
                    path,
                )

                # API اصلی PyTgCalls
                await self._call(
                    "play",
                    chat_id,
                    stream,
                )

                self.current_track = track
                self.current_chat_id = chat_id

                self.is_playing = True
                self.is_paused = False

                self.started_at = time.monotonic()
                self.paused_at = None
                self.position = 0

                logger.info(
                    "🟢 NOW PLAYING: %s",
                    track.title,
                )

                return True

            except Exception:

                logger.exception(
                    "❌ PyTgCalls playback failed | chat=%s | track=%s",
                    chat_id,
                    track.title,
                )

                return False

    # -----------------------------------------------------
    # Play downloaded track
    # -----------------------------------------------------

    async def play_track(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:

        if not track.filepath:

            filepath = await self.downloader.download(
                track
            )

            if not filepath:
                return False

            track.filepath = filepath

        return await self.play(
            chat_id,
            track,
        )

    # -----------------------------------------------------
    # Queue
    # -----------------------------------------------------

    def add_to_queue(
        self,
        track: TrackInfo,
    ):

        if track:
            self.queue.append(track)

    def clear_queue(self):

        self.queue.clear()

    def get_queue(self):

        return list(self.queue)

    # -----------------------------------------------------
    # Next
    # -----------------------------------------------------

    async def next(
        self,
        chat_id: int,
    ) -> bool:

        if not self.queue:
            logger.info(
                "Queue is empty"
            )
            return False

        track = self.queue.pop(0)

        if self.current_track:
            self.history.append(
                self.current_track
            )

            if len(self.history) > 20:
                self.history.pop(0)

        return await self.play_track(
            chat_id,
            track,
        )

    # -----------------------------------------------------
    # Previous
    # -----------------------------------------------------

    async def previous(
        self,
        chat_id: int,
    ) -> bool:

        if not self.history:
            return False

        track = self.history.pop()

        return await self.play_track(
            chat_id,
            track,
        )

    # -----------------------------------------------------
    # Stop
    # -----------------------------------------------------

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        async with self._lock:

            try:

                await self._call(
                    "leave_call",
                    chat_id,
                )

                if self.current_track:
                    try:
                        if self.current_track.filepath:
                            path = Path(
                                self.current_track.filepath
                            )

                            # فایل‌های کوچک قدیمی را پاک کن
                            # اما فایل‌های در حال استفاده را
                            # قبل از خروج پاک نمی‌کنیم.
                    except Exception:
                        pass

                self.current_track = None
                self.current_chat_id = None

                self.is_playing = False
                self.is_paused = False

                self.started_at = None
                self.paused_at = None
                self.position = 0

                logger.info(
                    "⏹️ Playback stopped: %s",
                    chat_id,
                )

                return True

            except Exception:

                logger.exception(
                    "❌ Stop failed"
                )

                return False

    # -----------------------------------------------------
    # Pause
    # -----------------------------------------------------

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            result = await self._call(
                "pause",
                chat_id,
            )

            if result is None:
                logger.error(
                    "❌ PyTgCalls pause method unavailable"
                )
                return False

            self.is_paused = True
            self.is_playing = False

            if self.started_at:
                self.position = (
                    time.monotonic()
                    - self.started_at
                )

            self.paused_at = time.monotonic()

            return True

        except Exception:

            logger.exception(
                "❌ Pause failed"
            )

            return False

    # -----------------------------------------------------
    # Resume
    # -----------------------------------------------------

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            result = await self._call(
                "resume",
                chat_id,
            )

            if result is None:
                logger.error(
                    "❌ PyTgCalls resume method unavailable"
                )
                return False

            self.is_paused = False
            self.is_playing = True

            if self.paused_at:
                paused_time = (
                    time.monotonic()
                    - self.paused_at
                )

                if self.started_at:
                    self.started_at += paused_time

            self.paused_at = None

            return True

        except Exception:

            logger.exception(
                "❌ Resume failed"
            )

            return False

    # -----------------------------------------------------
    # Volume
    # -----------------------------------------------------

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:

        if not self._available:
            return False

        try:

            volume = int(volume)

        except Exception:
            return False

        volume = max(
            0,
            min(200, volume),
        )

        try:

            method = getattr(
                self.client,
                "change_volume_call",
                None,
            )

            if not callable(method):
                method = getattr(
                    self.client,
                    "change_volume",
                    None,
                )

            if not callable(method):
                logger.error(
                    "❌ PyTgCalls volume method unavailable"
                )
                return False

            await _maybe_await(
                method(
                    chat_id,
                    volume,
                )
            )

            self.volume = volume

            return True

        except Exception:

            logger.exception(
                "❌ Volume change failed"
            )

            return False

    # -----------------------------------------------------
    # Seek
    # -----------------------------------------------------

    async def seek(
        self,
        chat_id: int,
        seconds: int,
    ) -> bool:

        if not self._available:
            return False

        try:
            seconds = int(seconds)
        except Exception:
            return False

        if not self.current_track:
            return False

        seconds = max(
            0,
            seconds,
        )

        # PyTgCalls versions مختلف هستند.
        # اگر seek در نسخه نصب‌شده وجود داشته باشد استفاده می‌شود.
        for method_name in (
            "seek",
            "seek_stream",
            "change_stream",
        ):

            method = getattr(
                self.client,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:

                result = await _maybe_await(
                    method(
                        chat_id,
                        seconds,
                    )
                )

                self.position = seconds

                if self.started_at:
                    self.started_at = (
                        time.monotonic()
                        - seconds
                    )

                return True

            except Exception:
                logger.exception(
                    "Seek method failed: %s",
                    method_name,
                )

        logger.warning(
            "⚠️ Seek is not supported by installed PyTgCalls version"
        )

        return False

    # -----------------------------------------------------
    # Forward
    # -----------------------------------------------------

    async def forward(
        self,
        chat_id: int,
        seconds: int = 10,
    ) -> bool:

        try:
            seconds = max(
                1,
                min(100, int(seconds)),
            )
        except Exception:
            seconds = 10

        current = self.get_position()

        return await self.seek(
            chat_id,
            current + seconds,
        )

    # -----------------------------------------------------
    # Backward
    # -----------------------------------------------------

    async def backward(
        self,
        chat_id: int,
        seconds: int = 10,
    ) -> bool:

        try:
            seconds = max(
                1,
                min(100, int(seconds)),
            )
        except Exception:
            seconds = 10

        current = self.get_position()

        return await self.seek(
            chat_id,
            max(0, current - seconds),
        )

    # -----------------------------------------------------
    # Position
    # -----------------------------------------------------

    def get_position(self) -> int:

        if self.is_paused:
            return int(
                self.position
            )

        if (
            self.is_playing
            and self.started_at
        ):

            return max(
                0,
                int(
                    time.monotonic()
                    - self.started_at
                ),
            )

        return int(
            self.position
        )

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    def get_status(
        self,
    ) -> Dict[str, Any]:

        position = self.get_position()

        duration = 0

        if self.current_track:
            duration = int(
                self.current_track.duration
                or 0
            )

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
            "position": position,
            "duration": duration,
            "queue_size": len(
                self.queue
            ),
        }

    # -----------------------------------------------------
    # Cleanup
    # -----------------------------------------------------

    async def cleanup_files(
        self,
        max_files: int = 30,
    ):

        try:

            files = []

            for path in (
                self.downloader.downloads_dir.iterdir()
            ):

                if not path.is_file():
                    continue

                if path.suffix.lower() not in {
                    ".mp3",
                    ".m4a",
                    ".webm",
                    ".opus",
                    ".ogg",
                    ".wav",
                    ".aac",
                    ".flac",
                }:
                    continue

                files.append(path)

            files.sort(
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for path in files[max_files:]:

                try:
                    path.unlink()
                except Exception:
                    pass

        except Exception:

            logger.exception(
                "Cleanup failed"
            )


# =========================================================
# Global downloader
# =========================================================

downloader = MusicDownloader()
