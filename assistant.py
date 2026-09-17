from __future__ import annotations

import logging
import os

from pyrogram import Client


logger = logging.getLogger("SILENT.assistant")


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

def _get_env(name: str) -> str:
    """
    Read a required secret from environment variables.

    Secret values are never written to logs.
    """

    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} is not configured"
        )

    return value


# ============================================================
# CREATE ASSISTANT
# ============================================================

def create_assistant(
    api_id: int,
    api_hash: str,
) -> Client:
    """
    Create the Telegram user-account client used as
    the voice-chat assistant.

    Required secret:

        ASSISTANT_SESSION

    The session string is never printed or logged.
    """

    # --------------------------------------------------------
    # API ID
    # --------------------------------------------------------

    try:

        api_id = int(api_id)

    except (TypeError, ValueError) as exc:

        raise RuntimeError(
            "API_ID is invalid"
        ) from exc

    if api_id <= 0:

        raise RuntimeError(
            "API_ID must be greater than zero"
        )

    # --------------------------------------------------------
    # API HASH
    # --------------------------------------------------------

    api_hash = str(
        api_hash or ""
    ).strip()

    if not api_hash:

        raise RuntimeError(
            "API_HASH is not configured"
        )

    # --------------------------------------------------------
    # ASSISTANT SESSION
    # --------------------------------------------------------

    session_string = _get_env(
        "ASSISTANT_SESSION"
    )

    # --------------------------------------------------------
    # PYROGRAM CLIENT
    # --------------------------------------------------------

    try:

        assistant = Client(
            name="assistant_account",
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            in_memory=True,
        )

    except Exception as exc:

        # IMPORTANT:
        # Never include the session string in an error message.

        logger.exception(
            "❌ Failed to create assistant client"
        )

        raise RuntimeError(
            "Could not create assistant client"
        ) from exc

    # --------------------------------------------------------
    # SAFE LOGGING
    # --------------------------------------------------------

    logger.info(
        "✅ Assistant client created successfully"
    )

    return assistant


# ============================================================
# SESSION CHECK
# ============================================================

def assistant_session_configured() -> bool:
    """
    Check whether ASSISTANT_SESSION exists.

    The actual session value is never returned.
    """

    value = os.getenv(
        "ASSISTANT_SESSION",
        "",
    )

    return bool(
        value.strip()
    )
