import hashlib
import hmac
import os
import secrets
import subprocess
import sys
import time
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
login_attempts = {}


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
    value = _progress()
    value.update(sessions=len(discover_sessions()), running=bool(process and process.poll() is None),
                 report=EXCEL_FILE.exists(), database=DATABASE_FILE.exists(),
                 keywords=DICTIONARY.stat().st_size if DICTIONARY.exists() else 0,
                 insecure_defaults=WEB_PASSWORD == "change-me")
    return jsonify(value)


def _save_sessions(files):
    valid = []
    for item in files:
        if not item.filename:
            continue
        header = item.stream.read(16)
        item.stream.seek(0)
        if header != b"SQLite format 3\x00":
            raise ValueError(f"{item.filename}: это не Telethon/SQLite .session")
        content = item.stream.read()
        item.stream.seek(0)
        valid.append((item, hashlib.sha256(content).hexdigest()[:24]))
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    for item, digest in valid:
        item.save(SESSIONS_DIR / f"session_{digest}.session")
    return len(valid)


@app.post("/api/start")
@api_login_required
def start():
    global process
    require_csrf()
    if process and process.poll() is None:
        return jsonify(error="Сканирование уже выполняется."), 409
    try:
        uploaded_count = _save_sessions(request.files.getlist("sessions"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    keywords = request.files.get("keywords")
    if keywords and keywords.filename:
        if Path(keywords.filename).suffix.lower() != ".txt":
            return jsonify(error="Ключевые слова нужно загружать в .txt."), 400
        DICTIONARY.parent.mkdir(parents=True, exist_ok=True)
        keywords.save(DICTIONARY)
    if not discover_sessions():
        return jsonify(error="Загрузите хотя бы одну авторизованную .session."), 400
    cmd = [sys.executable, str(BASE_DIR / "run.py"), "--min-users", request.form.get("min_users", "1"),
           "--min-messages", request.form.get("min_messages", "0"), "--exclude", request.form.get("exclude", "")]
    language = request.form.get("language", "")
    if language in {"ru", "uk", "en"}:
        cmd += ["--language", language]
    for flag in ("active_only", "public_only", "writable_only"):
        if request.form.get(flag) in {"true", "on", "1"}:
            cmd.append("--" + flag.replace("_", "-"))
    process = subprocess.Popen(cmd, cwd=BASE_DIR)
    return jsonify(ok=True, uploaded=uploaded_count)


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
