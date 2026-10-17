import asyncio
import argparse
import logging
from app.progress import update_progress

from app.config import validate_config

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Telegram Chat Parser")
        parser.add_argument("--min-users", type=int, default=1)
        parser.add_argument("--min-messages", type=int, default=0)
        parser.add_argument("--exclude", default="", help="Слова через запятую")
        parser.add_argument("--language", choices=["", "ru", "uk", "en"], default="")
        parser.add_argument("--active-only", action="store_true")
        parser.add_argument("--public-only", action="store_true")
        parser.add_argument("--writable-only", action="store_true")
        args = parser.parse_args()
        validate_config()
        from app.main import check_voice_chats
        from app.models import FilterConfig

        asyncio.run(check_voice_chats(FilterConfig(
            excluded_words=[x.strip() for x in args.exclude.split(",") if x.strip()],
            min_users=args.min_users, min_messages_24h=args.min_messages,
            language=args.language, active_only=args.active_only,
            public_only=args.public_only, writable_only=args.writable_only,
        )))
    except (RuntimeError, ValueError) as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
        logging.error("%s", exc)
        update_progress(phase="failed", phase_label="Ошибка запуска", error=str(exc))
        raise SystemExit(2)
