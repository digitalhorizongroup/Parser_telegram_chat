import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
SESSIONS_DIR = Path(os.getenv("TELEGRAM_SESSIONS_DIR", str(ASSETS_DIR / "sessions")))
load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} должен быть целым числом") from exc


API_ID = _env_int("TELEGRAM_API_ID", 0)
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_NAME = Path(os.getenv("TELEGRAM_SESSION", str(ASSETS_DIR / "session_name")))
DEVICE_MODEL = os.getenv("TELEGRAM_DEVICE_MODEL", "Telegram Parser")
SYSTEM_VERSION = os.getenv("TELEGRAM_SYSTEM_VERSION", "Windows")
APP_VERSION = os.getenv("TELEGRAM_APP_VERSION", "1.0")
LANG_CODE = os.getenv("TELEGRAM_LANG_CODE", "ru")
SYSTEM_LANG_CODE = os.getenv("TELEGRAM_SYSTEM_LANG_CODE", "ru-RU")
LANG_PACK = os.getenv("TELEGRAM_LANG_PACK", "")

MIN_GROUP_USERS = _env_int("MIN_GROUP_USERS", 1)
SEARCH_LIMIT = _env_int("SEARCH_LIMIT", 10)
MAX_MESSAGES_24H = _env_int("MAX_MESSAGES_24H", 10_000)
MAX_MESSAGES_30D = _env_int("MAX_MESSAGES_30D", 50_000)
CONCURRENCY = _env_int("CONCURRENCY", 3)
REQUEST_RETRIES = _env_int("REQUEST_RETRIES", 4)
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.35"))

EXCEL_FILE = Path(os.getenv("OUTPUT_FILE", str(ASSETS_DIR / "groups.xlsx")))
DICTIONARY = Path(os.getenv("KEYWORDS_FILE", str(ASSETS_DIR / "keywords.txt")))
DATABASE_FILE = Path(os.getenv("DATABASE_FILE", str(ASSETS_DIR / "history.sqlite3")))
COOLDOWN_FILE = Path(os.getenv("TELEGRAM_COOLDOWN_FILE", str(ASSETS_DIR / "account_cooldowns.json")))
LONG_FLOODWAIT_THRESHOLD = _env_int("LONG_FLOODWAIT_THRESHOLD", 3600)
LONG_ACCOUNT_REST_SECONDS = _env_int("LONG_ACCOUNT_REST_SECONDS", 172800)


def validate_config() -> None:
    missing = []
    if API_ID <= 0:
        missing.append("TELEGRAM_API_ID")
    if not API_HASH:
        missing.append("TELEGRAM_API_HASH")
    if not DICTIONARY.is_file():
        missing.append(f"файл ключевых слов: {DICTIONARY}")
    if missing:
        raise RuntimeError("Не настроено: " + ", ".join(missing))
