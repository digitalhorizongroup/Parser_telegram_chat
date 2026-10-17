# Telegram Chat & Channel Parser

Python-парсер для поиска Telegram-чатов и каналов, анализа их аудитории и экспорта статистики в Excel. Проект собирает данные об участниках, пользователях онлайн, сообщениях за последние сутки и активности голосовых чатов.

[Telegram](https://t.me/digitalhorizongroup) · [Discord](https://discord.com/invite/fjqzSYCETC)

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

Создайте файл `.env` в корне проекта (можно скопировать `.env.example`) и укажите параметры Telegram API:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash

# Необязательные параметры
MIN_GROUP_USERS=100
SEARCH_LIMIT=10
MAX_MESSAGES_24H=10000
```

Добавьте поисковые запросы в `assets/keywords.txt`, по одному ключевому слову на строку.

## Использование

```bash
python run.py
```

Пример запуска с фильтрами:

```bash
python run.py --min-users 1000 --min-messages 10 --public-only --language ru --exclude "casino,spam"
```

Доступны также `--active-only` и `--writable-only`. При повторном запуске с теми же ключами и фильтрами незавершённое сканирование возобновится из SQLite.

### Веб-панель

Интерфейс построен на React + Vite, а Flask предоставляет защищённый JSON API.

Перед запуском задайте в `.env` логин, сильный пароль и случайный секрет:

```dotenv
WEB_USERNAME=admin
WEB_PASSWORD=replace_with_a_strong_password
WEB_SECRET_KEY=replace_with_a_long_random_secret
```

```bash
python web.py
```

Для изменения frontend в режиме разработки:

```bash
cd frontend
npm install
npm run dev
```

Для production-сборки:

```bash
cd frontend
npm run build
```

Откройте `http://127.0.0.1:8080`. В панели можно загрузить файл ключевых слов, задать фильтры, видеть прогресс и скачать Excel-отчёт.

В форме можно выбрать сразу несколько Telethon-файлов `.session`. Исходные имена файлов не важны: панель выдаёт им безопасные случайные имена. Все авторизованные сессии работают параллельно, получая свою часть общей очереди. Невалидные или неавторизованные сессии пропускаются.

### Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Панель будет доступна на `http://127.0.0.1:8080`. Сессии, SQLite-история, ключевые слова и отчёты хранятся в постоянном Docker-томе `telegram-data`.

### Тесты

```bash
python -m unittest discover -s tests -v
```

После завершения работы парсер создаст Excel-файл со статистикой найденных чатов и каналов.
При первом запуске Telegram попросит номер телефона, код подтверждения и, если включена, пароль 2FA. Файл сессии хранится локально в `assets/` и не должен публиковаться.

## Пример отчёта

![Пример Excel-отчёта со статистикой Telegram-чатов и каналов](assets/Example.jpg)

## Технологии

- [Telethon](https://github.com/LonamiWebs/Telethon) — работа с Telegram API
- [openpyxl](https://openpyxl.readthedocs.io/) — создание Excel-отчётов
- Python `asyncio` — асинхронный сбор данных

## Участие в разработке

Нашли ошибку или хотите предложить улучшение? [Создайте issue](https://github.com/digitalhorizongroup/Parser_telegram_chat/issues) или отправьте pull request.
