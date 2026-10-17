import datetime
import re

from app.config import MAX_MESSAGES_30D


def detect_language(text: str) -> str:
    text = text.lower()
    cyrillic = len(re.findall(r"[а-яёіїєґ]", text))
    latin = len(re.findall(r"[a-z]", text))
    if cyrillic > latin:
        return "uk" if re.search(r"[іїєґ]", text) else "ru"
    return "en" if latin else "unknown"


async def collect_analytics(client, chat) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    cut_1d = now - datetime.timedelta(days=1)
    cut_7d = now - datetime.timedelta(days=7)
    cut_30d = now - datetime.timedelta(days=30)
    counts = {"1d": 0, "7d": 0, "30d": 0}
    authors, views, reactions, samples = set(), 0, 0, []
    last_activity = ""

    async for message in client.iter_messages(chat, limit=MAX_MESSAGES_30D):
        if not last_activity:
            last_activity = message.date.astimezone(datetime.timezone.utc).isoformat()
        if message.date <= cut_30d:
            break
        counts["30d"] += 1
        counts["7d"] += int(message.date > cut_7d)
        counts["1d"] += int(message.date > cut_1d)
        if message.sender_id:
            authors.add(message.sender_id)
        views += message.views or 0
        if message.reactions:
            reactions += sum(getattr(item, "count", 0) for item in message.reactions.results)
        if message.message and len(samples) < 30:
            samples.append(message.message)

    return {
        "last_activity": last_activity,
        "messages_24h": counts["1d"], "messages_7d": counts["7d"],
        "messages_30d": counts["30d"], "average_7d": round(counts["7d"] / 7, 2),
        "average_30d": round(counts["30d"] / 30, 2), "active_authors": len(authors),
        "views": views, "reactions": reactions,
        "engagement_rate": round(reactions / views * 100, 3) if views else 0.0,
        "language": detect_language(" ".join([chat.title or "", *samples])),
    }
