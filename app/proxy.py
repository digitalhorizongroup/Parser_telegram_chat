import json
import os
from pathlib import Path

import socks


class ProxyConfig:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self, include_password: bool = False) -> dict | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return None
        if not isinstance(value, dict) or not value.get("host") or not value.get("port"):
            return None
        result = dict(value)
        result["enabled"] = True
        result["has_password"] = bool(result.get("password"))
        if not include_password:
            result.pop("password", None)
        return result

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
        previous = self.load(include_password=True) or {}
        password = str(value.get("password", ""))
        if not password and value.get("keep_password"):
            password = str(previous.get("password", ""))
        config = {"type": proxy_type, "host": host, "port": port,
                  "username": str(value.get("username", "")).strip(), "password": password}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        return self.load() or {}

    def delete(self):
        self.path.unlink(missing_ok=True)

    def telethon_proxy(self):
        value = self.load(include_password=True)
        if not value:
            return None
        kind = socks.SOCKS5 if value["type"] == "socks5" else socks.HTTP
        return (kind, value["host"], value["port"], True,
                value.get("username") or None, value.get("password") or None)

    def test(self, timeout: int = 8):
        value = self.load(include_password=True)
        if not value:
            raise ValueError("Сначала сохраните настройки прокси")
        connection = socks.create_connection(
            ("149.154.167.51", 443), timeout=timeout,
            proxy_type=socks.SOCKS5 if value["type"] == "socks5" else socks.HTTP,
            proxy_addr=value["host"], proxy_port=value["port"],
            proxy_username=value.get("username") or None,
            proxy_password=value.get("password") or None,
        )
        connection.close()
