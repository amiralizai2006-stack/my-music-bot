"""
Platform detection utilities for cross-platform compatibility.
"""
import platform
import sys
import os

# Detect Android/Termux environment
def is_android() -> bool:
    """Check if running on Android (Termux)."""
    # Method 1: Check platform string
    platform_str = platform.platform().lower()
    if "android" in platform_str:
        return True
    
    # Method 2: Check sys.platform
    if sys.platform == "android":
        return True
    
    # Method 3: Check for Termux-specific environment variables
    if os.environ.get("TERMUX_VERSION") is not None:
        return True
    
    # Method 4: Check for ANDROID_ROOT
    if os.environ.get("ANDROID_ROOT") is not None:
        return True
    
    return False


def is_linux() -> bool:
    """Check if running on Linux (but not Android)."""
    return sys.platform.startswith("linux") and not is_android()


def is_macos() -> bool:
    """Check if running on macOS."""
    return sys.platform == "darwin"


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def get_platform_name() -> str:
    """Get human-readable platform name."""
    if is_android():
        return "Android (Termux)"
    elif is_linux():
        return "Linux"
    elif is_macos():
        return "macOS"
    elif is_windows():
        return "Windows"
    else:
        return f"Unknown ({sys.platform})"


# Global constants for easy checking
IS_ANDROID = is_android()
IS_LINUX = is_linux()
IS_MACOS = is_macos()
IS_WINDOWS = is_windows()
PLATFORM_NAME = get_platform_name()

# Voice chat availability
HAS_VOICE_CHAT_SUPPORT = not IS_ANDROID  # pytgcalls/tgcalls not available on Android

# Log platform info
import logging
logger = logging.getLogger(__name__)
logger.info(f"Platform detected: {PLATFORM_NAME}")
logger.info(f"Voice chat support: {'Available' if HAS_VOICE_CHAT_SUPPORT else 'Unavailable'}")