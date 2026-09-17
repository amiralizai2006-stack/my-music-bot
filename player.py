from future import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from optional_deps import MediaStream

logger = logging.getLogger(name)

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
    if not self.performer and self.artist:
        self.performer = self.artist

    if not self.artist and self.performer:
        self.artist = self.performer

class MusicDownloader:

def __init__(self):
    self.download_dir = Path(
        os.getenv(
            "DOWNLOAD_DIR",
            "downloads",
        )
    )

    self.download_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

async def search(
    self,
    query: str,
    limit: int = 1,
) -> Optional[TrackInfo]:

    query = (query or "").strip()

    if not query:
        return None

    try:
        import yt_dlp
    except ImportError:
        logger.exception(
            "yt-dlp is not installed"
        )
        return None

    def _search():

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "default_search": "ytsearch",
        }

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            result = ydl.extract_info(
                f"ytsearch{max(1, limit)}:{query}",
                download=False,
            )

        entries = (
            result.get("entries")
            or []
        )

        if not entries:
            return None

        item = entries[0]

        return TrackInfo(
            title=(
                item.get("title")
                or "موزیک بدون نام"
            ),
            performer=(
                item.get("artist")
                or item.get("uploader")
                or ""
            ),
            artist=(
                item.get("artist")
                or item.get("uploader")
                or ""
            ),
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
            ),
        )

    try:
        return await asyncio.to_thread(
            _search
        )

    except Exception:
        logger.exception(
            "Music search failed"
        )
        return None

async def download(
    self,
    track: TrackInfo,
) -> Optional[str]:

    if not track:
        return None

    if (
        track.filepath
        and Path(
            track.filepath
        ).exists()
    ):
        return track.filepath

    try:
        import yt_dlp
    except ImportError:
        logger.exception(
            "yt-dlp is not installed"
        )
        return None

    source = (
        track.webpage_url
        or track.url
    )

    if not source:
        return None

    def _download():

        output_template = str(
            self.download_dir
            / "%(id)s.%(ext)s"
        )

        options = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "prefer_ffmpeg": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            info = ydl.extract_info(
                source,
                download=True,
            )

            prepared = (
                ydl.prepare_filename(
                    info
                )
            )

        mp3_path = str(
            Path(
                prepared
            ).with_suffix(
                ".mp3"
            )
        )

        if Path(
            mp3_path
        ).exists():
            return mp3_path

        if Path(
            prepared
        ).exists():
            return prepared

        return None

    try:
        filepath = (
            await asyncio.to_thread(
                _download
            )
        )

        if filepath:
            track.filepath = filepath

        return filepath

    except Exception:
        logger.exception(
            "Download failed"
        )
        return None

async def prepare(
    self,
    track: TrackInfo,
) -> Optional[TrackInfo]:

    filepath = (
        await self.download(
            track
        )
    )

    if not filepath:
        return None

    track.filepath = filepath

    return track

class MusicPlayer:

def __init__(
    self,
    app: Any = None,
    call: Any = None,
):

    self.app = app
    self.call = call

    self.downloader = (
        MusicDownloader()
    )

    self.queues: dict[
        int,
        list[TrackInfo],
    ] = {}

    self.current: dict[
        int,
        Optional[TrackInfo],
    ] = {}

    self.history: dict[
        int,
        list[TrackInfo],
    ] = {}

    self.started_at: dict[
        int,
        float,
    ] = {}

    self.paused_at: dict[
        int,
        float,
    ] = {}

    self.volume: dict[
        int,
        int,
    ] = {}

    self.locks: dict[
        int,
        asyncio.Lock,
    ] = {}

def _lock(
    self,
    chat_id: int,
) -> asyncio.Lock:

    if chat_id not in self.locks:
        self.locks[chat_id] = (
            asyncio.Lock()
        )

    return self.locks[chat_id]

def _queue(
    self,
    chat_id: int,
) -> list[TrackInfo]:

    return self.queues.setdefault(
        chat_id,
        [],
    )

async def play_track(
    self,
    chat_id: int,
    track: TrackInfo,
) -> bool:

    if not track:
        return False

    async with self._lock(
        chat_id
    ):

        prepared = (
            await self.downloader.prepare(
                track
            )
        )

        if (
            not prepared
            or not prepared.filepath
        ):
            logger.error(
                "Could not prepare track"
            )
            return False

        if self.call is None:
            logger.error(
                "PyTgCalls is not connected"
            )
            return False

        try:

            stream = MediaStream(
                prepared.filepath
            )

            await self.call.play(
                chat_id,
                stream,
            )

            old = self.current.get(
                chat_id
            )

            if old:
                self.history.setdefault(
                    chat_id,
                    [],
                ).append(old)

            self.current[
                chat_id
            ] = prepared

            self.started_at[
                chat_id
            ] = time.time()

            self.paused_at.pop(
                chat_id,
                None,
            )

            return True

        except Exception:
            logger.exception(
                "Playback failed"
            )
            return False

async def play(
    self,
    chat_id: int,
    track: TrackInfo,
) -> bool:

    if not track:
        return False

    if self.current.get(
        chat_id
    ):
        self._queue(
            chat_id
        ).append(track)

        return True

    return await self.play_track(
        chat_id,
        track,
    )

async def add_to_queue(
    self,
    chat_id: int,
    track: TrackInfo,
) -> bool:

    if not track:
        return False

    self._queue(
        chat_id
    ).append(track)

    return True

async def pause(
    self,
    chat_id: int,
) -> bool:

    if self.call is None:
        return False

    try:

        await self.call.pause(
            chat_id
        )

        self.paused_at[
            chat_id
        ] = time.time()

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

    if self.call is None:
        return False

    try:

        await self.call.resume(
            chat_id
        )

        paused = (
            self.paused_at.pop(
                chat_id,
                None,
            )
        )

        if paused:
            self.started_at[
                chat_id
            ] += (
                time.time()
                - paused
            )

        return True

    except Exception:
        logger.exception(
            "Resume failed"
        )
        return False

async def stop(
    self,
    chat_id: int,
) -> bool:

    try:

        if self.call is not None:
            await self.call.leave_call(
                chat_id
            )

    except Exception:
        logger.exception(
            "Leave call failed"
        )

    self.current.pop(
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

    self.queues.pop(
        chat_id,
        None,
    )

    return True

async def next(
    self,
    chat_id: int,
) -> Optional[TrackInfo]:

    queue = self._queue(
        chat_id
    )

    if not queue:
        await self.stop(
            chat_id
        )
        return None

    track = queue.pop(0)

    self.current[
        chat_id
    ] = None

    success = (
        await self.play_track(
            chat_id,
            track,
        )
    )

    if not success:
        return None

    return track

async def previous(
    self,
    chat_id: int,
) -> Optional[TrackInfo]:

    history = self.history.setdefault(
        chat_id,
        [],
    )

    if not history:
        return None

    track = history.pop()

    current = self.current.get(
        chat_id
    )

    if current:
        self._queue(
            chat_id
        ).insert(
            0,
            current,
        )

    self.current[
        chat_id
    ] = None

    success = (
        await self.play_track(
            chat_id,
            track,
        )
    )

    if not success:
        return None

    return track

async def clear_queue(
    self,
    chat_id: int,
) -> bool:

    self.queues.pop(
        chat_id,
        None,
    )

    return True

async def set_volume(
    self,
    chat_id: int,
    volume: int,
) -> bool:

    volume = max(
        1,
        min(
            200,
            int(volume),
        ),
    )

    if self.call is None:
        return False

    try:

        await self.call.change_volume(
            chat_id,
            volume,
        )

        self.volume[
            chat_id
        ] = volume

        return True

    except Exception:
        logger.exception(
            "Volume change failed"
        )
        return False

async def get_position(
    self,
    chat_id: int,
) -> int:

    current = self.current.get(
        chat_id
    )

    if not current:
        return 0

    end = self.paused_at.get(
        chat_id,
        time.time(),
    )

    started = self.started_at.get(
        chat_id,
        end,
    )

    position = int(
        max(
            0,
            end - started,
        )
    )

    if current.duration:
        position = min(
            position,
            current.duration,
        )

    return position

async def seek(
    self,
    chat_id: int,
    position: int,
) -> bool:

    if self.call is None:
        return False

    current = self.current.get(
        chat_id
    )

    if not current:
        return False

    position = max(
        0,
        int(position),
    )

    if current.duration:
        position = min(
            position,
            current.duration,
        )

    try:

        await self.call.seek(
            chat_id,
            position,
        )

        self.started_at[
            chat_id
        ] = (
            time.time()
            - position
        )

        return True

    except Exception:
        logger.exception(
            "Seek failed"
        )
        return False

async def forward(
    self,
    chat_id: int,
    seconds: int = 10,
) -> bool:

    position = (
        await self.get_position(
            chat_id
        )
    )

    return await self.seek(
        chat_id,
        position + int(seconds),
    )

async def backward(
    self,
    chat_id: int,
    seconds: int = 10,
) -> bool:

    position = (
        await self.get_position(
            chat_id
        )
    )

    return await self.seek(
        chat_id,
        max(
            0,
            position - int(seconds),
        ),
    )

def get_current(
    self,
    chat_id: int,
) -> Optional[TrackInfo]:

    return self.current.get(
        chat_id
    )

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

async def get_status(
    self,
    chat_id: int,
) -> dict[str, Any]:

    current = self.current.get(
        chat_id
    )

    position = (
        await self.get_position(
            chat_id
        )
    )

    return {
        "playing": (
            current is not None
        ),
        "current": current,
        "position": position,
        "duration": (
            current.duration
            if current
            else 0
        ),
        "queue_size": len(
            self.queues.get(
                chat_id,
                [],
            )
        ),
        "volume": self.volume.get(
            chat_id,
            100,
        ),
        "paused": (
            chat_id
            in self.paused_at
        ),
    }

async def cleanup_files(
    self,
    chat_id: int,
) -> None:

    files = []

    current = self.current.get(
        chat_id
    )

    if (
        current
        and current.filepath
    ):
        files.append(
            current.filepath
        )

    for track in self.queues.get(
        chat_id,
        [],
    ):
        if track.filepath:
            files.append(
                track.filepath
            )

    for filepath in files:

        try:

            path = Path(filepath)

            if path.exists():
                path.unlink()

        except Exception:
            logger.exception(
                "Could not remove file"
            )

async def cleanup_chat(
    self,
    chat_id: int,
) -> None:

    try:
        await self.stop(
            chat_id
        )

    except Exception:
        logger.exception(
            "Cleanup failed"
        )

    self.queues.pop(
        chat_id,
        None,
    )

    self.current.pop(
        chat_id,
        None,
    )

    self.history.pop(
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

    self.volume.pop(
        chat_id,
        None,
    )

    self.locks.pop(
        chat_id,
        None,
    )

:::end

این نسخه را کامل جایگزین "player.py" کن؛ هیچ خطی قبل یا بعد از کد داخل فایل نگذار. سپس Commit و Deploy کن.
