# Автоматизация карточек из AI-разборов

Модуль уменьшает ручную очередь вопросов собеседований, но не публикует новые общие карточки без решения человека. Он построен поверх существующего AI-разбора, общей колоды карточек и ARQ-очереди.

## Модель данных

Существующая `IntelligenceQuestion` играет роль `QuestionOccurrence`: это одно появление вопроса в конкретном собеседовании. В неё добавлены направление, нормализованный и канонический варианты, контекст, тип учебного объекта, признаки качества, состояние и ревизия автоматизации, ссылка на кластер и объяснение последнего решения.

Новые сущности:

- `QuestionCluster` — теневой смысловой кластер одного направления и одного типа учебного объекта. Хранит агрегаты, приоритет, ревизии состава/статистики, предложение ответа и ручной статус;
- `AutomationDecision` — неизменяемая запись решения правила, AI или человека: кандидаты, оценки, confidence, причина, модель, версии prompt/schema, usage/cost, audit/override;
- `PersonalReviewItem` — приватное обязательное повторение ученика, когда общей карточки ещё нет;
- `CardAutomationSettings` — отдельные безопасные настройки для каждого направления.

`InterviewCard` остаётся единственной канонической общей карточкой. `InterviewCardOccurrence` остаётся источником частотности и имеет ограничения, не позволяющие учесть один вопрос или одну карточку дважды в одном собеседовании. Автоматическая связь не превращает формулировку в доверенный alias: `alias_human_confirmed` выставляется только ручной модерацией.

```mermaid
flowchart LR
    T[Транскрипция и AI extraction] --> O[QuestionOccurrence]
    O --> R{Правила и routing}
    R -->|noise / другой тип| A[Audit decision]
    R -->|карточный вопрос| E{Exact / confirmed alias}
    E -->|нет| S[Semantic top-N]
    S --> J[Pairwise judge]
    E -->|match| L[Предложение или auto-link]
    J -->|все gates пройдены| L
    J -->|неоднозначно| C[Shadow QuestionCluster]
    C --> P{Порог зрелости}
    P -->|достигнут| M[Одна задача модерации]
    M -->|решение человека| K[Canonical InterviewCard]
    O --> W{Ответ слабый/отсутствует}
    W -->|карточка найдена| D[Сделать общую карточку due]
    W -->|карточки нет| PR[Private PersonalReviewItem]
```

## Состояния occurrence

```mermaid
stateDiagram-v2
    [*] --> created
    created --> routing
    routing --> routed
    routing --> auto_ignored
    routed --> searching_card
    searching_card --> auto_linked
    searching_card --> searching_cluster
    searching_card --> routed: proposal/shadow
    searching_cluster --> clustered
    clustered --> needs_review
    routed --> personal_only
    created --> failed
    routing --> failed
    searching_card --> failed
    searching_cluster --> failed
    failed --> routing: manual retry/new revision
```

Каждая job принимает ревизию сущности. Перед финальной записью worker блокирует строку и проверяет ревизию, поэтому устаревшая job не может затереть ручное изменение. Детерминированный ARQ job id включает функцию, UUID и ревизию. Периодический reconciler повторно ставит незавершённые состояния и кластеры с устаревшей статистикой.

## Правила routing и auto-link

Сначала выполняются дешёвые детерминированные правила. Они отсеивают служебные реплики, HR/организационные вопросы, низкую уверенность транскрипции и вопросы, зависящие от отсутствующего кода/изображения. Остальные коротко классифицирует AI через strict Structured Output. Транскрипция и пользовательский текст всегда помещаются только в секцию untrusted data и не могут менять system instructions.

Поиск общей карточки идёт строго в пределах направления и опубликованных колод/карточек:

1. точное нормализованное совпадение с каноническим вопросом;
2. точное совпадение с формулировкой, которую ранее подтвердил человек;
3. semantic top-N существующим механизмом embeddings;
4. независимый pairwise judge.

Semantic auto-link разрешён только одновременно при:

- допустимом `LearningObjectType`;
- отсутствии критических quality flags;
- совпадении направления;
- similarity не ниже настройки;
- достаточном разрыве между первым и вторым кандидатом;
- ответе judge `same_card`;
- confidence judge не ниже настройки;
- включённом semantic auto-link и выключенном shadow mode.

Ошибка ложного объединения считается хуже пропущенного совпадения. В сомнительном случае occurrence остаётся предложением или попадает в теневой кластер.

## Кластеры и приоритет

Создание кластера сериализуется PostgreSQL advisory lock по узкому ключу `direction:type:normalized`, повторно ищет кластер внутри транзакции и защищено уникальным ограничением. Агрегаты считаются по исходным строкам, а не инкрементами:

- appearances;
- уникальные интервью, компании и ученики;
- уникальные интервью со слабым/отсутствующим ответом;
- первая/последняя дата;
- quality, confidence и воспроизводимый priority score.

Кластер поднимается из shadow в `needs_review`, когда достигнут хотя бы один порог: число уникальных интервью, компаний, слабых ответов либо ручная пометка важности. Повторные появления обновляют одну задачу — отдельная таблица задач на каждое появление не создаётся.

## Answer contract

Для созревшего кластера сильная модель получает только явно разрешённые опубликованные источники того же направления: существующие карточки, статьи базы знаний и материалы роадмапа. Ответ кандидата и сырая транскрипция не являются источниками истины.

Structured Output содержит краткий ответ, обязательные/дополнительные пункты, ошибки, follow-up, уровень, version scope, ссылки на source IDs и confidence. Затем отдельный вызов валидирует поддержку, противоречия и пробелы. Backend повторно проверяет allowlist source IDs. Без источников или подтверждения статус становится `needs_expert_source`/`needs_manual_review`; новая общая карточка всё равно создаётся только администратором.

## Личное повторение

Если ответ слабый или отсутствует:

- при найденной общей карточке существующий Anki-progress становится due немедленно;
- без общей карточки и при включённом флаге создаётся ровно один приватный `PersonalReviewItem` на `(student, occurrence)`;
- ученик видит только свои элементы, ментор/админ — только в разрешённом контексте;
- четыре успешных повторения переводят элемент в mastered;
- после ручного создания канонической карточки временный элемент архивируется/помечается заменённым.

Личный элемент не влияет на глобальную частотность и не виден другим ученикам.

## Feature flags и безопасные значения

Настройки хранятся в БД отдельно для Python и Go. После миграции:

- `enabled=false`;
- `shadow_mode=true`;
- все auto-link/auto-ignore выключены;
- `personal_review_enabled=false`;
- `cluster_moderation_enabled=false`;
- `legacy_queue_enabled=true`;
- `global_auto_publish_enabled=false`.

Последний флаг нельзя включить ни API-схемой, ни DB check constraint. Старая очередь модерации остаётся доступной во время всего rollout.
API и БД также запрещают выключить legacy queue, пока одновременно не включены automation и cluster moderation: вопросы не могут остаться без какого-либо пути модерации.

## API и права

Администратор управляет кластерами, bulk actions, настройками и аудитом. Ментор читает только направления, которые ведёт, и выполняет ограниченные review-действия. Ученик получает только собственную очередь личного повторения. Все мутации проверяют ожидаемую версию и записывают audit; конфликт возвращает HTTP 409. Повторная отправка с тем же `Idempotency-Key` не повторяет действие.

Основные маршруты находятся под:

- `/api/v1/admin/card-automation/*`;
- `/api/v1/mentor/card-automation/*`;
- `/api/v1/students/me/personal-review-items/*`.

Администратор сохраняет проверенную формулировку, тему и answer contract отдельно через
`PATCH /api/v1/admin/card-automation/clusters/{cluster_id}/draft`. Запрос требует
`expected_version`, причину и `Idempotency-Key`, попадает в audit и сам по себе не создаёт
общую карточку. Изменение смысла вопроса очищает устаревший embedding, а изменение смысла
или answer contract возвращает ответ в ручную проверку. Создание канонической карточки
остаётся отдельным явным действием администратора через `create-card`.

## Rollout

Перед production-миграцией сделайте резервную копию:

```bash
make prod-backup
make prod-migrate
```

Рекомендуемый порядок для каждого направления отдельно:

1. Оставить automation выключенной, проверить миграцию и старую очередь.
2. Включить `enabled` и `shadow_mode`; auto-link оставить выключенным.
3. Сделать dry-run и небольшой backfill.
4. Сравнить shadow decisions с человеческой разметкой offline evaluation.
5. После приемлемого false-merge rate включить noise/exact/confirmed-alias automation.
6. Несколько дней проверять audit sample и override rate.
7. Отдельно включить conservative semantic auto-link.
8. Отдельно включить личные повторения.
9. Только после проверки включить cluster moderation UI; legacy queue пока оставить.

Примеры:

```bash
make card-automation-backfill CARD_AUTOMATION_ARGS='--direction python --dry-run --batch-size 100'
make card-automation-backfill CARD_AUTOMATION_ARGS='--direction python --unreviewed-only --batch-size 50 --max-ai-requests 200'
make card-automation-evaluate CARD_AUTOMATION_ARGS='--direction python --from-date 2026-07-01 --to-date 2026-08-16'

make prod-card-automation-backfill CARD_AUTOMATION_ARGS='--direction go --dry-run --batch-size 100'
make prod-card-automation-evaluate CARD_AUTOMATION_ARGS='--direction go --from-date 2026-07-01'
```

### Безопасный backfill

Backfill идемпотентен и возобновляем: он обрабатывает данные маленькими batch и ставит revision-aware jobs с устойчивым job key. Флаг `--resume` оставлен явным для runbook, но возобновление безопасно и без него: завершённые состояния больше не выбираются, а повторная постановка ещё не выполненного `CREATED` occurrence дедуплицируется Redis по UUID и revision.

Скрипт выбирает только вопросы со статусом ручной модерации `PENDING`, без публичной карточки и без human-confirmed alias. `APPROVED`, `REJECTED` и `MENTOR_APPROVED` не меняются ни в обычном режиме, ни с `--unreviewed-only`. Dry-run выполняет те же SELECT и подсчёт, но не меняет строки и не обращается к Redis:

```bash
make prod-card-automation-backfill CARD_AUTOMATION_ARGS='--direction python --dry-run --batch-size 100 --max-ai-requests 200'
```

`--max-ai-requests` — консервативный бюджет, а не число occurrence. На один occurrence резервируется восемь запросов: routing + максимум один pairwise judge на каждую из четырёх ARQ-попыток. Поэтому бюджет `200` подготовит максимум `floor(200 / 8) = 25` occurrence и выведет `reserved_ai_requests`. Кэш и rule-only пути обычно уменьшают фактический расход, но не увеличивают резерв.

Боевой бюджетный запуск отклоняется, если для выбранного направления включён `cluster_moderation_enabled`: генерация и валидация answer contract — отдельные AI jobs и иначе смогли бы выйти за этот бюджет. Dry-run остаётся доступным, так как он не создаёт jobs. Оставляйте cluster moderation выключенной до полного опустошения очереди backfill. Это также защищает от её случайного включения до запуска; переключение настройки во время уже выполняющейся очереди остаётся операционным риском, поэтому rollout нужно выполнять последовательно.

### Повторная классификация кластеров без темы

Для уже созданных кластеров используйте отдельную команду. Она не трогает опубликованные карточки, вопросы с ручным решением и подтверждённые человеком aliases. По умолчанию команда работает в dry-run и только показывает объём работ:

```bash
make prod-card-automation-reprocess-missing-topics \
  CARD_TOPIC_REPROCESS_ARGS='--direction python'
```

Для первого боевого запуска оставьте `shadow_mode` включённым и задайте небольшой AI-бюджет:

```bash
make prod-card-automation-reprocess-missing-topics \
  CARD_TOPIC_REPROCESS_ARGS='--direction python --execute --max-ai-requests 160'
```

На один occurrence консервативно резервируется до 16 AI-запросов с учётом повторной маршрутизации, сравнения кандидатов, генерации ответа и возможных повторных попыток. Бюджет `160` поэтому поставит в очередь не более 10 occurrences; фактический расход обычно меньше. Кластер всегда переносится целиком и не разрезается границей бюджета.

По умолчанию повторно обрабатываются кластеры без широкой темы или с темой, которой нет среди опубликованных карточек этого направления. Чтобы дополнительно переобработать кластеры с корректной широкой темой, но без детальной подтемы, добавьте `--include-missing-subtopics`:

```bash
make prod-card-automation-reprocess-missing-topics \
  CARD_TOPIC_REPROCESS_ARGS='--direction python --include-missing-subtopics'
```

Перед `--execute` automation должна быть включена, а `shadow_mode` — оставаться включённым до опустошения созданной очереди. `intelligence-ai-worker` должен работать. Дождитесь завершения batch перед следующим запуском и повторяйте небольшие запуски, пока dry-run не покажет `prepared_occurrences: 0`. Для уже кластеризованных вопросов не используйте старый `prod-card-automation-backfill`: он предназначен для первоначальной обработки occurrence.

### Offline evaluation без утечки ground truth

Evaluation является строго read-only: выполняет только `SELECT`, не вызывает OpenAI, не строит embeddings и не создаёт `AutomationDecision`. Человеческая разметка определяется так:

- `APPROVED` со ссылкой на ранее существовавшую карточку — `existing_card`;
- `APPROVED`, создавший legacy-карточку `ai-{question_id}` — `new_card`;
- `REJECTED` — историческая метка отклонения;
- `APPROVED` без сохранившейся карточки исключается из знаменателей и отражается в `excluded_examples`.

Для каждого примера используется временной срез на момент `admin_reviewed_at` (с безопасным fallback на `updated_at`/`created_at`):

- карточка должна быть создана не позднее человеческого решения и оставаться опубликованной в текущем snapshot;
- карточка `ai-{question_id}`, созданная из самого примера, всегда исключается из кандидатов;
- alias должен быть подтверждён человеком строго раньше решения, а текущий occurrence не может быть собственным доказательством;
- saved automation decision учитывается только если он создан строго до human label и его source не `HUMAN`;
- post-label decisions и aliases не используются.

Это предотвращает распространённую ошибку, когда evaluator «угадывает» правильную карточку только потому, что проверяемый вопрос уже был к ней привязан человеком. Exact canonical и prior-confirmed alias воспроизводятся правилами. Semantic auto-link оценивается только при наличии сохранённого pre-label pairwise decision; CLI не подменяет отсутствующий judge эвристикой. Если решения нет, система честно `abstain`, а ближайший локальный/embedding-кандидат используется только для объяснения примера false split.

Пример запуска и сохранения отчёта:

```bash
make prod-card-automation-evaluate CARD_AUTOMATION_ARGS='--direction python --from-date 2026-01-01 --to-date 2026-08-16 --error-limit 100'
```

`--to-date` включителен целиком в UTC. JSON-отчёт содержит:

- число загруженных, оценённых и исключённых примеров;
- auto-link coverage/precision/recall;
- false merge и false split rate;
- noise precision/recall;
- cluster purity;
- ручные задачи до и оценку задач после automation;
- предполагаемое сокращение очереди;
- долю совпадения сохранённого topic prediction с human category;
- количество реально оценённых saved semantic decisions;
- количество human cluster split решений и перенесённых ими occurrence;
- до 50 (или `--error-limit`) примеров false merge, false split, ошибок noise и topic с вопросом, выбранной/правильной карточкой, similarity, judge, confidence и причиной.

Оценка `estimated_manual_tasks_after` консервативна: сохранённые pre-label cluster decisions используются как есть, а без них unresolved вопросы группируются только по точной нормализованной формулировке. Она не выдаёт желаемый semantic clustering за измеренный результат. `cluster_purity` считается по human card labels внутри этих unresolved clusters.

Ограничения исторической разметки:

- старая очередь не хранила структурированную причину отказа, поэтому `REJECTED` является proxy для noise/non-card и noise-метрики нужно проверять по примерам;
- старый интерфейс мог перезаписать исходный текст отредактированной формулировкой, если отдельная исходная версия тогда не сохранялась;
- история публикации карточек/колод не версионировалась, поэтому evaluator использует текущий published snapshot плюс исторический `created_at`;
- без сохранённого pre-label pairwise результата CLI измеряет точный/alias baseline, но не заявляет качество semantic judge.

Для решения о включении semantic automation используйте выборку, в которой shadow mode успел сохранить pairwise decisions до ручной модерации. Если `saved_semantic_predictions_evaluated = 0`, false merge rate ещё не доказывает безопасность semantic режима.

## Метрики и контроль качества

API метрик показывает объём routing, exact/alias/semantic links, созданные/promoted clusters, личные элементы, ручные задачи на 100 интервью, возраст очереди, override/false-merge/noise false-positive rate и среднюю стоимость на интервью/вопрос/кластер.

Token usage сохраняется всегда. Для денежной оценки задайте актуальные цены настроенных моделей через `OPENAI_LIGHT_INPUT_PRICE_PER_MILLION_USD`, `OPENAI_LIGHT_OUTPUT_PRICE_PER_MILLION_USD`, `OPENAI_ANALYSIS_INPUT_PRICE_PER_MILLION_USD` и `OPENAI_ANALYSIS_OUTPUT_PRICE_PER_MILLION_USD`. Нулевые значения намеренно оставляют `cost` неизвестной, а не выдают ложную оценку; цены не зашиты в код, потому что меняются независимо от релиза платформы.

Перед включением следующего режима проверяйте:

- false merge и reviewed override rate;
- ошибки классификации noise;
- долю решений без достаточного score gap;
- рост AI cost;
- возраст `needs_review`;
- количество `failed` occurrence и stale revisions.

Для включения semantic auto-link требуется репрезентативный pre-label shadow-набор и `false_merge_rate <= 0.01`. Нулевая ошибка на наборе без `saved_semantic_predictions_evaluated` не считается прохождением этого gate.

## Ручной retry и troubleshooting

1. Найдите occurrence/cluster в UI и прочитайте `automation_error` и последнее audit decision.
2. Убедитесь, что для направления включена automation, а `intelligence-ai-worker` и Redis healthy.
3. Используйте ручной reprocess из API/UI: он увеличивает ревизию и создаёт новый уникальный job id.
4. Не меняйте статус строк напрямую: это обходит optimistic locking и audit.
5. Если budgeted backfill остановлен сообщением про `cluster_moderation_enabled`, выключите только cluster moderation для выбранного направления, дождитесь завершения уже запущенных answer jobs и повторите dry-run.
6. Если evaluation показывает `examples=0`, проверьте период, slug направления и наличие финальных `APPROVED`/`REJECTED` human labels. Если semantic count равен нулю, сначала накопите shadow decisions, а не включайте semantic auto-link по exact-only метрикам.

Полезные команды:

```bash
docker compose -f infra/docker-compose.yml --env-file .env ps
docker compose -f infra/docker-compose.yml --env-file .env logs --tail=200 intelligence-ai-worker
make test-backend
make test-frontend
make lint
make typecheck
```

Ошибки AI с retryable-признаком получают ограниченный exponential backoff. Невалидный или исчерпавший retries результат переводит сущность в явный `failed`/`needs_manual_review`, а не оставляет её «подвисшей».

## Удаление и rollback

При удалении AI-разбора или трека собеседований сервис сначала определяет затронутые карточки/кластеры, удаляет карточные occurrence, архивирует личные элементы, а после каскада пересчитывает частотность и статистику. Подтверждённая каноническая карточка не удаляется.

Для application rollback сначала выключите automation и оставьте legacy queue. После остановки новых jobs можно вернуть предыдущий backend/frontend. Downgrade миграции удаляет только добавленные структуры/поля, поэтому перед ним обязательно нужен backup; результаты automation после downgrade будут потеряны. Не используйте `docker compose down -v`.

## Тестирование

```bash
make ensure-test-db
cd backend && poetry run pytest
cd backend && poetry run ruff check app tests
cd backend && poetry run mypy app
cd frontend && pnpm test
cd frontend && pnpm lint
cd frontend && pnpm typecheck
cd frontend && pnpm build
```

Особенно важны сценарии exact/alias, score gap, related-but-different scope, singleton shadow, promotion по независимым интервью, retry/idempotency, параллельное создание кластера, личное повторение, удаление/пересчёт и границы доступа.
