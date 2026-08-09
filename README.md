# Job Bot

Десктоп-приложение, которое автоматизирует поиск работы в Telegram-каналах. Бот опрашивает выбранные каналы, парсит вакансии через LLM, сравнивает их с вашим резюме по эмбеддингам, и отправляет HR-ам отклики через ваш собственный Telegram-аккаунт.

Всё локально: PySide6-окно, SQLite, Pyrogram-сессия. Облако не требуется — LLM можно подключить локальный (LM Studio, Ollama) или внешний по OpenAI-совместимому API.

## Стек

- **UI** — PySide6 + QWebEngineView, фронт на чистом HTML/JS (`client/web/main.html`, `wizard.html`).
- **Bridge** — `client/bridge.py`, два QObject (`WizardApi` для онбординга, `MainApi` для основного режима), общаются с JS через QWebChannel.
- **Бот** — `backend/bot.py`, Pyrogram-клиент в фоновом asyncio-loop, цикл опроса каналов в `backend/flows.py`.
- **БД** — SQLite через async SQLAlchemy + Alembic-миграции. Креды (api_hash, password, session_string) шифруются через `cryptography` Fernet, ключ хранится в OS keyring.
- **LLM-адаптер** — `adapters/lm_studio.py`, OpenAI-совместимый. Используется и для chat-моделей (парсинг/классификация), и для embedding-моделей (similarity).

## Что делает бот

Цикл `flows.IngestionPipeline`:
1. **Опрос каналов** — каждый `poll_interval_sec` пуллит свежие сообщения из активных Telegram-каналов через Pyrogram.
2. **Парсинг** — каждое сообщение прогоняется через LLM с промптом «это вакансия?»; на выходе структура `ParsedVacancy` с полями (грейд, стек, формат, salary, и т.д.).
3. **Скоринг** — сравнение эмбеддинга вакансии с эмбеддингом резюме, плюс LLM-валидатор «подходит/не подходит». Дубликаты отсеиваются по cosine-similarity.
4. **Отклик** — для подходящих вакансий генерируется cover letter, отправляется HR'у в личку.
5. **Классификация ответов HR** — входящие сообщения от HR-ов классифицируются (ANSWERED / REJECTED / INVITE / DECLINE) и обновляют статус вакансии.

## Запуск

```powershell
pipenv install
pipenv run python main.py
```

Первый запуск откроет визард: api_id/api_hash → код подтверждения → опционально 2FA → выбор LLM (chat + embedding) → загрузка резюме (PDF). После этого открывается основное окно.

## Где лежат данные

- **Windows**: `%APPDATA%\JobBot\`
- **macOS**: `~/Library/Application Support/JobBot/`
- **Linux**: `${XDG_DATA_HOME:-~/.local/share}/JobBot/`

Внутри:
- `jobbot.db` — основная SQLite-база (вакансии, контакты, переписка, настройки).
- `jobbot.log` — журнал приложения; переходит на новый файл каждые 5 МБ, хранится четыре. В оконной сборке это единственное, что переживает закрытие окна: экран «Логи» показывает кольцевой буфер в памяти.
- `sessions/` — Pyrogram-сессия (`.session`-файл).
- `media/` — скачанные медиа из вакансий.

## Экраны

- **Профиль** — редактируемое резюме (опыт, скиллы, языки, ожидаемые форматы/грейды), CV в PDF.
- **Вакансии** — список с фильтрами по статусу/грейду/формату, детальная карточка, история смены статусов, ручная привязка HR/компании.
- **Контакты** — HR-ы (с переписками), компании, каналы, чёрный список.
- **Статистика** — KPI, воронка статусов, распределение по каналам и скиллам, медианное время ответа HR.
- **Система** — две вкладки:
  - **Настройки** — Telegram (api_id/api_hash/phone, login/logout), LLM для чата, LLM для эмбеддингов, пайплайн (score threshold, интервал опроса, лимит сообщений за цикл, симуляция отправки DM для dev-режима), опасная зона (полное удаление данных). Все поля автосейвятся при `blur`/`change`.
  - **Логи** — in-memory ring-buffer на 5000 записей, мульти-фильтр уровней, авто-обновление.

## Разработка

### Миграции

```powershell
pipenv run alembic revision --autogenerate -m "..."
pipenv run alembic upgrade head
```

При старте `main.py` сам выполняет `alembic upgrade head` (см. `backend/bootstrap.py`), отдельный шаг руками не нужен.

### Сборка `.exe`

Конфигурация в `JobBot.spec` (PyInstaller, single-file Windows-бандл).

```powershell
pipenv run pip install pyinstaller          # один раз — в venv
pipenv run python -m PyInstaller JobBot.spec --clean --noconfirm
```

После сборки готовый файл лежит в `dist/JobBot.exe` (~240 МБ). Холодный старт — 5–15 сек: онешот распаковывает себя во временный `_MEIPASS`-каталог. БД и логи живут в `%APPDATA%\JobBot`, рядом с .exe ничего не сохраняется — распространять можно как один файл.

Что вшито в бандл (см. `JobBot.spec`): `client/web/` (HTML/JS/шрифты/flatpickr), `alembic.ini` + `alembic/env.py` + `alembic/script.py.mako` + init-миграция, `client/icon.ico`. Hidden imports: `aiosqlite`, `keyring.backends.Windows`, `logging.config`, явные имена alembic-versions модулей.

> Seed-миграция `aa4e0de05368_seed_initial_data.py` (персональные данные разработчика — CV, опыт, скиллы, подписанные каналы) gitignored и в стандартной spec-сборке **не попадает в бандл**. Получатель .exe увидит чистую БД + first-run wizard.

### Структура проекта

```
backend/
  bootstrap.py        # alembic upgrade + first-run setup
  bot.py              # Bot-класс, Pyrogram-клиент + цикл
  flows.py            # IngestionPipeline: опрос → парсинг → скоринг → отклик
  domain/             # бизнес-логика без I/O, по одному модулю на предмет
  cv_parser.py        # PDF-резюме → структурированные поля профиля
  llm/                # промпты и разбор ответов, по одному модулю на предмет
  models/             # SQLAlchemy-модели, по одному модулю на предмет
  repository/         # типизированные query-функции, по модулю на предмет
  runtime_settings.py # in-memory-кеш конфигурации (TG creds, LLM endpoints, app-settings)
  log_buffer.py       # буфер для UI «Логи», вымарывание секретов, отчёт о своей беде
  payloads.py         # dataclass-структуры для bridge-обмена

adapters/
  lm_studio.py        # OpenAI-совместимый LLM-клиент (chat / embed / list_models)
  telegram.py         # фабрика Pyrogram-клиента
  db.py               # фабрика SQLAlchemy-engine

client/
  shell.py            # точка входа Qt; QApplication + QMainWindow + QWebChannel
  bridge.py           # WizardApi + MainApi (все @Slot и Signal'ы для JS)
  web/
    main.html         # основное приложение (4 секции + Система)
    wizard.html       # первичная настройка
    qwebchannel.js    # клиентская часть QWebChannel

alembic/
  versions/*.py       # миграции
  env.py

docs/
  not-duplicates.md   # разобранные пары «это не повторы», с отпечатками
  Статусы.md          # граф переходов статусов вакансии (источник правды)

main.py               # CLI-entrypoint
config.py             # пути к user-data-dir
```

## Зависимости

- Python 3.13+
- `pyrogram` + `tgcrypto`
- `pyside6` (Qt 6.x)
- `sqlalchemy` (async) + `aiosqlite` + `alembic`
- `httpx`, `cryptography`, `keyring`, `pypdf`, `numpy`

LLM-провайдер не привязан к коду — нужен любой OpenAI-совместимый endpoint с `/v1/chat/completions`, `/v1/embeddings` и `/v1/models`. Для LM Studio используется и его native `/api/v0/models` (фильтрация по `state=loaded` + `type` для UI-picker'а).
