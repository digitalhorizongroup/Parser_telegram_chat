import logging
from telethon.tl.functions.contacts import SearchRequest
from app.utils import load_keywords
from app.config import MIN_GROUP_USERS, SEARCH_LIMIT
from app.progress import update_progress
from app.rate_limit import AccountCooldownError
from app.models import SearchCandidate

logger = logging.getLogger()

async def search_groups(clients, limiters, db, run_id):
    found_groups = {item.chat_id: item for item in db.candidates(run_id)}
    keywords = load_keywords()
    completed_keywords = db.completed_keywords(run_id)

    for index, keyword in enumerate(keywords):
        if keyword in completed_keywords:
            continue
        keyword_finished = False
        update_progress(
            phase="searching",
            phase_label="Поиск сообществ",
            completed=len(completed_keywords),
            total=len(keywords),
            remaining=len(keywords) - len(completed_keywords),
            current=f"Ключевое слово: {keyword}",
            found=len(found_groups),
            error="",
        )
        logger.info(f"🔎 Ищем чаты по слову: {keyword}")
        try:
            result = None
            last_error = None
            cooldowns = []
            for shift in range(len(clients)):
                worker = (index + shift) % len(clients)
                try:
                    result = await limiters[worker].call(lambda: clients[worker](SearchRequest(q=keyword, limit=SEARCH_LIMIT)))
                    break
                except Exception as exc:
                    last_error = exc
                    if isinstance(exc, AccountCooldownError):
                        cooldowns.append(exc.seconds)
                    logger.warning("Аккаунт %s не выполнил поиск, пробуем следующий: %s", worker + 1, exc)
            if result is None:
                if len(cooldowns) == len(clients):
                    raise AccountCooldownError(min(cooldowns))
                raise last_error or RuntimeError("Нет доступных аккаунтов")
            for chat in result.chats:
                if (
                    (getattr(chat, "megagroup", False) or getattr(chat, "broadcast", False))
                    and (chat.participants_count is None or chat.participants_count >= MIN_GROUP_USERS)
                    and chat.id not in found_groups
                ):
                    candidate = SearchCandidate(
                        chat_id=chat.id,
                        title=chat.title,
                        username=chat.username,
                        chat_type="channel" if getattr(chat, "broadcast", False) else "chat",
                        participants=getattr(chat, "participants_count", None),
                        access_hash=getattr(chat, "access_hash", None),
                    )
                    db.save_candidate(run_id, candidate)
                    found_groups[chat.id] = candidate
                    logger.info(f"✅ Найдено: {chat.title} (@{chat.username if chat.username else 'Приватный'})")
            keyword_finished = True
        except AccountCooldownError:
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске {keyword}: {e}")
            keyword_finished = True
        finally:
            if keyword_finished:
                db.mark_keyword_complete(run_id, keyword)
                completed_keywords.add(keyword)
            update_progress(
                completed=len(completed_keywords),
                total=len(keywords),
                remaining=len(keywords) - len(completed_keywords),
                current=(f"Завершено: {keyword}" if keyword_finished else f"Ожидает: {keyword}"),
                found=len(found_groups),
            )
    return db.candidates(run_id)
