from __future__ import annotations

import logging
import os
from typing import Optional

from pyrogram import Client

logger = logging.getLogger("SILENT.assistant")


# ============================================================
# ENV HELPERS
# ============================================================

def _get_env(name: str) -> str:
    """
    خواندن مقدار Secret بدون نمایش مقدار آن.
    """
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} is not configured"
        )

    return value


# ============================================================
# ASSISTANT
# ============================================================

def create_assistant(
    api_id: int,
    api_hash: str,
) -> Client:
    """
    ساخت کلاینت اکانت دستیار تلگرام.

    اطلاعات حساس فقط از Environment Variables خوانده می‌شوند:

        ASSISTANT_SESSION

    Session String هیچ‌وقت در لاگ چاپ نمی‌شود.
    """

    # --------------------------------------------------------
    # Validate API credentials
    # --------------------------------------------------------

    try:
        api_id = int(api_id)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "API_ID is invalid"
        ) from exc

    api_hash = str(
        api_hash or ""
    ).strip()

    if api_id <= 0:
        raise RuntimeError(
            "API_ID must be greater than zero"
        )

    if not api_hash:
        raise RuntimeError(
            "API_HASH is not configured"
        )

    # --------------------------------------------------------
    # Read assistant session
    # --------------------------------------------------------

    session_string = _get_env(
        "ASSISTANT_SESSION"
    )

    # --------------------------------------------------------
    # Create Pyrogram client
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

        # Never include session_string in the error.
        logger.exception(
            "❌ Failed to create assistant client"
        )

        raise RuntimeError(
            "Could not create assistant client"
        ) from exc

    # --------------------------------------------------------
    # Safe log
    # --------------------------------------------------------

    logger.info(
        "✅ Assistant client created successfully"
    )

    return assistant


# ============================================================
# OPTIONAL VALIDATION
# ============================================================

def assistant_session_configured() -> bool:
    """
    بررسی می‌کند که ASSISTANT_SESSION وجود دارد یا نه.

    مقدار Session را برنمی‌گرداند.
    """

    value: Optional[str] = os.getenv(
        "ASSISTANT_SESSION"
    )

    return bool(
        value and value.strip()
    )
