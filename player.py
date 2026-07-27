"""
Music Downloader and Player for Telegram Music Bot.

This module handles:
- Music downloading via yt-dlp
- Playback management via PyTgCalls (when available)
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import yt_dlp

from config import config
from optional_deps import (
    VOICE_CHAT_AVAILABLE, AudioPiped, PyTgCalls, logger as _logger
)

# Use optional_deps logger
logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    """Information about a music track."""
    title: str
    duration: int
    url: str
    webpage_url: str
    thumbnail: str
    uploader: str
    filepath: Optional[str] = None


class MusicDownloader:
    """Downloads audio from various sources using yt-dlp."""
    
    def __init__(self):
        self.downloads_dir = Path(config.downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self._ydl_opts = {
            'format': config.ytdl_format,
            'outtmpl': str(self.downloads_dir / '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
        }
    
    async def extract_info(self, query: str) -> Optional[TrackInfo]:
        """Extract info from URL or search query without downloading."""
        loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL({**self._ydl_opts, 'extract_flat': True}) as ydl:
                # Check if it's a URL or search query
                if query.startswith(('http://', 'https://')):
                    info = await loop.run_in_executor(None, ydl.extract_info, query, False)
                else:
                    info = await loop.run_in_executor(None, ydl.extract_info, f"ytsearch:{query}", False)
                
                if not info:
                    return None
                
                # Handle playlist/search results
                if 'entries' in info:
                    info = info['entries'][0] if info['entries'] else None
                
                if not info:
                    return None
                
                return TrackInfo(
                    title=info.get('title', 'Unknown'),
                    duration=info.get('duration', 0) or 0,
                    url=info.get('url', ''),
                    webpage_url=info.get('webpage_url', ''),
                    thumbnail=info.get('thumbnail', ''),
                    uploader=info.get('uploader', 'Unknown')
                )
        except Exception as e:
            logger.error(f"Error extracting info: {e}")
            return None
    
    async def download(self, track: TrackInfo) -> Optional[str]:
        """Download audio file for a track."""
        loop = asyncio.get_event_loop()
        try:
            ydl_opts = {
                **self._ydl_opts,
                'outtmpl': str(self.downloads_dir / f'{track.title}.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([track.webpage_url])
                    # Find the downloaded file
                    for ext in ['mp3', 'm4a', 'webm', 'opus']:
                        files = list(self.downloads_dir.glob(f'{track.title}.{ext}'))
                        if files:
                            return str(files[0])
                    return None
            
            filepath = await loop.run_in_executor(None, _download)
            if filepath and Path(filepath).exists():
                track.filepath = filepath
                logger.info(f"Downloaded: {filepath}")
                return filepath
            return None
        except Exception as e:
            logger.error(f"Error downloading {track.title}: {e}")
            return None
    
    async def search(self, query: str, limit: int = 5) -> List[TrackInfo]:
        """Search for tracks."""
        loop = asyncio.get_event_loop()
        try:
            with yt_dlp.YoutubeDL({**self._ydl_opts, 'extract_flat': True}) as ydl:
                info = await loop.run_in_executor(None, ydl.extract_info, f"ytsearch{limit}:{query}", False)
                tracks = []
                if info and 'entries' in info:
                    for entry in info['entries'][:limit]:
                        if entry:
                            tracks.append(TrackInfo(
                                title=entry.get('title', 'Unknown'),
                                duration=entry.get('duration', 0) or 0,
                                url=entry.get('url', ''),
                                webpage_url=entry.get('webpage_url', ''),
                                thumbnail=entry.get('thumbnail', ''),
                                uploader=entry.get('uploader', 'Unknown')
                            ))
                return tracks
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []


class MusicPlayer:
    """Wrapper for PyTgCalls playback management.
    
    This class is a no-op when PyTgCalls is not available (Android).
    """
    
    def __init__(self, pytgcalls_client=None):
        self.client = pytgcalls_client
        self.current_track: Optional[TrackInfo] = None
        self.current_chat_id: Optional[int] = None
        self.volume: int = config.default_volume
        self.repeat_mode: str = "off"  # off, one, all
        self.is_playing: bool = False
        self.is_paused: bool = False
        self._leave_task: Optional[asyncio.Task] = None
        self._available = VOICE_CHAT_AVAILABLE
        
        if not self._available:
            logger.warning("MusicPlayer initialized but voice chat is NOT available on this platform")
    
    async def join_call(self, chat_id: int) -> bool:
        """Join voice chat."""
        if not self._available:
            logger.error("Voice chat not available on this platform")
            return False
        
        try:
            await self.client.join_group_call(chat_id, None)
            self.current_chat_id = chat_id
            self._cancel_leave_timer()
            return True
        except Exception as e:
            logger.error(f"Failed to join call: {e}")
            return False
    
    async def leave_call(self, chat_id: int) -> bool:
        """Leave voice chat."""
        if not self._available:
            return False
        
        try:
            await self.client.leave_group_call(chat_id)
            self.current_chat_id = None
            self.current_track = None
            self.is_playing = False
            self.is_paused = False
            self._cancel_leave_timer()
            return True
        except Exception as e:
            logger.error(f"Failed to leave call: {e}")
            return False
    
    async def play(self, chat_id: int, track: TrackInfo) -> bool:
        """Play a track in voice chat."""
        if not self._available:
            logger.error("Voice chat not available on this platform")
            return False
        
        if not track.filepath or not Path(track.filepath).exists():
            logger.error(f"File not found: {track.filepath}")
            return False
        
        try:
            # Join if not already in call
            if self.current_chat_id != chat_id:
                await self.leave_call(self.current_chat_id) if self.current_chat_id else None
                await self.join_call(chat_id)
            
            # Create audio stream
            audio_piped = AudioPiped(
                track.filepath,
                audio_parameters=AudioPiped.HighQualityAudio()
            )
            
            await self.client.change_stream(chat_id, audio_piped)
            
            self.current_track = track
            self.current_chat_id = chat_id
            self.is_playing = True
            self.is_paused = False
            self._cancel_leave_timer()
            
            logger.info(f"Playing: {track.title} in chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Error playing track: {e}")
            return False
    
    async def pause(self, chat_id: int) -> bool:
        """Pause playback."""
        if not self._available:
            return False
        
        try:
            await self.client.pause_stream(chat_id)
            self.is_paused = True
            self.is_playing = False
            return True
        except Exception as e:
            logger.error(f"Error pausing: {e}")
            return False
    
    async def resume(self, chat_id: int) -> bool:
        """Resume playback."""
        if not self._available:
            return False
        
        try:
            await self.client.resume_stream(chat_id)
            self.is_paused = False
            self.is_playing = True
            return True
        except Exception as e:
            logger.error(f"Error resuming: {e}")
            return False
    
    async def stop(self, chat_id: int) -> bool:
        """Stop playback and leave call."""
        if not self._available:
            return False
        
        try:
            await self.client.leave_group_call(chat_id)
            self.current_track = None
            self.current_chat_id = None
            self.is_playing = False
            self.is_paused = False
            self._cancel_leave_timer()
            return True
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False
    
    async def set_volume(self, chat_id: int, volume: int) -> bool:
        """Set volume (0-200)."""
        if not self._available:
            return False
        
        try:
            volume = max(0, min(200, volume))
            await self.client.change_volume_call(chat_id, volume)
            self.volume = volume
            return True
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def _cancel_leave_timer(self):
        if self._leave_task:
            self._leave_task.cancel()
            self._leave_task = None
    
    def _schedule_auto_leave(self, chat_id: int, timeout: int):
        self._cancel_leave_timer()
        if timeout > 0:
            self._leave_task = asyncio.create_task(self._auto_leave(chat_id, timeout))
    
    async def _auto_leave(self, chat_id: int, timeout: int):
        await asyncio.sleep(timeout)
        if self.current_chat_id == chat_id and not self.is_playing:
            await self.leave_call(chat_id)
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "available": self._available,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "current_track": self.current_track.title if self.current_track else None,
            "current_chat_id": self.current_chat_id,
            "volume": self.volume,
            "repeat_mode": self.repeat_mode
        }
    
    def is_voice_chat_available(self) -> bool:
        """Check if voice chat functionality is available."""
        return self._available


# Global instances
downloader = MusicDownloader()
# player will be initialized in main.py after pytgcalls client is created