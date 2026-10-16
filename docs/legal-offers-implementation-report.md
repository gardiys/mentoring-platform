# Отчёт о реализации оферт и подтверждения договоров

Дата: 16.10.2026. Изменения подготовлены в рабочем дереве репозитория.

## Результат

Для повторного Python и перехода Python → Go добавлены версионированные оферты,
checkout с обязательными сведениями и тремя подтверждениями, подтверждение email,
неизменяемый акцепт при успешной оплате, транзакционная очередь письма с точным PDF,
кабинет документов и административный просмотр. Договор не возникает при создании ссылки
или банковской авторизации. Ошибка почты не откатывает договор или доступ.

## Найденные и переиспользованные механизмы

- Telegram/browser/desktop авторизация, `CurrentUser`, `StudentUser`, `AdminUser`,
  штатная защита cookie-запросов от CSRF и `apiRequest` frontend.
- Существующие заявки `PythonRepeatApplication` и `GoTransitionApplication`,
  `OpportunityPaymentAttempt`, платежи Точки с фискализацией, `PaymentWebhookEvent`.
- RS256-проверка webhook и authenticated Get Payment Operation Info. Разбор расширен
  `Operation/Order`, временем фактического списания, валютой и сведениями о возврате.
  `Order.orderId` не трактуется как merchant paymentLinkId.
- Существующая выдача доступа после оплаты, Python repeat enrollment/обязательства/награды.
- Brevo `CareerPackageEmailService`, `NotificationWorkerSettings` ARQ, приватный S3
  `PrivateMediaStore`. Новый SMTP-клиент, брокер или платежный адаптер не добавлялись.
- Штатные платежи результативного компонента. Новый Go получает два календарных платежа
  после квалификации нового Go-трудоустройства командой; прежние Python-графики сохраняются.
- Отдельного универсального договора/акцепта и подтверждения email до этой задачи не было.
  Политика квалификации трудоустройства не подменяется новой моделью покупки.

## Данные, API и фоновые задачи

Миграция `20261016_0100` создаёт семь таблиц: версии оферт, checkout, акцепты, email Outbox,
проверки email, черновики анкет и аудит. Первоначальные редакции импортированы как active;
PDF находятся в приложении по хешированным неизменяемым путям, вне SQL-миграции.
Добавлены ограничения уникальности и триггеры запрета изменения/удаления доказательств.
В ответ существующего платежного API добавлено необязательное поле `checkout_session_id`.

Существующие POST `/opportunities/go-transition/{id}/payment-link` и
`/opportunities/python-repeat/applications/{id}/checkout` принимают новый обязательный
`CheckoutConfirmation`. Общая логика не дублирует банковские операции. Новые методы
`/legal/*` и `/admin/legal/*` обслуживают версии, анкеты, проверку email, документы,
resend, состояния договора и мониторинг. Полная таблица методов — в эксплуатационной документации.
OpenAPI TypeScript-файл перегенерирован.

`deliver_legal_emails` обрабатывает email Outbox; `monitor_legal_health` проверяет наличие
оферт/PDF и очередь. Обе задачи включены в существующий notification-worker.
Доставка сохраняет pending/processing/sent/delivered/bounced/failed отдельно, с Message-ID и retry.
Ручной resend не создаёт новый договор. Audit доступен администратору.

Новые настройки: `LEGAL_EMAIL_FROM`, `LEGAL_EMAIL_REPLY_TO`,
`CONTRACT_EMAIL_MAX_RETRIES`, `CONTRACT_EMAIL_RESEND_COOLDOWN_SECONDS`,
`BREVO_DELIVERY_WEBHOOK_TOKEN`, `TOCHKA_ACQUIRING_CURRENCY`.
URL, timezone и storage используют существующую конфигурацию; официальный email находится
в одном `Settings.legal_official_email`. Настройки проведены в dev/prod compose.
В `arq_healthcheck.py` исправлена несовместимая с установленной версией redis аннотация
типа; поведение heartbeat не изменялось.

## Проверки: фактические результаты

| Проверка | Результат |
| --- | --- |
| `make lint` | PASS: Ruff и ESLint |
| `make format-python-check` | PASS: 442 файла |
| `make test` | PASS: backend 1209 passed, 8 skipped; frontend 347 passed, 52 файла |
| Окончательный прогон затронутых backend-компонентов в отдельной базе `_test` | PASS: 186 тестов, включая 34 legal-сценария |
| После уточнения банковских approval/refund идентификаторов: `pytest tests/test_legal_contracts.py tests/test_tochka.py -q` | PASS: 67 тестов |
| `make typecheck` | PASS: mypy (232 source files) и TypeScript |
| `make format-frontend-check` | PASS: Prettier |
| `pnpm --dir frontend build` | PASS: TypeScript и production Vite build |
| `python -m unittest discover -s scripts -p 'test_*.py'` | PASS: 6 тестов Git test runner |
| `python -m app.legal.cli verify-bundled` | PASS: оба PDF, размеры/SHA-256 и соответствие Markdown |
| Вся цепочка `alembic upgrade head` в отдельной новой локальной базе `_test` | PASS: head `20261016_0100`, две active оферты; временная база удалена |
| Новая миграция поверх существующей схемы + bulk SQL guard | PASS: integration test с `schema_change` |
| `git diff --check` | PASS |
| Dev/prod compose YAML и передача legal env backend/worker | PASS: YAML разобран и проверены environment блоки |
| `.local/bin/graphify update .` | PASS: граф кода обновлён без LLM/API |

Полный прогон выполнен до последних уточнений переиспользования endpoints и разбора
банковских идентификаторов; эти изменения затем проверены отдельными 186/67 тестами.
8 пропусков относятся к существующему полному набору. Реальные банковские платежи и
письма студентам при проверках не выполнялись: используются stub/fake provider и MockTransport.
Один ранний параллельный запуск столкнулся с блокировкой общей тестовой базы; окончательная
проверка выполнена успешно в отдельной временной базе. Graphify предупредил об отсутствии
PDF-extra в своём окружении: граф кода обновлён, а юридические файлы независимо проверены
штатным `pypdf` приложения. Семантическая индексация PDF не запускалась.

## Запуск и ручная проверка

Команды импорта/активации обеих редакций с путями PDF/Markdown и admin ID, миграции,
запуск notification-worker, env и пошаговые сценарии приведены в
[эксплуатационной инструкции](legal-offers-and-contract-confirmation.md#импорт-и-запуск).

Основной сценарий: одобрить заявку → открыть правильный PDF → подтвердить email → заполнить
анкету → отметить три чекбокса → оплатить → проверить договор, доступ, Outbox и PDF письма.
Повторить для обоих продуктов; отдельно проверить дубли webhook, отказ Brevo, retry/resend,
старую редакцию после активации новой, чужой UUID, возврат и bounce.

## Ограничения и эксплуатационные условия

- Production deployment не выполнялся. Для запуска применить миграцию и настроить
  существующий Brevo sender/API key; для доставки статусов настроить защищённый webhook.
- Штатный acquiring v1.0 работает в RUB; чужая явная валюта отвергается. Момент списания
  берётся из approval time, а при его отсутствии — из локального времени успешного webhook.
- При поздней оплате cancelled/expired/revoked checkout нужна ручная проверка команды.
  Сессия ограничена 24 часами; отмена в БД не означает возврат банковского платежа.
- Старые договоры не реконструируются задним числом. Старые документы сохраняются.
- Достоверность доставки известна только при webhook Brevo. Его idempotency TTL — 15 минут;
  при потере ответа API и длительном простое возможна неопределённость внешней доставки.
- Resend использует первоначальный email договора; изменение исторического адреса запрещено.
- IP берётся из `Request.client`, без доверия произвольному X-Forwarded-For.
- Техническая проверка не заменяет проверку применимости результативного компонента командой.

## Изменённые и добавленные файлы

- `.env.example`
- `.env.production.example`
- `backend/app/arq_healthcheck.py`
- `backend/app/career_packages/email.py`
- `backend/app/core/config.py`
- `backend/app/db/models.py`
- `backend/app/legal/__init__.py`
- `backend/app/legal/catalog.py`
- `backend/app/legal/cli.py`
- `backend/app/legal/documents/legal/offers/python-to-go-transition/2026-09-03/568a536665d42f56c7014fa19c51522be5fe54000ec4d0bd70a113abc959fd39.md`
- `backend/app/legal/documents/legal/offers/python-to-go-transition/2026-09-03/d5482491d8cc7c5497885000b618f94cf1b38922f529fa129bb1fd9e2c42811b.pdf`
- `backend/app/legal/documents/legal/offers/repeat-python-mentorship/2026-09-02/2f7a2c4e01609f37a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f.pdf`
- `backend/app/legal/documents/legal/offers/repeat-python-mentorship/2026-09-02/c79a137a98c497543d5b52e053cffef963768c514a25b51f224d4db80274ffa9.md`
- `backend/app/legal/documents/manifest.json`
- `backend/app/legal/jobs.py`
- `backend/app/legal/models.py`
- `backend/app/legal/router.py`
- `backend/app/legal/schemas.py`
- `backend/app/legal/service.py`
- `backend/app/legal/storage.py`
- `backend/app/main.py`
- `backend/app/notifications/jobs.py`
- `backend/app/opportunities/python_repeat_router.py`
- `backend/app/opportunities/python_repeat_service.py`
- `backend/app/opportunities/router.py`
- `backend/app/opportunities/schemas.py`
- `backend/app/opportunities/service.py`
- `backend/app/payments/router.py`
- `backend/app/payments/service.py`
- `backend/app/payments/tochka.py`
- `backend/migrations/versions/20261016_0100_legal_contracts.py`
- `backend/tests/conftest.py`
- `backend/tests/legal_helpers.py`
- `backend/tests/test_legal_contracts.py`
- `backend/tests/test_opportunities.py`
- `backend/tests/test_security_middleware.py`
- `docs/legal-offers-and-contract-confirmation.md`
- `docs/legal-offers-implementation-report.md`
- `frontend/src/api/client.ts`
- `frontend/src/api/generated/schema.ts`
- `frontend/src/components/AppLayout.tsx`
- `frontend/src/components/LegalCheckout.tsx`
- `frontend/src/features/opportunities/legalQuestionnaire.ts`
- `frontend/src/pages/GoTransitionOpportunityPage.tsx`
- `frontend/src/pages/LegalDocumentsPage.tsx`
- `frontend/src/pages/PythonRepeatOpportunityPage.tsx`
- `frontend/src/routes/router.tsx`
- `frontend/tests/legal-checkout.test.tsx`
- `frontend/tests/legalFixtures.ts`
- `frontend/tests/opportunities.test.tsx`
- `infra/docker-compose.prod.yml`
- `infra/docker-compose.yml`
