import sys
import platform
import logging

logger = logging.getLogger(__name__)

IS_ANDROID = (
    sys.platform == "android"
    or "android" in platform.platform().lower()
)

IS_TERMUX = (
    "com.termux" in platform.platform().lower()
    or "TERMUX" in platform.platform().upper()
)

IS_LINUX = sys.platform.startswith("linux") and not IS_ANDROID
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

VOICE_CHAT_AVAILABLE = False

PyTgCalls = None
MediaStream = None
AudioQuality = None
VideoQuality = None

IMPORT_ERROR = None


if not IS_ANDROID:
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types import MediaStream
        from pytgcalls.types import AudioQuality
        from pytgcalls.types import VideoQuality

        VOICE_CHAT_AVAILABLE = True

        logger.info("✅ PyTgCalls imports loaded successfully")

    except Exception as e:
        IMPORT_ERROR = e
        VOICE_CHAT_AVAILABLE = False

        logger.exception(
            "❌ PyTgCalls import failed: %s",
            e,
        )

else:
    logger.warning(
        "⚠️ Android/Termux detected. "
        "Voice chat is disabled on Android."
    )


# Optional psutil
psutil = None
HAS_PSUTIL = False

if not IS_ANDROID:
    try:
        import psutil

        HAS_PSUTIL = True

    except Exception:
        psutil = None
        HAS_PSUTIL = False


def check_voice_chat_support():
    if IS_ANDROID:
        return (
            False,
            "Voice chat is not supported on Android/Termux."
        )

    if not VOICE_CHAT_AVAILABLE:
        if IMPORT_ERROR:
            return (
                False,
                f"PyTgCalls import failed: {IMPORT_ERROR}"
            )

        return (
            False,
            "PyTgCalls is not available."
        )

    return (
        True,
        "Voice chat is supported."
    )


def get_platform_info():
    info = {
        "system": platform.system(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "is_android": IS_ANDROID,
        "is_termux": IS_TERMUX,
        "is_linux": IS_LINUX,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "voice_chat_available": VOICE_CHAT_AVAILABLE,
        "has_psutil": HAS_PSUTIL,
    }

    if IMPORT_ERROR:
        info["pytgcalls_import_error"] = str(IMPORT_ERROR)

    try:
        import pytgcalls

        info["pytgcalls_version"] = getattr(
            pytgcalls,
            "__version__",
            "unknown",
        )

    except Exception:
        info["pytgcalls_version"] = "unknown"

    return info
