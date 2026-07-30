# Telegram Chat & Channel Parser

Python-парсер для поиска Telegram-чатов и каналов, анализа их аудитории и экспорта статистики в Excel. Проект собирает данные об участниках, пользователях онлайн, сообщениях за последние сутки и активности голосовых чатов.

## Возможности

- Поиск публичных Telegram-чатов и каналов по ключевым словам
- Сбор статистики об участниках и пользователях онлайн
- Анализ сообщений за последние 24 часа
- Определение голосовых чатов и трансляций
- Экспорт отформатированного отчёта в Excel

## Требования

- Python 3.13+
- Telegram API ID и API Hash с [my.telegram.org](https://my.telegram.org/)

## Установка

```bash
git clone https://github.com/digitalhorizongroup/Parser_telegram_chat.git
cd Parser_telegram_chat
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Настройка

Укажите параметры Telegram API и остальные настройки в `app/config.py`:

```python
from pathlib import Path

API_ID = 123456
API_HASH = "your_api_hash"
SESSION_NAME = Path("assets") / "session_name"
DEVICE_MODE = ""
SYSTEM_VERSION = ""
APP_VERSION = ""
LANG_CODE = ""
SYSTEM_LANG_CODE = ""
```

Добавьте поисковые запросы в `assets/keywords.txt`, по одному ключевому слову на строку.

## Использование

```bash
python run.py
```

После завершения работы парсер создаст Excel-файл со статистикой найденных чатов и каналов.

## Пример отчёта

![Пример Excel-отчёта со статистикой Telegram-чатов и каналов](assets/Example.jpg)

## Технологии

- [Telethon](https://github.com/LonamiWebs/Telethon) — работа с Telegram API
- [openpyxl](https://openpyxl.readthedocs.io/) — создание Excel-отчётов
- Python `asyncio` — асинхронный сбор данных

## Участие в разработке

Нашли ошибку или хотите предложить улучшение? [Создайте issue](https://github.com/digitalhorizongroup/Parser_telegram_chat/issues) или отправьте pull request.

Если у вас есть вопросы или предложения, пишите в [Telegram](https://t.me/digitalhorizongroup) или [Discord](https://discord.com/invite/fjqzSYCETC) 🚀
