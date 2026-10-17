import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)


class AccountCooldownError(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Аккаунт ограничен Telegram ещё на {seconds} сек.")


class TelegramLimiter:
    def __init__(self, concurrency: int = 3, delay: float = 0.35, retries: int = 4):
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.delay = max(0.0, delay)
        self.retries = max(0, retries)
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self._blocked_until = 0.0

    @property
    def cooldown_remaining(self) -> int:
        return max(0, int(self._blocked_until - time.monotonic()))

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
                    self._blocked_until = time.monotonic() + wait
                    logger.error("Telegram FloodWait %s сек.; аккаунт переведён в cooldown без ожидания", exc.seconds)
                    raise AccountCooldownError(exc.seconds) from exc
                logger.warning("Telegram FloodWait: ожидание %.1f с", wait)
                await asyncio.sleep(wait)
            except (ConnectionError, TimeoutError):
                if attempt >= self.retries:
                    raise
                wait = min(30, 2 ** attempt) + random.uniform(0, 0.5)
                logger.warning("Повтор Telegram-запроса через %.1f с", wait)
                await asyncio.sleep(wait)
        raise RuntimeError("Исчерпаны повторные попытки")
