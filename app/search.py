import logging
from telethon.tl.functions.contacts import SearchRequest
from app.utils import load_keywords
from app.config import MIN_GROUP_USERS, SEARCH_LIMIT

logger = logging.getLogger()

async def search_groups(clients, limiters):
    found_groups = {}
    keywords = load_keywords()
    
    for index, keyword in enumerate(keywords):
        logger.info(f"🔎 Ищем чаты по слову: {keyword}")
        try:
            result = None
            last_error = None
            for shift in range(len(clients)):
                worker = (index + shift) % len(clients)
                try:
                    result = await limiters[worker].call(lambda: clients[worker](SearchRequest(q=keyword, limit=SEARCH_LIMIT)))
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Аккаунт %s не выполнил поиск, пробуем следующий: %s", worker + 1, exc)
            if result is None:
                raise last_error or RuntimeError("Нет доступных аккаунтов")
            for chat in result.chats:
                if (
                    (getattr(chat, "megagroup", False) or getattr(chat, "broadcast", False))
                    and (chat.participants_count is None or chat.participants_count >= MIN_GROUP_USERS)
                    and chat.id not in found_groups
                ):
                    found_groups[chat.id] = chat
                    logger.info(f"✅ Найдено: {chat.title} (@{chat.username if chat.username else 'Приватный'})")
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске {keyword}: {e}")
    return list(found_groups.values())
