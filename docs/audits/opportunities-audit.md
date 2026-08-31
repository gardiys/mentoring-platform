# Аудит раздела «Возможности»

Дата: 2026-08-31  
Репозиторий: `mentoring-platform`  
Baseline: ветка `main`, HEAD `4cd928d23dbc764981c823583e8056c232e96b76`  
Итог: **NOT_READY**

## 1. Scope

Проверены общий каталог возможностей и три продукта:

- платные консультации;
- повторное Python-менторство;
- переход выпускника Python в Go.

Аудит включал backend, frontend, RBAC/ownership, финансовые snapshots и начисления, миграции, feature flags, уведомления, тесты и сквозные сценарии. Проверка выполнялась по фактическому коду и текущей продуктовой матрице, а не только по наличию страниц.

## 2. Repository baseline

На момент начала аудита рабочее дерево уже содержало незакоммиченные изменения раздела. Они сохранены. До исправлений целевые проверки давали:

- backend opportunities: 12 тестов пройдены;
- frontend opportunities: 6 тестов пройдены;
- общий frontend suite: 229 тестов пройдены, 2 нестабильных падения в ранее существовавшем `card-automation`, не связанных с разделом.

## 3. Сохранённые пользовательские изменения

Во время аудита не были отменены следующие осознанные изменения относительно исходного задания:

- администратор выбирает, какие менторы принимают платные консультации;
- при заявке по умолчанию можно выбрать «любой ментор»;
- шесть прикладных типов консультаций вместо исходного перечня;
- настраиваемые цена, публичная цена, вознаграждение и длительность каждого типа;
- премиальные консультации за 6 000 ₽ при публичной цене 7 000 ₽ и выплате ментору 3 000 ₽;
- редактируемое описание перехода Python → Go;
- отдельный «Кабинет выпускника», доступный действующим ученикам в режиме просмотра;
- повторное Python-менторство и Python → Go сохранены как разные продукты.

## 4. Implementation map

Backend:

- `app/opportunities/models.py` — заявки, консультации, Go enrollment, repeat-Python домен и snapshots;
- `app/opportunities/service.py` — общий dashboard, консультации и Go;
- `app/opportunities/python_repeat_service.py` — repeat-Python eligibility, state machine, платежи, оффер, обязательства и начисления;
- `app/opportunities/router.py`, `python_repeat_router.py` — student/admin API;
- `app/payments/tochka.py` и общий webhook — платёжный адаптер;
- `app/notifications/*` — in-app notifications и Telegram outbox платформы.

Frontend:

- `/opportunities`, `/opportunities/alumni`;
- `/opportunities/consultations`;
- `/opportunities/python-repeat`;
- `/opportunities/python-to-go`;
- `/admin/opportunities`, `/admin/opportunities/python-repeat`.

Миграции раздела: `0070`–`0077`; один Alembic head — `20260831_0077`.

## 5. Audit matrix

Статусы: `PASS`, `PARTIAL`, `FAIL`, `REQUIRES_PRODUCT_DECISION`.

### Общий раздел

| ID | Статус | Результат |
|---|---|---|
| OPP-001 | PASS | Desktop/mobile navigation и refresh-safe маршруты присутствуют. |
| OPP-002 | PARTIAL | Сегмент, доступность, цены и flags приходят с backend; часть CTA-состояния всё ещё собирается frontend из состояния заявки. |
| OPP-003 | PARTIAL | Repeat-Python versioned offer и snapshots реализованы; консультации используют конфигурацию с snapshot заказа; Go-условия пока заданы доменными константами, а не полноценным ProductOffer. |
| OPP-004 | PASS | Для Python-выпускника продукты разделены, ссылки и цены не смешаны. |
| OPP-005 | PARTIAL | Основные состояния CTA поддержаны; Go не имеет полной review/clarification/expired state machine. |
| OPP-006 | PASS | Alumni определяется по завершению направления; роль `graduate` не создавалась, история enrollment сохраняется. |
| OPP-007 | PASS | Добавлены четыре независимых feature flag; новые операции блокируются, история остаётся доступной, начатый checkout repeat-Python может завершиться. |

### Консультации

| ID | Статус | Результат |
|---|---|---|
| CONS-001 | PARTIAL | Настраиваемый пользовательский каталог типов есть, но у ментора нет поддержки типов консультаций на уровне данных. |
| CONS-002 | FAIL | Бриф хранится одним текстом; нет структурных полей «задача/результат/пробовали/контекст/ссылки», URL-валидации и отдельного предупреждения о конфиденциальности. |
| CONS-003 | PARTIAL | Активность и административный allowlist проверяются сервером; специализация проверяется по направлению, но не по конкретному типу консультации. |
| CONS-004 | FAIL | Нет модели availability slot, выбора слота, timezone UX, 15-минутного hold и освобождения истёкшего hold. |
| CONS-005 | FAIL | Нет DB constraint/lock и concurrency test, запрещающих двойное бронирование одного слота, потому что слот как сущность отсутствует. |
| CONS-006 | PASS | Базовые 5 000/4 000/2 500 ₽ и пользовательские премиальные тарифы хранятся сервером в копейках; заявка получает snapshot. |
| CONS-007 | PARTIAL | Повторный checkout отзывает прошлую pending-ссылку, webhook идемпотентен; отдельные order/booking и hold-confirmation отсутствуют. |
| CONS-008 | PASS | Development payment endpoint защищён средой и проверен негативным production-тестом. |
| CONS-009 | FAIL | Нет полноценного подтверждения с выбранным слотом, timezone, встречей и правилами переноса. |
| CONS-010 | PARTIAL | Admin может назначить, запланировать, завершить с итогом и отменить; no-show, рекомендации и production refund отсутствуют. |
| CONS-011 | PARTIAL | Начисление теперь создаётся один раз только после `COMPLETED`; reversal после возврата не реализован. |
| CONS-012 | PARTIAL | Student ownership и admin RBAC есть; отдельного рабочего кабинета назначенного ментора для консультаций нет. |

`CONS-004` и `CONS-005` являются релизными BLOCKER, если продукт позиционируется как бронирование времени ментора, а не как заявка с последующим ручным согласованием.

### Повторное Python-менторство

| ID | Статус | Результат |
|---|---|---|
| PYR-001 | PASS | Проверяются завершённый Python, активность аккаунта, несовместимые enrollment/application, задолженность и первые 30 дней поддержки; проверки повторяются на критических стадиях. |
| PYR-002 | PASS | Страница показывает 30 000 ₽ + 100%, срок, два мока и probation support; старое публичное предложение не используется. |
| PYR-003 | PASS | Типизированная форма, ограничения длины/дат/копеек, ownership и запрет двух активных заявок реализованы; clarification теперь можно исправить и отправить повторно. |
| PYR-004 | PARTIAL | State machine и история есть; `request_id` в истории не заполняется, автоматическое истечение одобренных условий не вынесено в worker. |
| PYR-005 | PASS | При одобрении сохраняется immutable versioned snapshot всех условий. |
| PYR-006 | PASS | Есть явное согласие, actor/time/version/snapshot, срок действия и запрет принятия expired terms. |
| PYR-007 | PARTIAL | Сумма, валюта, snapshot, retry и idempotency реализованы через payment attempt; отдельной сущности `Order` нет. |
| PYR-008 | PASS | Создаётся отдельный Python repeat enrollment со ссылкой на завершённый enrollment; старый прогресс не переоткрывается. |
| PYR-009 | PASS | Назначение доступного активного Python-ментора валидируется и идемпотентно. |
| PYR-010 | PASS | После оплаты и назначения создаётся ровно одно фиксированное начисление 10 000 ₽ из snapshot. |
| PYR-011 | PASS | Оффер связан с новым enrollment, проходит submit и admin verification. |
| PYR-012 | PASS | Для 250 000 ₽ создаются четыре точных платежа по 62 500 ₽, obligation уникален. |
| PYR-013 | PARTIAL | 30% начисляется только с каждого полученного платежа и идемпотентно; корректный финансовый reversal refund не реализован. |
| PYR-014 | PASS | Контроль: клиент 280 000 ₽, ментор 85 000 ₽, валовой остаток 195 000 ₽; внутренняя экономика скрыта от ученика. |

### Переход Python → Go

| ID | Статус | Результат |
|---|---|---|
| GO-001 | PARTIAL | Базовая серверная eligibility есть; требуется единая повторная проверка всех долгов и несовместимых программ на каждой критической стадии. |
| GO-002 | PASS | 30 000 ₽ + 100% и сравнение 45 000 ₽ + 150% показаны отдельно от repeat-Python. |
| GO-003 | PASS | Описание программы есть и редактируется администратором. |
| GO-004 | FAIL | Форма содержит только мотивацию; отсутствуют должность, стек, доступное время, старт, режим перехода и комментарий. |
| GO-005 | FAIL | Нет полной draft/review/clarification/expired/enrolled state machine и аудита переходов. |
| GO-006 | PASS | Добавлены version, expiration, approved и accepted immutable snapshots, включая comparison terms. |
| GO-007 | PARTIAL | Платёж на 30 000 ₽ идемпотентен и создаёт enrollment; отдельной order-сущности нет. |
| GO-008 | PARTIAL | Создаётся отдельный source-specific Go enrollment со ссылкой на прежний Python track; mentor/roadmap и явное состояние ручного назначения отсутствуют. |
| GO-009 | PARTIAL | Enrollment хранит 100% snapshot и готов к привязке финансового цикла, но source-specific Go offer/obligation/installments пока не реализованы. |

### Сквозные области

| Область | Статус | Результат |
|---|---|---|
| FIN-001 Деньги | PASS | Integer kopecks/Decimal, явное округление, без float. |
| FIN-002 Versioning | PARTIAL | Полноценно только repeat-Python; консультации и Go требуют единой versioned offer модели. |
| FIN-003 Snapshots | PARTIAL | Repeat-Python полно; консультации достаточны для текущего заказа; Go дополнен accepted/enrollment snapshot, но нет success-fee obligation. |
| FIN-004 Payment state | PARTIAL | Основные переходы согласованы тестами, но нет общей reconciliation-команды. |
| FIN-005 Idempotency | PARTIAL | Webhook/enrollment/accrual/obligation защищены; slot booking проверить невозможно. |
| FIN-006 Refunds | FAIL | Production refund, partial refund и signed reversal ledger для новых продуктов не закончены. |
| SEC-001 Authorization | PARTIAL | Student ownership и admin RBAC есть; mentor consultation scope отсутствует вместе с mentor API. |
| SEC-002 Mass assignment | PASS | Пользовательские DTO не принимают цену, payout, status, source или verified salary. |
| SEC-003 Dev endpoints | PASS | Production guard покрыт тестом. |
| SEC-004 Webhook | PARTIAL | Используется общий защищённый адаптер и idempotency; в новых tests нет отдельных негативных сценариев currency/amount/replay. |
| SEC-005 Text/links | PARTIAL | React не исполняет brief как HTML и размеры ограничены; структурная URL-валидация отсутствует. |
| SEC-006 PII/analytics | PASS | Свободные тексты не отправляются в аналитику; внутренняя выплата ментора удалена из student API. |
| DB integrity | PARTIAL | Уникальности заявок/enrollment/payment/rewards присутствуют; booking/slot constraints отсутствуют. |
| Migrations | PASS после исправления | Один head, текущая БД и чистый `upgrade head` проходят. Архивная `0059` теперь пропускает строки без разрешимого пользователя, когда PII-файл намеренно отсутствует в image. |
| Frontend/UX | PARTIAL | Responsive routes, loading/error/disabled states и форматирование есть; consultation confirmation/slot UX и полные Go statuses отсутствуют. |
| Admin | PARTIAL | Базовые операции всех продуктов есть; нет pagination/filtering, консультационных refunds/no-show и полного Go enrollment management. |
| Notifications/outbox | PARTIAL | Repeat-Python создаёт идемпотентные platform notifications и domain events; консультации и Go не покрывают требуемый набор событий и Telegram outbox. |
| Analytics | FAIL | Воронки трёх новых продуктов не реализованы. |
| Demo data | PARTIAL | Есть dev persona/seed для базовых alumni flows и repeat-Python; нет полной матрицы из 20 состояний и consultation slots. |
| Automated tests | PARTIAL | Основные финансовые и RBAC сценарии покрыты; нет slot/concurrency/refund/Go-success-fee тестов. |

## 6. Найденные проблемы

### BLOCKER

1. Консультации не имеют availability/hold/booking модели и DB-защиты от двойного бронирования.
2. Чистый `alembic upgrade head` падал в архивной миграции `0059` при отсутствии PII-файла/пользователя. Исправлено в рамках аудита.

### HIGH

1. Вознаграждение ментора по консультации начислялось при оплате, а не после фактического `COMPLETED`. Исправлено.
2. Внутренняя сумма вознаграждения ментора возвращалась ученику через API. Исправлено.
3. Не было проверки первоначального 30-дневного сопровождения для repeat-Python. Исправлено.
4. Go enrollment не имел самостоятельного source-specific доменного объекта и immutable accepted terms snapshot. Исправлено.
5. Нет корректного refund/reversal цикла для консультаций и repeat-Python.
6. У Go отсутствует заявленный source-specific цикл 100% постоплаты.

### MEDIUM

- clarification repeat-Python нельзя было отредактировать — исправлено;
- business datetime принимали naive значения — исправлено;
- feature flags были неполными — исправлено;
- payout политика Go-ментора не определена;
- admin списки ограничены первыми 200 строками без pagination/filtering;
- аудит repeat-Python не заполняет request/correlation ID;
- события консультаций и Go не подключены к существующему outbox.

## 7. Исправлено в ходе аудита

- добавлены четыре feature flag в config, env examples и compose;
- добавлена безопасная остановка новых операций при выключенном флаге с сохранением истории;
- добавлено редактирование repeat-Python заявки в `NEEDS_CLARIFICATION`;
- добавлена timezone-aware server validation дат;
- усилена повторная eligibility-проверка submit/approval/checkout/enrollment;
- учтён 30-дневный период первичной поддержки;
- запрещён override несовместимых активных программ и долгов;
- начисление за консультацию перенесено с оплаты на `COMPLETED` и защищено от дубля;
- внутренний consultation mentor payout удалён из student API;
- Go получил explicit terms acceptance, version/expiration/accepted snapshots и отдельный Go enrollment;
- добавлена миграция `0077` с безопасным backfill;
- исправлена чистая установка через безопасное поведение архивной миграции `0059` без legacy PII;
- расширены regression/E2E тесты до полной финансовой проверки repeat-Python.

## 8. REQUIRES_PRODUCT_DECISION

1. Консультации остаются ручной заявкой с согласованием времени администратором или становятся self-service booking со слотами и 15-минутным hold? Текущий продуктовый текст требует второй вариант.
2. Политика cancellation/no-show/partial refund и судьба начисления ментору.
3. Схема вознаграждения Go-ментора с постоплаты — требования запрещают придумывать её технически.
4. Нужно ли активным ученикам разрешать покупать консультацию, поддержка по которой уже входит в программу, или оставлять только read-only каталог.

## 9. Test results

Фактически выполнено:

- `poetry run ruff check app tests` — PASS;
- `poetry run mypy app` — PASS, 159 файлов;
- `poetry run pytest -q tests/test_opportunities.py` — PASS, 15 тестов;
- полный backend `poetry run pytest -q` — PASS, 580 тестов за 866,48 с;
- frontend `tsc -b` — PASS;
- frontend `eslint .` — PASS;
- `vitest run tests/opportunities.test.tsx` — PASS, 6 тестов;
- полный frontend `vitest run` — 228 PASS, 3 падения в несвязанном `card-automation` при параллельном полном прогоне;
- отдельный `vitest run tests/card-automation.test.tsx` — PASS, 22 теста; падения полного suite классифицированы как изоляция/таймаут test runner, а не регрессия «Возможностей»;
- frontend production build — PASS;
- `alembic heads` — PASS, один head `20260831_0077`;
- чистый `alembic upgrade head` на одноразовой PostgreSQL без volume — PASS после исправления `0059`.

## 10. End-to-end results

### A. Консультация — PARTIAL

Подтверждено: выпускник → тип → любой/конкретный разрешённый ментор → admin assignment → checkout → webhook → paid → completed → ровно одно начисление 2 500 ₽. Не покрыт реальный slot/hold/booking и refund.

### B. Повторное Python-менторство — PASS без refund

Подтверждено: eligibility → draft → submit → review → approve → immutable acceptance → 30 000 ₽ → новое enrollment → mentor → 10 000 ₽ → verified offer 250 000 ₽ → четыре платежа по 62 500 ₽ → четыре начисления по 18 750 ₽. Повторные payment events не создают дубли.

### C. Python → Go — PARTIAL

Подтверждено: Python completion → application → admin approve → explicit immutable acceptance → 30 000 ₽ → отдельный Go enrollment, Python enrollment сохранён. Не покрыт Go offer/postpayment lifecycle.

## 11. Финансовая контрольная проверка

Для repeat-Python при зарплате 250 000 ₽ тест подтверждает:

| Показатель | Сумма |
|---|---:|
| Вступительный платёж | 30 000 ₽ |
| Постоплата, 4 × 62 500 ₽ | 250 000 ₽ |
| Всего получено от клиента | 280 000 ₽ |
| Фиксированное начисление ментору | 10 000 ₽ |
| Переменные начисления, 4 × 18 750 ₽ | 75 000 ₽ |
| Всего начислено ментору | 85 000 ₽ |
| Валовой остаток платформы | 195 000 ₽ |

Это валовой остаток, не чистая прибыль.

## 12. Known limitations

- Без решения slot/hold и refund/reversal консультации нельзя считать полностью готовым платёжным продуктом.
- Go нельзя рекламировать как завершённый финансовый цикл `30 000 ₽ + 100%`, пока 100% не привязаны к source-specific offer/obligation/installments.
- Исторические consultation rewards, созданные прежней логикой до `COMPLETED`, автоматически не переписываются; перед релизом нужен read-only reconciliation production-данных и ручное решение по найденным строкам.
- Полный browser E2E с реальным Точка API намеренно не выполнялся: использован общий webhook/mock путь в test/development.

## 13. Final verdict

**NOT_READY** для полного релиза всех трёх продуктов как завершённой коммерческой системы.

Повторное Python-менторство готово к контролируемому rollout после добавления refund/reversal. Общий кабинет и базовый Go onboarding функциональны. Консультации безопасно выпускать только как ручную заявку без обещания выбора слота либо после реализации booking/hold; Go — только после явного ограничения scope или завершения offer/postpayment цикла.
