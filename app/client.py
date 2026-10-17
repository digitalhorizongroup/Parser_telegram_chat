from pathlib import Path

from app.config import (API_HASH, API_ID, APP_VERSION, DEVICE_MODEL, LANG_CODE,
                        LANG_PACK, SESSION_NAME, SESSIONS_DIR, SYSTEM_LANG_CODE,
                        SYSTEM_VERSION)
from telethon import TelegramClient

def create_client(session: Path | str = SESSION_NAME) -> TelegramClient:
    client = TelegramClient(
        session=session,
        api_id=API_ID,
        api_hash=API_HASH,
        device_model=DEVICE_MODEL,
        system_version=SYSTEM_VERSION,
        app_version=APP_VERSION,
        lang_code=LANG_CODE,
        system_lang_code=SYSTEM_LANG_CODE,
    )
    # Telethon 1.39 does not expose lang_pack in TelegramClient.__init__,
    # but keeps it on the InitConnection request sent before authorization.
    client._init_request.lang_pack = LANG_PACK
    return client


def discover_sessions() -> list[Path]:
    """Return uploaded Telethon sessions; names are intentionally irrelevant."""
    if not SESSIONS_DIR.exists():
        return []
    return sorted(path for path in SESSIONS_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".session")


def create_clients() -> tuple[list[TelegramClient], bool]:
    sessions = discover_sessions()
    if sessions:
        return [create_client(path) for path in sessions], True
    return [create_client()], False
