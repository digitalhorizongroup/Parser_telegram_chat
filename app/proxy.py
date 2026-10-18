from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

import socks


class ProxyConfig:
    """Persistent proxy pool with stable per-session distribution."""
    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> list[dict]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return []
        if isinstance(value, dict) and value.get("host"):
            legacy_id = hashlib.sha256(f"{value.get('host')}:{value.get('port')}".encode()).hexdigest()[:12]
            value = {"proxies": [{"id": legacy_id, **value}]}
        items = value.get("proxies", []) if isinstance(value, dict) else []
        return [item for item in items if isinstance(item, dict) and item.get("host") and item.get("port")]

    def list(self, include_password: bool = False) -> list[dict]:
        result = []
        for item in self._read():
            value = dict(item)
            value["enabled"] = True
            value["has_password"] = bool(value.get("password"))
            if not include_password:
                value.pop("password", None)
            result.append(value)
        return result

    def load(self, include_password: bool = False):
        items = self.list(include_password)
        return items[0] if items else None

    def save(self, value: dict) -> dict:
        proxy_type = str(value.get("type", "socks5")).lower()
        if proxy_type not in {"socks5", "http"}:
            raise ValueError("Поддерживаются только SOCKS5 и HTTP")
        host = str(value.get("host", "")).strip()
        if not host or len(host) > 255:
            raise ValueError("Укажите корректный адрес прокси")
        try:
            port = int(value.get("port", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Порт прокси должен быть числом") from exc
        if not 1 <= port <= 65535:
            raise ValueError("Порт прокси должен быть от 1 до 65535")
        items = self._read()
        proxy_id = str(value.get("id") or secrets.token_hex(6))
        previous = next((item for item in items if item.get("id") == proxy_id), {})
        password = str(value.get("password", "")) or (str(previous.get("password", "")) if value.get("keep_password") else "")
        config = {"id": proxy_id, "type": proxy_type, "host": host, "port": port,
                  "username": str(value.get("username", "")).strip(), "password": password}
        items = [config if item.get("id") == proxy_id else item for item in items]
        if not previous:
            items.append(config)
        self._write(items)
        return next(item for item in self.list() if item["id"] == proxy_id)

    def _write(self, items: list[dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({"proxies": items}, ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def delete(self, proxy_id: str | None = None):
        if proxy_id is None:
            self.path.unlink(missing_ok=True)
            return
        self._write([item for item in self._read() if item.get("id") != proxy_id])

    def assigned(self, account: str, include_password: bool = False):
        items = self.list(include_password)
        if not items:
            return None
        index = int(hashlib.sha256(str(account).encode()).hexdigest(), 16) % len(items)
        return items[index]

    def telethon_proxy(self, account: str = ""):
        value = self.assigned(account, include_password=True)
        if not value:
            return None
        kind = socks.SOCKS5 if value["type"] == "socks5" else socks.HTTP
        return (kind, value["host"], value["port"], True,
                value.get("username") or None, value.get("password") or None)

    def test(self, proxy_id: str, timeout: int = 8):
        value = next((item for item in self.list(True) if item.get("id") == proxy_id), None)
        if not value:
            raise ValueError("Прокси не найден")
        connection = socks.create_connection(
            ("149.154.167.51", 443), timeout=timeout,
            proxy_type=socks.SOCKS5 if value["type"] == "socks5" else socks.HTTP,
            proxy_addr=value["host"], proxy_port=value["port"],
            proxy_username=value.get("username") or None,
            proxy_password=value.get("password") or None,
        )
        connection.close()
