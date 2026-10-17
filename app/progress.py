import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import ASSETS_DIR

PROGRESS_FILE = ASSETS_DIR / "live-progress.json"


def update_progress(**values):
    current = {}
    if PROGRESS_FILE.exists():
        try:
            current = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    current.update(values)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = PROGRESS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    temporary.replace(PROGRESS_FILE)


def read_progress():
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
