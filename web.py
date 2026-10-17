import hashlib
import hmac
import io
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory, session

from app.client import discover_sessions
from app.config import DATABASE_FILE, DICTIONARY, EXCEL_FILE, SESSIONS_DIR
from app.database import Database

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("WEB_SECRET_KEY") or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=64 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("WEB_HTTPS", "0") == "1")
WEB_USERNAME = os.getenv("WEB_USERNAME", "admin")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "change-me")
process = None
process_state = {}
login_attempts = {}
LOGS_DIR = DATABASE_FILE.parent / "logs"


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify(error="authentication_required"), 401
        return view(*args, **kwargs)
    return wrapped


def require_csrf():
    supplied = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf", "")
    if not hmac.compare_digest(session.get("csrf", ""), supplied):
        abort(400, "Invalid CSRF token")


def _rate_limited(ip):
    now = time.time()
    login_attempts[ip] = [item for item in login_attempts.get(ip, []) if now - item < 300]
    return len(login_attempts[ip]) >= 5


@app.get("/api/session")
def api_session():
    return jsonify(authenticated=bool(session.get("authenticated")), csrf=csrf_token(),
                   username=WEB_USERNAME if session.get("authenticated") else None)


@app.post("/api/login")
def api_login():
    require_csrf()
    ip = request.remote_addr or "local"
    if _rate_limited(ip):
        return jsonify(error="Слишком много попыток. Попробуйте через 5 минут."), 429
    payload = request.get_json(silent=True) or {}
    valid = (hmac.compare_digest(str(payload.get("username", "")), WEB_USERNAME)
             and hmac.compare_digest(str(payload.get("password", "")), WEB_PASSWORD))
    if not valid:
        login_attempts.setdefault(ip, []).append(time.time())
        return jsonify(error="Неверный логин или пароль."), 401
    login_attempts.pop(ip, None)
    session.clear()
    session["authenticated"] = True
    return jsonify(ok=True, csrf=csrf_token(), username=WEB_USERNAME)


@app.post("/api/logout")
@api_login_required
def api_logout():
    require_csrf()
    session.clear()
    return jsonify(ok=True)


def _progress():
    if not DATABASE_FILE.exists():
        return {"status": "idle", "total": 0, "completed": 0}
    db = Database(DATABASE_FILE)
    value = db.latest_progress()
    db.close()
    return value


@app.get("/api/dashboard")
@api_login_required
def dashboard():
    exit_code = process.poll() if process else None
    value = _progress()
    value.update(sessions=len(discover_sessions()), running=bool(process and process.poll() is None),
                 report=EXCEL_FILE.exists(), database=DATABASE_FILE.exists(),
                 keywords=DICTIONARY.stat().st_size if DICTIONARY.exists() else 0,
                 insecure_defaults=WEB_PASSWORD == "change-me", exit_code=exit_code,
                 process=process_state)
    return jsonify(value)


@app.get("/api/runs")
@api_login_required
def runs():
    if not DATABASE_FILE.exists():
        return jsonify(runs=[])
    db = Database(DATABASE_FILE)
    values = db.run_history()
    db.close()
    return jsonify(runs=values)


@app.get("/api/accounts")
@api_login_required
def accounts():
    values = [{"name": path.name, "size": path.stat().st_size,
               "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
              for path in discover_sessions()]
    return jsonify(accounts=values)


@app.delete("/api/accounts/<name>")
@api_login_required
def delete_account(name):
    require_csrf()
    if process and process.poll() is None:
        return jsonify(error="Нельзя удалить аккаунт во время сканирования."), 409
    target = next((path for path in discover_sessions() if path.name == name), None)
    if not target:
        return jsonify(error="Аккаунт не найден."), 404
    target.unlink()
    return jsonify(ok=True)


def _log_files():
    if not LOGS_DIR.exists():
        return []
    return sorted(LOGS_DIR.glob("run-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)


@app.get("/api/logs")
@api_login_required
def logs():
    files = _log_files()
    selected = request.args.get("name") or (files[0].name if files else "")
    target = next((path for path in files if path.name == selected), None)
    content = ""
    if target:
        with target.open("rb") as stream:
            stream.seek(max(0, target.stat().st_size - 200_000))
            content = stream.read().decode("utf-8", errors="replace")
    return jsonify(files=[{"name": path.name, "size": path.stat().st_size,
                           "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
                          for path in files], selected=selected, content=content)


@app.get("/download/logs/<name>")
@api_login_required
def download_log(name):
    target = next((path for path in _log_files() if path.name == name), None)
    return send_file(target, as_attachment=True) if target else ("Лог не найден", 404)


SQLITE_HEADER = b"SQLite format 3\x00"
MAX_ARCHIVE_ENTRIES = 50
MAX_SESSION_SIZE = 16 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED = 64 * 1024 * 1024
MAX_REMOTE_ARCHIVE_SIZE = 32 * 1024 * 1024
MAX_REMOTE_URLS = 20
REMOTE_SESSION_HOSTS = {"2zie.com", "www.2zie.com"}


def _validated_session(content, source):
    if len(content) > MAX_SESSION_SIZE:
        raise ValueError(f"{source}: файл сессии слишком большой")
    if not content.startswith(SQLITE_HEADER):
        raise ValueError(f"{source}: это не Telethon/SQLite .session")
    return hashlib.sha256(content).hexdigest()[:24], content


def _sessions_from_zip(item):
    try:
        with zipfile.ZipFile(item.stream) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError(f"{item.filename}: слишком много файлов в архиве")
            if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_UNCOMPRESSED:
                raise ValueError(f"{item.filename}: архив слишком большой после распаковки")
            sessions = []
            for entry in entries:
                if entry.is_dir() or Path(entry.filename).suffix.lower() != ".session":
                    continue
                if entry.file_size > MAX_SESSION_SIZE:
                    raise ValueError(f"{item.filename}: файл сессии слишком большой")
                sessions.append(_validated_session(archive.read(entry), f"{item.filename}/{entry.filename}"))
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"{item.filename}: повреждённый или защищённый ZIP-архив") from exc
    if not sessions:
        raise ValueError(f"{item.filename}: внутри нет файла .session")
    return sessions


def _remote_archive(url):
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in REMOTE_SESSION_HOSTS:
        raise ValueError("Ссылки на сессии разрешены только с https://2zie.com")
    clean_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
    if not parsed.path.rstrip("/").endswith("/download"):
        clean_url = clean_url.rstrip("/") + "/download"

    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urllib.parse.urlsplit(newurl)
            if target.scheme != "https" or target.hostname not in REMOTE_SESSION_HOSTS:
                raise ValueError("Ссылка перенаправляет на запрещённый адрес")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    request_url = urllib.request.Request(clean_url, headers={
        "User-Agent": "Mozilla/5.0 TelegramSessionImporter/1.0",
        "Accept": "application/zip,application/octet-stream,*/*",
    })
    try:
        with urllib.request.build_opener(SafeRedirect()).open(request_url, timeout=30) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_REMOTE_ARCHIVE_SIZE:
                raise ValueError("Удалённый ZIP слишком большой")
            content = response.read(MAX_REMOTE_ARCHIVE_SIZE + 1)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(("Ссылка", "Удалённый")):
            raise
        raise ValueError("Не удалось скачать ZIP по ссылке") from exc
    if len(content) > MAX_REMOTE_ARCHIVE_SIZE:
        raise ValueError("Удалённый ZIP слишком большой")
    filename = Path(parsed.path).name or "account.zip"
    return type("RemoteUpload", (), {"filename": filename, "stream": io.BytesIO(content)})()


def _save_sessions(files, urls=()):
    valid = {}
    remote_urls = [url.strip() for url in urls if url.strip()]
    if len(remote_urls) > MAX_REMOTE_URLS:
        raise ValueError(f"За один запуск можно загрузить не более {MAX_REMOTE_URLS} ссылок")
    items = list(files) + [_remote_archive(url) for url in remote_urls]
    for item in items:
        if not item.filename:
            continue
        suffix = Path(item.filename).suffix.lower()
        if suffix == ".zip":
            for digest, content in _sessions_from_zip(item):
                valid[digest] = content
        elif suffix == ".session":
            content = item.stream.read(MAX_SESSION_SIZE + 1)
            digest, content = _validated_session(content, item.filename)
            valid[digest] = content
        else:
            raise ValueError(f"{item.filename}: поддерживаются только .session и .zip")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    added = 0
    for digest, content in valid.items():
        destination = SESSIONS_DIR / f"session_{digest}.session"
        if not destination.exists():
            destination.write_bytes(content)
            added += 1
    return added


@app.post("/api/start")
@api_login_required
def start():
    global process, process_state
    require_csrf()
    if process and process.poll() is None:
        return jsonify(error="Сканирование уже выполняется."), 409
    try:
        uploaded_count = _save_sessions(
            request.files.getlist("sessions"), request.form.get("session_urls", "").splitlines()
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    keywords = request.files.get("keywords")
    if keywords and keywords.filename:
        if Path(keywords.filename).suffix.lower() != ".txt":
            return jsonify(error="Ключевые слова нужно загружать в .txt."), 400
        DICTIONARY.parent.mkdir(parents=True, exist_ok=True)
        keywords.save(DICTIONARY)
    if not discover_sessions():
        return jsonify(error="Загрузите хотя бы одну авторизованную .session или ZIP с сессией."), 400
    cmd = [sys.executable, str(BASE_DIR / "run.py"), "--min-users", request.form.get("min_users", "1"),
           "--min-messages", request.form.get("min_messages", "0"), "--exclude", request.form.get("exclude", "")]
    language = request.form.get("language", "")
    if language in {"ru", "uk", "en"}:
        cmd += ["--language", language]
    for flag in ("active_only", "public_only", "writable_only"):
        if request.form.get(flag) in {"true", "on", "1"}:
            cmd.append("--" + flag.replace("_", "-"))
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = LOGS_DIR / f"run-{stamp}.log"
    log_stream = log_path.open("ab", buffering=0)
    process = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=log_stream, stderr=subprocess.STDOUT)
    log_stream.close()
    process_state = {"pid": process.pid, "started_at": datetime.now(timezone.utc).isoformat(),
                     "log": log_path.name}
    return jsonify(ok=True, uploaded=uploaded_count, log=log_path.name)


@app.post("/api/stop")
@api_login_required
def stop():
    global process
    require_csrf()
    if not process or process.poll() is not None:
        return jsonify(error="Активного запуска нет."), 409
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    return jsonify(ok=True, exit_code=process.poll())


@app.delete("/api/sessions")
@api_login_required
def clear_sessions():
    require_csrf()
    if process and process.poll() is None:
        return jsonify(error="Нельзя удалить сессии во время сканирования."), 409
    paths = discover_sessions()
    for path in paths:
        path.unlink()
    return jsonify(ok=True, removed=len(paths))


@app.get("/download/report")
@api_login_required
def download_report():
    return send_file(EXCEL_FILE, as_attachment=True) if EXCEL_FILE.exists() else ("Отчёт ещё не создан", 404)


@app.get("/download/database")
@api_login_required
def download_database():
    return send_file(DATABASE_FILE, as_attachment=True) if DATABASE_FILE.exists() else ("История ещё не создана", 404)


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/assets/<path:filename>")
def frontend_assets(filename):
    return send_from_directory(FRONTEND_DIST / "assets", filename)


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    if path.startswith("api/"):
        return jsonify(error="not_found"), 404
    if path and (FRONTEND_DIST / path).is_file():
        return send_from_directory(FRONTEND_DIST, path)
    if (FRONTEND_DIST / "index.html").is_file():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return jsonify(error="frontend_not_built", hint="cd frontend && npm install && npm run build"), 503


if __name__ == "__main__":
    app.run(host=os.getenv("WEB_HOST", "127.0.0.1"), port=int(os.getenv("WEB_PORT", "8080")), debug=False)
