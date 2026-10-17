import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.models import ChatResult, ScanError


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    def _create_schema(self):
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                total INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS results (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                chat_id INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (run_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                chat_id INTEGER, title TEXT, kind TEXT, message TEXT, occurred_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_results_chat ON results(chat_id);
            CREATE INDEX IF NOT EXISTS idx_runs_fingerprint ON runs(fingerprint, status);
        """)
        self.connection.commit()

    def start_or_resume(self, fingerprint: str) -> tuple[int, bool]:
        row = self.connection.execute(
            "SELECT id FROM runs WHERE fingerprint=? AND status='running' ORDER BY id DESC LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if row:
            return row["id"], True
        cursor = self.connection.execute(
            "INSERT INTO runs(fingerprint, started_at, status) VALUES(?, ?, 'running')",
            (fingerprint, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()
        return cursor.lastrowid, False

    def set_total(self, run_id: int, total: int):
        self.connection.execute("UPDATE runs SET total=? WHERE id=?", (total, run_id))
        self.connection.commit()

    def processed_ids(self, run_id: int) -> set[int]:
        rows = self.connection.execute("SELECT chat_id FROM results WHERE run_id=?", (run_id,))
        done = {row[0] for row in rows}
        rows = self.connection.execute("SELECT chat_id FROM errors WHERE run_id=? AND chat_id IS NOT NULL", (run_id,))
        return done | {row[0] for row in rows}

    def previous_participants(self, chat_id: int, before_run: int) -> int | None:
        rows = self.connection.execute(
            "SELECT payload FROM results WHERE chat_id=? AND run_id<? ORDER BY run_id DESC LIMIT 1",
            (chat_id, before_run),
        ).fetchone()
        if not rows:
            return None
        return json.loads(rows["payload"]).get("participants")

    def save_result(self, run_id: int, result: ChatResult):
        self.connection.execute(
            "INSERT OR REPLACE INTO results(run_id, chat_id, payload) VALUES(?, ?, ?)",
            (run_id, result.chat_id, json.dumps(result.to_dict(), ensure_ascii=False)),
        )
        self._update_completed(run_id)

    def save_error(self, run_id: int, error: ScanError):
        self.connection.execute(
            "INSERT INTO errors(run_id, chat_id, title, kind, message, occurred_at) VALUES(?,?,?,?,?,?)",
            (run_id, error.chat_id, error.title, error.kind.value, error.message, error.occurred_at),
        )
        self._update_completed(run_id)

    def _update_completed(self, run_id: int):
        self.connection.execute(
            "UPDATE runs SET completed=(SELECT COUNT(*) FROM results WHERE run_id=?)+(SELECT COUNT(*) FROM errors WHERE run_id=?) WHERE id=?",
            (run_id, run_id, run_id),
        )
        self.connection.commit()

    def results(self, run_id: int) -> list[ChatResult]:
        rows = self.connection.execute("SELECT payload FROM results WHERE run_id=?", (run_id,))
        return [ChatResult(**json.loads(row[0])) for row in rows]

    def errors(self, run_id: int) -> list[dict]:
        rows = self.connection.execute(
            "SELECT chat_id,title,kind,message,occurred_at FROM errors WHERE run_id=? ORDER BY id", (run_id,)
        )
        return [dict(row) for row in rows]

    def finish(self, run_id: int):
        self.connection.execute(
            "UPDATE runs SET status='completed', finished_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), run_id),
        )
        self.connection.commit()

    def latest_progress(self) -> dict:
        row = self.connection.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else {"status": "idle", "total": 0, "completed": 0}

    def run_history(self, limit: int = 30) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT r.*, COUNT(DISTINCT x.chat_id) AS results_count,
                   COUNT(DISTINCT e.id) AS errors_count
            FROM runs r
            LEFT JOIN results x ON x.run_id=r.id
            LEFT JOIN errors e ON e.run_id=r.id
            GROUP BY r.id ORDER BY r.id DESC LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        )
        return [dict(row) for row in rows]

    def result_table(self, run_id: int | None = None, query: str = "", limit: int = 200, offset: int = 0) -> dict:
        if run_id is None:
            row = self.connection.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            run_id = row["id"] if row else None
        if run_id is None:
            return {"run_id": None, "total": 0, "rows": [], "errors": []}
        rows = [json.loads(row[0]) for row in self.connection.execute(
            "SELECT payload FROM results WHERE run_id=? ORDER BY chat_id", (run_id,)
        )]
        needle = query.casefold().strip()
        if needle:
            rows = [row for row in rows if needle in str(row.get("title", "")).casefold()
                    or needle in str(row.get("username", "")).casefold()]
        total = len(rows)
        rows = rows[max(0, offset):max(0, offset) + max(1, min(limit, 100000))]
        errors = self.errors(run_id)
        return {"run_id": run_id, "total": total, "rows": rows, "errors": errors}

    def close(self):
        self.connection.close()
