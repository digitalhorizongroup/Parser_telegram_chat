import logging
from telethon.tl.functions.contacts import SearchRequest
from app.utils import load_keywords
from app.config import MIN_GROUP_USERS, SEARCH_LIMIT

logger = logging.getLogger()

async def search_groups(client, limiter=None):
    found_groups = {}
    keywords = load_keywords()
    
    for keyword in keywords:
        logger.info(f"🔎 Ищем чаты по слову: {keyword}")
        try:
            operation = lambda: client(SearchRequest(q=keyword, limit=SEARCH_LIMIT))
            result = await limiter.call(operation) if limiter else await operation()
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
