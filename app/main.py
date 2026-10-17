import asyncio
import hashlib
import json
import logging

from telethon.tl.functions.channels import GetFullChannelRequest

from app.analytics import collect_analytics
from app.client import create_clients
from app.config import DATABASE_FILE, REQUEST_DELAY, REQUEST_RETRIES
from app.database import Database
from app.errors import classify_error
from app.export import save_to_excel
from app.models import ChatResult, ErrorKind, FilterConfig, ScanError
from app.rate_limit import TelegramLimiter
from app.search import search_groups
from app.utils import load_keywords

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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
    logger.info("Запуск #%s%s", run_id, " (возобновлён)" if resumed else "")

    active_clients = []
    try:
        for client in clients:
            if uploaded_sessions:
                await client.connect()
                if not await client.is_user_authorized():
                    logger.error("Сессия %s не авторизована и пропущена", client.session.filename)
                    await client.disconnect()
                    continue
            else:
                await client.start()
            active_clients.append(client)

        if not active_clients:
            raise RuntimeError("Нет ни одной авторизованной Telegram-сессии")

        limiters = [TelegramLimiter(1, REQUEST_DELAY, REQUEST_RETRIES) for _ in active_clients]
        logger.info("Активных сессий: %s", len(active_clients))
        groups = await search_groups(active_clients[0], limiters[0])
        db.set_total(run_id, len(groups))
        processed = db.processed_ids(run_id)

        async def process(chat, client, limiter):
            if chat.id in processed:
                return
            try:
                entity = chat
                if client is not active_clients[0] and chat.username:
                    entity = await limiter.call(lambda: client.get_entity(chat.username))
                full = await limiter.call(lambda: client(GetFullChannelRequest(entity)))
                is_channel = bool(getattr(chat, "broadcast", False))
                can_write = False
                if not is_channel:
                    permissions = await limiter.call(lambda: client.get_permissions(entity, "me"))
                    can_write = bool(getattr(permissions, "send_messages", False))
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
            except Exception as exc:
                kind = classify_error(exc)
                db.save_error(run_id, ScanError(chat.id, chat.title, kind, str(exc)))
                logger.exception("Ошибка: %s", chat.title)

        pending = [chat for chat in groups if chat.id not in processed]
        public_index = 0
        tasks = []
        for chat in pending:
            worker_index = public_index % len(active_clients) if chat.username else 0
            public_index += int(bool(chat.username))
            tasks.append(process(chat, active_clients[worker_index], limiters[worker_index]))
        await asyncio.gather(*tasks)

        results, errors = db.results(run_id), db.errors(run_id)
        save_to_excel(results, errors=errors, run_id=run_id)
        db.finish(run_id)
        logger.info("Завершено: %s результа(ов), %s ошибка(ок)", len(results), len(errors))
    finally:
        await asyncio.gather(*(item.disconnect() for item in active_clients), return_exceptions=True)
        db.close()
