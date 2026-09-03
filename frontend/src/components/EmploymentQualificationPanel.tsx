import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  NumberInput,
  Progress,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  Timeline,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMemo, useState } from "react";

import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import {
  useAssessEmploymentCase,
  useMyEmploymentCases,
  useMyEmploymentTrackOptions,
  useOpenEmploymentDispute,
  useReportEmploymentActualDuties,
  useReportEmploymentChange,
  useReportEmploymentEnd,
  useReportEmploymentOffer,
  useReportEmploymentOfferStatus,
  useReportEmploymentWorkStart,
  useRequestEmploymentInformation,
  useRequestEmploymentAISuggestion,
  useStudentEmploymentCases,
  useUploadEmploymentEvidence,
  useResolveEmploymentDispute,
} from "../features/employment/queries";
import type {
  EmploymentCase,
  EmploymentProfileClassification,
} from "../types/api";

const caseLabels: Record<string, string> = {
  reported: "Сообщено",
  awaiting_initial_documents: "Ждём документы",
  awaiting_actual_duties: "Нужно уточнить обязанности",
  awaiting_staff_review: "На проверке",
  monitoring_non_profile: "Наблюдение за изменениями",
  profile_confirmed: "Профильная работа подтверждена",
  non_profile_confirmed: "Непрофильная работа",
  disputed: "Открыт спор",
  ended: "Работа завершена",
  closed: "Кейс закрыт",
};

const classificationLabels: Record<EmploymentProfileClassification, string> = {
  profile: "Профильная",
  mixed_profile: "Смешанная профильная",
  non_profile: "Непрофильная",
  insufficient_data: "Недостаточно данных",
  disputed: "Спорная",
};

function commaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function showError(error: Error) {
  notifications.show({ color: "red", message: error.message });
}

function CaseSummary({ item }: { item: EmploymentCase }) {
  const assessment = item.assessments.at(-1);
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={3}>{item.company_name}</Title>
          <Text c="dimmed">
            {item.official_job_title ??
              item.vacancy_title ??
              "Должность уточняется"}
            {item.direction
              ? ` · ${item.direction === "python" ? "Python" : "Go"}`
              : ""}
          </Text>
        </div>
        <Badge
          color={item.case_status === "profile_confirmed" ? "green" : "blue"}
        >
          {item.case_status ? caseLabels[item.case_status] : "Архивный кейс"}
        </Badge>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Text size="sm">
          Начало работы: {item.employment_started_at ?? "не подтверждено"}
        </Text>
        <Text size="sm">
          Профильная работа:{" "}
          {item.profile_activity_started_at ?? "не подтверждена"}
        </Text>
        <Text size="sm">
          Договор: {item.policy_version ?? "legacy / не привязан"}
        </Text>
      </SimpleGrid>
      {item.policy_control_period_started_at && (
        <Text size="sm" c="dimmed">
          Контрольный период: {item.policy_control_period_started_at} —{" "}
          {item.policy_control_period_ended_at}
          {item.policy_extension_ended_at
            ? ` · продление до ${item.policy_extension_ended_at}`
            : ""}
        </Text>
      )}
      {item.net_salary_kopecks !== null && (
        <Text size="sm">
          Подтверждённое вознаграждение:{" "}
          {new Intl.NumberFormat("ru-RU", {
            style: "currency",
            currency: "RUB",
            maximumFractionDigits: 0,
          }).format(item.net_salary_kopecks / 100)}
        </Text>
      )}
      {item.actual_stack.length > 0 && (
        <Group gap="xs">
          {item.actual_stack.map((technology) => (
            <Badge key={technology} variant="light">
              {technology}
            </Badge>
          ))}
        </Group>
      )}
      {assessment && (
        <Alert
          color={
            assessment.classification.includes("profile") ? "green" : "blue"
          }
        >
          <Text fw={700}>
            {classificationLabels[assessment.classification]}
          </Text>
          <Text size="sm">{assessment.rationale}</Text>
        </Alert>
      )}
      {item.qualification_window && (
        <Text size="sm" c="dimmed">
          Договорное окно: {item.qualification_window.classification}.{" "}
          {item.qualification_window.evaluation_reason}
        </Text>
      )}
      {item.billing_on_hold && (
        <Badge color="orange">Расчёт приостановлен из-за спора</Badge>
      )}
      {item.evidence.length > 0 && (
        <Text size="sm" c="dimmed">
          Подтверждения:{" "}
          {item.evidence
            .map((value) => value.filename ?? value.evidence_type)
            .join(", ")}
        </Text>
      )}
    </Stack>
  );
}

function StudentOfferForm() {
  const tracks = useMyEmploymentTrackOptions();
  const mutation = useReportEmploymentOffer();
  const [trackId, setTrackId] = useState<string | null>(null);
  const [employer, setEmployer] = useState("");
  const [title, setTitle] = useState("");
  const [receivedAt, setReceivedAt] = useState("");
  const [expectedStart, setExpectedStart] = useState("");
  const [stack, setStack] = useState("");
  const [salary, setSalary] = useState<number | string>("");
  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={3}>Сообщить об оффере</Title>
          <Text size="sm" c="dimmed">
            Сообщение фиксирует новую работу, но само по себе не создаёт
            начисление.
          </Text>
        </div>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select
            label="Направление"
            data={(tracks.data ?? []).map((item) => ({
              value: item.id,
              label: item.title,
            }))}
            value={trackId}
            onChange={setTrackId}
            required
          />
          <Select
            label="Тип отношений"
            defaultValue="employment_contract"
            data={[
              { value: "employment_contract", label: "Трудовой договор" },
              { value: "civil_contract", label: "ГПХ" },
              { value: "self_employed", label: "Самозанятость" },
              { value: "individual_entrepreneur", label: "ИП" },
              { value: "other", label: "Другое" },
            ]}
            readOnly
          />
          <TextInput
            label="Работодатель"
            value={employer}
            onChange={(e) => setEmployer(e.currentTarget.value)}
            required
          />
          <TextInput
            label="Название вакансии"
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            required
          />
          <TextInput
            type="date"
            label="Дата получения оффера"
            value={receivedAt}
            onChange={(e) => setReceivedAt(e.currentTarget.value)}
            required
          />
          <TextInput
            type="date"
            label="Предполагаемая дата выхода"
            value={expectedStart}
            onChange={(e) => setExpectedStart(e.currentTarget.value)}
          />
          <TextInput
            label="Стек вакансии через запятую"
            value={stack}
            onChange={(e) => setStack(e.currentTarget.value)}
          />
          <NumberInput
            label="Зарплата на руки, ₽ (если известна)"
            value={salary}
            onChange={setSalary}
            min={1}
          />
        </SimpleGrid>
        <Button
          loading={mutation.isPending}
          disabled={
            !trackId || !employer.trim() || !title.trim() || !receivedAt
          }
          onClick={() => {
            if (!trackId) return;
            mutation.mutate(
              {
                track_id: trackId,
                employer_name: employer.trim(),
                vacancy_title: title.trim(),
                activity_type: "employment_contract",
                offer_received_at: receivedAt,
                expected_start_date: expectedStart || null,
                vacancy_stack: commaList(stack),
                offer_stack: commaList(stack),
                net_salary_rubles: salary === "" ? null : Number(salary),
                idempotency_key: crypto.randomUUID(),
              },
              { onError: showError },
            );
          }}
        >
          Зафиксировать оффер
        </Button>
      </Stack>
    </Card>
  );
}

function StudentCaseActions({ item }: { item: EmploymentCase }) {
  const start = useReportEmploymentWorkStart();
  const offerStatus = useReportEmploymentOfferStatus();
  const duties = useReportEmploymentActualDuties();
  const change = useReportEmploymentChange();
  const end = useReportEmploymentEnd();
  const dispute = useOpenEmploymentDispute();
  const uploadEvidence = useUploadEmploymentEvidence();
  const [dateValue, setDateValue] = useState("");
  const [offerStatusDate, setOfferStatusDate] = useState("");
  const [offerStatusEvent, setOfferStatusEvent] = useState<string | null>(
    item.offer_accepted_at ? "contract_signed" : "offer_accepted",
  );
  const [jobTitle, setJobTitle] = useState(
    item.official_job_title ?? item.vacancy_title ?? "",
  );
  const [actualDuties, setActualDuties] = useState(item.actual_duties ?? "");
  const [stack, setStack] = useState(item.actual_stack.join(", "));
  const [project, setProject] = useState(item.project_description ?? "");
  const [reason, setReason] = useState("");
  const [directionUsage, setDirectionUsage] = useState<string | null>(
    "unknown",
  );
  const [usageType, setUsageType] = useState<string | null>("coding");
  const [usageFrequency, setUsageFrequency] = useState<string | null>(
    "regular",
  );
  const [usageStartedAt, setUsageStartedAt] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidenceType, setEvidenceType] = useState<string | null>("offer");
  const [uploadProgress, setUploadProgress] = useState(0);
  const technologyUsages =
    directionUsage === "yes" && item.direction && usageType && usageFrequency
      ? [
          {
            normalized_name: item.direction === "python" ? "Python" : "Go",
            usage_type: usageType,
            frequency: usageFrequency,
            part_of_official_duties: "yes",
            part_of_project: "yes",
            started_at: usageStartedAt || null,
            evidence_ids: [],
          },
        ]
      : [];
  return (
    <Accordion variant="separated">
      {(!item.offer_accepted_at || !item.contract_signed_at) && (
        <Accordion.Item value="offer-status">
          <Accordion.Control>Принятие оффера и договор</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Select
                label="Что произошло"
                value={offerStatusEvent}
                onChange={setOfferStatusEvent}
                data={[
                  ...(!item.offer_accepted_at
                    ? [{ value: "offer_accepted", label: "Оффер принят" }]
                    : []),
                  ...(!item.contract_signed_at
                    ? [{ value: "contract_signed", label: "Договор подписан" }]
                    : []),
                ]}
              />
              <TextInput
                type="date"
                label="Фактическая дата"
                value={offerStatusDate}
                onChange={(event) =>
                  setOfferStatusDate(event.currentTarget.value)
                }
              />
              <Button
                variant="light"
                loading={offerStatus.isPending}
                disabled={!offerStatusEvent || !offerStatusDate}
                onClick={() => {
                  if (!offerStatusEvent) return;
                  offerStatus.mutate(
                    {
                      caseId: item.id,
                      payload: {
                        event: offerStatusEvent,
                        effective_at: offerStatusDate,
                        expected_lock_version: item.lock_version,
                        idempotency_key: crypto.randomUUID(),
                      },
                    },
                    { onError: showError },
                  );
                }}
              >
                Сохранить событие
              </Button>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      )}
      {!item.employment_started_at && (
        <Accordion.Item value="start">
          <Accordion.Control>Сообщить о выходе на работу</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <TextInput
                type="date"
                label="Фактическая дата выхода"
                value={dateValue}
                onChange={(e) => setDateValue(e.currentTarget.value)}
                required
              />
              <TextInput
                label="Официальное название должности"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.currentTarget.value)}
                required
              />
              <Textarea
                label="Фактические обязанности (можно уточнить позднее)"
                minRows={4}
                value={actualDuties}
                onChange={(e) => setActualDuties(e.currentTarget.value)}
              />
              <TextInput
                label="Фактический стек через запятую"
                value={stack}
                onChange={(e) => setStack(e.currentTarget.value)}
              />
              <Select
                label={`Используется ли ${item.direction === "go" ? "Go" : "Python"}?`}
                value={directionUsage}
                onChange={setDirectionUsage}
                data={[
                  { value: "yes", label: "Да, регулярно в работе" },
                  { value: "no", label: "Нет" },
                  { value: "unknown", label: "Пока неизвестно" },
                ]}
              />
              {directionUsage === "yes" && (
                <SimpleGrid cols={{ base: 1, sm: 3 }}>
                  <Select
                    label="Как используется"
                    value={usageType}
                    onChange={setUsageType}
                    data={[
                      { value: "coding", label: "Разработка" },
                      { value: "testing", label: "Тестирование" },
                      { value: "code_review", label: "Code review" },
                      { value: "architecture", label: "Архитектура" },
                      { value: "maintenance", label: "Сопровождение" },
                      { value: "operations", label: "Эксплуатация" },
                      {
                        value: "technical_leadership",
                        label: "Техническое руководство",
                      },
                    ]}
                  />
                  <Select
                    label="Регулярность"
                    value={usageFrequency}
                    onChange={setUsageFrequency}
                    data={[
                      { value: "one_time", label: "Один раз" },
                      { value: "occasional", label: "Иногда" },
                      { value: "regular", label: "Регулярно" },
                      { value: "primary", label: "Основная работа" },
                    ]}
                  />
                  <TextInput
                    type="date"
                    label="С какой даты"
                    value={usageStartedAt}
                    onChange={(e) => setUsageStartedAt(e.currentTarget.value)}
                  />
                </SimpleGrid>
              )}
              <Button
                loading={start.isPending}
                disabled={!dateValue || !jobTitle.trim()}
                onClick={() =>
                  start.mutate(
                    {
                      caseId: item.id,
                      payload: {
                        employment_started_at: dateValue,
                        official_job_title: jobTitle.trim(),
                        actual_duties: actualDuties.trim() || null,
                        actual_stack: commaList(stack),
                        technology_usages: technologyUsages,
                        expected_lock_version: item.lock_version,
                        idempotency_key: crypto.randomUUID(),
                      },
                    },
                    { onError: showError },
                  )
                }
              >
                Зафиксировать выход
              </Button>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      )}
      <Accordion.Item value="duties">
        <Accordion.Control>
          Уточнить фактические обязанности и стек
        </Accordion.Control>
        <Accordion.Panel>
          <Stack>
            <Textarea
              label="Что вы регулярно делаете на работе"
              description="Опишите свои задачи, а не стек всей компании"
              minRows={5}
              value={actualDuties}
              onChange={(e) => setActualDuties(e.currentTarget.value)}
              required
            />
            <TextInput
              label="Фактический стек через запятую"
              description="Можно оставить пустым, если стек пока неизвестен"
              value={stack}
              onChange={(e) => setStack(e.currentTarget.value)}
            />
            <Select
              label={`Используется ли ${item.direction === "go" ? "Go" : "Python"}?`}
              value={directionUsage}
              onChange={setDirectionUsage}
              data={[
                { value: "yes", label: "Да" },
                { value: "no", label: "Нет" },
                { value: "unknown", label: "Пока неизвестно" },
              ]}
            />
            {directionUsage === "yes" && (
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                <Select
                  label="Как используется"
                  value={usageType}
                  onChange={setUsageType}
                  data={[
                    { value: "coding", label: "Разработка" },
                    { value: "testing", label: "Тестирование" },
                    { value: "code_review", label: "Code review" },
                    { value: "architecture", label: "Архитектура" },
                    { value: "maintenance", label: "Сопровождение" },
                    { value: "operations", label: "Эксплуатация" },
                    {
                      value: "technical_leadership",
                      label: "Техническое руководство",
                    },
                  ]}
                />
                <Select
                  label="Регулярность"
                  value={usageFrequency}
                  onChange={setUsageFrequency}
                  data={[
                    { value: "one_time", label: "Один раз" },
                    { value: "occasional", label: "Иногда" },
                    { value: "regular", label: "Регулярно" },
                    { value: "primary", label: "Основная работа" },
                  ]}
                />
                <TextInput
                  type="date"
                  label="С какой даты"
                  value={usageStartedAt}
                  onChange={(e) => setUsageStartedAt(e.currentTarget.value)}
                />
              </SimpleGrid>
            )}
            <Textarea
              label="Команда или проект"
              value={project}
              onChange={(e) => setProject(e.currentTarget.value)}
            />
            <Button
              loading={duties.isPending}
              disabled={actualDuties.trim().length < 10}
              onClick={() =>
                duties.mutate(
                  {
                    caseId: item.id,
                    payload: {
                      actual_duties: actualDuties.trim(),
                      actual_stack: commaList(stack),
                      project_description: project.trim() || null,
                      technology_usages: technologyUsages,
                      expected_lock_version: item.lock_version,
                      idempotency_key: crypto.randomUUID(),
                    },
                  },
                  { onError: showError },
                )
              }
            >
              Отправить на проверку
            </Button>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
      <Accordion.Item value="change">
        <Accordion.Control>
          Изменились обязанности, проект или стек
        </Accordion.Control>
        <Accordion.Panel>
          <Stack>
            <TextInput
              type="date"
              label="Дата изменения"
              value={dateValue}
              onChange={(e) => setDateValue(e.currentTarget.value)}
            />
            <Textarea
              label="Что изменилось"
              minRows={4}
              value={reason}
              onChange={(e) => setReason(e.currentTarget.value)}
            />
            <TextInput
              label="Новый фактический стек"
              value={stack}
              onChange={(e) => setStack(e.currentTarget.value)}
            />
            <Button
              loading={change.isPending}
              disabled={!dateValue || !reason.trim()}
              onClick={() =>
                change.mutate(
                  {
                    caseId: item.id,
                    payload: {
                      change_type: "stack",
                      effective_at: dateValue,
                      new_state: reason.trim(),
                      actual_stack: commaList(stack),
                      technology_usages: [],
                      expected_lock_version: item.lock_version,
                      idempotency_key: crypto.randomUUID(),
                    },
                  },
                  { onError: showError },
                )
              }
            >
              Сообщить об изменении
            </Button>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
      <Accordion.Item value="evidence">
        <Accordion.Control>Приложить подтверждение</Accordion.Control>
        <Accordion.Panel>
          <Stack>
            <Text size="sm" c="dimmed">
              Подойдут PDF, изображение или текстовый файл до 20 МБ. Не
              загружайте исходный код, секреты работодателя и лишние
              персональные данные.
            </Text>
            <Select
              label="Тип подтверждения"
              value={evidenceType}
              onChange={setEvidenceType}
              data={[
                { value: "offer", label: "Оффер" },
                { value: "contract_excerpt", label: "Фрагмент договора" },
                { value: "job_description", label: "Описание обязанностей" },
                { value: "manager_message", label: "Сообщение руководителя" },
                { value: "project_assignment", label: "Назначение на проект" },
                { value: "role_change", label: "Изменение роли" },
                { value: "other", label: "Другое" },
              ]}
            />
            <FileInput
              label="Файл"
              value={evidenceFile}
              onChange={setEvidenceFile}
              accept="application/pdf,image/*,text/plain,text/markdown"
              clearable
            />
            {uploadEvidence.isPending && (
              <Progress value={uploadProgress} animated />
            )}
            <Button
              variant="light"
              loading={uploadEvidence.isPending}
              disabled={!evidenceFile || !evidenceType}
              onClick={() => {
                if (!evidenceFile || !evidenceType) return;
                setUploadProgress(0);
                uploadEvidence.mutate(
                  {
                    caseId: item.id,
                    evidenceType,
                    file: evidenceFile,
                    onProgress: setUploadProgress,
                  },
                  {
                    onSuccess: () => {
                      setEvidenceFile(null);
                      notifications.show({
                        color: "green",
                        message: "Подтверждение сохранено",
                      });
                    },
                    onError: showError,
                  },
                );
              }}
            >
              Загрузить подтверждение
            </Button>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
      {item.assessments.length > 0 && (
        <Accordion.Item value="dispute">
          <Accordion.Control>Оспорить квалификацию</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Textarea
                label="Что именно неверно и почему"
                minRows={4}
                value={reason}
                onChange={(e) => setReason(e.currentTarget.value)}
              />
              <Button
                color="orange"
                loading={dispute.isPending}
                disabled={reason.trim().length < 10}
                onClick={() =>
                  dispute.mutate(
                    {
                      caseId: item.id,
                      payload: {
                        disputed_conclusion: "profile_activity",
                        reason: reason.trim(),
                        idempotency_key: crypto.randomUUID(),
                      },
                    },
                    { onError: showError },
                  )
                }
              >
                Открыть спор и приостановить расчёт
              </Button>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      )}
      {item.employment_status === "active" && item.employment_started_at && (
        <Accordion.Item value="end">
          <Accordion.Control>Сообщить о прекращении работы</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <TextInput
                type="date"
                label="Последний день работы"
                value={dateValue}
                onChange={(e) => setDateValue(e.currentTarget.value)}
              />
              <Textarea
                label="Причина"
                value={reason}
                onChange={(e) => setReason(e.currentTarget.value)}
              />
              <Button
                color="red"
                variant="light"
                loading={end.isPending}
                disabled={!dateValue || reason.trim().length < 3}
                onClick={() =>
                  end.mutate(
                    {
                      caseId: item.id,
                      payload: {
                        employment_ended_at: dateValue,
                        reason: reason.trim(),
                        expected_lock_version: item.lock_version,
                        idempotency_key: crypto.randomUUID(),
                      },
                    },
                    { onError: showError },
                  )
                }
              >
                Зафиксировать прекращение работы
              </Button>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      )}
    </Accordion>
  );
}

export function EmploymentQualificationStudentPanel() {
  const query = useMyEmploymentCases();
  if (query.isPending)
    return <LoadingState label="Загружаем данные о работе…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const active = query.data.items.find(
    (item) => item.employment_status === "active",
  );
  return (
    <Stack gap="lg">
      <Alert
        color="blue"
        title="Сообщайте о любой оплачиваемой работе в разработке ПО"
      >
        Даже если должность называется PHP Developer, Java Developer, Software
        Engineer или иначе. Само сообщение не создаёт начисление: учитываются
        фактические обязанности и технологии. Смешанный стек может быть
        профильным, а разовое или личное использование Python/Go — нет.
      </Alert>
      {!active && <StudentOfferForm />}
      {query.data.items.map((item) => (
        <Card key={item.id} withBorder>
          <Stack>
            <CaseSummary item={item} />
            {item.employment_status === "active" && (
              <StudentCaseActions item={item} />
            )}
            {item.events.length > 0 && (
              <Accordion>
                <Accordion.Item value="timeline">
                  <Accordion.Control>
                    История изменений ({item.events.length})
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Timeline bulletSize={20} lineWidth={2}>
                      {item.events.map((event) => (
                        <Timeline.Item
                          key={event.id}
                          title={event.event_type.replaceAll("_", " ")}
                        >
                          <Text size="sm" c="dimmed">
                            Фактически: {event.effective_at} · сообщено{" "}
                            {new Date(event.recorded_at).toLocaleString(
                              "ru-RU",
                            )}
                          </Text>
                        </Timeline.Item>
                      ))}
                    </Timeline>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            )}
          </Stack>
        </Card>
      ))}
    </Stack>
  );
}

export function EmploymentQualificationStaffPanel({
  studentId,
}: {
  studentId: string;
}) {
  const query = useStudentEmploymentCases(studentId);
  const assess = useAssessEmploymentCase(studentId);
  const requestInfo = useRequestEmploymentInformation(studentId);
  const requestAI = useRequestEmploymentAISuggestion(studentId);
  const resolveDispute = useResolveEmploymentDispute(studentId);
  const [classification, setClassification] =
    useState<EmploymentProfileClassification>("insufficient_data");
  const [startedAt, setStartedAt] = useState("");
  const [criterion, setCriterion] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");
  const [disputeResolution, setDisputeResolution] = useState("");
  const dueAt = useMemo(
    () => new Date(Date.now() + 10 * 86_400_000).toISOString().slice(0, 10),
    [],
  );
  if (query.isPending)
    return <LoadingState label="Загружаем фактическую работу…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  if (query.data.items.length === 0)
    return <Text c="dimmed">Ученик ещё не сообщал о новой работе.</Text>;
  return (
    <Stack gap="lg">
      {query.data.items.map((item) => (
        <Card key={item.id} withBorder>
          <Stack>
            <CaseSummary item={item} />
            {item.actual_duties && (
              <Alert title="Фактические обязанности">
                {item.actual_duties}
              </Alert>
            )}
            {item.ai_suggestions[0]?.output && (
              <Alert
                color="violet"
                title="Рекомендация AI — требуется решение сотрудника"
              >
                <Text>{item.ai_suggestions[0].output.summary}</Text>
                <Text size="sm" c="dimmed">
                  Предложение:{" "}
                  {
                    classificationLabels[
                      item.ai_suggestions[0].output.suggested_classification
                    ]
                  }
                  {item.ai_suggestions[0].output.suggested_profile_started_at
                    ? ` · с ${item.ai_suggestions[0].output.suggested_profile_started_at}`
                    : ""}
                </Text>
              </Alert>
            )}
            {item.ai_suggestions[0]?.status === "failed" && (
              <Alert color="red" title="AI-анализ не выполнен">
                {item.ai_suggestions[0].safe_error_message ??
                  "Можно повторить запуск."}
              </Alert>
            )}
            {item.disputes
              .filter(
                (dispute) =>
                  dispute.status === "open" ||
                  dispute.status === "under_review",
              )
              .map((dispute) => (
                <Alert key={dispute.id} color="orange" title="Открытый спор">
                  <Stack gap="sm">
                    <Text>{dispute.reason}</Text>
                    <Textarea
                      label="Мотивированное решение"
                      minRows={3}
                      value={disputeResolution}
                      onChange={(event) =>
                        setDisputeResolution(event.currentTarget.value)
                      }
                    />
                    <Group>
                      <Button
                        color="green"
                        loading={resolveDispute.isPending}
                        disabled={disputeResolution.trim().length < 10}
                        onClick={() =>
                          resolveDispute.mutate(
                            {
                              caseId: item.id,
                              disputeId: dispute.id,
                              resolution: disputeResolution.trim(),
                              outcome: "resolved",
                            },
                            { onError: showError },
                          )
                        }
                      >
                        Удовлетворить спор
                      </Button>
                      <Button
                        variant="light"
                        color="red"
                        loading={resolveDispute.isPending}
                        disabled={disputeResolution.trim().length < 10}
                        onClick={() =>
                          resolveDispute.mutate(
                            {
                              caseId: item.id,
                              disputeId: dispute.id,
                              resolution: disputeResolution.trim(),
                              outcome: "rejected",
                            },
                            { onError: showError },
                          )
                        }
                      >
                        Отклонить спор
                      </Button>
                    </Group>
                  </Stack>
                </Alert>
              ))}
            <Accordion variant="separated">
              <Accordion.Item value="ai">
                <Accordion.Control>Вспомогательный AI-анализ</Accordion.Control>
                <Accordion.Panel>
                  <Stack>
                    <Text size="sm" c="dimmed">
                      AI сравнит фактические обязанности и доказательства, но не
                      сможет подтвердить профильность или создать начисление.
                    </Text>
                    <Button
                      variant="light"
                      loading={requestAI.isPending}
                      onClick={() =>
                        requestAI.mutate(
                          {
                            caseId: item.id,
                            evidenceIds: item.evidence.map((value) => value.id),
                          },
                          {
                            onSuccess: () =>
                              notifications.show({
                                color: "green",
                                message: "AI-анализ поставлен в очередь",
                              }),
                            onError: showError,
                          },
                        )
                      }
                    >
                      Запустить AI-анализ
                    </Button>
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
              <Accordion.Item value="review">
                <Accordion.Control>
                  Квалифицировать фактическую работу
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack>
                    <Alert color="orange">
                      Решение может создать или пересчитать результативный
                      компонент. Проверьте дату начала профильной деятельности,
                      версию договора и контрольный период.
                    </Alert>
                    {item.policy_is_legacy && (
                      <Alert color="red">
                        Кейс не связан с принятой версией договорной политики.
                        Квалификацию можно сохранить, но автоматическое
                        начисление не появится.
                      </Alert>
                    )}
                    <Select
                      label="Решение"
                      value={classification}
                      onChange={(value) =>
                        value &&
                        setClassification(
                          value as EmploymentProfileClassification,
                        )
                      }
                      data={Object.entries(classificationLabels).map(
                        ([value, label]) => ({ value, label }),
                      )}
                    />
                    {(classification === "profile" ||
                      classification === "mixed_profile") && (
                      <>
                        <TextInput
                          type="date"
                          label="Дата начала профильной деятельности"
                          value={startedAt}
                          onChange={(e) => setStartedAt(e.currentTarget.value)}
                          required
                        />
                        <Select
                          label="Критерий существенного использования"
                          value={criterion}
                          onChange={setCriterion}
                          data={[
                            { value: "coding", label: "Регулярная разработка" },
                            { value: "testing", label: "Тестирование кода" },
                            {
                              value: "code_review",
                              label: "Обязательное code review",
                            },
                            {
                              value: "architecture",
                              label: "Архитектура и проектирование",
                            },
                            { value: "maintenance", label: "Сопровождение" },
                            { value: "operations", label: "Эксплуатация" },
                            {
                              value: "technical_leadership",
                              label: "Техническое руководство",
                            },
                          ]}
                          required
                        />
                      </>
                    )}
                    <Textarea
                      label="Мотивированное решение"
                      minRows={4}
                      value={rationale}
                      onChange={(e) => setRationale(e.currentTarget.value)}
                      required
                    />
                    <Button
                      loading={assess.isPending}
                      disabled={
                        rationale.trim().length < 10 ||
                        ((classification === "profile" ||
                          classification === "mixed_profile") &&
                          (!startedAt || !criterion))
                      }
                      onClick={() =>
                        assess.mutate(
                          {
                            caseId: item.id,
                            classification,
                            startedAt: startedAt || null,
                            rationale: rationale.trim(),
                            criterion,
                            lockVersion: item.lock_version,
                          },
                          {
                            onSuccess: () =>
                              notifications.show({
                                color: "green",
                                message:
                                  "Решение сохранено новой неизменяемой версией",
                              }),
                            onError: showError,
                          },
                        )
                      }
                    >
                      Подтвердить решение
                    </Button>
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
              <Accordion.Item value="request">
                <Accordion.Control>
                  Запросить дополнительные сведения
                </Accordion.Control>
                <Accordion.Panel>
                  <Button
                    variant="light"
                    loading={requestInfo.isPending}
                    onClick={() =>
                      requestInfo.mutate(
                        {
                          caseId: item.id,
                          fields: [
                            "actual_duties",
                            "actual_stack",
                            "project_description",
                          ],
                          dueAt,
                        },
                        {
                          onSuccess: () =>
                            notifications.show({
                              color: "green",
                              message: "Запрос отправлен ученику",
                            }),
                          onError: showError,
                        },
                      )
                    }
                  >
                    Запросить обязанности и стек до {dueAt}
                  </Button>
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          </Stack>
        </Card>
      ))}
    </Stack>
  );
}
