from future import annotations

import asyncio
import logging
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse

import yt_dlp

try:
from pytgcalls.types import MediaStream
except Exception:
MediaStream = None

logger = logging.getLogger("SILENT.player")

============================================================

PATHS

============================================================

BASE_DIR = Path(file).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

============================================================

TRACK

============================================================

@dataclass
class TrackInfo:
title: str
performer: str = ""
artist: str = ""
duration: int = 0
url: str = ""
source_url: str = ""
file_path: str = ""
thumbnail: str = ""

def display_name(self) -> str:
    if self.performer:
        return f"{self.title} — {self.performer}"
    if self.artist:
        return f"{self.title} — {self.artist}"
    return self.title

============================================================

YOUTUBE / AUDIO DOWNLOADER

============================================================

class MusicDownloader:

YDL_SEARCH_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": False,
    "noplaylist": True,
    "default_search": "ytsearch",
}

YDL_INFO_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
}

YDL_DOWNLOAD_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "restrictfilenames": True,
    "overwrites": False,
    "continuedl": True,
}

def __init__(self):
    self._lock = asyncio.Lock()

@staticmethod
def _is_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
        return parsed.scheme in ("http", "https")
    except Exception:
        return False

@staticmethod
def _clean_query(query: str) -> str:
    query = re.sub(r"\s+", " ", query or "").strip()
    return query

@staticmethod
def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120] or "audio"

def _search_sync(self, query: str) -> Optional[dict]:
    query = self._clean_query(query)

    if not query:
        return None

    search_query = (
        query
        if self._is_url(query)
        else f"ytsearch1:{query}"
    )

    options = dict(self.YDL_SEARCH_OPTIONS)

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(
            search_query,
            download=False,
        )

    if not info:
        return None

    if "entries" in info:
        entries = [
            item for item in info.get("entries", [])
            if item
        ]

        if not entries:
            return None

        return entries[0]

    return info

def _download_sync(self, info: dict) -> Optional[Path]:
    video_id = (
        str(info.get("id"))
        if info.get("id")
        else ""
    )

    title = (
        str(info.get("title"))
        if info.get("title")
        else "audio"
    )

    if not video_id:
        return None

    # ----------------------------------------------------
    # Existing file
    # ----------------------------------------------------

    existing = list(
        DOWNLOAD_DIR.glob(
            f"{self._safe_filename(video_id)}.*"
        )
    )

    if existing:
        for item in existing:
            if item.is_file():
                return item

    # ----------------------------------------------------
    # Download
    # ----------------------------------------------------

    options = dict(self.YDL_DOWNLOAD_OPTIONS)

    with yt_dlp.YoutubeDL(options) as ydl:

        result = ydl.extract_info(
            info.get("webpage_url")
            or info.get("original_url")
            or info.get("url"),
            download=True,
        )

        if not result:
            return None

        prepared = ydl.prepare_filename(result)

    prepared_path = Path(prepared)

    if prepared_path.exists():
        return prepared_path

    # yt-dlp may return a different extension after post-processing.
    candidates = list(
        DOWNLOAD_DIR.glob(
            f"{self._safe_filename(video_id)}.*"
        )
    )

    if candidates:
        candidates.sort(
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0]

    # Fallback: locate by video id.
    candidates = [
        p for p in DOWNLOAD_DIR.iterdir()
        if p.is_file()
        and video_id in p.name
    ]

    if candidates:
        candidates.sort(
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0]

    logger.warning(
        "Downloaded file not found for %s (%s)",
        video_id,
        title,
    )

    return None

async def search(self, query: str, limit: int = 1):
    """
    Search YouTube.

    Returns a list of TrackInfo.
    """

    query = self._clean_query(query)

    if not query:
        return []

    try:

        info = await asyncio.to_thread(
            self._search_sync,
            query,
        )

    except Exception:

        logger.exception(
            "YouTube search failed: %s",
            query,
        )

        return []

    if not info:
        return []

    return [
        self._track_from_info(info)
    ]

def _track_from_info(
    self,
    info: dict,
) -> TrackInfo:

    title = (
        str(info.get("title"))
        if info.get("title")
        else "Unknown"
    )

    performer = (
        str(info.get("uploader"))
        if info.get("uploader")
        else ""
    )

    artist = (
        str(info.get("artist"))
        if info.get("artist")
        else performer
    )

    duration = info.get("duration") or 0

    try:
        duration = int(duration)
    except Exception:
        duration = 0

    webpage_url = (
        str(info.get("webpage_url"))
        if info.get("webpage_url")
        else ""
    )

    if not webpage_url:
        webpage_url = (
            str(info.get("original_url"))
            if info.get("original_url")
            else ""
        )

    thumbnail = (
        str(info.get("thumbnail"))
        if info.get("thumbnail")
        else ""
    )

    return TrackInfo(
        title=title,
        performer=performer,
        artist=artist,
        duration=duration,
        url=webpage_url,
        source_url=webpage_url,
        thumbnail=thumbnail,
    )

async def prepare(
    self,
    track: TrackInfo,
) -> Optional[TrackInfo]:
    """
    Download a TrackInfo and attach the local file path.
    """

    async with self._lock:

        try:

            info = await asyncio.to_thread(
                self._search_sync,
                track.source_url or track.url,
            )

        except Exception:

            logger.exception(
                "Could not resolve source: %s",
                track.source_url or track.url,
            )

            return None

        if not info:
            return None

        try:

            file_path = await asyncio.to_thread(
                self._download_sync,
                info,
            )

        except Exception:

            logger.exception(
                "Audio download failed: %s",
                track.title,
            )

            return None

        if not file_path:
            return None

        resolved = self._track_from_info(info)

        resolved.file_path = str(file_path)

        return resolved

============================================================

PLAYER

============================================================

class MusicPlayer:

def __init__(
    self,
    call: Any = None,
):
    self.call = call
    self.downloader = MusicDownloader()

    # ----------------------------------------------------
    # Current tracks by chat
    # ----------------------------------------------------

    self.current: dict[int, TrackInfo] = {}

    # ----------------------------------------------------
    # Queue by chat
    # ----------------------------------------------------

    self.queues: dict[int, list[TrackInfo]] = {}

    # ----------------------------------------------------
    # Playback history
    # ----------------------------------------------------

    self.history: dict[int, list[TrackInfo]] = {}

    # ----------------------------------------------------
    # Pause state
    # ----------------------------------------------------

    self.paused: dict[int, bool] = {}

    # ----------------------------------------------------
    # Playback timing
    # ----------------------------------------------------

    self.started_at: dict[int, float] = {}
    self.paused_at: dict[int, float] = {}
    self.offset: dict[int, float] = {}

    # ----------------------------------------------------
    # Per-chat locks
    # ----------------------------------------------------

    self._locks: dict[int, asyncio.Lock] = {}

    # ----------------------------------------------------
    # Prevent duplicate automatic next calls
    # ----------------------------------------------------

    self._advancing: set[int] = set()

    # ----------------------------------------------------
    # Active voice chats
    # ----------------------------------------------------

    self.active_chat_ids: set[int] = set()

# ========================================================
# LOCK
# ========================================================

def _get_lock(self, chat_id: int) -> asyncio.Lock:
    chat_id = int(chat_id)

    if chat_id not in self._locks:
        self._locks[chat_id] = asyncio.Lock()

    return self._locks[chat_id]

# ========================================================
# CALL HELPERS
# ========================================================

async def _call_play(
    self,
    chat_id: int,
    file_path: str,
):
    if not self.call:
        raise RuntimeError(
            "PyTgCalls is not available"
        )

    if not MediaStream:
        raise RuntimeError(
            "MediaStream is unavailable"
        )

    stream = MediaStream(
        file_path,
        video_flags=MediaStream.Flags.IGNORE,
    )

    result = self.call.play(
        int(chat_id),
        stream,
    )

    if asyncio.iscoroutine(result):
        await result

async def _call_leave(
    self,
    chat_id: int,
):
    if not self.call:
        return

    leave = getattr(
        self.call,
        "leave_call",
        None,
    )

    if not callable(leave):
        return

    try:

        result = leave(
            int(chat_id)
        )

        if asyncio.iscoroutine(result):
            await result

    except Exception:

        logger.exception(
            "Could not leave call %s",
            chat_id,
        )

# ========================================================
# DOWNLOAD / RESOLVE
# ========================================================

async def _prepare_track(
    self,
    track: TrackInfo,
) -> Optional[TrackInfo]:

    if track.file_path:

        path = Path(track.file_path)

        if path.exists() and path.is_file():
            return track

    return await self.downloader.prepare(
        track
    )

async def resolve(
    self,
    query: str,
) -> Optional[TrackInfo]:
    """
    Resolve a name or YouTube URL.
    """

    query = str(query or "").strip()

    if not query:
        return None

    results = await self.downloader.search(
        query,
        limit=1,
    )

    if not results:
        return None

    return results[0]

# ========================================================
# PLAY FIRST / ADD TO QUEUE
# ========================================================

async def play(
    self,
    chat_id: int,
    track: TrackInfo,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        # ------------------------------------------------
        # NOTHING PLAYING
        # ------------------------------------------------

        if chat_id not in self.current:

            return await self._start_track_locked(
                chat_id,
                track,
            )

        # ------------------------------------------------
        # SOMETHING IS PLAYING
        # NEW TRACK GOES TO QUEUE
        # ------------------------------------------------

        queue = self.queues.setdefault(
            chat_id,
            [],
        )

        queue.append(track)

        logger.info(
            "➕ Added to queue | chat=%s | %s",
            chat_id,
            track.display_name(),
        )

        return {
            "status": "queued",
            "track": track,
            "position": len(queue),
            "queue_size": len(queue),
        }

async def play_query(
    self,
    chat_id: int,
    query: str,
) -> dict:

    track = await self.resolve(
        query
    )

    if not track:
        return {
            "status": "not_found",
            "track": None,
        }

    return await self.play(
        chat_id,
        track,
    )

# ========================================================
# START TRACK
# ========================================================

async def _start_track_locked(
    self,
    chat_id: int,
    track: TrackInfo,
) -> dict:

    prepared = await self._prepare_track(
        track
    )

    if not prepared:

        logger.error(
            "❌ Could not prepare track: %s",
            track.display_name(),
        )

        return {
            "status": "error",
            "track": track,
            "error": "download_failed",
        }

    if not prepared.file_path:

        return {
            "status": "error",
            "track": prepared,
            "error": "file_missing",
        }

    # ----------------------------------------------------
    # Play
    # ----------------------------------------------------

    try:

        await self._call_play(
            chat_id,
            prepared.file_path,
        )

    except Exception:

        logger.exception(
            "❌ Failed to start track in chat %s",
            chat_id,
        )

        return {
            "status": "error",
            "track": prepared,
            "error": "play_failed",
        }

    # ----------------------------------------------------
    # State
    # ----------------------------------------------------

    self.current[chat_id] = prepared
    self.paused[chat_id] = False
    self.started_at[chat_id] = time.monotonic()
    self.paused_at[chat_id] = 0.0
    self.offset[chat_id] = 0.0
    self.active_chat_ids.add(chat_id)

    logger.info(
        "▶️ Playing | chat=%s | %s",
        chat_id,
        prepared.display_name(),
    )

    return {
        "status": "playing",
        "track": prepared,
        "queue_size": len(
            self.queues.get(chat_id, [])
        ),
    }

async def play_track(
    self,
    chat_id: int,
    track: TrackInfo,
    save_history: bool = True,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        if save_history:

            old = self.current.get(
                chat_id
            )

            if old:

                self.history.setdefault(
                    chat_id,
                    [],
                ).append(old)

        return await self._start_track_locked(
            chat_id,
            track,
        )

# ========================================================
# ADD QUEUE
# ========================================================

async def add_to_queue(
    self,
    chat_id: int,
    track: TrackInfo,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        queue = self.queues.setdefault(
            chat_id,
            [],
        )

        queue.append(track)

        position = len(queue)

        logger.info(
            "➕ Queue #%s | chat=%s | %s",
            position,
            chat_id,
            track.display_name(),
        )

        return {
            "status": "queued",
            "position": position,
            "queue_size": position,
            "track": track,
        }

# ========================================================
# NEXT
# ========================================================

async def next(
    self,
    chat_id: int,
    automatic: bool = False,
) -> dict:

    chat_id = int(chat_id)

    # ----------------------------------------------------
    # Avoid two simultaneous next operations.
    # ----------------------------------------------------

    if chat_id in self._advancing:
        return {
            "status": "already_advancing",
        }

    self._advancing.add(chat_id)

    try:

        async with self._get_lock(chat_id):

            old = self.current.get(
                chat_id
            )

            queue = self.queues.setdefault(
                chat_id,
                [],
            )

            # --------------------------------------------
            # Save current in history
            # --------------------------------------------

            if old:

                self.history.setdefault(
                    chat_id,
                    [],
                ).append(old)

            # --------------------------------------------
            # QUEUE HAS NEXT TRACK
            # --------------------------------------------

            if queue:

                next_track = queue.pop(0)

                result = await self._start_track_locked(
                    chat_id,
                    next_track,
                )

                result["automatic"] = automatic

                logger.info(
                    "⏭️ Next track | chat=%s | remaining=%s",
                    chat_id,
                    len(queue),
                )

                return result

            # --------------------------------------------
            # NOTHING IN QUEUE
            # --------------------------------------------

            self.current.pop(
                chat_id,
                None,
            )

            self.paused.pop(
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

            self.offset.pop(
                chat_id,
                None,
            )

            await self._call_leave(
                chat_id
            )

            self.active_chat_ids.discard(
                chat_id
            )

            logger.info(
                "⏹️ Queue empty | chat=%s",
                chat_id,
            )

            return {
                "status": "empty",
                "track": None,
                "automatic": automatic,
            }

    finally:

        self._advancing.discard(
            chat_id
        )

# ========================================================
# AUTO NEXT
# ========================================================

async def on_stream_end(
    self,
    chat_id: int,
) -> dict:

    """
    Called by main.py when PyTgCalls reports
    that the current stream has ended.
    """

    chat_id = int(chat_id)

    logger.info(
        "🎵 Stream ended | chat=%s",
        chat_id,
    )

    return await self.next(
        chat_id,
        automatic=True,
    )

# Alias for compatibility
async def handle_stream_end(
    self,
    chat_id: int,
) -> dict:

    return await self.on_stream_end(
        chat_id
    )

# ========================================================
# PAUSE
# ========================================================

async def pause(
    self,
    chat_id: int,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        if chat_id not in self.current:

            return {
                "status": "nothing_playing"
            }

        if self.paused.get(
            chat_id,
            False,
        ):

            return {
                "status": "already_paused",
                "track": self.current[chat_id],
            }

        pause_method = getattr(
            self.call,
            "pause",
            None,
        )

        if not callable(pause_method):

            return {
                "status": "unsupported",
            }

        try:

            result = pause_method(
                chat_id
            )

            if asyncio.iscoroutine(result):
                await result

        except Exception:

            logger.exception(
                "Pause failed | chat=%s",
                chat_id,
            )

            return {
                "status": "error"
            }

        self.paused[chat_id] = True
        self.paused_at[chat_id] = time.monotonic()

        logger.info(
            "⏸️ Paused | chat=%s",
            chat_id,
        )

        return {
            "status": "paused",
            "track": self.current[chat_id],
        }

# ========================================================
# RESUME
# ========================================================

async def resume(
    self,
    chat_id: int,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        if chat_id not in self.current:

            return {
                "status": "nothing_playing"
            }

        if not self.paused.get(
            chat_id,
            False,
        ):

            return {
                "status": "already_playing",
                "track": self.current[chat_id],
            }

        resume_method = getattr(
            self.call,
            "resume",
            None,
        )

        if not callable(resume_method):

            return {
                "status": "unsupported",
            }

        try:

            result = resume_method(
                chat_id
            )

            if asyncio.iscoroutine(result):
                await result

        except Exception:

            logger.exception(
                "Resume failed | chat=%s",
                chat_id,
            )

            return {
                "status": "error"
            }

        self.paused[chat_id] = False

        if self.paused_at.get(chat_id):

            self.offset[chat_id] += (
                time.monotonic()
                - self.paused_at[chat_id]
            )

        self.paused_at[chat_id] = 0.0

        logger.info(
            "▶️ Resumed | chat=%s",
            chat_id,
        )

        return {
            "status": "resumed",
            "track": self.current[chat_id],
        }

# ========================================================
# STOP / END
# ========================================================

async def stop(
    self,
    chat_id: int,
    clear_queue: bool = True,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        current = self.current.get(
            chat_id
        )

        if clear_queue:

            self.queues.pop(
                chat_id,
                None,
            )

        self.current.pop(
            chat_id,
            None,
        )

        self.paused.pop(
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

        self.offset.pop(
            chat_id,
            None,
        )

        await self._call_leave(
            chat_id
        )

        self.active_chat_ids.discard(
            chat_id
        )

        logger.info(
            "⏹️ Stopped | chat=%s",
            chat_id,
        )

        return {
            "status": "stopped",
            "track": current,
        }

# ========================================================
# CLEAR QUEUE
# ========================================================

async def clear_queue(
    self,
    chat_id: int,
) -> int:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        queue = self.queues.pop(
            chat_id,
            [],
        )

        count = len(queue)

        logger.info(
            "🗑️ Queue cleared | chat=%s | count=%s",
            chat_id,
            count,
        )

        return count

# ========================================================
# PREVIOUS
# ========================================================

async def previous(
    self,
    chat_id: int,
) -> dict:

    chat_id = int(chat_id)

    async with self._get_lock(chat_id):

        history = self.history.setdefault(
            chat_id,
            [],
        )

        if not history:

            return {
                "status": "no_history"
            }

        previous_track = history.pop()

        current = self.current.get(
            chat_id
        )

        if current:

            self.queues.setdefault(
                chat_id,
                [],
            ).insert(
                0,
                current,
            )

        return await self._start_track_locked(
            chat_id,
            previous_track,
        )

# ========================================================
# SEEK
# ========================================================

async def seek(
    self,
    chat_id: int,
    seconds: int,
) -> dict:

    chat_id = int(chat_id)
    seconds = max(0, int(seconds))

    seek_method = getattr(
        self.call,
        "seek",
        None,
    )

    if not callable(seek_method):

        return {
            "status": "unsupported"
        }

    try:

        result = seek_method(
            chat_id,
            seconds,
        )

        if asyncio.iscoroutine(result):
            await result

    except Exception:

        logger.exception(
            "Seek failed | chat=%s",
            chat_id,
        )

        return {
            "status": "error"
        }

    self.offset[chat_id] = float(
        seconds
    )

    self.started_at[chat_id] = (
        time.monotonic()
    )

    return {
        "status": "seeked",
        "seconds": seconds,
    }

# ========================================================
# POSITION
# ========================================================

def get_position(
    self,
    chat_id: int,
) -> int:

    chat_id = int(chat_id)

    if chat_id not in self.current:
        return 0

    base = self.offset.get(
        chat_id,
        0.0,
    )

    if self.paused.get(
        chat_id,
        False,
    ):

        if self.paused_at.get(chat_id):

            return int(
                base
                + (
                    self.paused_at[chat_id]
                    - self.started_at.get(
                        chat_id,
                        self.paused_at[chat_id],
                    )
                )
            )

        return int(base)

    return int(
        base
        + (
            time.monotonic()
            - self.started_at.get(
                chat_id,
                time.monotonic(),
            )
        )
    )

# ========================================================
# VOLUME
# ========================================================

async def set_volume(
    self,
    chat_id: int,
    volume: int,
) -> dict:

    chat_id = int(chat_id)

    volume = max(
        0,
        min(200, int(volume)),
    )

    volume_method = getattr(
        self.call,
        "change_volume_call",
        None,
    )

    if not callable(volume_method):

        volume_method = getattr(
            self.call,
            "set_volume",
            None,
        )

    if not callable(volume_method):

        return {
            "status": "unsupported"
        }

    try:

        result = volume_method(
            chat_id,
            volume,
        )

        if asyncio.iscoroutine(result):
            await result

    except Exception:

        logger.exception(
            "Volume change failed | chat=%s",
            chat_id,
        )

        return {
            "status": "error"
        }

    return {
        "status": "volume_changed",
        "volume": volume,
    }

# ========================================================
# CURRENT
# ========================================================

def get_current(
    self,
    chat_id: int,
) -> Optional[TrackInfo]:

    return self.current.get(
        int(chat_id)
    )

# ========================================================
# QUEUE
# ========================================================

def get_queue(
    self,
    chat_id: int,
) -> list[TrackInfo]:

    return list(
        self.queues.get(
            int(chat_id),
            [],
        )
    )

def queue_count(
    self,
    chat_id: int,
) -> int:

    return len(
        self.queues.get(
            int(chat_id),
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

    return int(chat_id) in self.current

def is_paused(
    self,
    chat_id: int,
) -> bool:

    return bool(
        self.paused.get(
            int(chat_id),
            False,
        )
    )

# ========================================================
# CLEANUP
# ========================================================

async def cleanup_chat(
    self,
    chat_id: int,
):

    chat_id = int(chat_id)

    try:
        await self.stop(
            chat_id,
            clear_queue=True,
        )
    except Exception:
        logger.exception(
            "Cleanup failed | chat=%s",
            chat_id,
        )

    self.history.pop(
        chat_id,
        None,
    )

    self._locks.pop(
        chat_id,
        None,
    )

async def cleanup(self):

    chat_ids = set(
        self.active_chat_ids
    )

    chat_ids.update(
        self.current.keys()
    )

    for chat_id in list(chat_ids):

        try:
            await self.cleanup_chat(
                chat_id
            )
        except Exception:
            logger.exception(
                "Cleanup failed | chat=%s",
                chat_id,
            )

    # ----------------------------------------------------
    # Remove temporary downloads.
    # ----------------------------------------------------

    try:

        for file in DOWNLOAD_DIR.iterdir():

            if not file.is_file():
                continue

            try:
                file.unlink()
            except Exception:
                pass

    except Exception:
        pass

============================================================

GLOBAL SINGLETON HELPER

============================================================

downloader = MusicDownloader()
