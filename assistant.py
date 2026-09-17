import os
import logging

from pyrogram import Client

logger = logging.getLogger(__name__)


def create_assistant(api_id: int, api_hash: str):
    """
    ساخت اکانت کاربری دستیار با ASSISTANT_SESSION.

    Session از Environment Variable خوانده می‌شود
    و هیچ‌وقت در لاگ چاپ نمی‌شود.
    """

    session_string = os.getenv("ASSISTANT_SESSION")

    if not session_string:
        raise RuntimeError(
            "ASSISTANT_SESSION is not configured"
        )

    assistant = Client(
        "assistant_account",
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        in_memory=True,
    )

    logger.info(
        "✅ Assistant client object created"
    )

    return assistant
