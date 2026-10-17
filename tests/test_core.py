import tempfile
import unittest
import io
import sqlite3
import hashlib
import zipfile
from unittest.mock import patch
from pathlib import Path

import openpyxl
from telethon.sessions import SQLiteSession

import app.client as client_module
from app.analytics import detect_language
from app.database import Database
from app.export import save_to_excel
from app.models import ChatResult, ErrorKind, ScanError, SearchCandidate


def compact_session_bytes():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "compact.session"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE sessions (dc_id INTEGER NOT NULL, server_address TEXT NOT NULL, port INTEGER NOT NULL, auth_key BLOB NOT NULL)")
        connection.execute("INSERT INTO sessions VALUES (2, '149.154.167.40', 443, ?)", (b"x" * 256,))
        connection.commit()
        connection.close()
        return path.read_bytes()


class DatabaseTests(unittest.TestCase):
    def test_resume_history_and_growth_source(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            first, resumed = db.start_or_resume("one")
            self.assertFalse(resumed)
            db.save_result(first, ChatResult(1, "Test", participants=100))
            self.assertEqual(db.processed_ids(first), {1})
            same, resumed = db.start_or_resume("one")
            self.assertEqual(same, first)
            self.assertTrue(resumed)
            db.finish(first)
            second, _ = db.start_or_resume("two")
            self.assertEqual(db.previous_participants(1, second), 100)
            db.save_error(second, ScanError(2, "Bad", ErrorKind.PRIVATE, "private"))
            self.assertEqual(db.latest_progress()["completed"], 1)
            db.close()

    def test_retryable_errors_are_not_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            run_id, _ = db.start_or_resume("retry")
            db.save_error(run_id, ScanError(10, "Flooded", ErrorKind.FLOOD_WAIT, "wait"))
            db.save_error(run_id, ScanError(10, "Flooded", ErrorKind.FLOOD_WAIT, "wait again"))
            self.assertEqual(db.latest_progress()["completed"], 1)
            db.pause(run_id)
            resumed_id, resumed = db.start_or_resume("retry")
            self.assertTrue(resumed)
            self.assertEqual(resumed_id, run_id)
            db.clear_retryable_errors(run_id)
            self.assertEqual(db.processed_ids(run_id), set())
            self.assertEqual(db.latest_progress()["completed"], 0)
            db.close()

    def test_candidates_and_keywords_are_persisted_incrementally(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            run_id, _ = db.start_or_resume("stream")
            db.save_candidate(run_id, SearchCandidate(42, "Partial", "partial", "channel", 123, 999))
            db.mark_keyword_complete(run_id, "test keyword")
            db.close()

            reopened = Database(Path(directory) / "test.sqlite3")
            self.assertEqual(reopened.completed_keywords(run_id), {"test keyword"})
            self.assertEqual(reopened.candidates(run_id)[0].title, "Partial")
            table = reopened.result_table(run_id)
            self.assertEqual(table["total"], 1)
            self.assertEqual(table["rows"][0]["status"], "found")
            reopened.save_result(run_id, ChatResult(42, "Partial", "partial", "channel", 123))
            table = reopened.result_table(run_id)
            self.assertEqual(table["total"], 1)
            self.assertEqual(table["rows"][0]["status"], "processed")
            reopened.close()


class ExportTests(unittest.TestCase):
    def test_workbook_structure_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.xlsx"
            item = ChatResult(1, "=unsafe", "example", "chat", 200, messages_24h=8, score=10)
            save_to_excel([item], path, [{"chat_id": 2, "title": "Bad", "kind": "Error", "message": "x", "occurred_at": "now"}], 7)
            workbook = openpyxl.load_workbook(path)
            self.assertEqual(workbook.sheetnames, ["Сводка", "Чаты", "Каналы", "Ошибки"])
            self.assertEqual(workbook["Чаты"]["C2"].hyperlink.target, "https://t.me/example")
            self.assertEqual(workbook["Чаты"]["B2"].value, "'=unsafe")


class AnalyticsTests(unittest.TestCase):
    def test_language_detection(self):
        self.assertEqual(detect_language("Привет это русский текст"), "ru")
        self.assertEqual(detect_language("This is an English text"), "en")
        self.assertEqual(detect_language("Привіт, це український текст"), "uk")


class SessionTests(unittest.TestCase):
    def test_discovers_arbitrarily_named_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            original = client_module.SESSIONS_DIR
            try:
                client_module.SESSIONS_DIR = Path(directory)
                (Path(directory) / "unknown-name.session").touch()
                (Path(directory) / "123.session").touch()
                (Path(directory) / "ignore.txt").touch()
                self.assertEqual(len(client_module.discover_sessions()), 2)
            finally:
                client_module.SESSIONS_DIR = original


class WebTests(unittest.TestCase):
    def test_compact_session_is_upgraded_for_telethon(self):
        import web
        content = compact_session_bytes()
        digest, upgraded = web._validated_session(content, "compact.session")
        self.assertEqual(digest, hashlib.sha256(upgraded).hexdigest()[:24])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "upgraded.session"
            target.write_bytes(upgraded)
            session = SQLiteSession(str(target))
            self.assertEqual(session.dc_id, 2)
            session.close()

    def test_remote_import_rejects_non_allowlisted_hosts(self):
        import web
        with self.assertRaisesRegex(ValueError, "2zie.com"):
            web._remote_archive("https://127.0.0.1/private.zip")

    def test_remote_import_adds_download_path(self):
        import web
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("account.session", compact_session_bytes())
        response = type("Response", (), {
            "headers": {"Content-Length": str(len(archive_data.getvalue()))},
            "read": lambda self, size: archive_data.getvalue(),
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        })()
        opener = type("Opener", (), {"open": lambda self, req, timeout: response})()
        with patch("web.urllib.request.build_opener", return_value=opener):
            item = web._remote_archive("https://2zie.com/file/example/account.zip")
        self.assertEqual(len(web._sessions_from_zip(item)), 1)

    def test_zip_session_import_and_deduplication(self):
        import web
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("account.json", "{}")
            archive.writestr("nested/account.session", compact_session_bytes())
        payload.seek(0)
        with tempfile.TemporaryDirectory() as directory:
            original = web.SESSIONS_DIR
            try:
                web.SESSIONS_DIR = Path(directory)
                files = [type("Upload", (), {"filename": "account.zip", "stream": payload})()]
                self.assertEqual(web._save_sessions(files), 1)
                payload.seek(0)
                self.assertEqual(web._save_sessions(files), 0)
                self.assertEqual(len(list(Path(directory).glob("*.session"))), 1)
            finally:
                web.SESSIONS_DIR = original

    def test_authentication_and_dashboard(self):
        import web
        client = web.app.test_client()
        root = client.get("/")
        self.assertEqual(root.status_code, 200)
        root.close()
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/api/dashboard").status_code, 401)
        state = client.get("/api/session").get_json()
        response = client.post("/api/login", json={
            "username": web.WEB_USERNAME, "password": web.WEB_PASSWORD,
        }, headers={"X-CSRF-Token": state["csrf"]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(client.get("/api/dashboard").status_code, 200)


if __name__ == "__main__":
    unittest.main()
