import {
  Badge,
  Button,
  Card,
  Divider,
  Drawer,
  Group,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminApplication,
  useAdminApplications,
  useExecuteAdminApplicationAction,
} from "../features/admin/applicationQueries";
import type {
  OnboardingApplicationAction,
  OnboardingApplicationDetail,
} from "../types/api";

const PAGE_SIZE = 30;

const STATUS_LABELS: Record<string, string> = {
  NEW_LEAD: "Новая заявка",
  QUALIFICATION_STARTED: "Заполняет короткую анкету",
  QUALIFICATION_COMPLETED: "Квалификация заполнена",
  QUALIFICATION_REVIEW_REQUIRED: "Нужно рассмотреть",
  APPROVED_FOR_CALL: "Допущен к созвону",
  REJECTED_BEFORE_CALL: "Отказ до созвона",
  BOOKING_LINK_SENT: "Ссылка на созвон отправлена",
  BOOKING_CREATED: "Созвон назначен",
  BOOKING_RESCHEDULED: "Созвон перенесён",
  BOOKING_CANCELLED: "Созвон отменён",
  CALL_REMINDER_SENT: "Напоминание отправлено",
  CALL_COMPLETED: "Созвон завершён",
  APPROVED_AFTER_CALL: "Одобрен после созвона",
  REJECTED_AFTER_CALL: "Отказ после созвона",
  FOLLOW_UP_REQUIRED: "Нужно уточнение",
  APPLICATION_FORM_SENT: "Подробная анкета отправлена",
  APPLICATION_FORM_STARTED: "Заполняет подробную анкету",
  APPLICATION_FORM_SUBMITTED: "Подробная анкета получена",
  PAYMENT_LINK_CREATED: "Ссылка на оплату создана",
  PAYMENT_LINK_SENT: "Ссылка на оплату отправлена",
  PAYMENT_PENDING: "Ожидаем оплату",
  PAYMENT_APPROVED: "Оплата подтверждена",
  PAYMENT_FAILED: "Ошибка оплаты",
  PAYMENT_MANUAL_REVIEW: "Проверка оплаты",
  ONBOARDING_STARTED: "Онбординг идёт",
  ONBOARDING_COMPLETED: "Онбординг завершён",
  ACTIVE_STUDENT: "Активный ученик",
  ARCHIVED: "В архиве",
};

const STAGES = [
  { value: "all", label: "Вся воронка", statuses: [] },
  {
    value: "review",
    label: "На рассмотрении",
    statuses: ["QUALIFICATION_REVIEW_REQUIRED"],
  },
  {
    value: "call",
    label: "Созвоны",
    statuses: [
      "APPROVED_FOR_CALL",
      "BOOKING_LINK_SENT",
      "BOOKING_CREATED",
      "BOOKING_RESCHEDULED",
      "CALL_REMINDER_SENT",
      "CALL_COMPLETED",
      "FOLLOW_UP_REQUIRED",
    ],
  },
  {
    value: "payment",
    label: "Анкета и оплата",
    statuses: [
      "APPLICATION_FORM_SENT",
      "APPLICATION_FORM_STARTED",
      "APPLICATION_FORM_SUBMITTED",
      "PAYMENT_LINK_CREATED",
      "PAYMENT_LINK_SENT",
      "PAYMENT_PENDING",
      "PAYMENT_FAILED",
      "PAYMENT_MANUAL_REVIEW",
    ],
  },
  {
    value: "onboarding",
    label: "Онбординг",
    statuses: [
      "PAYMENT_APPROVED",
      "ONBOARDING_STARTED",
      "ONBOARDING_COMPLETED",
    ],
  },
  {
    value: "closed",
    label: "Завершённые",
    statuses: [
      "ACTIVE_STUDENT",
      "REJECTED_BEFORE_CALL",
      "REJECTED_AFTER_CALL",
      "ARCHIVED",
    ],
  },
] as const;

const ACTIONS: Record<
  OnboardingApplicationAction,
  { label: string; color?: string; confirmation?: string }
> = {
  approve_qualification: { label: "Допустить к созвону", color: "green" },
  reject_qualification: {
    label: "Отказать до созвона",
    color: "red",
    confirmation: "Отказать кандидату до созвона? Бот отправит уведомление.",
  },
  approve_after_call: { label: "Одобрить после созвона", color: "green" },
  reject_after_call: {
    label: "Отказать после созвона",
    color: "red",
    confirmation: "Отказать кандидату после созвона? Бот отправит уведомление.",
  },
  request_follow_up: { label: "Нужно уточнение", color: "yellow" },
  confirm_payment: {
    label: "Подтвердить оплату",
    color: "green",
    confirmation: "Подтвердить оплату вручную и запустить онбординг?",
  },
  resend_payment: { label: "Отправить новую ссылку", color: "blue" },
  complete_onboarding: { label: "Завершить онбординг", color: "green" },
  confirm_access: { label: "Доступы получены", color: "green" },
  access_missing: { label: "Письмо не найдено", color: "orange" },
};

const FORM_LABELS: Record<string, string> = {
  last_name: "Фамилия",
  first_name: "Имя",
  patronymic: "Отчество",
  phone: "Телефон",
  email: "Email",
  telegram_username: "Telegram",
  direction: "Направление",
  personal_data_consent: "Согласие на обработку данных",
};

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function statusColor(status: string) {
  if (status.includes("REJECTED") || status === "PAYMENT_FAILED") return "red";
  if (status === "ACTIVE_STUDENT" || status.includes("APPROVED"))
    return "green";
  if (status.includes("REVIEW") || status.includes("REQUIRED")) return "yellow";
  if (status.includes("PAYMENT") || status.includes("ONBOARDING"))
    return "cyan";
  return "blue";
}

function formatDate(value: string | null, withTime = false) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value));
}

function countStatuses(
  counts: Record<string, number>,
  statuses: readonly string[],
) {
  return statuses.reduce((total, status) => total + (counts[status] ?? 0), 0);
}

function Value({ label, value }: { label: string; value: unknown }) {
  const normalized =
    value === true
      ? "Да"
      : value === false
        ? "Нет"
        : String(value ?? "").trim() || "—";
  return (
    <div>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={500}>
        {normalized}
      </Text>
    </div>
  );
}

function ApplicationDetails({
  application,
}: {
  application: OnboardingApplicationDetail;
}) {
  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-start">
        <div>
          <Text className="technical-label">{application.applicant_id}</Text>
          <Title order={2}>{application.name || "Без имени"}</Title>
        </div>
        <Badge color={statusColor(application.status)} size="lg">
          {statusLabel(application.status)}
        </Badge>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <Value
          label="Telegram"
          value={
            application.telegram_username
              ? `@${application.telegram_username}`
              : application.telegram_user_id
          }
        />
        <Value label="Email" value={application.email} />
        <Value label="Город" value={application.city} />
        <Value label="Направление" value={application.direction} />
        <Value
          label="Создана"
          value={formatDate(application.created_at, true)}
        />
        <Value
          label="Обновлена"
          value={formatDate(application.updated_at, true)}
        />
      </SimpleGrid>

      <Divider label="Короткая анкета" labelPosition="left" />
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <Value label="Возраст" value={application.age} />
        <Value label="Источник" value={application.referral_source} />
        <Value
          label="Время на обучение"
          value={application.study_time_per_day}
        />
        <Value
          label="Военный документ"
          value={application.military_document_status}
        />
      </SimpleGrid>
      <Value label="Начальные знания" value={application.initial_knowledge} />
      <Value
        label="Жизненные сложности"
        value={application.life_difficulties}
      />

      {Object.keys(application.form_answers).length > 0 && (
        <>
          <Divider label="Подробная анкета" labelPosition="left" />
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {Object.entries(application.form_answers)
              .filter(([key]) => FORM_LABELS[key])
              .map(([key, value]) => (
                <Value
                  key={key}
                  label={FORM_LABELS[key] ?? key}
                  value={value}
                />
              ))}
          </SimpleGrid>
        </>
      )}

      {application.admin_comment && (
        <Card withBorder padding="md" bg="yellow.0">
          <Text size="xs" c="dimmed">
            Комментарий администратора
          </Text>
          <Text>{application.admin_comment}</Text>
        </Card>
      )}

      {(application.bookings.length > 0 || application.payments.length > 0) && (
        <>
          <Divider label="Созвон и оплата" labelPosition="left" />
          {application.bookings[0] && (
            <Card withBorder padding="md">
              <Group justify="space-between">
                <div>
                  <Text fw={600}>Ближайший созвон</Text>
                  <Text size="sm">
                    {formatDate(application.bookings[0].start_time, true)}
                  </Text>
                </div>
                {application.bookings[0].meeting_url && (
                  <Button
                    component="a"
                    href={application.bookings[0].meeting_url}
                    target="_blank"
                    variant="light"
                  >
                    Открыть встречу
                  </Button>
                )}
              </Group>
            </Card>
          )}
          {application.payments[0] && (
            <Card withBorder padding="md">
              <Group justify="space-between">
                <div>
                  <Text fw={600}>
                    Платёж · {application.payments[0].status}
                  </Text>
                  <Text size="sm">
                    {application.payments[0].amount}{" "}
                    {application.payments[0].currency}
                  </Text>
                </div>
                {application.payments[0].payment_url && (
                  <Button
                    component="a"
                    href={application.payments[0].payment_url}
                    target="_blank"
                    variant="light"
                  >
                    Ссылка на оплату
                  </Button>
                )}
              </Group>
            </Card>
          )}
        </>
      )}

      <Divider label="История" labelPosition="left" />
      <Stack gap="xs" className="application-timeline">
        {application.events.map((event, index) => (
          <div
            className="application-timeline-item"
            key={`${event.created_at}-${index}`}
          >
            <Text size="sm" fw={600}>
              {event.new_status
                ? statusLabel(event.new_status)
                : event.event_type}
            </Text>
            <Text size="xs" c="dimmed">
              {formatDate(event.created_at, true)} · {event.source}
            </Text>
          </div>
        ))}
      </Stack>
    </Stack>
  );
}

export function AdminApplicationsPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search.trim(), 250);
  const [stage, setStage] = useState("all");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const statuses = useMemo(
    () => [...(STAGES.find((item) => item.value === stage)?.statuses ?? [])],
    [stage],
  );
  const applications = useAdminApplications({
    query: debouncedSearch,
    statuses,
    page,
    pageSize: PAGE_SIZE,
  });
  const detail = useAdminApplication(selectedId);
  const actionMutation = useExecuteAdminApplicationAction();

  useEffect(() => setPage(1), [debouncedSearch, stage]);

  const runAction = (action: OnboardingApplicationAction) => {
    if (!selectedId) return;
    const metadata = ACTIONS[action];
    if (metadata.confirmation && !window.confirm(metadata.confirmation)) return;
    if (action === "request_follow_up" && !comment.trim()) {
      notifications.show({
        color: "red",
        message: "Добавьте комментарий для уточнения",
      });
      return;
    }
    actionMutation.mutate(
      { applicantId: selectedId, action, comment: comment.trim() || null },
      {
        onSuccess: (result) => {
          notifications.show({
            color: result.delivered === false ? "yellow" : "green",
            message:
              result.delivered === false
                ? `${result.message}. Сообщение в Telegram не доставлено.`
                : result.message,
          });
          setComment("");
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const counts = applications.data?.status_counts ?? {};
  const kpis = [
    {
      label: "Нужно рассмотреть",
      value: counts.QUALIFICATION_REVIEW_REQUIRED ?? 0,
      color: "yellow",
    },
    {
      label: "В работе по созвону",
      value: countStatuses(counts, STAGES[2].statuses),
      color: "blue",
    },
    {
      label: "Ожидают оплату",
      value: countStatuses(counts, [
        "PAYMENT_LINK_SENT",
        "PAYMENT_PENDING",
        "PAYMENT_FAILED",
        "PAYMENT_MANUAL_REVIEW",
      ]),
      color: "cyan",
    },
    {
      label: "Идёт онбординг",
      value: counts.ONBOARDING_STARTED ?? 0,
      color: "green",
    },
  ];

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Админ-панель · Воронка"
        title="Заявки"
        description="Управляйте кандидатом от короткой анкеты до выдачи доступа — бот сам отправит нужное сообщение и сохранит действие в истории."
      />

      <SimpleGrid cols={{ base: 2, md: 4 }}>
        {kpis.map((item) => (
          <Card key={item.label} withBorder className="application-kpi">
            <Badge color={item.color} variant="dot">
              {item.label}
            </Badge>
            <Text fz="2rem" fw={800}>
              {item.value}
            </Text>
          </Card>
        ))}
      </SimpleGrid>

      <Card withBorder>
        <Stack>
          <Group grow align="flex-end">
            <TextInput
              label="Поиск"
              placeholder="Имя, email, Telegram или ID заявки"
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
            />
            <Select
              label="Этап"
              value={stage}
              onChange={(value) => setStage(value ?? "all")}
              data={STAGES.map(({ value, label }) => ({ value, label }))}
            />
          </Group>

          {applications.isPending ? (
            <LoadingState label="Загружаем заявки…" />
          ) : applications.isError ? (
            <ErrorState
              error={applications.error}
              retry={() => void applications.refetch()}
            />
          ) : (
            <>
              <Group justify="space-between">
                <Text fw={600}>Найдено заявок: {applications.data.total}</Text>
                <Text size="sm" c="dimmed">
                  Данные синхронизируются с onboarding-ботом
                </Text>
              </Group>
              <Table.ScrollContainer minWidth={850}>
                <Table highlightOnHover verticalSpacing="md">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Кандидат</Table.Th>
                      <Table.Th>Этап</Table.Th>
                      <Table.Th>Направление</Table.Th>
                      <Table.Th>Следующее событие</Table.Th>
                      <Table.Th>Обновлена</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {applications.data.items.map((application) => (
                      <Table.Tr key={application.applicant_id}>
                        <Table.Td>
                          <Text fw={600}>
                            {application.name || "Без имени"}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {application.telegram_username
                              ? `@${application.telegram_username}`
                              : application.telegram_user_id}{" "}
                            · {application.applicant_id}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={statusColor(application.status)}>
                            {statusLabel(application.status)}
                          </Badge>
                        </Table.Td>
                        <Table.Td>{application.direction || "—"}</Table.Td>
                        <Table.Td>
                          {application.booking_start_time
                            ? formatDate(application.booking_start_time, true)
                            : application.payment_status
                              ? `Платёж: ${application.payment_status}`
                              : "—"}
                        </Table.Td>
                        <Table.Td>
                          {formatDate(application.updated_at, true)}
                        </Table.Td>
                        <Table.Td>
                          <Button
                            size="xs"
                            variant="light"
                            onClick={() =>
                              setSelectedId(application.applicant_id)
                            }
                          >
                            Открыть
                          </Button>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {applications.data.items.length === 0 && (
                <Text ta="center" c="dimmed" py="xl">
                  По выбранным фильтрам заявок нет.
                </Text>
              )}
              {applications.data.total > PAGE_SIZE && (
                <Pagination
                  value={page}
                  onChange={setPage}
                  total={Math.ceil(applications.data.total / PAGE_SIZE)}
                />
              )}
            </>
          )}
        </Stack>
      </Card>

      <Drawer
        opened={Boolean(selectedId)}
        onClose={() => {
          setSelectedId(null);
          setComment("");
        }}
        title="Карточка заявки"
        position="right"
        size="xl"
      >
        {detail.isPending ? (
          <LoadingState label="Загружаем карточку…" />
        ) : detail.isError ? (
          <ErrorState
            error={detail.error}
            retry={() => void detail.refetch()}
          />
        ) : detail.data ? (
          <Stack gap="xl">
            <ApplicationDetails application={detail.data} />
            {detail.data.available_actions.length > 0 && (
              <Card withBorder className="application-actions">
                <Stack>
                  <div>
                    <Text fw={700}>Действия</Text>
                    <Text size="sm" c="dimmed">
                      Доступны только корректные переходы для текущего статуса.
                    </Text>
                  </div>
                  {detail.data.available_actions.includes(
                    "request_follow_up",
                  ) && (
                    <Textarea
                      label="Комментарий для уточнения"
                      value={comment}
                      onChange={(event) =>
                        setComment(event.currentTarget.value)
                      }
                      minRows={2}
                      maxLength={2000}
                    />
                  )}
                  <Group>
                    {detail.data.available_actions.map((action) => (
                      <Button
                        key={action}
                        color={ACTIONS[action].color}
                        variant={action.includes("reject") ? "light" : "filled"}
                        loading={actionMutation.isPending}
                        onClick={() => runAction(action)}
                      >
                        {ACTIONS[action].label}
                      </Button>
                    ))}
                  </Group>
                </Stack>
              </Card>
            )}
          </Stack>
        ) : null}
      </Drawer>
    </Stack>
  );
}
