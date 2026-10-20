import asyncio
import hashlib
import json
import logging

from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetFullChannelRequest

from app.analytics import collect_analytics
from app.client import create_clients
from app.config import (COOLDOWN_FILE, DATABASE_FILE, LONG_ACCOUNT_REST_SECONDS,
                        LONG_FLOODWAIT_THRESHOLD, REQUEST_DELAY, REQUEST_RETRIES)
from app.database import Database
from app.errors import classify_error
from app.export import save_to_excel
from app.models import ChatResult, ErrorKind, FilterConfig, ScanError
from app.progress import update_progress
from app.rate_limit import AccountCooldownError, CooldownStore, TelegramLimiter
from app.search import search_groups
from app.utils import load_keywords

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _can_write(client, entity, limiter) -> bool:
    try:
        permissions = await limiter.call(lambda: client.get_permissions(entity, "me"))
    except UserNotParticipantError:
        # Public groups can be inspected without joining. In that case Telegram
        # cannot return participant permissions, which simply means we cannot write.
        return False
    return bool(getattr(permissions, "send_messages", False))


def _fingerprint(filters: FilterConfig) -> str:
    value = {"keywords": load_keywords(), "filters": filters.__dict__ if hasattr(filters, "__dict__") else {
        name: getattr(filters, name) for name in filters.__dataclass_fields__
    }}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _discussion_url(full_chat) -> str:
    linked_id = getattr(full_chat.full_chat, "linked_chat_id", None)
    linked = next((item for item in full_chat.chats if item.id == linked_id), None)
    return f"https://t.me/{linked.username}" if linked and linked.username else ""


def _matches(result: ChatResult, filters: FilterConfig) -> bool:
    title = result.title.casefold()
    if any(word.casefold() in title for word in filters.excluded_words if word.strip()):
        return False
    if (result.participants or 0) < filters.min_users:
        return False
    if filters.active_only and not result.last_activity:
        return False
    if filters.public_only and not result.username:
        return False
    if filters.language and result.language != filters.language:
        return False
    if filters.writable_only and not result.can_write:
        return False
    return result.messages_24h >= filters.min_messages_24h


async def check_voice_chats(filters: FilterConfig | None = None):
    filters = filters or FilterConfig()
    db = Database(DATABASE_FILE)
    run_id, resumed = db.start_or_resume(_fingerprint(filters))
    clients, uploaded_sessions = create_clients()
    cooldown_store = CooldownStore(COOLDOWN_FILE)
    logger.info("Запуск #%s%s", run_id, " (возобновлён)" if resumed else "")
    update_progress(
        run_id=run_id, phase="connecting", phase_label="Подключение аккаунтов",
        completed=0, total=len(clients), remaining=len(clients), current="", found=0, error="",
    )

    active_clients = []
    try:
        async def prepare_client(index, client):
            name = getattr(client.session, "filename", f"account-{index}")
            logger.info("Проверка аккаунта %s/%s: %s", index, len(clients), name)
            update_progress(current=f"Проверка аккаунта {index} из {len(clients)}")
            remaining = cooldown_store.remaining(str(name))
            if remaining:
                logger.warning("Аккаунт %s отдыхает ещё %s сек. и пропущен", index, remaining)
                return None
            try:
                if uploaded_sessions:
                    await asyncio.wait_for(client.connect(), timeout=20)
                    if not await asyncio.wait_for(client.is_user_authorized(), timeout=15):
                        logger.error("Сессия %s не авторизована и пропущена", name)
                        await asyncio.wait_for(client.disconnect(), timeout=5)
                        return None
                else:
                    await asyncio.wait_for(client.start(), timeout=60)
                logger.info("Аккаунт %s готов", index)
                return client
            except asyncio.TimeoutError:
                logger.error("Таймаут подключения аккаунта %s; сессия пропущена", index)
            except Exception as exc:
                logger.error("Ошибка подключения аккаунта %s: %s", index, exc)
            try:
                await asyncio.wait_for(client.disconnect(), timeout=5)
            except Exception:
                pass
            return None

        prepared = await asyncio.gather(*(prepare_client(i, client) for i, client in enumerate(clients, 1)))
        active_clients.extend(client for client in prepared if client is not None)

        if not active_clients:
            raise RuntimeError("Нет ни одной авторизованной Telegram-сессии")

        limiters = [TelegramLimiter(
            1, REQUEST_DELAY, REQUEST_RETRIES, cooldown_store,
            str(getattr(client.session, "filename", f"account-{index + 1}")),
            LONG_FLOODWAIT_THRESHOLD, LONG_ACCOUNT_REST_SECONDS,
        ) for index, client in enumerate(active_clients)]
        logger.info("Активных сессий: %s", len(active_clients))
        keyword_count = len(load_keywords())
        update_progress(
            phase="searching", phase_label="Поиск сообществ", active_sessions=len(active_clients),
            completed=0, total=keyword_count, remaining=keyword_count,
            current="Подготовка поиска", found=0, error="",
        )
        groups = await search_groups(active_clients, limiters, db, run_id)
        db.set_total(run_id, len(groups))
        db.clear_retryable_errors(run_id)
        processed = db.processed_ids(run_id)
        completed_count = len(processed)
        update_progress(phase="processing", phase_label="Анализ сообществ", total=len(groups), completed=completed_count, remaining=max(0, len(groups)-completed_count), current="", found=len(groups), error="")

        async def process(chat, client, limiter):
            nonlocal completed_count
            if chat.id in processed:
                return True
            update_progress(current=chat.title)
            try:
                if chat.username:
                    entity = await limiter.call(lambda: client.get_entity(chat.username))
                else:
                    entity = await limiter.call(lambda: client.get_input_entity(chat.id))
                full = await limiter.call(lambda: client(GetFullChannelRequest(entity)))
                is_channel = bool(getattr(chat, "broadcast", False))
                can_write = False
                if not is_channel:
                    can_write = await _can_write(client, entity, limiter)
                analytics = await limiter.call(lambda: collect_analytics(client, entity))
                participants = getattr(full.full_chat, "participants_count", None)
                previous = db.previous_participants(chat.id, run_id)
                voice = getattr(full.full_chat, "call", None) is not None
                result = ChatResult(
                    chat_id=chat.id, title=chat.title, username=chat.username,
                    chat_type="channel" if is_channel else "chat", participants=participants,
                    can_write=can_write, voice_active=voice,
                    voice_type="stream" if voice and is_channel else "voice" if voice else "",
                    online_users=getattr(full.full_chat, "online_count", None),
                    audience_growth=(participants - previous) if participants is not None and previous is not None else None,
                    discussion_url=_discussion_url(full), **analytics,
                )
                result.score = round(
                    result.messages_24h * 2 + result.active_authors + result.engagement_rate * 10
                    + max(0, result.audience_growth or 0) * 0.1, 2
                )
                if _matches(result, filters):
                    db.save_result(run_id, result)
                else:
                    db.save_error(run_id, ScanError(chat.id, chat.title, ErrorKind.FILTERED, "Не прошёл фильтры"))
                logger.info("Готово: %s", chat.title)
            except AccountCooldownError:
                raise
            except Exception as exc:
                kind = classify_error(exc)
                db.save_error(run_id, ScanError(chat.id, chat.title, kind, str(exc)))
                logger.exception("Ошибка: %s", chat.title)
            finally:
                pass
            completed_count += 1
            processed.add(chat.id)
            update_progress(completed=completed_count, remaining=max(0, len(groups)-completed_count), current=chat.title)
            return True

        pending = [chat for chat in groups if chat.id not in processed]
        public_queue = asyncio.Queue()
        private_pending = []
        for chat in pending:
            (public_queue.put_nowait(chat) if chat.username else private_pending.append(chat))

        cooldowns = []

        async def worker(worker_index):
            client, limiter = active_clients[worker_index], limiters[worker_index]
            while True:
                try:
                    chat = public_queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await process(chat, client, limiter)
                except AccountCooldownError as exc:
                    public_queue.put_nowait(chat)
                    cooldowns.append(exc.seconds)
                    logger.warning(
                        "Аккаунт %s в cooldown на %s сек.; задача вернута в очередь",
                        worker_index + 1, exc.seconds,
                    )
                    return
                finally:
                    public_queue.task_done()

        await asyncio.gather(*(worker(i) for i in range(len(active_clients))))

        if public_queue.qsize():
            wait = min(cooldowns) if cooldowns else min(
                (item.cooldown_remaining for item in limiters if item.cooldown_remaining), default=0
            )
            db.pause(run_id)
            message = f"Все Telegram-аккаунты ограничены. Повторите запуск через {wait} сек."
            logger.warning("%s В очереди осталось: %s", message, public_queue.qsize())
            update_progress(
                phase="paused", phase_label="Ожидание Telegram", error=message,
                remaining=max(0, len(groups) - completed_count), cooldown_seconds=wait,
            )
            return

        for chat in private_pending:
            try:
                await process(chat, active_clients[0], limiters[0])
            except AccountCooldownError as exc:
                db.pause(run_id)
                message = f"Основной Telegram-аккаунт ограничен ещё на {exc.seconds} сек."
                logger.warning("%s Очередь сохранена.", message)
                update_progress(
                    phase="paused", phase_label="Ожидание Telegram", error=message,
                    remaining=max(0, len(groups) - completed_count), cooldown_seconds=exc.seconds,
                )
                return

        update_progress(phase="exporting", phase_label="Формирование Excel", current="")
        results, errors = db.results(run_id), db.errors(run_id)
        save_to_excel(results, errors=errors, run_id=run_id)
        db.finish(run_id)
        logger.info("Завершено: %s результа(ов), %s ошибка(ок)", len(results), len(errors))
        update_progress(phase="completed", phase_label="Завершено", completed=len(groups), total=len(groups), remaining=0, current="", error="")
    except AccountCooldownError as exc:
        db.pause(run_id)
        message = f"Telegram ограничил все аккаунты. Повторите запуск через {exc.seconds} сек."
        logger.warning(message)
        update_progress(
            phase="paused", phase_label="Ожидание Telegram", error=message,
            cooldown_seconds=exc.seconds,
        )
    finally:
        await asyncio.gather(*(item.disconnect() for item in active_clients), return_exceptions=True)
        db.close()
