"""
Platform detection and optional dependencies utilities.
"""

import sys
import platform
from typing import Optional, Any


# Platform detection
IS_ANDROID = sys.platform == "android" or "android" in platform.platform().lower()
IS_TERMUX = "com.termux" in platform.platform().lower() or "TERMUX" in (platform.platform() + "").upper()
IS_LINUX = sys.platform.startswith("linux") and not IS_ANDROID
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def get_platform_info() -> dict:
    """Get detailed platform information."""
    return {
        "system": platform.system(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "is_android": IS_ANDROID,
        "is_termux": IS_TERMUX,
        "is_linux": IS_LINUX,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
    }


# Optional dependencies
class OptionalDependency:
    """Wrapper for optional dependencies with graceful degradation."""
    
    def __init__(self, name: str):
        self.name = name
        self._module: Optional[Any] = None
        self._error: Optional[Exception] = None
        self._loaded = False
    
    def load(self) -> bool:
        """Try to load the module."""
        if self._loaded:
            return self._module is not None
        
        self._loaded = True
        try:
            self._module = __import__(self.name)
            return True
        except Exception as e:
            self._error = e
            return False
    
    @property
    def available(self) -> bool:
        """Check if dependency is available."""
        if not self._loaded:
            self.load()
        return self._module is not None
    
    @property
    def module(self) -> Optional[Any]:
        """Get the loaded module (loads if needed)."""
        if not self._loaded:
            self.load()
        return self._module
    
    @property
    def error(self) -> Optional[Exception]:
        """Get the import error if any."""
        if not self._loaded:
            self.load()
        return self._error
    
    def __getattr__(self, name: str):
        """Delegate attribute access to the module."""
        if not self._loaded:
            self.load()
        if self._module is None:
            raise ImportError(
                f"Optional dependency '{self.name}' is not available. "
                f"Import error: {self._error}"
            )
        return getattr(self._module, name)


# Optional dependencies
psutil = OptionalDependency("psutil")
pytgcalls = OptionalDependency("pytgcalls")
tgcalls = OptionalDependency("tgcalls")


# Feature flags
HAS_PSUTIL = psutil.available
HAS_PYTGCALLS = pytgcalls.available
HAS_TGCALLS = tgcalls.available

# Voice chat availability
VOICE_CHAT_AVAILABLE = HAS_PYTGCALLS and HAS_TGCALLS


def print_platform_info():
    """Print platform information for debugging."""
    info = get_platform_info()
    print("=== Platform Info ===")
    for key, value in info.items():
        print(f"  {key}: {value}")
    print("=== Optional Dependencies ===")
    print(f"  psutil: {'✅' if HAS_PSUTIL else '❌'}")
    print(f"  pytgcalls: {'✅' if HAS_PYTGCALLS else '❌'}")
    print(f"  tgcalls: {'✅' if HAS_TGCALLS else '❌'}")
    print(f"  Voice Chat: {'✅' if VOICE_CHAT_AVAILABLE else '❌'}")