import asyncio
import logging
import random
import time
import json
import threading
from pathlib import Path
from collections.abc import Awaitable, Callable

from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)


class CooldownStore:
    """Persistent per-session cooldowns, surviving process and container restarts."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, OSError, ValueError):
            return {}

    def remaining(self, account: str) -> int:
        with self._lock:
            values = self._read()
            remaining = max(0, int(float(values.get(account, 0)) - time.time()))
            if not remaining and account in values:
                values.pop(account, None)
                self._write(values)
            return remaining

    def block(self, account: str, seconds: int) -> int:
        with self._lock:
            values = self._read()
            expires_at = max(float(values.get(account, 0)), time.time() + max(1, seconds))
            values[account] = expires_at
            self._write(values)
            return max(1, int(expires_at - time.time()))

    def _write(self, values: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)


class AccountCooldownError(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Аккаунт ограничен Telegram ещё на {seconds} сек.")


class TelegramLimiter:
    def __init__(self, concurrency: int = 3, delay: float = 0.35, retries: int = 4,
                 cooldown_store: CooldownStore | None = None, account: str = "",
                 long_threshold: int = 3600, long_rest: int = 172800):
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.delay = max(0.0, delay)
        self.retries = max(0, retries)
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._blocked_until = 0.0
        self.cooldown_store = cooldown_store
        self.account = account
        self.long_threshold = max(1, long_threshold)
        self.long_rest = max(1, long_rest)

    @property
    def cooldown_remaining(self) -> int:
        memory = max(0, int(self._blocked_until - time.monotonic()))
        persisted = self.cooldown_store.remaining(self.account) if self.cooldown_store and self.account else 0
        return max(memory, persisted)

    async def _pace(self):
        async with self._lock:
            wait = self.delay - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def call(self, operation: Callable[[], Awaitable]):
        remaining = self.cooldown_remaining
        if remaining > 0:
            raise AccountCooldownError(remaining)
        for attempt in range(self.retries + 1):
            try:
                async with self.semaphore:
                    await self._pace()
                    return await operation()
            except FloodWaitError as exc:
                wait = max(1, exc.seconds) + random.uniform(0, 1)
                if wait > 120:
                    rest = max(exc.seconds, self.long_rest) if exc.seconds >= self.long_threshold else exc.seconds
                    self._blocked_until = time.monotonic() + rest
                    if self.cooldown_store and self.account:
                        rest = self.cooldown_store.block(self.account, rest)
                    logger.error(
                        "Telegram FloodWait %s сек.; аккаунт отправлен отдыхать на %s сек. (до двух суток минимум для больших лимитов)",
                        exc.seconds, rest,
                    )
                    raise AccountCooldownError(rest) from exc
                logger.warning("Telegram FloodWait: ожидание %.1f с", wait)
                await asyncio.sleep(wait)
            except (ConnectionError, TimeoutError):
                if attempt >= self.retries:
                    raise
                wait = min(30, 2 ** attempt) + random.uniform(0, 0.5)
                logger.warning("Повтор Telegram-запроса через %.1f с", wait)
                await asyncio.sleep(wait)
        raise RuntimeError("Исчерпаны повторные попытки")
