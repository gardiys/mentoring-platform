# Mentoring Platform

Рабочая платформа менторской программы Python и Go Backend: ученик входит из Telegram Mini App, получает оплаченный трек, читает материалы, использует базу знаний, готовится к собеседованиям по карточкам и отмечает прогресс; назначенный ментор видит результат, а администратор управляет треками, доступами, роадмапами и материалами.

## Архитектура и стек

Проект — monorepo и модульный монолит:

- `backend/`: Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy/asyncpg, Alembic, PostgreSQL;
- `frontend/`: React, TypeScript strict, Vite, React Router, TanStack Query, Mantine, react-markdown;
- `infra/`: development Compose и production-контур с PostgreSQL, автоматическими миграциями, Nginx и Caddy/HTTPS.

Backend разделён по предметным модулям `auth`, `users`, `students`, `tracks`, `roadmaps`, `progress`, `mentors`, `knowledge`, `interviews`, `payments`, `notifications`. `LearningTrackEnrollment` определяет доступ к материалам и колодам направления, а `RoadmapEnrollment` хранит состояние прохождения. Условия выплат ученика фиксируются отдельно от снимка условий трудоустройства, поэтому уже созданный график воспроизводим. Frontend хранит серверное состояние только в TanStack Query. В Telegram исходный `initData` берётся непосредственно из SDK и не копируется в отдельное хранилище. Временный UUID хранится в `localStorage` только в development-сборке.

Архитектура, безопасный rollout, backfill и эксплуатация автоматизации карточек из AI-разборов описаны в [`docs/card-automation.md`](docs/card-automation.md).

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

## Production-деплой на VPS

Production-конфигурация рассчитана на Linux-сервер с Docker Compose, публичным доменом и открытыми портами `80/tcp`, `443/tcp` и `443/udp`. DNS-запись `A` (и `AAAA`, если используется IPv6) должна указывать на сервер. PostgreSQL и FastAPI наружу не публикуются; единственная публичная точка входа — Caddy, который автоматически получает и обновляет TLS-сертификат.

На сервере скопируйте production-шаблон:

```bash
cp .env.production.example .env.production
openssl rand -hex 32  # пароль PostgreSQL
openssl rand -hex 32  # REDIS_PASSWORD (URL-safe)
openssl rand -hex 32  # BOT_INTEGRATION_TOKEN
openssl rand -hex 32  # WEB_SESSION_SECRET
```

Заполните `.env.production`: укажите домен, email для сертификата, сгенерированные секреты, token из `@BotFather`, параметры Web Login и ссылку вида `https://t.me/your_bot`. Значение `POSTGRES_PASSWORD` в примере должно совпадать с паролем внутри `DATABASE_URL`. `REDIS_PASSWORD` должен состоять минимум из 32 URL-safe символов; внутренний `REDIS_URL` Compose соберёт автоматически. Файл `.env.production` исключён из Git, автоматически получает права `0600` при preflight и не должен отправляться в репозиторий или Telegram.

Проверить конфигурацию и запустить сервис:

```bash
make prod-init  # только при первом запуске на новом сервере
make prod-preflight
make prod-config
make prod-up
make prod-ps
curl https://platform.example.com/health
curl https://platform.example.com/ready
```

`make prod-preflight` и все production-команды, зависящие от `prod-config`, останавливаются при
оставшихся `REPLACE_*`, development-провайдерах, слабых или совпадающих секретах и небезопасных
production URL. `make prod-up` выполняет deployment последовательно: сначала собирает образы, затем поднимает
PostgreSQL и Redis, запускает Alembic отдельным одноразовым контейнером и только после успешной
миграции принудительно пересоздаёт backend, оба AI worker, worker уведомлений, frontend и Caddy. Поэтому одного запуска
достаточно и новые переменные окружения гарантированно попадают в контейнеры. Frontend собирается
в production-режиме; HTML и SPA-маршруты отдаются с `Cache-Control: no-store`, а хешированные
assets продолжают кэшироваться как immutable. `make seed` в production выполнять не нужно:
учебные данные Python импортируются миграциями, а ученики поступают из платёжного бота.

Базовые production-образы PostgreSQL, Redis, Caddy, Python, Node, Nginx и FFmpeg закреплены по
digest: деплой не подхватит неожиданно изменившийся upstream tag. PostgreSQL собирается из
`infra/postgres/Dockerfile` без уязвимого статического `gosu`, а Caddy — из
`infra/caddy/Dockerfile` на исправленной Go toolchain с зависимостями, закреплёнными в `go.sum`.
Оба постоянных процесса работают без root и без Linux capabilities; перед их запуском
`make prod-up` выполняет короткие изолированные `postgres-permissions` и `caddy-permissions`, которые
выставляют владельца только на соответствующих named volumes.
Не заменяйте эти hardened-образы прямыми upstream-тегами. Обновляйте digest и Go-зависимости
осознанно после проверки release/security notes и сканирования собранных runtime-образов. Compose разделяет
публичную `edge`, внутреннюю `data` и worker-only `egress` сети; не подключайте Caddy или frontend
к `data`, иначе они получат ненужный прямой маршрут к PostgreSQL и Redis.

После первого запуска назначьте свой Telegram-аккаунт администратором:

```bash
make prod-admin telegram_id=123456789 first_name=Антон
```

Команда идемпотентна: она создаёт пользователя или повышает существующего до роли `admin`. Затем в `@BotFather` укажите `https://platform.example.com` как URL Mini App и настройте Web Login по инструкции ниже. В production UUID-вход недоступен, а обычный браузер авторизуется через Telegram.

Обновление и обслуживание:

```bash
git pull
make prod-up       # пересобирает образы и применяет новые миграции
make prod-logs     # общие логи
make prod-backup   # PostgreSQL dump в локальный каталог backups/
make prod-down     # остановка без удаления volume с данными
```

Миграция `0036` пересчитывает появления вопросов, удаляет старые повторы и создаёт уникальный
индекс. Перед её первым production-запуском сделайте `make prod-backup` и выберите период низкой
нагрузки; на большом объёме `interview_card_occurrences` операция может временно блокировать запись.

Production-база и персистентная Redis-очередь хранятся во внешних Docker volumes
`mentoring-platform-production_postgres_data` и `mentoring-platform-production_redis_data`,
которые `docker compose down -v` не удаляет. Имена совпадают с именами volumes из предыдущей
production-конфигурации, поэтому при обновлении существующие данные подключаются без копирования.
`make prod-init` создаёт оба volume при первом развёртывании на новом сервере. Обычный
`make prod-up` проверяет их наличие и завершится с ошибкой, если один из них неожиданно пропал.

External volume защищает от случайного удаления через Compose, но пользователь с доступом к Docker всё ещё может удалить его явной командой `docker volume rm` или очисткой всех неиспользуемых volumes. Не выполняйте такие команды на production-сервере. `make prod-backup` создаёт каталог с правами `0700`, а дамп — `0600`; резервные копии всё равно нужно шифровать и выгружать за пределы сервера. Записи собеседований и офферы находятся во внешнем S3, поэтому для них отдельно включите versioning/backup-политику у провайдера объектного хранилища.

Для production нужен приватный S3-совместимый bucket. Укажите `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` и endpoint провайдера в `.env.production`. Для AWS S3 оба endpoint оставьте пустыми. Публичный anonymous-доступ включать нельзя.

Загрузка из браузера идёт напрямую в S3, поэтому bucket CORS должен разрешать origin `https://<DOMAIN>`, методы `GET`, `HEAD`, `POST` и `PUT`, заголовки `*`, а также открывать response header `ETag`. `PUT` и доступный браузеру `ETag` обязательны для загрузки отдельных multipart-частей. AWS CLI-совместимый шаблон находится в `infra/s3-cors.production.json.example`, XML-вариант для панели провайдера — в `infra/s3-cors.production.xml.example`. Перед применением замените пример origin точным значением `https://DOMAIN` из `.env.production`. Если у платформы несколько frontend-origin, перечислите каждый отдельным `AllowedOrigin`, не используйте `*` для production.

В lifecycle production-bucket настройте две независимые очистки: удаление завершённых временных объектов с префиксом `pending/` через один день и `AbortIncompleteMultipartUpload` с `DaysAfterInitiation=1` для всего bucket. Вторая политика удаляет только брошенные части и не должна содержать глобальный `Expiration`, иначе через сутки будут удаляться опубликованные материалы. Готовая стандартная S3-конфигурация находится в `infra/s3-lifecycle.production.json.example`.

Runtime credentials платформы должны позволять операции `CreateMultipartUpload`, `UploadPart`, `CompleteMultipartUpload`, `AbortMultipartUpload`, `ListMultipartUploads`, `HeadObject`, `GetObject` и `DeleteObject`. Для AWS IAM это обычно объектные действия `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:AbortMultipartUpload` и bucket-действие `s3:ListBucketMultipartUploads` только для нужного bucket. Права чтения и изменения CORS/lifecycle нужны deployment-учётке, но не обязаны выдаваться runtime-контейнерам. Названия разрешений у S3-совместимого провайдера могут отличаться.

Перед изменением сохраните существующие конфигурации. `put-bucket-cors` и `put-bucket-lifecycle-configuration` заменяют конфигурацию bucket целиком, а не добавляют правила. Если ответы `get-*` уже содержат правила, объедините их с шаблонами вручную и применяйте объединённые JSON-файлы. В частности, не потеряйте lifecycle для versioning, архивирования или резервных копий.

Из корня проекта загрузите production-переменные без вывода secrets и сопоставьте имена credentials с теми, которые понимает AWS CLI. Не включайте `set -x` для этой shell-сессии:

```bash
set -a
source .env.production
set +a
export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="$S3_REGION"
```

Сохраните текущие конфигурации в каталог резервной копии. `NoSuchCORSConfiguration` или `NoSuchLifecycleConfiguration` означает, что соответствующей конфигурации ещё нет; в этом случае не считайте пустой перенаправленный файл резервной копией:

```bash
S3_CONFIG_BACKUP_DIR="backups/s3-config-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$S3_CONFIG_BACKUP_DIR"

aws s3api get-bucket-cors \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  --bucket "$S3_BUCKET" \
  --output json > "$S3_CONFIG_BACKUP_DIR/cors.json.tmp" \
  && mv "$S3_CONFIG_BACKUP_DIR/cors.json.tmp" "$S3_CONFIG_BACKUP_DIR/cors.json"

aws s3api get-bucket-lifecycle-configuration \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  --bucket "$S3_BUCKET" \
  --output json > "$S3_CONFIG_BACKUP_DIR/lifecycle.json.tmp" \
  && mv "$S3_CONFIG_BACKUP_DIR/lifecycle.json.tmp" "$S3_CONFIG_BACKUP_DIR/lifecycle.json"
```

Создайте рабочий CORS-файл с production-origin и проверьте его перед применением:

```bash
jq --arg origin "https://$DOMAIN" \
  '.CORSRules[0].AllowedOrigins = [$origin]' \
  infra/s3-cors.production.json.example \
  > /tmp/mentoring-s3-cors.json
jq empty /tmp/mentoring-s3-cors.json
```

Если старых правил нет, скопируйте lifecycle-шаблон без изменений. Если они есть, создайте `/tmp/mentoring-s3-lifecycle.json`, содержащий и старые правила, и оба правила платформы. После ручной проверки примените полные конфигурации:

```bash
# Выполните cp только если старой lifecycle-конфигурации не было.
# Иначе сначала сохраните объединённый JSON по этому же пути.
cp infra/s3-lifecycle.production.json.example /tmp/mentoring-s3-lifecycle.json
jq empty /tmp/mentoring-s3-lifecycle.json

aws s3api put-bucket-cors \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  --bucket "$S3_BUCKET" \
  --cors-configuration file:///tmp/mentoring-s3-cors.json

aws s3api put-bucket-lifecycle-configuration \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  --bucket "$S3_BUCKET" \
  --lifecycle-configuration file:///tmp/mentoring-s3-lifecycle.json
```

Сразу перечитайте обе конфигурации теми же `get-bucket-cors` и `get-bucket-lifecycle-configuration`. Затем проверьте preflight через публичный endpoint:

```bash
curl -isS -X OPTIONS "${S3_PUBLIC_ENDPOINT_URL%/}/${S3_BUCKET}/multipart-smoke/object" \
  -H "Origin: https://${DOMAIN}" \
  -H 'Access-Control-Request-Method: PUT' \
  -H 'Access-Control-Request-Headers: content-type' \
  | grep -iE 'HTTP/|access-control-allow-origin|access-control-allow-methods|access-control-expose-headers'
```

Ответ должен разрешать точный origin платформы и метод `PUT`. Конфигурация или ответ должны открывать `ETag`; некоторые S3-провайдеры не возвращают `Access-Control-Expose-Headers` на `OPTIONS`, поэтому окончательно проверьте его на фактическом `UploadPart` в DevTools: ответ `PUT` должен содержать читаемый frontend-кодом header `ETag`.

Multipart использует части по 64 MiB (`S3_MULTIPART_PART_SIZE_BYTES`), presigned URL отдельной части сроком на шесть часов (`S3_MULTIPART_PRESIGN_TTL_SECONDS`) и upload-сессию сроком на сутки (`S3_MULTIPART_SESSION_TTL_SECONDS`). Отдельный TTL нужен для медленных загрузок до 5 GiB; общий `S3_PRESIGN_TTL_SECONDS=900` продолжает применяться к legacy upload/download и не меняется. Размер части не должен быть меньше 5 MiB; уменьшение размера резко увеличивает число запросов. Срок upload-сессии и `AbortIncompleteMultipartUpload` должны оставаться согласованными, чтобы пользователь не продолжал уже очищенную сессию.

Безопасный порядок production rollout: сначала примените CORS и lifecycle bucket, затем разверните backend и только после его readiness — frontend. Миграция БД не требуется. Старый frontend не передаёт `upload_protocol` и продолжает использовать legacy presigned POST; новый frontend явно запрашивает `multipart-v1`. Поэтому backend можно развернуть заранее без остановки загрузок. Для rollback сначала верните старый frontend, а новый backend сохраняйте как минимум на `S3_MULTIPART_SESSION_TTL_SECONDS` либо до завершения всех уже начатых multipart-загрузок; старый backend не умеет завершать такие сессии. Multipart-сессия хранится в S3 и подписанном токене, поэтому переживает перезапуск совместимого backend в пределах этого TTL, пока credentials и signing secrets не меняются.

После сборки нового backend выполните реальный provider smoke: команда создаёт upload через тот же код, что использует приложение, загружает 6 MiB по публичному presigned PUT URL, проверяет CORS для `WEB_FRONTEND_URL` и доступность `ETag`, завершает upload, проверяет объект через `HEAD` и удаляет его. `finally` дополнительно пытается прервать незавершённую сессию и удалить временный ключ; secrets и подписанные URL в вывод не попадают.

```bash
make prod-check-s3-multipart
```

Smoke использует внутренний `S3_ENDPOINT_URL` для создания/завершения сессии и `S3_PUBLIC_ENDPOINT_URL` для фактического PUT с browser-origin. После развёртывания frontend всё равно выполните небольшую загрузку из базы знаний и убедитесь в DevTools, что все `PUT` частей получили `2xx`, каждый ответ содержит доступный `ETag`, а запрос завершения вернул `2xx`.

Для FirstVDS используйте API endpoint `https://s3.firstvds.ru` и регион `default` — именно эти значения указаны в документации провайдера. `S3_ENDPOINT_URL` доступен backend-контейнеру, а `S3_PUBLIC_ENDPOINT_URL` должен открываться из браузера. Архивные записи из bucket `interviews` также читаются через авторизованный S3 API: личный дневник получает временный presigned URL, а защищённый URL каталога после проверки playback-ticket перенаправляет браузер на ещё более короткую подписанную ссылку. Прямой URL объекта в private bucket без `X-Amz-*` параметров должен отвечать `403` — это ожидаемое поведение.

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

## Заявки из onboarding-бота

Администратор управляет всей воронкой кандидатов на странице `/admin/applications`: видит
короткую и безопасную часть подробной анкеты, историю статусов, созвоны и платежи, а также
выполняет доступные для текущего этапа действия. Backend платформы проксирует команды в
`codewaste-onboarding`; интеграционный токен никогда не передаётся браузеру.

Для локальной разработки запустите API onboarding-бота на порту `8001` и добавьте:

```dotenv
ONBOARDING_BOT_API_BASE_URL=http://host.docker.internal:8001
ONBOARDING_BOT_INTEGRATION_TOKEN=replace-with-random-secret
ONBOARDING_BOT_TIMEOUT_SECONDS=15
```

Значение `ONBOARDING_BOT_INTEGRATION_TOKEN` должно совпадать с
`MENTORING_PLATFORM_INTEGRATION_TOKEN` в `codewaste-onboarding`. Для обратного создания
оплаченного ученика тот же секрет задаётся в `BOT_INTEGRATION_TOKEN` платформы.

Обычный браузер не загружает SDK с `telegram.org`: это исключает долгую блокировку страницы в сетях, где Telegram недоступен. При запуске внутри Mini App frontend распознаёт параметры `tgWebApp*` и асинхронно подключает закреплённую копию SDK со своего домена (`/vendor/telegram-web-app-2026-07-14.js`). Ожидание ограничено тремя секундами, а подписанный `tgWebAppData` остаётся доступен для авторизации даже при ошибке загрузки SDK. Происхождение и контрольная сумма локальной копии описаны в `frontend/public/vendor/README.md`.

## Уведомления и Telegram

Колокольчик показывает персональные события платформы. Telegram-сообщения сохраняются в outbox
в той же транзакции, что и событие, а `notification-worker` отправляет их отдельно с повторными
попытками и защитой от дублей. Для production добавьте:

```dotenv
# ID супергруппы/чата «Паровоз собеседований»; оставьте пустым, чтобы не публиковать в чат.
TELEGRAM_INTERVIEW_CHAT_ID=-1001234567890
# ID конкретного forum topic; оставьте пустым для общего чата.
TELEGRAM_GROUP_TOPIC_ID=123
# Маршрутизация по направлениям. Эти значения имеют приоритет над общими выше.
TELEGRAM_INTERVIEW_PYTHON_CHAT_ID=-1001111111111
TELEGRAM_INTERVIEW_PYTHON_TOPIC_ID=
TELEGRAM_INTERVIEW_GO_CHAT_ID=-1002222222222
TELEGRAM_INTERVIEW_GO_TOPIC_ID=
# Оставьте пустым при прямом доступе. Допустимо использовать тот же HTTP(S)-proxy, что для OAuth.
TELEGRAM_BOT_PROXY_URL=
NOTIFICATION_REMINDER_TIMEZONE=Europe/Moscow
NOTIFICATION_REMINDER_HOUR=10
# Напоминать ученику о ближайшем групповом/разовом созвоне за 30 минут.
TELEGRAM_GROUP_CALL_REMINDERS_ENABLED=true
TELEGRAM_GROUP_CALL_REMINDER_MINUTES=30
# Ежедневно напоминать активным ученикам о дейлике в 20:00.
TELEGRAM_DAILY_REMINDERS_ENABLED=true
TELEGRAM_DAILY_REMINDER_HOUR=20
```

Бот должен быть добавлен в чат и иметь право отправлять сообщения. Для личных напоминаний о
платежах, созвонах и дейлике ученик должен хотя бы один раз открыть бота: Telegram не позволяет
боту первым начать личный диалог. Напоминания о созвонах учитывают направление, назначенного
ментора и разовый перенос времени. Ученикам со статусом «закончили обучение», исключённым и с
закрытым доступом дейлики не отправляются. Ссылки из сообщений ведут на авторизованные страницы
платформы или на HTTPS-встречу; private S3 URL в Telegram не публикуются.

В локальной разработке `http://localhost:5173` нельзя использовать в Telegram inline-кнопке:
этот адрес существует только на компьютере разработчика. Поэтому worker отправит локальное
smoke-сообщение без кнопки. Для проверки перехода укажите публичный HTTPS URL туннеля в
`WEB_FRONTEND_URL`; на production кнопка ведёт на `https://${DOMAIN}` автоматически.

## Вход через обычный браузер

Браузерная авторизация использует Telegram OpenID Connect Authorization Code Flow с PKCE. В `@BotFather` откройте Bot Settings → Web Login и добавьте оба Allowed URL:

```text
https://platform.example.com
https://platform.example.com/api/v1/auth/web/telegram/callback
```

Скопируйте показанные BotFather Client ID и Client Secret в `.env.production`:

```dotenv
TELEGRAM_WEB_CLIENT_ID=replace-with-client-id
TELEGRAM_WEB_CLIENT_SECRET=replace-with-client-secret
TELEGRAM_OIDC_PROXY_URL=
WEB_SESSION_SECRET=replace-with-openssl-rand-hex-32
WEB_SESSION_TTL_SECONDS=2592000
```

После `make prod-up` откройте `https://platform.example.com/login` и нажмите «Войти через Telegram». Backend проверяет `state`, PKCE и подпись ID token по JWKS Telegram, затем ищет существующего пользователя по `telegram_id`. Если платёжный бот ещё не выдал доступ, аккаунт не создаётся. Успешный вход устанавливает host-only HttpOnly cookie с `Secure` и `SameSite=Lax`; Telegram ID token во frontend не сохраняется. Кнопка выхода удаляет эту cookie.

Исходящие OIDC-запросы используют IPv4 и повторяются при ошибке подключения. Если VPS полностью блокирует `oauth.telegram.org:443`, задайте доверенный HTTPS/HTTP proxy в `TELEGRAM_OIDC_PROXY_URL`; при прямом доступе оставьте переменную пустой.

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
    "telegram_username": "ivan_backend",
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "track_slug": "python",
    "repayment_percent": 200,
    "mentor_reward_percent": 60,
    "entry_payment_rubles": 45000,
    "entry_payment_paid": true
  }'
```

Endpoint доверяет боту проверку факта оплаты, создаёт или обновляет ученика (включая Telegram username, если он передан), завершает платформенный онбординг и выдаёт выбранный опубликованный трек со всеми входящими в него опубликованными роадмапами. Повторный запрос идемпотентен: дубликаты пользователя и доступа не создаются. Если доступ ученика был закрыт администратором, новый подтверждённый платёж снова активирует аккаунт. В production endpoint должен вызываться только backend-процессом бота по HTTPS; `BOT_INTEGRATION_TOKEN` нельзя передавать во frontend или Mini App.

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

Development Compose автоматически запускает приватный MinIO, создаёт bucket и настраивает CORS для `http://localhost:5173`. Закреплённый MinIO OSS использует глобальный CORS через `MINIO_API_CORS_ALLOW_ORIGIN`; bucket-level `PutBucketCors` в OSS-редакции недоступен. Временные объекты `pending/` удаляются lifecycle-правилом из `infra/minio-lifecycle.json`, а незавершённые multipart-загрузки старше суток — эквивалентной серверной очисткой `MINIO_API_STALE_UPLOADS_EXPIRY=24h`. S3 API доступен на `http://localhost:9000`, консоль MinIO — на `http://localhost:9001`; локальные ключи берутся из `.env.example`. Загружаемые файлы сохраняются в Docker volume `minio_data`.

Для `make api-generate` backend должен быть доступен по `OPENAPI_URL` (по умолчанию `http://localhost:8000/openapi.json`). Сгенерированный файл — единственный источник DTO frontend; прикладные aliases находятся в `frontend/src/types/api.ts`.

## Development-пользователи

Seed всегда выводит UUID и создаёт:

- ученик Иван: `20000000-0000-4000-8000-000000000001`;
- ментор Антон: `10000000-0000-4000-8000-000000000001`.
- администратор: `90000000-0000-4000-8000-000000000001`.

Кнопки быстрого входа читают эти значения из `VITE_DEV_STUDENT_ID` и `VITE_DEV_MENTOR_ID`; UUID не зашиты в production-компоненты.

Временная browser-авторизация отправляет `X-Dev-User-Id` только в dev-сборке. Telegram-авторизация проверяет подпись и срок действия `initData` в `backend/app/auth`, автоматически связывает пользователя по `telegram_id` и обновляет имя и username из Telegram. Telegram SDK изолирован в `frontend/src/platform`: там находятся инициализация, тема, BackButton, viewport и haptic feedback.

## API

- `GET /health`, `GET /ready`;
- `GET /api/v1/me`;
- `GET /api/v1/auth/web/telegram/start` и `GET /api/v1/auth/web/telegram/callback` — браузерный Telegram OIDC;
- `POST /api/v1/auth/web/logout` — завершить браузерную сессию;
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
- `GET /api/v1/interviews/journal/companies?q=...` — ранжированные подсказки общего справочника компаний;
- `GET /api/v1/interviews/catalog/companies?q=...` — компании с треками учеников и поиском по алиасам;
- `GET /api/v1/interviews/catalog/companies/{company_id}` — авторы, этапы, описания, записи, файлы и комментарии;
- `POST /api/v1/interviews/catalog/stages/{stage_id}/comments` — обратная связь к конкретному собеседованию;
- `DELETE /api/v1/interviews/catalog/comments/{comment_id}` — удалить собственный комментарий;
- `GET/POST /api/v1/interviews/journal/tracks` — личные треки собеседований ученика;
- `GET/PUT /api/v1/interviews/journal/tracks/{process_id}` — компания и полная история этапов;
- `PATCH /api/v1/interviews/journal/tracks/{process_id}/outcome` — закрыть процесс с причиной либо отметить оффер;
- `POST/PUT /api/v1/interviews/journal/tracks/{process_id}/stages/...` — добавить или изменить этап;
- `POST .../media/upload`, прямой S3 POST и `POST .../media/complete` — двухфазная загрузка записи;
- `GET .../media?inline=true` — защищённая ссылка для проигрывания записи на портале;
- аналогичные `.../attachments/upload`, `.../attachments/complete` и GET/DELETE — дополнительные файлы этапа;
- аналогичные `.../offer/upload`, `.../offer/complete`, а также защищённые GET/DELETE — файл оффера;
- `GET /api/v1/mentor/students`;
- `GET /api/v1/mentor/students/{student_id}`.
- `GET /api/v1/payments/me` и `PUT /api/v1/payments/me/schedule` — личный график и два платёжных дня;
- `POST /api/v1/payments/installments/{installment_id}/link` — платёжная ссылка Точка Банка;
- `GET /api/v1/mentor/students/{student_id}/payments` — график ученика;
- `PUT /api/v1/mentor/students/{student_id}/employment` — создать или обновить трудоустройство;
- `POST /api/v1/mentor/students/{student_id}/employment/terminate` — увольнение и отмена остатка графика;
- `GET /api/v1/mentor/rewards` — начисленные вознаграждения ментора;
- `POST /api/v1/mentor/payouts` — создать одну открытую заявку на выплату выбранной суммы;
- `POST /api/v1/mentor/payouts/{payout_id}/receipt/...` — опционально загрузить приватный чек после выплаты;
- `GET /api/v1/admin/payments` — реестр платежей и вознаграждений;
- `GET /api/v1/admin/payments/students` — активные трудоустройства с непогашенным остатком;
- `GET /api/v1/admin/payments/students/{student_id}` — полный график конкретного ученика;
- `GET /api/v1/admin/payments/overdue` — отдельный реестр всех просроченных взносов;
- `GET /api/v1/admin/payments/mentor-payouts` — агрегированные балансы и заявки менторов;
- `GET /api/v1/admin/payments/mentors/{mentor_id}` — баланс ментора с источниками начислений;
- `POST /api/v1/admin/payments/mentors/{mentor_id}/payouts` — выплатить весь доступный баланс или его часть;
- `POST /api/v1/admin/payments/payouts/{payout_id}/mark-paid` — подтвердить заявку ментора;
- `PATCH /api/v1/admin/payments/payouts/{payout_id}` — исправить сумму, дату, акт или комментарий выплаты с обязательной причиной;
- `POST /api/v1/admin/payments/payouts/{payout_id}/cancel` — отменить ошибочную выплату и вернуть сумму в доступный баланс;
- `POST /api/v1/admin/payments/rewards/{reward_id}/void` — убрать ошибочное начисление из баланса ментора с сохранением аудита;
- `POST /api/v1/admin/payments/installments/{installment_id}/confirm` — ручное подтверждение платежа;
- `POST /api/v1/admin/payments/installments/{installment_id}/revoke` — отменить ошибочное подтверждение с обязательной причиной;
- `POST /api/v1/admin/payments/rewards/{reward_id}/mark-paid` — отметить выплату ментору;
- `GET/POST /api/v1/admin/students` — таблица с поиском, фильтром доступа и создание ученика;
- `GET/PUT /api/v1/admin/students/{student_id}` — личные данные и назначенные треки;
- `PATCH /api/v1/admin/students/{student_id}/access` — закрыть или восстановить доступ без удаления прогресса;
- `GET /api/v1/admin/students/options` — треки для формы ученика;
- `GET /api/v1/admin/roadmaps` — все роадмапы, включая черновики;
- `POST /api/v1/admin/roadmaps` — атомарное создание roadmap с разделами и темами.
- `GET /api/v1/admin/roadmaps/{roadmap_id}` — данные для редактора;
- `PUT /api/v1/admin/roadmaps/{roadmap_id}` — обновление структуры с сохранением UUID.
- `GET /api/v1/admin/roadmaps/summaries` и `GET/PATCH /api/v1/admin/roadmaps/{roadmap_id}/outline` — облегчённые список и структура без Markdown;
- `POST/GET/PUT /api/v1/admin/roadmaps/{roadmap_id}/sections/...` — точечное создание и редактирование разделов и тем.
- `GET/POST /api/v1/admin/tracks` — список и создание треков обучения;
- `GET/PUT /api/v1/admin/tracks/{track_id}` — состав и настройки трека;
- `GET /api/v1/admin/tracks/options` — доступные роадмапы и ученики;
- `PUT/DELETE /api/v1/admin/tracks/{track_id}/students/{student_id}` — выдать или отозвать доступ.
- `GET/POST /api/v1/admin/knowledge/topics` — список и создание тем базы знаний;
- `GET/PUT /api/v1/admin/knowledge/topics/{topic_id}` — редактирование темы, статей и вопросов.
- `GET /api/v1/admin/knowledge/topics/summaries`, `GET/PATCH .../{topic_id}/outline` и `POST/GET/PUT .../{topic_id}/entries/...` — облегчённый табличный редактор и точечные операции.
- `GET/POST /api/v1/admin/interviews/decks` — список и создание колод интервью;
- `GET/PUT /api/v1/admin/interviews/decks/{deck_id}` — редактирование карточек колоды.
- `GET /api/v1/admin/interviews/decks/summaries`, `GET .../{deck_id}/cards?limit=50&offset=...` и `POST/GET/PUT .../{deck_id}/cards/...` — краткие списки, поиск, пагинация и редактирование одной карточки.

Полноценная админка учеников доступна по `/admin/students`: в таблице есть поиск по имени, email и Telegram ID, фильтр открытого/закрытого доступа, треки и дата последней отметки прогресса. Администратор может создать ученика, изменить личные данные и назначения Python/Go, а также обратимо закрыть доступ. Блокировка применяется ко всем способам входа, но не удаляет аккаунт, треки или прогресс.

Admin frontend для треков доступен по `/admin/tracks`: администратор включает роадмапы в направления Python/Go и управляет доступом учеников. Конструктор контента доступен по `/admin/roadmaps`. Создание поддерживает вложенную структуру, а редактирование показывает разделы и темы таблицами и открывает только одну запись с Markdown-контентом. Точечное сохранение сохраняет UUID и прогресс существующих тем, а отзыв трека не удаляет историю прогресса.

## База знаний

Пользовательский интерфейс доступен по `/knowledge`, редактор администратора — по `/admin/knowledge`. База организована по темам; внутри темы материалы показаны таблицей, а каждая статья или вопрос редактируются на отдельной странице. Полный Markdown не загружается в общий список. Неопубликованные темы и материалы не попадают в публичные списки, прямые ссылки и результаты поиска.

К статьям базы знаний и темам роадмапов администратор может прикреплять приватные аудио- и видеоматериалы. Для новых видео принимаются MP4 и MOV: только эти контейнеры проходят обязательную проверку и подготовку к браузерному воспроизведению. Видео учебных материалов ограничено 5 GiB параметром `CONTENT_VIDEO_MAX_BYTES`; это отдельный лимит и он не изменяет ограничение записей собеседований `INTERVIEW_VIDEO_MAX_BYTES`, которое по умолчанию остаётся равным 2 GiB.

После завершения загрузки MP4/MOV не публикуется сразу: отдельный `content-media-worker`
проверяет контейнер и без перекодирования перепаковывает H.264/AAC в обычный MP4 с индексом в
начале файла. Это устраняет тысячи мелких последовательных Range-запросов, характерных для
fragmented MP4, и не меняет качество записи. До завершения интерфейс показывает статус
«Подготавливаем видео»; при безопасно классифицированной ошибке администратор может повторить
операцию. Состояние хранится в PostgreSQL, а worker периодически восстанавливает задачи после
перезапуска Redis или контейнера. Миграция `20260805_0035` автоматически ставит уже загруженные
MP4/MOV в очередь, поэтому повторно загружать существующие файлы не нужно. Пока идёт фоновая
обработка старого материала, его исходная версия остаётся доступна в плеере; новый объект
подменяет её только после полной проверки.

Нормализация выполняется асинхронно в отдельном disk-backed volume, по одной записи одновременно.
Для максимального файла 5 GiB на production-хосте нужно не менее 12–15 GiB свободного места:
worker временно хранит исходник и результат, а затем гарантированно очищает staging. Исходный
S3-объект сохраняется до успешной проверки и атомарного переключения записи в БД. Лимиты и путь
задаются переменными `CONTENT_MEDIA_NORMALIZATION_*`; Compose запускает worker автоматически,
без Compose используется `make worker-media`.

Полнотекстовый поиск реализован средствами PostgreSQL: generated-колонка `TSVECTOR` использует русскую конфигурацию и разные веса для заголовка, описания и полного текста, а GIN-индекс ускоряет выборку. Отдельный поисковый сервис для MVP не требуется. `make seed` добавляет демонстрационные темы и материалы.

## Собеседования

Модуль доступен ученику по `/interviews`, административный редактор — по `/admin/interviews`. В админке вопросы показаны таблицей с поиском и серверной пагинацией по 50 строк; полный ответ загружается только при открытии одной карточки. Модуль не связан с таблицами базы знаний и может независимо расширяться новыми сервисами, например загрузкой и разбором записей собеседований.

Каждая колода относится к треку Python или Go и видна только ученикам с доступом к нему. Перед началом ученик выбирает уже пройденные темы; без выбора сессия остаётся пустой. Выбор хранится персонально для каждой колоды, а статистика, новые вопросы и повторения считаются только внутри выбранных тем. Это не позволяет преждевременно показывать, например, архитектуру приложений ученику, который пока прошёл только основы Python.

Карточка содержит Markdown-вопрос и скрытый до переворота Markdown-ответ. После ответа ученик выбирает «Не помню», «Сложно», «Помню» или «Легко»; от оценки рассчитывается следующая дата повторения. Успешно отвеченная хотя бы раз карточка считается изученной. Новые и назначенные к повторению частые вопросы сортируются раньше редких. В интерфейсе отображаются общее количество, изученные, оставшиеся и назначенные к повторению карточки.

В том же пользовательском разделе находится личный дневник собеседований. При создании трека компании ученик обязательно выбирает опубликованное направление платформы — сейчас Python или Go — и может указать до 20 Telegram-никнеймов рекрутеров. Контакты можно отредактировать позднее на странице трека. Ученик добавляет любое количество этапов с типом, датой и описанием, а затем закрывает процесс с обязательной причиной либо отмечает получение оффера. Закрытый после отказа процесс можно восстановить, продолжить новыми этапами и позднее отметить оффером; прежняя причина отказа остаётся в истории. Поддерживаются скрининг, технический скрининг, техническое интервью, системный дизайн, финальное интервью и произвольный тип. К этапу можно прикрепить основную аудио- или видеозапись и до 20 дополнительных файлов либо изображений. Запись проигрывается прямо в карточке этапа; изображения и PDF можно открыть по защищённой inline-ссылке. К офферу прикрепляется PDF либо изображение. Все endpoint-ы личного дневника проверяют владельца через `process_id + user_id`; другой ученик получает 404 при чтении или любой попытке изменения и может увидеть трек только через read-only каталог. Обязательное направление и перенос существующих процессов создаются миграцией `20260801_0016`.

Каталог собеседований доступен только активным ученикам и группирует накопленный опыт по компаниям. Каталог автоматически ограничивается выданными ученику направлениями: Python-ученик видит только Python, Go-ученик — только Go, а при одновременном доступе доступны оба направления. Это ограничение действует также для прямых ссылок на компанию, записи, вложения и комментарии. Поиск можно сузить по автору, направлению, типу этапа, наличию оффера, отдельно по видео или аудио и общим условием «есть видео или аудио»; выбранные условия применяются к одному треку одновременно и сохраняются при переходе в компанию. В списке авторов и карточках показываются имя и Telegram username без фамилии. Карточка трека также содержит Telegram-контакты рекрутеров, статус процесса, даты, типы и описания этапов, записи, дополнительные материалы и обсуждение каждого собеседования. Ученики могут оставлять фидбек и удалять собственные комментарии. Файл оффера в каталог не публикуется, поскольку может содержать персональные и финансовые данные. Комментарии создаются миграцией `20260801_0015`.

Компании хранятся в общем нормализованном справочнике. Поиск не зависит от регистра, пробелов и пунктуации, учитывает транслитерацию и распространённые фонетические варианты: например, `Yandex` находит `Яндекс`, а `Т-банк` — `Тбанк`. При сохранении удаляются юридические формы `ИП`, `ООО`, `ОАО`, `ЗАО`, `ПАО`, `АО`, `LLC`, `Ltd` и аналогичные. Если ученик вводит одно название, но выбирает другую существующую компанию, интерфейс отдельно спрашивает, является ли введённый текст альтернативным названием. Алиас сохраняется только после явного подтверждения; при отказе трек создаётся для выбранной компании без новой связи. Если ученик вообще не выбрал подсказку, перед созданием платформа повторно получает актуальные совпадения и предлагает либо явно связать ввод с одной из компаний, либо подтвердить создание новой. Уже существующий дубль при подтверждённом связывании объединяется с канонической компанией, а связанные треки перепривязываются к ней. Миграция `20260801_0012` создаёт нормализованный справочник, а `20260801_0013` добавляет алиасы и фонетические ключи поиска.

Файлы загружаются из браузера прямо в приватный S3 частями по подписанным multipart PUT URL и не проходят через память или диск FastAPI. Backend фиксирует допустимый MIME-тип, полный размер и размер каждой части в подписанной upload-сессии, после завершения повторно проверяет объект через `HEAD` и только затем сохраняет связь в БД. Старый presigned POST временно поддерживается как совместимый fallback для поэтапного rollout. В личном дневнике скачивание и inline-просмотр начинаются с авторизованного запроса и используют короткоживущую подписанную ссылку. В каталоге, базе знаний и материалах роадмапа авторизованный запрос создаёт HttpOnly-сессию просмотра, привязанную к пользователю и браузеру. Стабильный URL плеера проверяет эту сессию при каждом новом обращении и перенаправляет браузер на подписанный S3 URL с коротким TTL; поэтому HTTP Range обслуживает само хранилище, а тяжёлый видеопоток больше не проходит через FastAPI и Caddy. Срок playback-сессии задаётся через `INTERVIEW_STREAM_TICKET_TTL_SECONDS` (по умолчанию 10 минут), а TTL подписанной ссылки на S3 — через `MEDIA_STREAM_REDIRECT_TTL_SECONDS` (по умолчанию 15 минут, как для личных записей собеседований). Плеер при сетевом сбое один раз автоматически обновляет доступ, восстанавливает позицию и продолжает воспроизведение. Плеер скрывает скачивание, запрещает контекстное меню и показывает предупреждающий watermark. Абсолютную защиту воспроизводимого медиа от записи экрана может дать только специализированный DRM, поэтому текущая защита рассчитана на предотвращение постоянных публичных ссылок, обычного копирования и случайного скачивания. Лимиты по умолчанию: видео — 2 GiB, аудио — 500 MiB, PDF/изображение оффера — 20 MiB, дополнительное вложение этапа — 50 MiB; они задаются через `INTERVIEW_VIDEO_MAX_BYTES`, `INTERVIEW_AUDIO_MAX_BYTES`, `INTERVIEW_OFFER_MAX_BYTES` и `INTERVIEW_ATTACHMENT_MAX_BYTES`. Коллекция вложений создаётся миграцией `20260801_0014`.

Миграция `20260731_0006` загружает в Python-колоду 495 карточек из `backend/migrations/data/python_interview_questions.csv`. Она сохраняет тему, компании, исходный номер и исходную частотность. Значение `Часто` преобразуется в высокий приоритет, `Средне`, `Иногда`, `Редко` и пустое значение — в обычный. Контрольная сумма файла зафиксирована в миграции, поэтому случайно изменённый источник не будет загружен частично.

Миграция `20260801_0008` переносит полный Python Backend roadmap из `backend/migrations/data/python_backend_roadmap.md`: 22 раздела, 253 материала и 2 контрольные точки для мок-собеседований. Каждый материал становится отдельной отмечаемой темой со ссылкой на источник, а внутренние блоки продвинутого Python сохраняются в описании. Роадмап публикуется в Python-треке, и доступ автоматически получают все уже зачисленные в него ученики. Если до импорта у `python-backend` было содержимое, миграция переносит его в неопубликованный архив, не удаляя прогресс.

Миграция `20260801_0009` загружает график из `backend/migrations/data/python_roadmap_schedule.csv`: 18 планируемых этапов общей длительностью 138 календарных дней. Выдача доступа больше не считается стартом обучения. Ученик запускает роадмап кнопкой «Начать прохождение», после чего API рассчитывает накопительные дедлайны разделов и дату завершения. Первый перевод темы в работу также автоматически запускает роадмап. Для уже активных учеников дата старта восстанавливается по первой сохранённой активности, поэтому существующие сроки и прогресс не сбрасываются. Длительность раздела можно менять в административном конструкторе.

Миграция `20260801_0017` импортирует архив пользователей, компаний и собеседований из `legacy_users.csv`, `legacy_companies.csv` и `legacy_interviews.csv`. Из 238 исходных пользователей загружаются 219 записей — все, кроме 19 пользователей со статусом `Гость`. `Менти` и `Выпускник` становятся учениками, `Ментор` — ментором, `CEO` — администратором; направления Python/Go переносятся в доступы к учебным трекам, а для старых учеников без заполненного направления используется Python. Существующие пользователи сопоставляются по Telegram ID и не перезаписываются.

Миграция `20260815_0059` догружает последние 34 собеседования из Шу: данные образуют
31 пару «ученик + компания», поэтому новые этапы добавляются в уже существующие архивные
треки без дублей или создают отдельные закрытые треки. Семь новых исходных company ID
сопоставляются с каталогом по нормализованному названию, а отсутствующие компании создаются.
Импорт содержит 30 внешних S3-записей и не публикует миграционные события в Telegram.

Названия и альтернативные названия компаний проходят ту же нормализацию, что и каталог: 694 исходные строки образуют 638 канонических компаний и 156 алиасов. После объединения дублей интервью одного автора в одной компании собираются в единый закрытый исторический трек: импорт создаёт 1697 треков и 2463 этапа, исключая 36 интервью гостей. Типы старых этапов преобразуются в актуальный справочник, даты и тексты сохраняются. Миграция `20260801_0019` извлекает валидные Telegram usernames рекрутеров из CSV, объединяет дубликаты и добавляет 1764 контакта в 1624 архивных трека; старые строки с рекрутером удаляются из описаний, чтобы данные не дублировались. 2152 существующие аудио- и видеозаписи продолжают читаться из внешнего S3 через защищённый backend-плеер без повторного копирования файлов. Контрольные суммы всех трёх CSV зафиксированы в миграциях.

Чувствительные legacy-выгрузки пользователей, интервью, платежей, связей с менторами и ведомостей выплат намеренно исключены из новых Docker build contexts через `backend/.dockerignore` и не попадают в migration image. При отсутствии этих файлов исторические data-миграции пропускают только импорт данных; создание чистой схемы продолжается. Production-историю следует восстанавливать из проверенного зашифрованного DB backup. Если импорт действительно нужно повторить при создании новой БД, файлы передаются миграционному контейнеру явно и только на время одного запуска как read-only secret/bind mounts в `/app/migrations/data/<имя файла>`; после успешной миграции mounts и исходные файлы удаляются с сервера. На БД, где Alembic revision уже отмечен выполненным, эти миграции автоматически повторно не запускаются — используйте восстановление backup либо отдельную контролируемую import-задачу.

Перед обновлением существующей production БД проверьте её `alembic_version`. Если она ещё не прошла legacy revisions `20260801_0017`–`20260811_0045`, но исторические записи должны сохраниться, сначала восстановите актуальный DB backup либо подготовьте полный одноразовый набор read-only mounts. Запуск неполного набора безопасно пропустит соответствующий импорт и отметит revision выполненным; это режим для новой пустой установки без legacy-истории, а не способ частичного восстановления архива.

Эта защита относится только к новым build contexts и образам. Она не удаляет уже закоммиченные CSV из Git history и не очищает ранее собранные образы или registry cache. Полная очистка истории, ротация доступов и удаление старых image layers выполняются отдельной согласованной процедурой, чтобы не переписать общую историю репозитория неожиданно для команды.

Ошибки предметной области имеют форму `{"detail":{"code":"...","message":"..."}}`. Request middleware добавляет `X-Request-Id` и пишет method, path, status и duration без чувствительных заголовков.

## Платежи учеников и вознаграждения менторам

Администратор задаёт процент выплат при создании или редактировании ученика. Миграция выставляет
`150%` существующим ученикам только Go-направления и `200%` остальным; значение можно изменить до
первого подтверждённого платежа. В той же форме задаются вступительный платёж (по умолчанию
`45 000 ₽`) и доля ментора от одной зарплаты: по умолчанию `60%` для Python и `45%` для Go, но оба
процента редактируются отдельно для каждого ученика.

После фиксации компании, даты выхода и зарплаты на руки система создаёт взносы по `25%` зарплаты.
Первый срок — первый выбранный платёжный день не раньше чем через календарный месяц после выхода,
затем используются два дня в каждом месяце. По умолчанию это 10-е и 25-е; ученик или администратор
может выбрать любые два разных дня с 1-го по 28-е. Оплаченные и уже просроченные сроки при таком
изменении не переносятся.

Трудоустройства хранятся как история. При увольнении все неоплаченные взносы этого места работы
получают статус «отменён», а уже оплаченный процент сохраняется. Следующее трудоустройство создаёт
график только на остаток договорного процента: например, после выплаты `75%` из `200%` новый график
будет рассчитан на `125%` новой зарплаты. Если платежей не было, на новом месте создаётся полный
график. Исключение ученика из программы также закрывает доступ и отменяет активный неоплаченный
график.

После подтверждения вступительного платежа ментору единоразово начисляется `10 000 ₽`. Ещё
`10 000 ₽` начисляется при явном исключении ученика из программы. Зарплатная часть начисляется
только вслед за фактическим платежом ученика. Формула сохраняет согласованную итоговую долю:
`платёж ученика × процент ментора / договорный процент ученика`. Поэтому при условиях `200% / 60%`
платёж ученика в `25%` зарплаты создаёт вознаграждение ментору в `7,5%` зарплаты.

Администратор выплачивает не отдельные начисления, а весь доступный баланс ментора либо любую его
часть. Сумма распределяется по начислениям в порядке их создания. Ментор может создать одну
открытую заявку на конкретную сумму; она резервирует соответствующую часть баланса и защищает от
повторной выплаты. Администратор указывает номер акта или комментарий и подтверждает заявку либо
отменяет её, освобождая резерв. После подтверждения ментор при необходимости загружает приватный
PDF или изображение чека размером до 20 МБ. Чек необязателен и не блокирует закрытие выплаты.
Администратор может исправить сумму, дату и комментарий выплаты. Распределение по начислениям при
этом пересчитывается, а исходное и новое значения сохраняются в журнале изменений. Ошибочная
выплаченная сумма отменяется только с обязательной причиной: деньги возвращаются в доступный
баланс ментора, а сама запись остаётся в аудите со статусом «Отменена» вместо физического удаления.
Повторное архивное начисление можно удалить на странице конкретного ментора. Оно перестаёт
участвовать во всех балансах и исчезает из личного кабинета ментора, но сохраняется в базе с датой,
администратором и причиной удаления. Начисление внутри открытой заявки или завершённой выплаты
сначала требует отменить связанную заявку либо выплату — это защищает распределённые суммы от
тихого рассогласования.

Миграция `20260811_0042` переносит 73 исторических трудоустройства и 607 платежей учеников.
Следующая миграция `20260811_0043` загружает семь ведомостей менторов: после исключения старых
пользователей со статусом «Гость» и подтверждённых исключённых учеников создаётся 186 начислений.
Фактические выплаты объединяются в одну архивную выплату на каждого из семи менторов, а доступный
остаток первоначально сохраняется по каждому исходному начислению. Миграция `20260811_0045`
сверяет зарплатные начисления с фактически оплаченными взносами из `0042`: невыплаченная учеником
будущая часть перестаёт быть доступной ментору, а уже состоявшиеся исторические выплаты остаются
неизменными. Исторические фиксированные `10 000 ₽`, для
которых источник не различает вступление и исключение, помечаются отдельным архивным типом.
Контрольные суммы CSV, число строк и итоговые суммы проверяются до завершения миграции.
Миграция `20260812_0047` добавляет аудит удаления ошибочных начислений без физического удаления
финансовых строк.

Административный финансовый раздел разделён на реестр учеников с активными офферами, карточку
платежей конкретного ученика, общий список просрочек и расчёты с менторами. Просроченные взносы
выделяются красной обводкой и доступны в отдельном реестре. На странице ментора видны ученик,
компания, исходный платёж, ставка и распределение каждого начисления.

Ошибочно подтверждённый платёж можно вернуть в статус «запланирован» с обязательной причиной.
Миграция `20260811_0044` добавляет дату, администратора и причину отмены. Невыплаченное начисление
ментору при этом удаляется. Если оно уже выплачено или находится в заявке ментора, отмена
блокируется до ручной сверки, чтобы не создать отрицательный баланс. Повторный webhook банка не
восстанавливает отменённый платёж автоматически, а переводится в ручную проверку.

Для production заполните настройки интернет-эквайринга Точка Банка в `.env.production`:

```dotenv
TOCHKA_CLIENT_ID=...
TOCHKA_JWT_TOKEN=...
TOCHKA_CUSTOMER_CODE=...
TOCHKA_PUBLIC_KEY=...
TOCHKA_API_BASE_URL=https://enter.tochka.com/uapi
TOCHKA_PROXY_URL=
TOCHKA_REDIRECT_URL=https://platform.example.com/payments
TOCHKA_FAIL_REDIRECT_URL=https://platform.example.com/payments
TOCHKA_PAYMENT_MODES=sbp,card
```

`TOCHKA_PROXY_URL` не нужно заполнять, если API Точки доступен с сервера
напрямую. Не используйте для банка Telegram/OpenAI proxy, который подменяет
TLS-сертификаты. Проверку TLS в платёжном клиенте отключать нельзя. Клиент
Точки не наследует глобальные `HTTP_PROXY`/`HTTPS_PROXY` контейнера и использует
только явно заданный `TOCHKA_PROXY_URL`.

Backend-образ устанавливает официальные `Russian Trusted Root CA` и
`Russian Trusted Sub CA`, необходимые для `enter.tochka.com`, в системный bundle
`/etc/ssl/certs/ca-certificates.crt`. Источник и контрольные отпечатки находятся
в `backend/certs/README.md`; отключать проверку сертификата через `verify=False`
не требуется и небезопасно.

Также проверьте параметры чека `TOCHKA_RECEIPT_*` и поставщика `TOCHKA_SUPPLIER_*` из
`.env.example` в соответствии с вашей системой налогообложения и договором. Для создания чека у
ученика должен быть указан email. Секреты хранятся только в backend environment и не попадают во
frontend. Redirect URL должны использовать HTTPS; backend проверяет это до обращения к API банка.

После deployment один раз зарегистрируйте webhook:

```bash
make prod-tochka-webhook
```

JWT-ключ должен включать разрешения `MakeAcquiringOperation`, `ReadAcquiringData` и
`ManageWebhookData`. Точка не позволяет добавить доступ к уже выпущенному JWT-ключу: если
`ManageWebhookData` отсутствует, перевыпустите ключ и обновите одновременно `TOCHKA_CLIENT_ID` и
`TOCHKA_JWT_TOKEN` перед повторным запуском команды.

`TOCHKA_PUBLIC_KEY` — не JWT приложения, а отдельный публичный ключ подписи webhook. Скачайте его
с `https://enter.tochka.com/doc/openapi/static/keys/public`, приведите JSON к одной строке и
сохраните целиком. Backend принимает официальный JWK JSON и PEM; placeholder
`REPLACE_WITH_TOCHKA_WEBHOOK_PUBLIC_KEY` оставлять нельзя.

Он указывает Точке публичный адрес
`https://<DOMAIN>/api/v1/payments/tochka/webhook`. Подписанный JWT проверяется публичным ключом;
для неподписанного production-события backend дополнительно сверяет операцию через API банка.
Повторная доставка безопасна: события и начисления дедуплицируются в PostgreSQL. Администратор
может подтвердить платёж вручную в разделе «Платежи». В development без реквизитов Точки
создаётся локальная stub-ссылка, чтобы проверить график и интерфейс без реального списания.

## Interview Intelligence

Разбор записей встроен в существующий журнал собеседований: `IntelligenceInterview` связан один-к-одному с `InterviewProcessStage`, поэтому компания, направление и дата не дублируются. Запись остаётся в приватном S3, браузер загружает её напрямую по multipart PUT, а FastAPI завершает upload, проверяет объект и ставит задачу в Redis. ARQ worker выполняет внешний pipeline:

```text
S3 upload → Nexara transcription + diarization → выбор кандидата
          → OpenAI structure extraction → per-answer review → mentor moderation
```

В development весь сценарий работает без внешних кредитов:

```dotenv
TRANSCRIPTION_PROVIDER=fake
INTERVIEW_AI_PROVIDER=fake
```

`docker compose` запускает Redis, отдельный worker транскрибации и отдельный OpenAI worker
автоматически. Без Compose запустите в разных терминалах `make worker` и `make worker-ai`.
Очереди имеют независимые лимиты `TRANSCRIPTION_MAX_CONCURRENCY` и
`OPENAI_MAX_CONCURRENCY`. Fake-провайдеры намеренно запрещены при `APP_ENV=production`.

### Nexara

Production-адаптер использует официальный асинхронный Python SDK `nexara`. Worker скачивает
private S3-объект во временный bounded staging, проверяет реальный контейнер, кодек и длительность
через `ffprobe`, загружает файл в Nexara, затем гарантированно очищает временный каталог. После
этого он опрашивает задачу по `job_id` и сохраняет сегменты, спикеров и временные метки в
PostgreSQL. Готовый результат Nexara нужно забрать до истечения срока хранения у провайдера.

```dotenv
TRANSCRIPTION_PROVIDER=nexara
NEXARA_API_KEY=nx-...
NEXARA_BASE_URL=https://api.nexara.ru/v1
NEXARA_MODEL=whisper-1
NEXARA_TIMEOUT_SECONDS=600
NEXARA_MAX_RETRIES=0
```

Повторы Nexara, как и OpenAI, выполняет ARQ worker с наблюдаемой попыткой и jitter;
встроенные повторы SDK отключены, чтобы не создавать вложенные волны запросов.

Проверить ключ без платной транскрибации можно запросом баланса:

```bash
make check-nexara
```

Команда выводит только результат подключения и модель — API key и баланс не печатаются. Nexara вызывается напрямую и не использует Amsterdam proxy.
Для `.env.production` используйте `make prod-check-nexara`.

Nexara получает файл от worker, поэтому HTTPS tunnel к локальному MinIO не нужен. Если в `.env`
настроено отдельное S3, override `infra/docker-compose.external-s3.yml` переключает backend и
worker на `S3_*` из `.env`. Обычный dev-compose использует MinIO, чтобы локальный запуск случайно
не изменил production bucket.

### Legacy ALAC аудио

Импортированные `.mp3`, внутри которых фактически лежит ALAC/M4A, один раз конвертируются
в MP3 и кэшируются в основном S3. `ffmpeg` запускается без environment приложения, с запретом
сетевых протоколов, одним CPU thread, timeout и лимитом размера output. Образ содержит закреплённые
по digest `ffmpeg` и `ffprobe`.

В production временные source и output нельзя класть в `/tmp`: у backend это маленький tmpfs.
Production Compose уже подключает обычный disk-backed named volume только к backend:

```yaml
services:
  backend:
    environment:
      INTERVIEW_LEGACY_TRANSCODE_DIRECTORY: /var/lib/mentoring/interview-legacy-transcode
    volumes:
      - interview_legacy_transcode:/var/lib/mentoring/interview-legacy-transcode

volumes:
  interview_legacy_transcode:
```

Конкурентность ограничена как внутри процесса, так и между uvicorn workers через lock-файлы. Перед
запуском проверяются byte budget и свободное место. Обычный и аварийный cleanup удаляет только
каталоги `legacy-alac-*`. При занятом slot, нехватке диска или I/O error API возвращает предсказуемый
`503` вместо зависания или заполнения tmpfs. Лимиты задаются переменными
`INTERVIEW_LEGACY_TRANSCODE_*` из `.env.production.example`.

### OpenAI и Amsterdam egress

Извлечение и первичная классификация вопросов используют дешёвую модель. Она за один проход
присваивает каждому вопросу тип `technical`, `hr`, `organizational` или `other`. Дорогая модель
получает только технические пары «вопрос + ответ» и максимум три соседние реплики. HR,
организационные вопросы и общее резюме обрабатывает дешёвая модель. Все вызовы используют
официальный async OpenAI SDK, Responses API и Pydantic Structured Outputs.

```dotenv
INTERVIEW_AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_EXTRACTION_MODEL=...
OPENAI_ANALYSIS_MODEL=...
OPENAI_LIGHT_REVIEW_MODEL=...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=256
OPENAI_PROXY_URL=http://10.8.0.1:3128
OPENAI_MAX_RETRIES=0
OPENAI_MAX_CONCURRENCY=4
OPENAI_EXTRACTION_MAX_OUTPUT_TOKENS=8000
OPENAI_REVIEW_MAX_OUTPUT_TOKENS=4000
OPENAI_SUMMARY_MAX_OUTPUT_TOKENS=4000
```

`OPENAI_EXTRACTION_MODEL` должна быть дешёвой моделью: она одновременно извлекает и
классифицирует вопросы. `OPENAI_LIGHT_REVIEW_MODEL` используется для HR/организационного
фидбека и общего резюме; если параметр пуст, используется `OPENAI_EXTRACTION_MODEL`.
`OPENAI_ANALYSIS_MODEL` предназначена только для углублённой проверки технических ответов.
`OPENAI_EMBEDDING_MODEL` и `OPENAI_EMBEDDING_DIMENSIONS` задают модель и размер кэшируемых
векторов для поиска смысловых дублей вопросов. После включения этой функции заполните векторы
для уже существующих карточек и одобренных формулировок:

```bash
make backfill-question-embeddings
# На production (команда сама применит миграции и соберёт актуальный worker):
make prod-backfill-question-embeddings
```

Backfill обрабатывает только опубликованные карточки и подтверждённые альтернативные
формулировки. Новые извлечённые вопросы получают embedding автоматически в AI worker. Расход
one-off backfill выводится в stdout как число запросов и input tokens; он не записывается в
`IntelligenceAIUsage`, потому что не относится к конкретному собеседованию.

Если `OPENAI_PROXY_URL` пуст, SDK подключается напрямую. Если URL задан, proxy передаётся только в централизованный `httpx.AsyncClient`; бизнес-логика и Nexara о нём не знают.
Повторы OpenAI-запросов выполняет worker с экспоненциальной задержкой и сохраняет каждую
попытку в базе, поэтому встроенные повторы SDK по умолчанию отключены.

Ученики и менторы могут запускать не более трёх платных AI-операций за календарный день по Москве
и не более одной одновременно. Долговечный журнал учитывает первичный анализ, ручной retry и
ручную генерацию резюме; удаление зависшего разбора не обнуляет квоту. Администратор не имеет
персональной дневной квоты; глобальный safety cap применяется ко всем ролям. Оперативно остановить
новые запуски можно через `INTERVIEW_AI_ENABLED=false`. Состояние pipeline, очередей и heartbeat
обоих worker доступно администратору в `GET /api/v1/admin/interviews/ai-operations`.

```text
RU Application Server
       │  WireGuard / firewall allowlist
       ▼
Amsterdam forward proxy
       │  HTTP CONNECT, no TLS MITM
       ▼
OpenAI API
```

Минимальный закрытый Squid-конфиг находится в `infra/amsterdam/squid.conf.example`. Порт proxy нельзя публиковать для всего интернета: разрешайте только private IP application server, не устанавливайте MITM CA и не сохраняйте пароль proxy в Git. OpenAI API key остаётся только на RU application server и внутри TLS-туннеля не виден proxy. Перед production deployment отдельно проверьте, что использование OpenAI и выбранная географическая маршрутизация соответствуют актуальным условиям сервиса.

### Retry и безопасность

Статусы обработки и каждая попытка сохраняются в БД. `POST /api/v1/interviews/{id}/retry` повторяет только упавший этап: Nexara submit/poll, extraction либо review. В интерфейс возвращается безопасное сообщение без provider payload и секретов. Signed S3 URL, исходный transcript и API keys не пишутся в diagnostic JSON или application log.

Ученик читает и удаляет только собственные разборы; назначенный ментор видит интервью своих учеников и модерирует AI-рекомендации; администратор видит всё. Изменения ментора не перезаписывают AI-версию: edit создаёт новую review-запись, approve/reject сохраняют решение. Удаление интервью каскадно удаляет transcript, вопросы, оценки и комментарии, а связанные S3-объекты удаляются отдельно.

AI-разбор запускается из этапа дневника с уже загруженной записью. Результат открывается на
`/interviews/analysis/{id}`, очередь ментора находится на `/mentor/interview-reviews`. API
документирован в OpenAPI под `/api/v1/interviews` и `/api/v1/mentor/interviews`.

Модерация извлечённых вопросов отделена от проверки самого интервью и доступна администратору
на `/admin/interview-question-moderation`. При одобрении вопрос нормализуется и сравнивается с
карточками и ранее одобренными формулировками того же направления. Точные и смысловые совпадения
показываются администратору как кандидаты; смысловое совпадение не объединяется автоматически.
После подтверждения сохраняется отдельный факт появления с компанией и датой. Счётчик
`interview_cards.asked_count` увеличивается не более одного раза для одной карточки в рамках одного
собеседования.

Для карточек в автоматическом режиме частотность становится `frequent`, когда вопрос подтверждён
как минимум в `INTERVIEW_CARD_FREQUENT_MIN_OCCURRENCES` разных собеседованиях (по умолчанию — в
трёх). Ручной режим сохраняет выбранную администратором частотность независимо от счётчика; он
используется в том числе для импортированных карточек.

## Тесты

Backend tests используют отдельную PostgreSQL database `mentoring_test`. Она создаётся init-скриптом нового Compose volume; `make test-backend` также безопасно пытается создать её для существующего volume. В production runtime `create_all()` не используется; оно разрешено только в изолированных тестах.

Frontend tests покрывают loading/data/error, структуру roadmap, mutation темы с обновлением UI, базу знаний и поиск, карточки собеседований, mentor list, онбординг и browser/Telegram adapters. Backend отдельно проверяет валидную, поддельную и просроченную Telegram-подпись, видимость опубликованных материалов, обновление полнотекстового индекса, доступ к колодам по треку и интервальное планирование карточек.

## Повторное менторство по Python

Для Python-выпускников доступен отдельный продукт с новой заявкой и отдельным enrollment:
30 000 ₽ при поступлении и 100% подтверждённой фиксированной месячной зарплаты четырьмя
платежами. Исторические условия не перезаписываются. Архитектура, demo-сценарий, feature flag и
production rollout описаны в [docs/python-repeat-mentorship.md](docs/python-repeat-mentorship.md).

Переключатель новых продаж:

```dotenv
PYTHON_REPEAT_MENTORSHIP_ENABLED=true
```

## Известные ограничения MVP

Нет email-входа, чатов и уведомлений вне интерфейса. Платёжная ссылка создаётся через Точка Банк,
а успешная оплата фиксируется webhook-ом либо вручную администратором. Вознаграждения менторам
учитываются в платформе, но перечисляются им вне платформы и отмечаются администратором вручную.
Сохранённые разделы роадмапов пока нельзя удалить: для этого потребуется отдельный подтверждаемый
сценарий с политикой хранения TopicProgress.
