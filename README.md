# Mentoring Platform

Рабочая платформа менторской программы Python и Go Backend: ученик входит из Telegram Mini App, получает оплаченный трек, читает материалы, использует базу знаний, готовится к собеседованиям по карточкам и отмечает прогресс; назначенный ментор видит результат, а администратор управляет треками, доступами, роадмапами и материалами.

## Архитектура и стек

Проект — monorepo и модульный монолит:

- `backend/`: Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy/asyncpg, Alembic, PostgreSQL;
- `frontend/`: React, TypeScript strict, Vite, React Router, TanStack Query, Mantine, react-markdown;
- `infra/`: Docker Compose с PostgreSQL, backend и frontend.

Backend разделён по предметным модулям `auth`, `users`, `tracks`, `roadmaps`, `progress`, `mentors`, `knowledge`, `interviews`. `LearningTrackEnrollment` определяет доступ к материалам и колодам направления, а `RoadmapEnrollment` хранит состояние прохождения. Процент не хранится в БД. Frontend хранит серверное состояние только в TanStack Query. В Telegram исходный `initData` берётся непосредственно из SDK и не копируется в отдельное хранилище. Временный UUID хранится в `localStorage` только в development-сборке.

Topic slug сделан глобально уникальным. Это намеренно более строгое ограничение, чем требуемая уникальность внутри roadmap, и позволяет не дублировать `roadmap_id` в `topics`.

## Требования

- Docker с Compose v2;
- Python 3.12 и Poetry 2.x для локального backend;
- Node.js 22, Corepack и pnpm 10 для локального frontend.

## Первый запуск в Docker

```bash
cp .env.example .env
make up
make migrate
make seed
```

Откройте `http://localhost:5173`. API доступен на `http://localhost:8000`, OpenAPI — на `http://localhost:8000/docs`.

Миграции не запускаются автоматически при старте контейнера. Это явный шаг `make migrate`.

## Telegram Mini App

1. Создайте бота через `@BotFather` и получите token.
2. В `@BotFather` откройте Bot Settings → Configure Mini App и укажите публичный HTTPS URL frontend.
3. Добавьте в `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:replace-with-real-token
TELEGRAM_INIT_DATA_TTL_SECONDS=86400
```

4. Перезапустите backend и примените миграции:

```bash
make up
make migrate
```

Mini App передаёт `Telegram.WebApp.initData` как `Authorization: tma <initData>`. Backend сверяет HMAC-SHA-256 с bot token и проверяет `auth_date`. Непроверенный `initDataUnsafe` не используется. Войти может только Telegram-пользователь, которому бот заранее выдал доступ после оплаты.

## Выдача доступа после оплаты

Платёжный Telegram-бот вызывает доверенный server-to-server endpoint. Создайте отдельный случайный token — не используйте для этого token из `@BotFather`:

```bash
openssl rand -hex 32
```

Добавьте результат в `.env` и перезапустите backend:

```dotenv
BOT_INTEGRATION_TOKEN=replace-with-random-secret
```

После подтверждённой оплаты бот отправляет данные ученика и slug выбранного трека (`python` или `go`):

```bash
curl -X POST http://localhost:8000/api/v1/integrations/telegram/students \
  -H "Authorization: Bearer $BOT_INTEGRATION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 123456789,
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "track_slug": "python"
  }'
```

Endpoint доверяет боту проверку факта оплаты, создаёт или обновляет ученика, завершает платформенный онбординг и выдаёт выбранный опубликованный трек со всеми входящими в него опубликованными роадмапами. Повторный запрос идемпотентен: дубликаты пользователя и доступа не создаются. В production endpoint должен вызываться только backend-процессом бота по HTTPS; `BOT_INTEGRATION_TOKEN` нельзя передавать во frontend или Mini App.

Dev-заголовок `X-Dev-User-Id` принимается только при `APP_ENV=development`. В production открыть кабинет по UUID нельзя.

## Локальная разработка

Установить зависимости:

```bash
cp .env.example .env
make install
docker compose -f infra/docker-compose.yml --env-file .env up -d postgres
make migrate
make seed
```

В двух терминалах:

```bash
make backend
make frontend
```

Основные команды:

```bash
make up                 # собрать и запустить все сервисы
make down               # остановить сервисы
make migrate            # применить Alembic migration
make migration name=x   # создать autogenerate migration
make seed               # идемпотентно заполнить development БД
make test               # backend и frontend tests
make test-backend
make test-frontend
make lint
make format
make typecheck
make api-generate       # обновить TS-типы из работающего FastAPI OpenAPI
```

Для `make api-generate` backend должен быть доступен по `OPENAPI_URL` (по умолчанию `http://localhost:8000/openapi.json`). Сгенерированный файл — единственный источник DTO frontend; прикладные aliases находятся в `frontend/src/types/api.ts`.

## Development-пользователи

Seed всегда выводит UUID и создаёт:

- ученик Иван: `20000000-0000-4000-8000-000000000001`;
- ментор Антон: `10000000-0000-4000-8000-000000000001`.
- администратор: `90000000-0000-4000-8000-000000000001`.

Кнопки быстрого входа читают эти значения из `VITE_DEV_STUDENT_ID` и `VITE_DEV_MENTOR_ID`; UUID не зашиты в production-компоненты.

Временная browser-авторизация отправляет `X-Dev-User-Id` только в dev-сборке. Telegram-авторизация проверяет подпись и срок действия `initData` в `backend/app/auth`, автоматически связывает пользователя по `telegram_id` и обновляет имя из Telegram. Telegram SDK изолирован в `frontend/src/platform`: там находятся инициализация, тема, BackButton, viewport и haptic feedback.

## API

- `GET /health`, `GET /ready`;
- `GET /api/v1/me`;
- `POST /api/v1/me/onboarding` — завершить интерфейсный онбординг без изменения доступов;
- `POST /api/v1/integrations/telegram/students` — создать ученика и выдать выбранный трек после оплаты;
- `GET /api/v1/roadmaps`;
- `GET /api/v1/roadmaps/{roadmap_slug}`;
- `POST /api/v1/roadmaps/{roadmap_slug}/start` — один раз зафиксировать личную дату старта;
- `GET /api/v1/topics/{topic_id}`;
- `PUT /api/v1/me/topics/{topic_id}/progress`;
- `GET /api/v1/knowledge/topics` — опубликованные темы базы знаний;
- `GET /api/v1/knowledge/topics/{topic_slug}` — статьи и вопросы темы;
- `GET /api/v1/knowledge/entries/{entry_slug}` — полный Markdown-материал;
- `GET /api/v1/knowledge/search?q=...` — полнотекстовый поиск по опубликованным материалам;
- `GET /api/v1/interviews/decks` — доступные ученику колоды и персональная статистика;
- `GET /api/v1/interviews/decks/{deck_slug}/session` — новые и запланированные карточки;
- `GET/PUT /api/v1/interviews/decks/{deck_slug}/topics` — доступные темы и персональный выбор ученика;
- `POST /api/v1/interviews/cards/{card_id}/reviews` — сохранить самооценку и назначить повторение;
- `GET /api/v1/mentor/students`;
- `GET /api/v1/mentor/students/{student_id}`.
- `GET /api/v1/admin/roadmaps` — все роадмапы, включая черновики;
- `POST /api/v1/admin/roadmaps` — атомарное создание roadmap с разделами и темами.
- `GET /api/v1/admin/roadmaps/{roadmap_id}` — данные для редактора;
- `PUT /api/v1/admin/roadmaps/{roadmap_id}` — обновление структуры с сохранением UUID.
- `GET/POST /api/v1/admin/tracks` — список и создание треков обучения;
- `GET/PUT /api/v1/admin/tracks/{track_id}` — состав и настройки трека;
- `GET /api/v1/admin/tracks/options` — доступные роадмапы и ученики;
- `PUT/DELETE /api/v1/admin/tracks/{track_id}/students/{student_id}` — выдать или отозвать доступ.
- `GET/POST /api/v1/admin/knowledge/topics` — список и создание тем базы знаний;
- `GET/PUT /api/v1/admin/knowledge/topics/{topic_id}` — редактирование темы, статей и вопросов.
- `GET/POST /api/v1/admin/interviews/decks` — список и создание колод интервью;
- `GET/PUT /api/v1/admin/interviews/decks/{deck_id}` — редактирование карточек колоды.

Admin frontend для треков доступен по `/admin/tracks`: администратор включает роадмапы в направления Python/Go и управляет доступом учеников. Конструктор контента доступен по `/admin/roadmaps`; формы поддерживают несколько разделов и тем, Markdown-контент, estimated time и независимые флаги публикации. Редактирование сохраняет UUID существующих тем, а отзыв трека не удаляет историю прогресса.

## База знаний

Пользовательский интерфейс доступен по `/knowledge`, редактор администратора — по `/admin/knowledge`. База организована по темам; внутри темы можно создавать статьи и вопросы, независимо менять их порядок и публикацию, а текст хранится в Markdown. Неопубликованные темы и материалы не попадают в публичные списки, прямые ссылки и результаты поиска.

Полнотекстовый поиск реализован средствами PostgreSQL: generated-колонка `TSVECTOR` использует русскую конфигурацию и разные веса для заголовка, описания и полного текста, а GIN-индекс ускоряет выборку. Отдельный поисковый сервис для MVP не требуется. `make seed` добавляет демонстрационные темы и материалы.

## Собеседования

Модуль доступен ученику по `/interviews`, административный редактор — по `/admin/interviews`. Он не связан с таблицами базы знаний и может независимо расширяться новыми сервисами, например загрузкой и разбором записей собеседований.

Каждая колода относится к треку Python или Go и видна только ученикам с доступом к нему. Перед началом ученик выбирает уже пройденные темы; без выбора сессия остаётся пустой. Выбор хранится персонально для каждой колоды, а статистика, новые вопросы и повторения считаются только внутри выбранных тем. Это не позволяет преждевременно показывать, например, архитектуру приложений ученику, который пока прошёл только основы Python.

Карточка содержит Markdown-вопрос и скрытый до переворота Markdown-ответ. После ответа ученик выбирает «Не помню», «Сложно», «Помню» или «Легко»; от оценки рассчитывается следующая дата повторения. Успешно отвеченная хотя бы раз карточка считается изученной. Новые и назначенные к повторению частые вопросы сортируются раньше редких. В интерфейсе отображаются общее количество, изученные, оставшиеся и назначенные к повторению карточки.

Миграция `20260731_0006` загружает в Python-колоду 495 карточек из `backend/migrations/data/python_interview_questions.csv`. Она сохраняет тему, компании, исходный номер и исходную частотность. Значение `Часто` преобразуется в высокий приоритет, `Средне`, `Иногда`, `Редко` и пустое значение — в обычный. Контрольная сумма файла зафиксирована в миграции, поэтому случайно изменённый источник не будет загружен частично.

Миграция `20260801_0008` переносит полный Python Backend roadmap из `backend/migrations/data/python_backend_roadmap.md`: 22 раздела, 253 материала и 2 контрольные точки для мок-собеседований. Каждый материал становится отдельной отмечаемой темой со ссылкой на источник, а внутренние блоки продвинутого Python сохраняются в описании. Роадмап публикуется в Python-треке, и доступ автоматически получают все уже зачисленные в него ученики. Если до импорта у `python-backend` было содержимое, миграция переносит его в неопубликованный архив, не удаляя прогресс.

Миграция `20260801_0009` загружает график из `backend/migrations/data/python_roadmap_schedule.csv`: 18 планируемых этапов общей длительностью 138 календарных дней. Выдача доступа больше не считается стартом обучения. Ученик запускает роадмап кнопкой «Начать прохождение», после чего API рассчитывает накопительные дедлайны разделов и дату завершения. Первый перевод темы в работу также автоматически запускает роадмап. Для уже активных учеников дата старта восстанавливается по первой сохранённой активности, поэтому существующие сроки и прогресс не сбрасываются. Длительность раздела можно менять в административном конструкторе.

Ошибки предметной области имеют форму `{"detail":{"code":"...","message":"..."}}`. Request middleware добавляет `X-Request-Id` и пишет method, path, status и duration без чувствительных заголовков.

## Тесты

Backend tests используют отдельную PostgreSQL database `mentoring_test`. Она создаётся init-скриптом нового Compose volume; `make test-backend` также безопасно пытается создать её для существующего volume. В production runtime `create_all()` не используется; оно разрешено только в изолированных тестах.

Frontend tests покрывают loading/data/error, структуру roadmap, mutation темы с обновлением UI, базу знаний и поиск, карточки собеседований, mentor list, онбординг и browser/Telegram adapters. Backend отдельно проверяет валидную, поддельную и просроченную Telegram-подпись, видимость опубликованных материалов, обновление полнотекстового индекса, доступ к колодам по треку и интервальное планирование карточек.

## Известные ограничения MVP

Нет browser OAuth/email-входа, встроенного приёма платежей, чатов и уведомлений вне интерфейса. Факт оплаты подтверждает внешний Telegram-бот. Admin создаёт треки и роадмапы, включает материалы в Python/Go, управляет доступами и базой знаний. Сохранённые разделы роадмапов пока нельзя удалить: для этого потребуется отдельный подтверждаемый сценарий с политикой хранения TopicProgress. Назначение менторов новым ученикам пока не вынесено в админку.
