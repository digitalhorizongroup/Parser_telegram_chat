import logging
import datetime
from telethon.errors import RPCError
from app.config import MAX_MESSAGES_24H

logger = logging.getLogger(__name__)

async def get_chat_statistics(client, chat, online_count=None):
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        last_24h = now - datetime.timedelta(days=1)
        last_message_date = "Нет сообщений"
        last_24h_messages = 0

        async for message in client.iter_messages(chat, limit=MAX_MESSAGES_24H):
            if last_message_date == "Нет сообщений":
                last_message_date = message.date.astimezone(
                    datetime.timezone.utc
                ).strftime('%Y-%m-%d %H:%M:%S UTC')
            if message.date <= last_24h:
                break
            last_24h_messages += 1

        return (
            last_message_date,
            last_24h_messages,
            online_count if online_count is not None else "❌🔒",
        )

    except RPCError as e:
        logger.error(f"Ошибка RPC при получении статистики {chat.title}: {e}")
    except Exception:
        logger.exception("Ошибка при получении статистики %s", chat.title)
    
    return "⚠️", "⚠️", "⚠️"
