import sys
import platform
import logging

logger = logging.getLogger(__name__)

IS_ANDROID = sys.platform == "android" or "android" in platform.platform().lower()
IS_TERMUX = "com.termux" in platform.platform().lower()

VOICE_CHAT_AVAILABLE = False
PyTgCalls = None
MediaStream = None
AudioQuality = None
VideoQuality = None
IMPORT_ERROR = None


# -------------------------------------------------
# Pyrogram / PyTgCalls compatibility fix
# -------------------------------------------------

try:
    import pyrogram.errors

    # PyTgCalls 2.3.3 expects:
    # GroupcallForbidden
    #
    # Pyrogram 2.0.106 provides:
    # GroupCallForbidden

    if not hasattr(pyrogram.errors, "GroupcallForbidden"):

        if hasattr(pyrogram.errors, "GroupCallForbidden"):
            pyrogram.errors.GroupcallForbidden = (
                pyrogram.errors.GroupCallForbidden
            )
            logger.info(
                "✅ Pyrogram/PyTgCalls compatibility fix applied"
            )

        else:

            class GroupcallForbidden(Exception):
                pass

            pyrogram.errors.GroupcallForbidden = GroupcallForbidden

except Exception as e:
    IMPORT_ERROR = e
    logger.exception(
        "❌ Could not apply Pyrogram compatibility fix"
    )


# -------------------------------------------------
# PyTgCalls
# -------------------------------------------------

if not IS_ANDROID:

    try:

        from pytgcalls import PyTgCalls
        from pytgcalls.types import MediaStream

        try:
            from pytgcalls.types import AudioQuality
        except ImportError:
            AudioQuality = None

        try:
            from pytgcalls.types import VideoQuality
        except ImportError:
            VideoQuality = None

        VOICE_CHAT_AVAILABLE = True

        logger.info(
            "✅ PyTgCalls imports loaded successfully"
        )

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
        "Voice chat disabled."
    )


# -------------------------------------------------
# psutil
# -------------------------------------------------

psutil = None
HAS_PSUTIL = False

try:

    import psutil

    HAS_PSUTIL = True

except Exception:

    psutil = None
    HAS_PSUTIL = False


# -------------------------------------------------
# Helpers
# -------------------------------------------------

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
        "voice_chat_available": VOICE_CHAT_AVAILABLE,
        "has_psutil": HAS_PSUTIL,
    }

    if IMPORT_ERROR:
        info["pytgcalls_import_error"] = str(
            IMPORT_ERROR
        )

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
