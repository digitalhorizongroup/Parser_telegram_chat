import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.models import ChatResult, ScanError, SearchCandidate


class Database:
    GRID_FIELDS = (
        ("chat_id", "ID", "number"), ("status", "Статус", "text"),
        ("title", "Сообщество", "text"), ("username", "Username", "text"),
        ("chat_type", "Тип", "text"), ("participants", "Участники", "number"),
        ("messages_24h", "Сообщения 24ч", "number"), ("messages_7d", "Сообщения 7д", "number"),
        ("messages_30d", "Сообщения 30д", "number"), ("average_7d", "Среднее 7д", "number"),
        ("average_30d", "Среднее 30д", "number"), ("active_authors", "Активные авторы", "number"),
        ("views", "Просмотры", "number"), ("reactions", "Реакции", "number"),
        ("engagement_rate", "ER", "number"), ("audience_growth", "Рост", "number"),
        ("online_users", "Онлайн", "number"), ("can_write", "Можно писать", "boolean"),
        ("voice_active", "Voice", "boolean"), ("last_activity", "Последняя активность", "date"),
        ("discussion_url", "Обсуждение", "text"), ("language", "Язык", "text"),
        ("score", "Рейтинг", "number"), ("collected_at", "Собрано", "date"),
    )
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
            CREATE TABLE IF NOT EXISTS candidates (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                chat_id INTEGER NOT NULL, payload TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                PRIMARY KEY (run_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS search_keywords (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                keyword TEXT NOT NULL, completed_at TEXT NOT NULL,
                PRIMARY KEY (run_id, keyword)
            );
            CREATE INDEX IF NOT EXISTS idx_results_chat ON results(chat_id);
            CREATE INDEX IF NOT EXISTS idx_runs_fingerprint ON runs(fingerprint, status);
            CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
        """)
        self.connection.commit()

    def start_or_resume(self, fingerprint: str) -> tuple[int, bool]:
        row = self.connection.execute(
            "SELECT id FROM runs WHERE fingerprint=? AND status IN ('running','paused') ORDER BY id DESC LIMIT 1",
            (fingerprint,),
        ).fetchone()
        if row:
            self.connection.execute("UPDATE runs SET status='running' WHERE id=?", (row["id"],))
            self.connection.commit()
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

    def save_candidate(self, run_id: int, candidate: SearchCandidate):
        self.connection.execute(
            "INSERT OR REPLACE INTO candidates(run_id,chat_id,payload,discovered_at) VALUES(?,?,?,?)",
            (run_id, candidate.chat_id, json.dumps({
                "chat_id": candidate.chat_id, "title": candidate.title,
                "username": candidate.username, "chat_type": candidate.chat_type,
                "participants": candidate.participants, "access_hash": candidate.access_hash,
            }, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def candidates(self, run_id: int) -> list[SearchCandidate]:
        rows = self.connection.execute(
            "SELECT payload FROM candidates WHERE run_id=? ORDER BY rowid", (run_id,)
        )
        return [SearchCandidate(**json.loads(row[0])) for row in rows]

    def completed_keywords(self, run_id: int) -> set[str]:
        rows = self.connection.execute("SELECT keyword FROM search_keywords WHERE run_id=?", (run_id,))
        return {row[0] for row in rows}

    def mark_keyword_complete(self, run_id: int, keyword: str):
        self.connection.execute(
            "INSERT OR REPLACE INTO search_keywords(run_id,keyword,completed_at) VALUES(?,?,?)",
            (run_id, keyword, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

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
            """UPDATE runs SET completed=(
                SELECT COUNT(*) FROM (
                    SELECT chat_id FROM results WHERE run_id=?
                    UNION
                    SELECT chat_id FROM errors WHERE run_id=? AND chat_id IS NOT NULL
                )
            ) WHERE id=?""",
            (run_id, run_id, run_id),
        )
        self.connection.commit()

    def clear_retryable_errors(self, run_id: int):
        self.connection.execute(
            "DELETE FROM errors WHERE run_id=? AND kind IN (?, ?)",
            (run_id, "Лимит Telegram", "Сетевая ошибка"),
        )
        self._update_completed(run_id)

    def pause(self, run_id: int):
        self.connection.execute("UPDATE runs SET status='paused' WHERE id=?", (run_id,))
        self.connection.commit()

    def pause_active_runs(self):
        self.connection.execute("UPDATE runs SET status='paused' WHERE status='running'")
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
                   COUNT(DISTINCT e.id) AS errors_count,
                   (SELECT COUNT(*) FROM candidates c WHERE c.run_id=r.id) AS candidates_count
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
            row = self.connection.execute(
                """SELECT r.id FROM runs r
                   ORDER BY (EXISTS(SELECT 1 FROM results x WHERE x.run_id=r.id)
                          OR EXISTS(SELECT 1 FROM candidates c WHERE c.run_id=r.id)) DESC,
                          r.id DESC LIMIT 1"""
            ).fetchone()
            run_id = row["id"] if row else None
        if run_id is None:
            return {"run_id": None, "total": 0, "rows": [], "errors": []}
        candidates = [json.loads(row[0]) for row in self.connection.execute(
            "SELECT payload FROM candidates WHERE run_id=? ORDER BY rowid", (run_id,)
        )]
        by_id = {}
        for candidate in candidates:
            partial = ChatResult(
                chat_id=candidate["chat_id"], title=candidate["title"],
                username=candidate.get("username"), chat_type=candidate.get("chat_type", "chat"),
                participants=candidate.get("participants"),
            ).to_dict()
            partial["status"] = "found"
            by_id[partial["chat_id"]] = partial
        for row in self.connection.execute(
            "SELECT payload FROM results WHERE run_id=? ORDER BY chat_id", (run_id,)
        ):
            result = json.loads(row[0])
            result["status"] = "processed"
            by_id[result["chat_id"]] = result
        rows = list(by_id.values())
        needle = query.casefold().strip()
        if needle:
            rows = [row for row in rows if needle in str(row.get("title", "")).casefold()
                    or needle in str(row.get("username", "")).casefold()]
        total = len(rows)
        rows = rows[max(0, offset):max(0, offset) + max(1, min(limit, 100000))]
        errors = self.errors(run_id)
        return {"run_id": run_id, "total": total, "rows": rows, "errors": errors}

    def grid_data(self, run_id=None, query="", filters=None, sorts=None, limit=100, offset=0,
                  group_by="", duplicate_field="") -> dict:
        fields = {key: (label, kind) for key, label, kind in self.GRID_FIELDS}
        if run_id is None:
            row = self.connection.execute(
                """SELECT r.id FROM runs r ORDER BY
                   (EXISTS(SELECT 1 FROM results x WHERE x.run_id=r.id) OR
                    EXISTS(SELECT 1 FROM candidates c WHERE c.run_id=r.id)) DESC, r.id DESC LIMIT 1"""
            ).fetchone()
            run_id = row["id"] if row else None
        columns = [{"key": key, "label": label, "type": kind, "editable": False}
                   for key, label, kind in self.GRID_FIELDS]
        if run_id is None:
            return {"run_id": None, "total": 0, "rows": [], "columns": columns,
                    "summary": {}, "groups": [], "duplicates": []}

        def expression(field):
            if field == "chat_id":
                return "chat_id"
            if field == "status":
                return "status"
            return f"json_extract(payload, '$.{field}')"

        where, params = ["run_id=?"], [run_id]
        if query.strip():
            like = f"%{query.strip()}%"
            where.append("(json_extract(payload,'$.title') LIKE ? OR json_extract(payload,'$.username') LIKE ?)")
            params.extend((like, like))
        operations = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
        for item in filters or []:
            field, operation, value = item.get("field"), item.get("op"), item.get("value")
            if field not in fields:
                continue
            expr = expression(field)
            if operation == "contains":
                where.append(f"CAST({expr} AS TEXT) LIKE ?")
                params.append(f"%{value}%")
            elif operation == "empty":
                where.append(f"({expr} IS NULL OR CAST({expr} AS TEXT)='')")
            elif operation in operations:
                where.append(f"{expr} {operations[operation]} ?")
                params.append(value)
        order = []
        for item in sorts or []:
            if item.get("field") in fields:
                order.append(f"{expression(item['field'])} {'DESC' if item.get('dir') == 'desc' else 'ASC'}")
        order_sql = ", ".join(order) if order else "chat_id ASC"
        cte = """WITH grid_rows AS (
            SELECT run_id,chat_id,payload,'processed' status FROM results WHERE run_id=?
            UNION ALL
            SELECT c.run_id,c.chat_id,c.payload,'found' status FROM candidates c
            WHERE c.run_id=? AND NOT EXISTS(
                SELECT 1 FROM results r WHERE r.run_id=c.run_id AND r.chat_id=c.chat_id)
        )"""
        # The run id is repeated inside the CTE and removed from the outer predicate parameters.
        outer_params = params[1:]
        predicate = " AND ".join(where[1:]) or "1=1"
        base_params = [run_id, run_id, *outer_params]
        total = self.connection.execute(
            f"{cte} SELECT COUNT(*) FROM grid_rows WHERE {predicate}", base_params
        ).fetchone()[0]
        page_limit = max(1, min(int(limit), 1000))
        page_offset = max(0, int(offset))
        records = self.connection.execute(
            f"{cte} SELECT chat_id,payload,status FROM grid_rows WHERE {predicate} "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?", [*base_params, page_limit, page_offset]
        )
        rows = []
        for record in records:
            value = json.loads(record["payload"])
            value["chat_id"], value["status"] = record["chat_id"], record["status"]
            rows.append(value)

        numeric = [key for key, _, kind in self.GRID_FIELDS if kind == "number"]
        aggregates = []
        for key in numeric:
            expr = expression(key)
            aggregates.extend((f"SUM({expr}) AS '{key}_sum'", f"AVG({expr}) AS '{key}_avg'"))
        summary_row = self.connection.execute(
            f"{cte} SELECT {','.join(aggregates)} FROM grid_rows WHERE {predicate}", base_params
        ).fetchone()
        summary = {key: {"sum": summary_row[f"{key}_sum"], "avg": summary_row[f"{key}_avg"]}
                   for key in numeric}
        groups = []
        if group_by in fields:
            expr = expression(group_by)
            grouped = self.connection.execute(
                f"{cte} SELECT {expr} value,COUNT(*) count FROM grid_rows WHERE {predicate} "
                f"GROUP BY {expr} ORDER BY count DESC LIMIT 200", base_params
            )
            groups = [dict(row) for row in grouped]
        duplicates = []
        if duplicate_field in fields:
            expr = expression(duplicate_field)
            duplicate_rows = self.connection.execute(
                f"{cte} SELECT {expr} value,COUNT(*) count FROM grid_rows WHERE {predicate} "
                f"AND {expr} IS NOT NULL AND CAST({expr} AS TEXT)!='' GROUP BY {expr} "
                f"HAVING COUNT(*)>1 ORDER BY count DESC LIMIT 200", base_params
            )
            duplicates = [dict(row) for row in duplicate_rows]
        return {"run_id": run_id, "total": total, "rows": rows, "columns": columns,
                "summary": summary, "groups": groups, "duplicates": duplicates,
                "limit": page_limit, "offset": page_offset}

    def close(self):
        self.connection.close()
