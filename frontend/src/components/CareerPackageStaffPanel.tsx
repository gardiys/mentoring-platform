import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/endpoints";
import { CareerPackageContent } from "./CareerPackageContent";
import { useMe } from "../features/auth/queries";
import {
  useCareerPackageActions,
  useCareerTrackOptions,
  useStaffCareerPackages,
} from "../features/careerPackages/queries";
import type {
  CareerActiveSearchParameters,
  CareerPackage,
  CareerSelfPresentationCard,
  CareerSourceData,
} from "../types/api";
import { openExternalResource } from "../utils/openExternalResource";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

const statusLabels: Record<CareerPackage["status"], string> = {
  not_started: "Не начат",
  collecting_data: "Сбор данных",
  generating: "AI формирует черновик",
  draft: "Черновик",
  review_required: "Требуется проверка",
  ready_to_publish: "Готов к публикации",
  delivery_pending: "Предоставляется",
  provided: "Предоставлен",
  revision_requested: "Запрошены исправления",
  cancelled: "Отменён",
};

const deliveryChannelLabels: Record<
  CareerPackage["deliveries"][number]["channel"],
  string
> = {
  platform: "Платформа",
  telegram: "Telegram",
  email: "Email",
};

const deliveryStatusLabels: Record<
  CareerPackage["deliveries"][number]["status"],
  string
> = {
  pending: "Ожидает отправки",
  delivered: "Доставлено",
  failed: "Ошибка доставки",
};

const deliveryPurposeLabels: Record<
  CareerPackage["deliveries"][number]["purpose"],
  string
> = {
  package_provided: "Предоставление пакета",
  payment_obligation: "Уведомление об оплате",
};

const splitLines = (value: string) =>
  value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

const joinLines = (value: string[] | undefined) => (value ?? []).join("\n");

const sourceTemplate = (direction: string) => {
  const isGo = direction.toLocaleLowerCase("ru").includes("go");
  return {
    target_positions: isGo
      ? "Go backend-разработчик\nGolang-разработчик"
      : "Python backend-разработчик",
    target_seniority: "Middle",
    primary_stack: isGo
      ? "Go\nPostgreSQL\nDocker\nKafka"
      : "Python\nFastAPI\nPostgreSQL\nDocker",
    employment_formats: "Полная занятость",
    geography: "Россия",
    remote_preferences: "Удалённая работа или гибрид",
    relocation_preferences: "Не готов к релокации",
    salary_min: 0,
    salary_target: 0,
    salary_currency: "RUB" as const,
    search_start_date: new Date().toISOString().slice(0, 10),
    applications_per_week: 25,
    preparation_priorities: isGo
      ? "Go и конкурентность\nАрхитектура backend-сервисов\nPostgreSQL\nСистемный дизайн"
      : "Python Core\nАрхитектура backend-сервисов\nPostgreSQL\nСистемный дизайн",
    mentor_context: "",
  };
};

const sourceFormValue = (packageItem: CareerPackage) => {
  const source = packageItem.source_data;
  if (!source) return sourceTemplate(packageItem.direction);
  return {
    target_positions: joinLines(source.target_positions),
    target_seniority: source.target_seniority,
    primary_stack: joinLines(source.primary_stack),
    employment_formats: joinLines(source.employment_formats),
    geography: joinLines(source.geography),
    remote_preferences: source.remote_preferences,
    relocation_preferences: source.relocation_preferences,
    salary_min: source.salary_min,
    salary_target: source.salary_target,
    salary_currency: source.salary_currency,
    search_start_date: source.search_start_date,
    applications_per_week: source.applications_per_week,
    preparation_priorities: joinLines(source.preparation_priorities),
    mentor_context: source.mentor_context ?? "",
  };
};

function notifyError(error: Error) {
  notifications.show({ color: "red", message: error.message });
}

function SourceEditor({
  packageItem,
  onSave,
  pending,
}: {
  packageItem: CareerPackage;
  onSave: (value: CareerSourceData) => void;
  pending: boolean;
}) {
  const source = packageItem.source_data;
  const [value, setValue] = useState(() => sourceFormValue(packageItem));

  useEffect(() => {
    setValue(sourceFormValue(packageItem));
  }, [packageItem.id, packageItem.direction, source]);

  const invalid =
    !value.target_positions.trim() ||
    !value.target_seniority.trim() ||
    !value.primary_stack.trim() ||
    !value.employment_formats.trim() ||
    !value.geography.trim() ||
    !value.remote_preferences.trim() ||
    !value.relocation_preferences.trim() ||
    !value.preparation_priorities.trim() ||
    value.salary_target < value.salary_min;

  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={3}>1. Фактические данные ученика</Title>
          <Text size="sm" c="dimmed">
            AI получает только резюме и эти данные. По одному значению на
            строку.
          </Text>
        </div>
        {!source && (
          <Alert color="blue" title={`Шаблон для направления ${packageItem.direction}`}>
            Типовые значения уже заполнены. Проверьте уровень, географию,
            зарплату и предпочтения конкретного ученика перед сохранением.
          </Alert>
        )}
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Textarea
            label="Целевые позиции"
            value={value.target_positions}
            onChange={(e) =>
              setValue({ ...value, target_positions: e.currentTarget.value })
            }
            minRows={2}
            required
          />
          <TextInput
            label="Целевой уровень"
            value={value.target_seniority}
            onChange={(e) =>
              setValue({ ...value, target_seniority: e.currentTarget.value })
            }
            required
          />
          <Textarea
            label="Основной стек"
            value={value.primary_stack}
            onChange={(e) =>
              setValue({ ...value, primary_stack: e.currentTarget.value })
            }
            minRows={2}
            required
          />
          <Textarea
            label="Форматы занятости"
            value={value.employment_formats}
            onChange={(e) =>
              setValue({ ...value, employment_formats: e.currentTarget.value })
            }
            minRows={2}
            required
          />
          <Textarea
            label="География"
            value={value.geography}
            onChange={(e) =>
              setValue({ ...value, geography: e.currentTarget.value })
            }
            minRows={2}
            required
          />
          <TextInput
            label="Удалённая работа"
            value={value.remote_preferences}
            onChange={(e) =>
              setValue({ ...value, remote_preferences: e.currentTarget.value })
            }
            required
          />
          <TextInput
            label="Релокация"
            value={value.relocation_preferences}
            onChange={(e) =>
              setValue({
                ...value,
                relocation_preferences: e.currentTarget.value,
              })
            }
            required
          />
          <Select
            label="Валюта"
            data={["RUB", "USD", "EUR"]}
            value={value.salary_currency}
            onChange={(next) =>
              next &&
              setValue({
                ...value,
                salary_currency: next as CareerSourceData["salary_currency"],
              })
            }
          />
          <NumberInput
            label="Минимальная зарплата"
            min={0}
            value={value.salary_min}
            onChange={(next) =>
              setValue({ ...value, salary_min: Number(next) || 0 })
            }
          />
          <NumberInput
            label="Целевая зарплата"
            min={0}
            value={value.salary_target}
            onChange={(next) =>
              setValue({ ...value, salary_target: Number(next) || 0 })
            }
          />
          <TextInput
            type="date"
            label="Начало поиска"
            value={value.search_start_date}
            onChange={(e) =>
              setValue({ ...value, search_start_date: e.currentTarget.value })
            }
            required
          />
          <NumberInput
            label="Откликов в неделю"
            min={1}
            value={value.applications_per_week}
            onChange={(next) =>
              setValue({ ...value, applications_per_week: Number(next) || 1 })
            }
          />
        </SimpleGrid>
        <Textarea
          label="Приоритеты подготовки"
          description="По одному на строку"
          value={value.preparation_priorities}
          onChange={(e) =>
            setValue({
              ...value,
              preparation_priorities: e.currentTarget.value,
            })
          }
          minRows={3}
          required
        />
        <Textarea
          label="Контекст ментора"
          value={value.mentor_context}
          onChange={(e) =>
            setValue({ ...value, mentor_context: e.currentTarget.value })
          }
          minRows={3}
        />
        <Group justify="flex-end">
          <Button
            disabled={invalid}
            loading={pending}
            onClick={() =>
              onSave({
                target_positions: splitLines(value.target_positions),
                target_seniority: value.target_seniority.trim(),
                primary_stack: splitLines(value.primary_stack),
                employment_formats: splitLines(value.employment_formats),
                geography: splitLines(value.geography),
                remote_preferences: value.remote_preferences.trim(),
                relocation_preferences: value.relocation_preferences.trim(),
                salary_min: value.salary_min,
                salary_target: value.salary_target,
                salary_currency: value.salary_currency,
                search_start_date: value.search_start_date,
                applications_per_week: value.applications_per_week,
                preparation_priorities: splitLines(
                  value.preparation_priorities,
                ),
                mentor_context: value.mentor_context.trim() || null,
              })
            }
          >
            Сохранить исходные данные
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function GeneratedEditor({
  packageItem,
  onSave,
  pending,
}: {
  packageItem: CareerPackage;
  onSave: (
    card: CareerSelfPresentationCard,
    search: CareerActiveSearchParameters,
  ) => void;
  pending: boolean;
}) {
  const initial = useMemo(
    () => ({
      card: packageItem.self_presentation_card,
      search: packageItem.active_search_parameters,
    }),
    [packageItem],
  );
  const [cardJson, setCardJson] = useState(() =>
    JSON.stringify(initial.card, null, 2),
  );
  const [searchJson, setSearchJson] = useState(() =>
    JSON.stringify(initial.search, null, 2),
  );
  const [parseError, setParseError] = useState<string | null>(null);
  useEffect(() => {
    setCardJson(JSON.stringify(initial.card, null, 2));
    setSearchJson(JSON.stringify(initial.search, null, 2));
  }, [initial]);
  if (
    !packageItem.self_presentation_card ||
    !packageItem.active_search_parameters
  )
    return null;
  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={3}>3. Проверка и редактирование AI-черновика</Title>
          <Text size="sm" c="dimmed">
            Проверьте факты, формулировки и отсутствие вымышленных данных.
            Публикация выполняется отдельно.
          </Text>
        </div>
        <CareerPackageContent
          selfPresentation={packageItem.self_presentation_card}
          activeSearch={packageItem.active_search_parameters}
        />
        {parseError && <Alert color="red">{parseError}</Alert>}
        <Accordion
          multiple
          defaultValue={["presentation", "search"]}
          className="brand-accordion"
        >
          <Accordion.Item value="presentation">
            <Accordion.Control>Карта самопрезентации</Accordion.Control>
            <Accordion.Panel>
              <Textarea
                value={cardJson}
                onChange={(e) => setCardJson(e.currentTarget.value)}
                autosize
                minRows={12}
                styles={{ input: { fontFamily: "monospace" } }}
              />
            </Accordion.Panel>
          </Accordion.Item>
          <Accordion.Item value="search">
            <Accordion.Control>Параметры активного поиска</Accordion.Control>
            <Accordion.Panel>
              <Textarea
                value={searchJson}
                onChange={(e) => setSearchJson(e.currentTarget.value)}
                autosize
                minRows={12}
                styles={{ input: { fontFamily: "monospace" } }}
              />
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
        <Group justify="flex-end">
          <Button
            loading={pending}
            onClick={() => {
              try {
                const card = JSON.parse(cardJson) as CareerSelfPresentationCard;
                const search = JSON.parse(
                  searchJson,
                ) as CareerActiveSearchParameters;
                setParseError(null);
                onSave(card, search);
              } catch {
                setParseError("Исправьте синтаксис данных перед сохранением.");
              }
            }}
          >
            Сохранить проверенный черновик
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function ReviewForm({
  pending,
  onSubmit,
}: {
  pending: boolean;
  onSubmit: (payload: Parameters<typeof api.saveCareerReview>[1]) => void;
}) {
  const [heldAt, setHeldAt] = useState("");
  const [strengths, setStrengths] = useState("");
  const [improvements, setImprovements] = useState("");
  const [nextAttempt, setNextAttempt] = useState("");
  const [notes, setNotes] = useState("");
  const [send, setSend] = useState(true);
  const [createDraft, setCreateDraft] = useState(false);
  const valid =
    heldAt && strengths.trim() && improvements.trim() && nextAttempt.trim();
  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={3}>Созвон по самопрезентации</Title>
          <Text size="sm" c="dimmed">
            Созвон не блокирует выдачу пакета. Результат хранится отдельно и
            может стать основанием новой редакции.
          </Text>
        </div>
        <TextInput
          type="datetime-local"
          label="Дата и время созвона"
          value={heldAt}
          onChange={(event) => setHeldAt(event.currentTarget.value)}
          required
        />
        <Textarea
          label="Что получилось хорошо"
          minRows={3}
          value={strengths}
          onChange={(event) => setStrengths(event.currentTarget.value)}
          required
        />
        <Textarea
          label="Что улучшить"
          minRows={3}
          value={improvements}
          onChange={(event) => setImprovements(event.currentTarget.value)}
          required
        />
        <Textarea
          label="Что подготовить к следующей попытке"
          minRows={3}
          value={nextAttempt}
          onChange={(event) => setNextAttempt(event.currentTarget.value)}
          required
        />
        <Textarea
          label="Дополнительные заметки"
          value={notes}
          onChange={(event) => setNotes(event.currentTarget.value)}
        />
        <Checkbox
          label="Показать результат ученику"
          checked={send}
          onChange={(event) => setSend(event.currentTarget.checked)}
        />
        <Checkbox
          label="Добавить рекомендации в новый черновик пакета"
          checked={createDraft}
          onChange={(event) => setCreateDraft(event.currentTarget.checked)}
        />
        <Group justify="flex-end">
          <Button
            disabled={!valid}
            loading={pending}
            onClick={() =>
              onSubmit({
                held_at: new Date(heldAt).toISOString(),
                strengths: strengths.trim(),
                improvements: improvements.trim(),
                preparation_for_next_attempt: nextAttempt.trim(),
                additional_notes: notes.trim() || null,
                send_to_student: send,
                create_draft_from_review: createDraft,
              })
            }
          >
            Сохранить итоги созвона
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

export function CareerPackageStaffPanel({ studentId }: { studentId: string }) {
  const me = useMe();
  const packages = useStaffCareerPackages(studentId);
  const options = useCareerTrackOptions(studentId);
  const actions = useCareerPackageActions(studentId);
  const [trackId, setTrackId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [obligationOpened, setObligationOpened] = useState(false);
  const [offerAcceptedOn, setOfferAcceptedOn] = useState("");
  const [recordComment, setRecordComment] = useState("");
  const [eligibilityConfirmed, setEligibilityConfirmed] = useState(false);
  const packageItem =
    packages.data?.find((item) => item.id === selectedId) ?? packages.data?.[0];

  const execute = <T,>(promise: Promise<T>, message: string) =>
    promise
      .then(() => notifications.show({ color: "green", message }))
      .catch((error: Error) => notifyError(error));

  if (packages.isPending || options.isPending) return <LoadingState />;
  if (packages.isError)
    return (
      <ErrorState
        error={packages.error}
        retry={() => void packages.refetch()}
      />
    );
  if (options.isError)
    return (
      <ErrorState error={options.error} retry={() => void options.refetch()} />
    );

  if (!packageItem) {
    return (
      <Card withBorder>
        <Stack>
          <Title order={3}>Создать Карьерный пакет</Title>
          <Text c="dimmed">
            Выберите направление ученика. Для каждого направления создаётся один
            пакет с историей версий.
          </Text>
          <Select
            label="Направление"
            data={options.data.map((item) => ({
              value: item.id,
              label: item.title,
            }))}
            value={trackId}
            onChange={setTrackId}
          />
          <Button
            disabled={!trackId}
            loading={actions.create.isPending}
            onClick={() =>
              trackId &&
              execute(
                actions.create.mutateAsync(trackId),
                "Карьерный пакет создан",
              )
            }
          >
            Создать пакет
          </Button>
        </Stack>
      </Card>
    );
  }
  const latestVersion = packageItem.versions[0];
  const isAdmin = me.data?.role === "admin";
  const canRecordObligation =
    isAdmin &&
    packageItem.status === "provided" &&
    (!packageItem.obligation || packageItem.obligation.status === "cancelled");

  const running = packageItem.status === "generating";
  return (
    <Stack gap="xl">
      <Modal
        opened={obligationOpened}
        onClose={() => setObligationOpened(false)}
        title="Зафиксировать обязательство"
        centered
      >
        <Stack>
          <Alert color="blue" title="Уведомление пока не отправляется">
            Здесь фиксируется уже возникшее обязательство на 30 000 ₽. Ученик
            его пока не увидит, а срок оплаты и просрочка не начнутся. Для этого
            используется отдельная кнопка уведомления.
          </Alert>
          <TextInput
            type="date"
            label="Дата акцепта применимой оферты"
            description="Допускается редакция от 03.09.2026 или более поздняя"
            min="2026-09-03"
            value={offerAcceptedOn}
            onChange={(event) => setOfferAcceptedOn(event.currentTarget.value)}
            required
          />
          <Textarea
            label="Комментарий администратора"
            description="Необязательно. Укажите основание и подтверждающие обстоятельства."
            minRows={3}
            maxLength={1000}
            value={recordComment}
            onChange={(event) => setRecordComment(event.currentTarget.value)}
          />
          <Checkbox
            checked={eligibilityConfirmed}
            onChange={(event) =>
              setEligibilityConfirmed(event.currentTarget.checked)
            }
            label="Подтверждаю, что ученик акцептовал применимую редакцию оферты и полный Карьерный пакет фактически предоставлен"
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setObligationOpened(false)}>
              Отмена
            </Button>
            <Button
              disabled={!offerAcceptedOn || !eligibilityConfirmed}
              loading={actions.recordObligation.isPending}
              onClick={() => {
                void actions.recordObligation
                  .mutateAsync({
                    packageId: packageItem.id,
                    offerAcceptedOn,
                    recordComment: recordComment.trim() || null,
                  })
                  .then(() => {
                    setObligationOpened(false);
                    setEligibilityConfirmed(false);
                    notifications.show({
                      color: "green",
                      message: "Обязательство зафиксировано без уведомления ученика",
                    });
                  })
                  .catch((error: Error) => notifyError(error));
              }}
            >
              Зафиксировать без уведомления
            </Button>
          </Group>
        </Stack>
      </Modal>
      <Group justify="space-between">
        <div>
          <Group gap="xs">
            <Title order={2}>Карьерный пакет</Title>
            <Badge>{packageItem.direction}</Badge>
            <Badge color={packageItem.status === "provided" ? "green" : "blue"}>
              {statusLabels[packageItem.status]}
            </Badge>
          </Group>
          <Text c="dimmed" size="sm">
            Версия черновика {packageItem.lock_version}
          </Text>
        </div>
        {(packages.data?.length ?? 0) > 1 && (
          <Select
            value={packageItem.id}
            onChange={setSelectedId}
            data={(packages.data ?? []).map((item) => ({
              value: item.id,
              label: item.direction,
            }))}
          />
        )}
      </Group>

      {packageItem.is_stale && (
        <Alert color="yellow" title="Резюме изменилось">
          AI-черновик создан по другой версии резюме. Перегенерируйте или
          перепроверьте его.
        </Alert>
      )}
      <Card withBorder>
        <Stack>
          <Title order={3}>Финальная версия резюме</Title>
          <Text>
            {packageItem.source_resume_version
              ? `Зафиксирована версия ${packageItem.source_resume_version.version_number} · SHA-256 ${packageItem.source_resume_version.content_sha256.slice(0, 16)}…`
              : "Версия ещё не зафиксирована"}
          </Text>
          <Group>
            <Button
              variant="light"
              loading={actions.finalizeResume.isPending}
              onClick={() =>
                execute(
                  actions.finalizeResume.mutateAsync(packageItem.id),
                  "Финальная версия резюме зафиксирована",
                )
              }
            >
              Зафиксировать текущее резюме
            </Button>
            {latestVersion && (
              <Button
                variant="subtle"
                onClick={() =>
                  void openExternalResource(
                    api.careerPackageResumeUrl(latestVersion.id),
                  )
                }
              >
                Скачать резюме версии
              </Button>
            )}
          </Group>
        </Stack>
      </Card>

      <SourceEditor
        packageItem={packageItem}
        pending={actions.saveDraft.isPending}
        onSave={(sourceData) =>
          execute(
            actions.saveDraft.mutateAsync({
              packageId: packageItem.id,
              lockVersion: packageItem.lock_version,
              sourceData,
            }),
            "Исходные данные сохранены",
          )
        }
      />

      <Card withBorder>
        <Stack>
          <Title order={3}>2. AI-формирование</Title>
          <Text c="dimmed">
            AI формирует только черновик. Проверьте его вручную до публикации.
          </Text>
          <Group>
            <Button
              disabled={
                running ||
                !packageItem.source_data ||
                !packageItem.source_resume_version
              }
              loading={actions.generate.isPending || running}
              onClick={() =>
                execute(
                  actions.generate.mutateAsync(packageItem.id),
                  "Генерация запущена",
                )
              }
            >
              {running ? "Формируем…" : "Сформировать два раздела"}
            </Button>
          </Group>
          {packageItem.generation_runs[0]?.safe_error_message && (
            <Alert color="red" title="Генерация не завершена">
              {packageItem.generation_runs[0].safe_error_message}
            </Alert>
          )}
          {packageItem.missing_data.map((item) => (
            <Alert
              key={item.field}
              color={item.blocking ? "red" : "yellow"}
              title={item.field}
            >
              {item.reason}
            </Alert>
          ))}
          {packageItem.warnings.map((item) => (
            <Alert key={item.code} color="yellow">
              {item.message}
            </Alert>
          ))}
        </Stack>
      </Card>

      <GeneratedEditor
        packageItem={packageItem}
        pending={actions.saveDraft.isPending}
        onSave={(selfPresentationCard, activeSearchParameters) =>
          execute(
            actions.saveDraft.mutateAsync({
              packageId: packageItem.id,
              lockVersion: packageItem.lock_version,
              selfPresentationCard,
              activeSearchParameters,
            }),
            "Проверенный черновик сохранён",
          )
        }
      />

      <Card withBorder>
        <Stack>
          <Title order={3}>4. Комплектность и предоставление</Title>
          {packageItem.readiness.complete ? (
            <Alert color="green">Все три обязательных компонента готовы.</Alert>
          ) : (
            <Alert color="yellow" title="Не хватает данных">
              {packageItem.readiness.missing.join(", ") ||
                "Устраните блокирующие замечания AI"}
            </Alert>
          )}
          <Group>
            <Button
              variant="light"
              loading={actions.validate.isPending}
              onClick={() =>
                execute(
                  actions.validate.mutateAsync(packageItem.id),
                  "Комплектность проверена",
                )
              }
            >
              Проверить комплектность
            </Button>
            <Button
              color="green"
              disabled={packageItem.status !== "ready_to_publish"}
              loading={actions.publish.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    "Опубликовать неизменяемую версию и уведомить ученика? Обязательство по оплате сейчас создано не будет.",
                  )
                )
                  void execute(
                    actions.publish.mutateAsync(packageItem.id),
                    "Карьерный пакет предоставлен ученику",
                  );
              }}
            >
              Опубликовать и предоставить
            </Button>
          </Group>
          {packageItem.status === "provided" && !packageItem.obligation && (
            <Alert color="green" title="Оплата сейчас не требуется">
              Пакет предоставлен для выхода на рынок. Возникшее обязательство
              отдельно фиксируется администратором при наличии основания.
            </Alert>
          )}
          {packageItem.obligation && (
            <Alert
              color={
                packageItem.obligation.status === "active"
                  ? "red"
                  : packageItem.obligation.status === "awaiting_notice"
                    ? "yellow"
                    : "gray"
              }
              title={
                packageItem.obligation.status === "active"
                  ? "Срок оплаты запущен"
                  : packageItem.obligation.status === "awaiting_notice"
                    ? "Обязательство зафиксировано — уведомление не отправлено"
                  : `Обязательство: ${packageItem.obligation.status}`
              }
            >
              30 000 ₽
              {packageItem.obligation.due_at
                ? ` · оплатить до ${new Date(
                    packageItem.obligation.due_at,
                  ).toLocaleDateString("ru-RU")}`
                : " · срок оплаты ещё не установлен"}
              {packageItem.obligation.recorded_at && (
                <Text size="sm" mt="xs">
                  Зафиксировано{" "}
                  {new Date(packageItem.obligation.recorded_at).toLocaleString(
                    "ru-RU",
                  )}
                </Text>
              )}
              {packageItem.obligation.status === "awaiting_notice" && (
                <Text size="sm" mt="xs">
                  По оферте уведомление следует направить не позднее одного
                  рабочего дня с фактического предоставления полного пакета.
                </Text>
              )}
            </Alert>
          )}
          {canRecordObligation && (
            <Group>
              <Button onClick={() => setObligationOpened(true)}>
                Зафиксировать обязательство
              </Button>
              <Text size="sm" c="dimmed">
                Без уведомления ученика и без запуска срока оплаты.
              </Text>
            </Group>
          )}
          {isAdmin &&
            packageItem.status === "provided" &&
            packageItem.obligation?.status === "awaiting_notice" && (
              <Group>
                <Button
                  color="red"
                  loading={actions.sendObligationNotice.isPending}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "Отправить ученику юридически значимое уведомление? Оно сразу появится на платформе, а срок оплаты 10 дней начнётся с текущего момента.",
                      )
                    )
                      return;
                    void execute(
                      actions.sendObligationNotice.mutateAsync(packageItem.id),
                      "Уведомление доставлено на платформе, срок оплаты запущен",
                    );
                  }}
                >
                  Уведомить и запустить срок 10 дней
                </Button>
                <Text size="sm" c="dimmed">
                  Email и Telegram будут поставлены в очередь как дополнительные
                  каналы доставки.
                </Text>
              </Group>
            )}
        </Stack>
      </Card>

      {packageItem.versions.length > 0 && (
        <Card withBorder>
          <Stack>
            <Title order={3}>Опубликованные версии</Title>
            {packageItem.versions.map((version) => (
              <Group key={version.id} justify="space-between">
                <div>
                  <Text fw={700}>Версия {version.version_number}</Text>
                  <Text size="sm" c="dimmed">
                    Предоставлена{" "}
                    {version.provided_at
                      ? new Date(version.provided_at).toLocaleString("ru-RU")
                      : "—"}{" "}
                    · SHA-256 {version.snapshot_sha256.slice(0, 16)}…
                  </Text>
                </div>
                <Button
                  variant="light"
                  onClick={() =>
                    void openExternalResource(
                      api.careerPackagePdfUrl(version.id),
                    )
                  }
                >
                  Скачать PDF
                </Button>
              </Group>
            ))}
          </Stack>
        </Card>
      )}

      {packageItem.deliveries.length > 0 && (
        <Card withBorder>
          <Stack>
            <div>
              <Title order={3}>Доставка ученику</Title>
              <Text size="sm" c="dimmed">
                Здесь видно, по каким каналам пакет действительно доставлен.
              </Text>
            </div>
            {packageItem.deliveries.map((delivery) => (
              <Group key={delivery.id} justify="space-between" align="flex-start">
                <div>
                  <Group gap="xs">
                    <Text fw={700}>
                      {deliveryChannelLabels[delivery.channel]} ·{" "}
                      {deliveryPurposeLabels[delivery.purpose]}
                    </Text>
                    <Badge
                      color={
                        delivery.status === "delivered"
                          ? "green"
                          : delivery.status === "failed"
                            ? "red"
                            : "yellow"
                      }
                    >
                      {deliveryStatusLabels[delivery.status]}
                    </Badge>
                  </Group>
                  {delivery.safe_error_message && (
                    <Text size="sm" c="red">
                      {delivery.safe_error_message}
                    </Text>
                  )}
                </div>
                {delivery.channel === "email" && delivery.status === "failed" && (
                  <Button
                    variant="light"
                    color="red"
                    loading={
                      delivery.purpose === "payment_obligation"
                        ? actions.retryObligationEmail.isPending
                        : actions.retryEmail.isPending
                    }
                    onClick={() =>
                      execute(
                        delivery.purpose === "payment_obligation"
                          ? actions.retryObligationEmail.mutateAsync(packageItem.id)
                          : actions.retryEmail.mutateAsync(packageItem.id),
                        "Повторная отправка поставлена в очередь",
                      )
                    }
                  >
                    Отправить повторно
                  </Button>
                )}
              </Group>
            ))}
          </Stack>
        </Card>
      )}

      {packageItem.objections.length > 0 && (
        <Card withBorder>
          <Stack>
            <Title order={3}>Возражения ученика</Title>
            {packageItem.objections.map((item) => (
              <Alert
                key={item.id}
                color={item.status === "submitted" ? "yellow" : "gray"}
                title={`${item.component} · ${item.status}`}
              >
                <Text>{item.reason}</Text>
                <Text size="sm" c="dimmed">
                  Ожидаемый результат: {item.expected_result}
                </Text>
                {item.status === "submitted" && (
                  <Group mt="sm">
                    <Button
                      size="xs"
                      variant="light"
                      loading={actions.resolveObjection.isPending}
                      onClick={() => {
                        const comment = window.prompt(
                          "Комментарий ученику по принятому возражению",
                        );
                        if (comment && comment.trim().length >= 3)
                          void execute(
                            actions.resolveObjection.mutateAsync({
                              packageId: packageItem.id,
                              objectionId: item.id,
                              status: "accepted",
                              resolutionComment: comment.trim(),
                              createRevision: true,
                            }),
                            "Возражение принято, создан новый черновик",
                          );
                      }}
                    >
                      Принять и создать редакцию
                    </Button>
                    <Button
                      size="xs"
                      variant="subtle"
                      color="gray"
                      loading={actions.resolveObjection.isPending}
                      onClick={() => {
                        const comment = window.prompt(
                          "Почему возражение отклонено?",
                        );
                        if (comment && comment.trim().length >= 3)
                          void execute(
                            actions.resolveObjection.mutateAsync({
                              packageId: packageItem.id,
                              objectionId: item.id,
                              status: "rejected",
                              resolutionComment: comment.trim(),
                              createRevision: false,
                            }),
                            "Ответ ученику сохранён",
                          );
                      }}
                    >
                      Отклонить
                    </Button>
                  </Group>
                )}
              </Alert>
            ))}
          </Stack>
        </Card>
      )}

      <ReviewForm
        pending={actions.saveReview.isPending}
        onSubmit={(payload) =>
          execute(
            actions.saveReview.mutateAsync({
              packageId: packageItem.id,
              ...payload,
            }),
            "Итоги созвона сохранены",
          )
        }
      />

      {packageItem.reviews.length > 0 && (
        <Card withBorder>
          <Stack>
            <Title order={3}>История созвонов</Title>
            {packageItem.reviews.map((review) => (
              <div key={review.id}>
                <Text fw={700}>
                  {new Date(review.held_at).toLocaleString("ru-RU")}
                </Text>
                <Text size="sm">Что получилось: {review.strengths}</Text>
                <Text size="sm">Что улучшить: {review.improvements}</Text>
              </div>
            ))}
          </Stack>
        </Card>
      )}

      <Accordion className="brand-accordion">
        <Accordion.Item value="audit">
          <Accordion.Control>Техническая история и доставка</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              {packageItem.deliveries.map((item) => (
                <Text key={item.id} size="sm">
                  {item.channel}: {item.status} ·{" "}
                  {new Date(item.attempted_at).toLocaleString("ru-RU")}
                </Text>
              ))}
              {packageItem.audit_timeline?.map((item) => (
                <Text key={item.id} size="sm">
                  {new Date(item.created_at).toLocaleString("ru-RU")} ·{" "}
                  {item.event_type} · {item.actor_role ?? "system"}
                </Text>
              ))}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
