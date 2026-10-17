import logging

from app.config import DICTIONARY

logger = logging.getLogger(__name__)

def load_keywords():
    try:
        with open(DICTIONARY, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error("Файл %s не найден", DICTIONARY)
        return []
    except Exception as e:
        logger.exception("Ошибка при чтении файла %s", DICTIONARY)
        return []
