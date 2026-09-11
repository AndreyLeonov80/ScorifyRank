# ScorifyRank — search, analyze and rank information from Telegram and the web into structured signals

Выпустил книгу о проекте: https://www.litres.ru/74436604/

> Высоконагруженная система скоринга Telegram: поиск, анализ и ранжирование информации из Telegram и веба в структурированные сигналы — лиды, сделки, need-сигналы, события, оценки контактов.

Проект также известен в коде и релизах как **GramLead / X-Files Client (backfront)** — это одно и то же продуктовое ядро: `ScorifyRank` — публичное имя, `GramLead / X-Files` — историческое имя модулей, API и Docker-сервисов.

---

## 🎬 Видео о проекте

| # | Площадка | Ссылка |
|---|----------|--------|
| 1 | YouTube | https://www.youtube.com/watch?v=lvz0n6envgQ |
| 2 | YouTube | https://www.youtube.com/watch?v=dEX4Z1j9f6s |
| 3 | YouTube | https://www.youtube.com/watch?v=PzhbbVdhKA0 |
| 4 | RuTube | https://rutube.ru/video/3a543335cc2819dcb9a7a727be91b124/ |
| 5 | RuTube | https://rutube.ru/video/ddee3f16f2139b51b96633551a20518b/ |
| 6 | RuTube | https://rutube.ru/video/d53fa91f7e9189bdb8e6a8106cb6c9a0/ |

Смотрите видео, чтобы увидеть живой контур: Import → Sync/Grid → Dashboard → Чаты → Сделки → выгрузка в CRM.

---

## 1. Что делает система

1. **Search (поиск).** Подключение Telegram-аккаунта (Telethon-сессия), каталог диалогов, выбор источников: каналы, группы, лички, боты. Фильтры, группы сканирования (A/B/C), лимиты истории и сообщений.
2. **Analyze (анализ).** Скачивание сообщений в JSONL → инкрементальный инжест в DuckDB → LLM-анализ через OpenRouter (или локально через LM Studio): квалификация контактов, даты мероприятий, адреса/маршруты, pain/prepay/pay-сигналы, саммари чатов, предложения ответов, дайджесты.
3. **Rank (ранжирование).** Скоринг лидов и сделок: температуры, стадии kanban, need-сигналы с тегами, conversion-воронка, north-star метрики, profit-optimization, аудит каждого изменения сделки.
4. **Signals (сигналы).** Структурированная выдача: таблицы источников, runtime-статусы чтения, SSE-стримы, HTML-отчёты `<lead>-llm.html`, DOCX-артефакты, выгрузка в Bitrix24 / amoCRM.

Ключевое свойство — **всё работает локально у клиента в Docker**: Telegram-данные, JSONL/DuckDB/PostgreSQL никогда не уходят на лицензионный сервер (там только метаданные лицензии — проверено privacy-тестами).

---

## 2. Где что лежит: frontend и backend

```
gramlead-main-new-optimize/
├── backfront/
│   ├── backend/            # ← BACKEND (FastAPI, Python 3.11, порт 8009)
│   │   ├── app/
│   │   │   ├── main.py             # точка входа app.main:app (роутеры + legacy back.py)
│   │   │   ├── celery_app.py       # Celery-приложение, очереди, маршруты задач
│   │   │   ├── routers/            # 20 доменных роутеров (см. §4)
│   │   │   ├── services/           # бизнес-логика: leads, deals, llm_client,
│   │   │   │                       # telegram_sync/*, contact_llm/*, crm_exports/*,
│   │   │   │                       # data_sources/*, jobs*, monitoring, outreach…
│   │   │   ├── schemas/            # Pydantic DTO всех доменов
│   │   │   ├── storage/            # duckdb/* (schema, ingest, queries, maintenance),
│   │   │   │                       # jsonl_store.py
│   │   │   ├── workers/            # celery_tasks.py, postgres_worker.py, analysis_cache.py
│   │   │   ├── core/ repositories/ runtime/
│   │   │   └── crm_export_app.py   # отдельное FastAPI-приложение выгрузки в CRM
│   │   ├── back.py                 # legacy-монолит (источник истины на время рефакторинга)
│   │   ├── requirements.txt        # прод-зависимости (точный пин)
│   │   ├── Dockerfile              # python:3.11-slim + uvicorn (run.sh)
│   │   ├── run.sh                  # инициализация /data и запуск uvicorn
│   │   └── tests/                  # ~50 pytest-модулей (контракты, кэш, DuckDB, CRM…)
│   │
│   ├── frontend/           # ← FRONTEND (Vite + TS + React, порт 8008)
│   │   ├── index.html / app.html   # оболочки (React vendor + /src/main.tsx)
│   │   ├── src/                    # новый слой: api/*, components/*, pages/*,
│   │   │                           # shared/*, types/* (dashboard, grid, import,
│   │   │                           # index/chat, deals, settings)
│   │   ├── js/                     # legacy-слой: api.client.js, script.api.js,
│   │   │                           # react.page-loader.js, vendor/react*.js, htm
│   │   ├── css/ scss/              # стили (sass scss/pages → css/pages)
│   │   ├── vite.config.ts          # dev/preview 0.0.0.0:8008, proxy /api → :8009
│   │   ├── nginx.conf              # прод-раздача dist (8008)
│   │   ├── package.json            # vite ^6, typescript ^5.8, sass
│   │   └── Dockerfile              # node:22-alpine → npm run build → preview
│   │
│   └── config/rabbitmq/            # consumer-timeout.conf
│
├── docker-compose.yml      # ← 11 сервисов (см. §6)
├── x-files-client-db/      # данные/миграции/сиды/бэкапы Postgres-контура
├── config/crm_exports.local.yaml
├── docs/                   # ТЗ, архитектура, операции, продажи, аудиты
├── license.xfiles.codeboost.ru/  # серверная копия лицензионного сервиса
├── license.local-front/          # локальное UI выдачи лицензий
├── scripts/                # релизные и операционные скрипты
└── LICENSE                 # коммерческая лицензия (проприетарная)
```

| Вопрос | Ответ |
|--------|-------|
| Где **backend**? | `backfront/backend/` — FastAPI-приложение `app.main:app`, запуск `run.sh` → `uvicorn … --port 8009`. В Docker — сервис `x-files-backfront-new-back` (`127.0.0.1:8009 → 8009`). |
| Где **frontend**? | `backfront/frontend/` — Vite + TypeScript + React (+ legacy JS-слой). Dev/preview `:8008`, прод — Nginx со `dist/`. В Docker — сервис `x-files-backfront-new-front` (`127.0.0.1:8008 → 8008`, `X_FILES_API_BASE=http://x-files-backfront-new-back:8009`, proxy `/api`). |
| Где точка входа пользователя? | `http://127.0.0.1:8008` → Import → Sync/Grid → Dashboard → Чаты → Сделки. |

---

## 3. Полный стек

### 3.1. Backend

| Слой | Технология | Версия / образ | Зачем |
|------|-----------|----------------|-------|
| Язык | Python | **3.11** (`python:3.11-slim`) | весь backend |
| HTTP API | FastAPI | **0.104.1** | ~20 доменных роутеров, SSE, FileResponse/HTMLResponse |
| ASGI-сервер | Uvicorn | **0.24.0** | запуск через `run.sh`, `UVICORN_WORKERS=1` по умолчанию |
| Валидация | Pydantic | **2.5.0** | все DTO в `app/schemas/` |
| Telegram | Telethon | **1.33.1** | сессии (`tg_export_session`), backfill + live-sync, отправка сообщений, каталог диалогов, FloodWait/cooldown-защита, группы сканирования |
| Аналитика | DuckDB | **1.4.1** | локальная OLAP-база сообщений (`gramlead.duckdb` + read-реплика `gramlead-read.duckdb`), инкрементальный инжест, `parquet/` |
| Система записей | PostgreSQL | **16-alpine** + `psycopg[binary]==3.1.18` | структурное хранилище приложения (`x-files-client-db:5432`) |
| Очереди | RabbitMQ | **3.13-management-alpine** (`:15672` management) | брокер Celery |
| Фоновые задачи | Celery | **5.3.6** | 5 воркеров, 11 очередей (см. §5), `task_acks_late`, DLX `gramlead.dlx` |
| Кэш/результаты | Redis | **7-alpine** (`redis==5.0.1`) | result backend Celery (`db 1`), снапшот-кэши API, прогрев sender-stats |
| Файловый кэш | JSONL + Parquet + state.json | — | `PAYME_OUT_DIR/*.jsonl`, `PAYME_CACHE_DIR`, `PAYME_STATE_PATH` |
| LLM-облако | OpenRouter | Chat Completions API | квалификация контактов, даты событий, адреса, скоринг; аудит запросов (prompt-hash, токены, cost USD), ретраи, PII-санитизация |
| LLM-локально | LM Studio | `LMSTUDIO_BASE_URL` (OpenAI-совместимый `/v1`) | офлайн-режим анализа (`LLM_PROVIDER`) |
| HTTP-клиент | requests | **2.31.0** (+ `charset-normalizer==2.1.1`) | OpenRouter/CRM вызовы из sync-контекстов |
| CRM-выгрузка | собственные провайдеры | — | Bitrix24 (`:8024`) и amoCRM (`:8025`) — отдельные uvicorn-приложения `app.crm_export_app:app`, DOCX/HTML-артефакты контакта |
| Утилиты | psutil | **5.9.8** | мониторинг runtime |
| Упаковка | Nuitka | `Dockerfile.nuitka*`, `nuitka_entrypoint.py` | нативные сборки десктоп/ZIP-релизов |
| Тесты | pytest | `pytest.ini`, `tests/` (~50 модулей) | контракты API, снапшоты, DuckDB-локи, CRM-провайдеры, приватность лицензии |

### 3.2. Frontend

| Слой | Технология | Где | Зачем |
|------|-----------|-----|-------|
| Сборка | Vite | **^6.3.5** (`vite.config.ts`) | dev/preview `:8008`, proxy `/api → :8009`, билд в `dist/` без sourcemap |
| Язык | TypeScript | **^5.8.3** (`strict`, `ES2022`, `react-jsx`) | `src/**/*.ts(x)`, `npm run typecheck` |
| UI-библиотека | React | vendor `react.production.min.js` + `react-dom` + `htm` + TSX-модули `src/` | страницы и компоненты; `src/main.tsx` подгружает классический `/js/app.entry.js` |
| Совместимость | Vanilla JS bridge | `src/api/client.js`, `src/api/endpoints.js`, `js/api.client.js`, `js/script.api.js`, `js/react.page-loader.js` | единый API-клиент с fallback `8009 → legacy 8001`, поэкранная миграция без остановки UI |
| Стили | SCSS/Sass | **sass ^1.99.0**, `scss/pages → css/pages` | `npm run scss:build/watch`, `css/style.css` |
| Раздача прод | Nginx / `vite preview` | `nginx.conf`, `Dockerfile` (`node:22-alpine`) | `try_files → index.html`, immutable-кэш статики, `no-store` для HTML |
| Экраны | Import, Grid/Sync, Dashboard, Chat/Index, Deals, Settings | `src/pages/{import,grid,dashboard,index,deals,settings}` | фильтры источников, runtime-статусы чтения, lead-карточки, kanban сделок, LLM-логи, промпты |
| Аудиты качества | Node-скрипты | `scripts/audit-*.mjs` (~30 штук) + Playwright smoke | размеры бандлов, polling-бюджет, виртуализация списков, error-boundary, кэш-дедуп |

### 3.3. Инфраструктура

| Компонент | Образ / средство |
|-----------|------------------|
| Оркестрация | Docker Compose (11 сервисов) |
| База | `postgres:16-alpine` (`127.0.0.1:5433 → 5432`) |
| Брокер | `rabbitmq:3.13-management-alpine` (`127.0.0.1:15672` UI) |
| Кэш | `redis:7-alpine` (`127.0.0.1:6379`, AOF) |
| Backend | сборка из `backfront/backend` |
| Frontend | сборка из `backfront/frontend` |
| Healthchecks | `pg_isready`, `rabbitmq-diagnostics ping`, `redis-cli ping` |
| Лицензии | `license.xfiles.codeboost.ru` (сервер), `license.local-front` (локальное UI `:8010`), signed `invite-license.json` в ZIP |

---

## 4. Backend API (домены `app/routers/`)

`app/main.py` монтирует новые роутеры поверх legacy `back.py` с дедупликацией маршрутов. Домены:

`health`, `config`, `license`, `jobs`, `channels`/`leads` (источники, runtime-статусы, SSE-стримы), `analysis` (LLM-запуски, история, токены), `contacts` (квалификация через OpenRouter), `search`, `events` (мероприятия/календарь), `routes` (адреса/маршруты), `deals` (сделки, kanban, аудит, margins, contract-kit, negotiation-brief, потребности/need-сигналы), `crm` + `outreach`, `data_sources` (SQL/API-плагины, writeback), `jur_entities`, `media` (OCR), `monitoring`, `legacy_api`.

Типовые паттерны: быстрый снапшот-кэш (`_cached_sync_snapshot_fast`, async-вариант со stale-окном), пагинация всех списков, серверная фильтрация лидов, SSE (`text/event-stream`) для live-прогресса.

---

## 5. Высоконагруженный контур: очереди и пайплайн

Celery-приложение (`app/celery_app.py`): брокер — RabbitMQ, результаты — Redis, persistent-доставка, dead-letter exchange `gramlead.dlx`.

| Воркер | Очереди | Задачи |
|--------|---------|--------|
| `celery_worker_telegram` | `telegram.import`, `telegram.sync` | live/backfill чтение Telegram, каталог диалогов |
| `celery_worker_preprocess` | `jsonl.ingest`, `duckdb.preprocess`, `cache.warm`, `ocr.media` | инжест JSONL → DuckDB, прогрев кэшей, OCR |
| `celery_worker_llm` | `llm.analysis` | OpenRouter/LM Studio анализ (дефолтная очередь) |
| `celery_worker_leads` | `lead.scoring`, `reply.suggest`, `digest.generate` | скоринг, ответы, дайджесты |
| `celery_worker_export` | `export.crm` | выгрузка в CRM |

Пайплайн сообщения: **Telegram → JSONL → DuckDB/Parquet → LLM-сигналы → скоринг лида → сделка/need-сигнал → Dashboard/Grid → CRM-экспорт**. Тяжёлые чтения идут через read-реплику DuckDB, чтобы не блокировать writer.

---

## 6. Docker-сервисы и порты (корень `docker-compose.yml`)

| Сервис | Порт хоста | Назначение |
|--------|-----------|------------|
| `x-files-backfront-new-front` | `127.0.0.1:8008` | frontend |
| `x-files-backfront-new-back` | `127.0.0.1:8009` | backend API |
| `x-files-client-db` | `127.0.0.1:5433` | PostgreSQL 16 |
| `x-files-rabbitmq` | `127.0.0.1:15672` | RabbitMQ management |
| `x-files-redis` | `127.0.0.1:6379` | Redis 7 |
| `celery_worker_{telegram,preprocess,llm,leads,export}` | — | 5 фоновых воркеров |
| `x-files-crm-bitrix24` | `127.0.0.1:8024` | выгрузка Bitrix24 |
| `x-files-crm-amocrm` | `127.0.0.1:8025` | выгрузка amoCRM |

Общие volume: `state/`, `out/`, `cache/`, `db/` (duckdb+parquet), `jur_entities/`, `tg-session/`, `license-runtime/`.

---

## 7. Скоринг: как считаются сигналы

- **Источники/лиды** (`services/leads.py`): прогресс чтения (`read/total/remaining/percent`), статусы `reading / waiting / pending / error / archived / empty`, scan-группы A/B/C с частотами, сортировка «активные сначала».
- **Need-сигналы** (`xfiles_deals_engine.py`): pain / prepay / pay теги из текста + LLM, страница сигналов с фильтром по тегу/источнику.
- **Сделки** (`services/deals*.py`, `xfiles_contracts.py`): стадии kanban, дедуп при создании, аудит-лента каждого изменения, margins продуктов, contract-kit и negotiation-brief, follow-up цепочки (без автоотправки), daily-contacts и north-star/конверсия/profit-optimization витрины.
- **Контакты** (`contact_llm/*`): шаблонный промпт → контекст сообщений автора → OpenRouter → структурированный русский ответ + DOCX/HTML-артефакты для CRM-карточки.
- **События/маршруты**: LLM-извлечение `event_date` (строгий JSON, `null` если даты нет) и физического адреса (анти-галлюцинация: «только Москва» → `null`).

---

## 8. Быстрый старт

```bash
# 1. Инфраструктура + приложение
docker compose up -d --build

# 2. Открыть UI
open http://127.0.0.1:8008
# API:  http://127.0.0.1:8009
# RabbitMQ UI: http://127.0.0.1:15672

# 3. Ввести в Settings: Telegram API (сессия), OpenRouter API key + модель
# 4. Import → добавить источники → Sync/Grid → наблюдать Dashboard
# 5. Чаты/Index → LLM-анализ → Deals → выгрузка в Bitrix24/amoCRM
```

Переменные окружения — см. `backfront/backend/.env.example` (`PAYME_*`, `XFILES_POSTGRES_DSN`, `RABBITMQ_URL`, `REDIS_URL`, `LLM_PROVIDER=openrouter`, `LMSTUDIO_BASE_URL`).

Локальная разработка:

```bash
# backend
cd backfront/backend && pip install -r requirements.txt && sh run.sh
# frontend
cd backfront/frontend && npm install && npm run dev   # :8008, proxy /api → :8009
```

Тесты: `cd backfront/backend && pytest`; фронт: `npm run typecheck`, `npm run audit:js-size`, `npm run smoke:playwright-pages`.

---

## 9. Лицензирование и коммерческое использование

Проект распространяется под **коммерческой проприетарной лицензией** — см. файл [`LICENSE`](./LICENSE). Кратко:

- все права принадлежат правообладателю ScorifyRank https://t.me/aidialog aidialog@mail.ru https://github.com/AndreyLeonov80/about;
- копирование, модификация, публикация, сублицензирование и коммерческое использование **без письменного разрешения запрещены**;
- универсальные Docker ZIP-релизы активируются invite-кодом (срок — от момента активации, один код — одна активация);
- на license-server передаются **только метаданные лицензии**, контент клиентов не передаётся.

Полный текст — в `LICENSE` (русская и английская версии).

---

## 10. Документация по запросу

- `docs/2026-05-25-program-full-description.md` — полное описание программы;
- `docs/program-technical-spec/` — архитектура, API, безопасность, доставка;
- `docs/program-business-functional-requirements/` — скоуп, роли, требования;
- `docs/operations/`, `docs/install/`, `docs/sales-docs/` — эксплуатация и продажи;
- `docs/*audit*.md`, `docs/*license*.md` — аудиты кода, лицензий, Telegram-контура.

---

© 2026 ScorifyRank (GramLead / X-Files). Все права защищены. См. [`LICENSE`](./LICENSE).
