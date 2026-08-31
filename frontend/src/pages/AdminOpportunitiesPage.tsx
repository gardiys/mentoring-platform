import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminOpportunities,
  useDecideAdminGoTransition,
  useSetAdminConsultationMentor,
  useUpdateAdminGoTransitionProgram,
  useUpdateAdminConsultationType,
  useUpdateAdminConsultation,
} from "../features/opportunities/queries";
import type {
  ConsultationStatus,
  ConsultationType,
  GoTransitionStatus,
  OpportunitiesDashboard,
} from "../types/api";
import { formatRubles } from "../utils/money";

const consultationLabels: Record<ConsultationStatus, string> = {
  requested: "Новая заявка",
  payment_pending: "Ожидает оплаты",
  paid: "Оплачена",
  scheduled: "Запланирована",
  completed: "Завершена",
  cancelled: "Отменена",
};

const transitionLabels: Record<GoTransitionStatus, string> = {
  submitted: "Новая заявка",
  approved: "Одобрена",
  payment_pending: "Ожидает оплаты",
  paid: "Оплачена",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

const consultationTypeLabels: Record<ConsultationType, string> = {
  free_topic: "Свободная тема",
  technical_mock: "Техническое мок-собеседование",
  legend_mock: "Мок-собеседование по легенде",
  resume_legend: "Составление резюме и легенды",
  system_design_mock: "Мок-собеседование по системному дизайну",
  work_task: "Помощь с рабочей задачей",
};

function ConsultationPriceCard({
  item,
}: {
  item: OpportunitiesDashboard["consultation_types"][number];
}) {
  const mutation = useUpdateAdminConsultationType();
  const [price, setPrice] = useState(item.price_kopecks / 100);
  const [comparisonPrice, setComparisonPrice] = useState(
    item.comparison_price_kopecks / 100,
  );
  const [mentorReward, setMentorReward] = useState(
    item.mentor_reward_kopecks / 100,
  );
  const [durationMinutes, setDurationMinutes] = useState(item.duration_minutes);
  const invalid =
    price <= 0 ||
    comparisonPrice < price ||
    mentorReward < 0 ||
    mentorReward > price ||
    durationMinutes < 15 ||
    durationMinutes > 480;
  const numberValue = (value: string | number) =>
    typeof value === "number" ? value : Number(value) || 0;

  return (
    <Card withBorder>
      <Stack h="100%">
        <div>
          <Title order={3}>{item.title}</Title>
          <Text size="sm" c="dimmed">
            {item.description}
          </Text>
        </div>
        <NumberInput
          label="Цена для выпускника"
          suffix=" ₽"
          min={1}
          step={500}
          value={price}
          onChange={(value) => setPrice(numberValue(value))}
        />
        <NumberInput
          label="Публичная цена"
          description="Показывается зачёркнутой для сравнения"
          suffix=" ₽"
          min={price}
          step={500}
          value={comparisonPrice}
          onChange={(value) => setComparisonPrice(numberValue(value))}
        />
        <NumberInput
          label="Вознаграждение ментора"
          suffix=" ₽"
          min={0}
          max={price}
          step={500}
          value={mentorReward}
          onChange={(value) => setMentorReward(numberValue(value))}
        />
        <NumberInput
          label="Длительность консультации"
          description="От 15 минут до 8 часов"
          suffix=" мин"
          min={15}
          max={480}
          step={15}
          value={durationMinutes}
          onChange={(value) => setDurationMinutes(numberValue(value))}
        />
        {invalid && (
          <Text c="red" size="sm">
            Публичная цена должна быть не ниже цены выпускника, а выплата
            ментору — не выше неё. Длительность — от 15 до 480 минут.
          </Text>
        )}
        <Button
          mt="auto"
          disabled={invalid}
          loading={mutation.isPending}
          onClick={() =>
            mutation.mutate(
              {
                consultationType: item.code,
                priceKopecks: Math.round(price * 100),
                comparisonPriceKopecks: Math.round(comparisonPrice * 100),
                mentorRewardKopecks: Math.round(mentorReward * 100),
                durationMinutes: Math.round(durationMinutes),
              },
              {
                onSuccess: () =>
                  notifications.show({
                    color: "green",
                    message: `Тариф «${item.title}» обновлён`,
                  }),
                onError: (error) =>
                  notifications.show({ color: "red", message: error.message }),
              },
            )
          }
        >
          Сохранить тариф
        </Button>
      </Stack>
    </Card>
  );
}

function GoTransitionProgramSettings({ description }: { description: string }) {
  const mutation = useUpdateAdminGoTransitionProgram();
  const [value, setValue] = useState(description);

  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={2}>Описание программы Python → Go</Title>
          <Text c="dimmed">
            Текст видят выпускники и действующие ученики в режиме просмотра.
            Поддерживается Markdown.
          </Text>
        </div>
        <Textarea
          label="Описание программы"
          minRows={10}
          autosize
          maxRows={24}
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
        />
        <Button
          w="fit-content"
          disabled={value.trim().length < 20}
          loading={mutation.isPending}
          onClick={() =>
            mutation.mutate(value.trim(), {
              onSuccess: () =>
                notifications.show({
                  color: "green",
                  message: "Описание программы обновлено",
                }),
              onError: (error) =>
                notifications.show({ color: "red", message: error.message }),
            })
          }
        >
          Сохранить описание
        </Button>
      </Stack>
    </Card>
  );
}

export function AdminOpportunitiesPage() {
  const query = useAdminOpportunities();
  const consultationMutation = useUpdateAdminConsultation();
  const consultantMutation = useSetAdminConsultationMentor();
  const transitionMutation = useDecideAdminGoTransition();
  const [consultationDrafts, setConsultationDrafts] = useState<
    Record<
      string,
      {
        mentorId: string | null;
        scheduledAt: string;
        note: string;
        summary: string;
      }
    >
  >({});
  const [transitionNotes, setTransitionNotes] = useState<
    Record<string, string>
  >({});
  if (query.isPending) return <LoadingState label="Загружаем заявки…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const error = (value: Error) =>
    notifications.show({ color: "red", message: value.message });
  const enabledMentorOptions = query.data.consultation_mentors
    .filter((mentor) => mentor.is_enabled)
    .map((mentor) => ({
      value: mentor.id,
      label: [mentor.first_name, mentor.last_name].filter(Boolean).join(" "),
    }));

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование"
        title="Возможности"
        description="Персональные предложения, заявки на консультации и переход Python → Go."
      />
      <GoTransitionProgramSettings
        description={query.data.go_transition_description_markdown}
      />
      <Stack>
        <div>
          <Title order={2}>Тарифы консультаций</Title>
          <Text c="dimmed">
            Суммы применяются только к новым заявкам. Цены в уже созданных
            заявках не меняются.
          </Text>
        </div>
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
          {query.data.consultation_types.map((item) => (
            <ConsultationPriceCard item={item} key={item.code} />
          ))}
        </SimpleGrid>
      </Stack>
      <Stack>
        <div>
          <Title order={2}>Менторы-консультанты</Title>
          <Text c="dimmed">
            Только включённые здесь менторы доступны выпускникам и могут быть
            назначены на заявку.
          </Text>
        </div>
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
          {query.data.consultation_mentors.map((mentor) => (
            <Card withBorder key={mentor.id}>
              <Switch
                checked={mentor.is_enabled}
                disabled={consultantMutation.isPending}
                label={[mentor.first_name, mentor.last_name]
                  .filter(Boolean)
                  .join(" ")}
                description={
                  mentor.telegram_username
                    ? `@${mentor.telegram_username}`
                    : "Telegram не указан"
                }
                onChange={(event) => {
                  const enabled = event.currentTarget.checked;
                  consultantMutation.mutate(
                    { mentorId: mentor.id, enabled },
                    {
                      onError: error,
                      onSuccess: () =>
                        notifications.show({
                          color: "green",
                          message: enabled
                            ? "Ментор добавлен в консультации"
                            : "Ментор убран из консультаций",
                        }),
                    },
                  );
                }}
              />
            </Card>
          ))}
        </SimpleGrid>
      </Stack>
      <Stack>
        <Title order={2}>Консультации</Title>
        {query.data.consultations.length === 0 && (
          <Alert color="gray">Новых заявок нет</Alert>
        )}
        {query.data.consultations.map((item) => (
          <Card withBorder key={item.id}>
            <Stack>
              <Group justify="space-between" align="flex-start">
                <div>
                  <Title order={3}>
                    {item.student.first_name} {item.student.last_name}
                  </Title>
                  <Text size="sm" c="dimmed">
                    Ментор: {item.mentor?.first_name ?? "не назначен"} ·{" "}
                    {formatRubles(item.price_kopecks)} · ментору{" "}
                    {formatRubles(item.mentor_reward_kopecks)} ·{" "}
                    {item.duration_minutes} мин
                  </Text>
                  <Badge mt="xs" variant="light">
                    {consultationTypeLabels[item.consultation_type]}
                  </Badge>
                  <Text mt="sm">{item.brief}</Text>
                </div>
                <Badge>{consultationLabels[item.status]}</Badge>
              </Group>
              {item.status === "requested" && (
                <Select
                  label="Назначить ментора"
                  description="Исполнитель обязателен перед выставлением счёта"
                  placeholder="Выберите доступного ментора"
                  data={enabledMentorOptions}
                  value={
                    consultationDrafts[item.id]?.mentorId ??
                    item.mentor?.id ??
                    null
                  }
                  onChange={(value) =>
                    setConsultationDrafts((current) => ({
                      ...current,
                      [item.id]: {
                        mentorId: value,
                        scheduledAt: current[item.id]?.scheduledAt ?? "",
                        note: current[item.id]?.note ?? item.admin_note ?? "",
                        summary:
                          current[item.id]?.summary ??
                          item.written_summary ??
                          "",
                      },
                    }))
                  }
                />
              )}
              <Textarea
                label="Комментарий администратора"
                value={
                  consultationDrafts[item.id]?.note ?? item.admin_note ?? ""
                }
                onChange={(event) =>
                  setConsultationDrafts((current) => ({
                    ...current,
                    [item.id]: {
                      mentorId:
                        current[item.id]?.mentorId ?? item.mentor?.id ?? null,
                      scheduledAt: current[item.id]?.scheduledAt ?? "",
                      note: event.currentTarget.value,
                      summary:
                        current[item.id]?.summary ?? item.written_summary ?? "",
                    },
                  }))
                }
              />
              {(["paid", "scheduled", "completed"] as string[]).includes(
                item.status,
              ) && (
                <Textarea
                  label="Краткий письменный итог"
                  description="Рекомендации и план дальнейших действий"
                  minRows={3}
                  value={
                    consultationDrafts[item.id]?.summary ??
                    item.written_summary ??
                    ""
                  }
                  onChange={(event) =>
                    setConsultationDrafts((current) => ({
                      ...current,
                      [item.id]: {
                        mentorId:
                          current[item.id]?.mentorId ?? item.mentor?.id ?? null,
                        scheduledAt: current[item.id]?.scheduledAt ?? "",
                        note: current[item.id]?.note ?? item.admin_note ?? "",
                        summary: event.currentTarget.value,
                      },
                    }))
                  }
                />
              )}
              <Group justify="flex-end">
                {item.status === "requested" && (
                  <Group>
                    <Button
                      loading={consultationMutation.isPending}
                      disabled={
                        !(
                          consultationDrafts[item.id]?.mentorId ??
                          item.mentor?.id
                        )
                      }
                      onClick={() =>
                        consultationMutation.mutate(
                          {
                            id: item.id,
                            status: "payment_pending",
                            mentor_id:
                              consultationDrafts[item.id]?.mentorId ??
                              item.mentor?.id ??
                              null,
                            scheduled_at: null,
                            admin_note:
                              consultationDrafts[item.id]?.note || null,
                            written_summary: null,
                          },
                          { onError: error },
                        )
                      }
                    >
                      Одобрить и выставить счёт
                    </Button>
                    <Button
                      color="red"
                      variant="light"
                      onClick={() =>
                        consultationMutation.mutate(
                          {
                            id: item.id,
                            status: "cancelled",
                            mentor_id:
                              consultationDrafts[item.id]?.mentorId ??
                              item.mentor?.id ??
                              null,
                            scheduled_at: null,
                            admin_note:
                              consultationDrafts[item.id]?.note || null,
                            written_summary: null,
                          },
                          { onError: error },
                        )
                      }
                    >
                      Отклонить
                    </Button>
                  </Group>
                )}
                {(item.status === "paid" || item.status === "scheduled") && (
                  <>
                    <TextInput
                      type="datetime-local"
                      aria-label="Дата консультации"
                      value={
                        consultationDrafts[item.id]?.scheduledAt ??
                        item.scheduled_at?.slice(0, 16) ??
                        ""
                      }
                      onChange={(event) =>
                        setConsultationDrafts((current) => ({
                          ...current,
                          [item.id]: {
                            mentorId:
                              current[item.id]?.mentorId ??
                              item.mentor?.id ??
                              null,
                            scheduledAt: event.currentTarget.value,
                            note:
                              current[item.id]?.note ?? item.admin_note ?? "",
                            summary:
                              current[item.id]?.summary ??
                              item.written_summary ??
                              "",
                          },
                        }))
                      }
                    />
                    <Button
                      variant="light"
                      disabled={
                        !(
                          consultationDrafts[item.id]?.scheduledAt ??
                          item.scheduled_at
                        )
                      }
                      onClick={() => {
                        const scheduled =
                          consultationDrafts[item.id]?.scheduledAt ??
                          item.scheduled_at;
                        consultationMutation.mutate(
                          {
                            id: item.id,
                            status: "scheduled",
                            mentor_id: item.mentor?.id ?? null,
                            scheduled_at: scheduled
                              ? new Date(scheduled).toISOString()
                              : null,
                            admin_note:
                              consultationDrafts[item.id]?.note ??
                              item.admin_note,
                            written_summary:
                              consultationDrafts[item.id]?.summary ??
                              item.written_summary,
                          },
                          { onError: error },
                        );
                      }}
                    >
                      Запланировать
                    </Button>
                    <Button
                      disabled={
                        (
                          consultationDrafts[item.id]?.summary ??
                          item.written_summary ??
                          ""
                        ).trim().length < 10
                      }
                      onClick={() =>
                        consultationMutation.mutate(
                          {
                            id: item.id,
                            status: "completed",
                            mentor_id: item.mentor?.id ?? null,
                            scheduled_at: item.scheduled_at,
                            admin_note:
                              consultationDrafts[item.id]?.note ??
                              item.admin_note,
                            written_summary:
                              consultationDrafts[item.id]?.summary ??
                              item.written_summary,
                          },
                          { onError: error },
                        )
                      }
                    >
                      Завершить с итогом
                    </Button>
                  </>
                )}
              </Group>
            </Stack>
          </Card>
        ))}
      </Stack>
      <Stack>
        <Title order={2}>Переход Python → Go</Title>
        {query.data.go_transition_applications.length === 0 && (
          <Alert color="gray">Новых заявок нет</Alert>
        )}
        {query.data.go_transition_applications.map((item) => (
          <Card withBorder key={item.id}>
            <Stack>
              <Group justify="space-between" align="flex-start">
                <div>
                  <Title order={3}>
                    {item.student.first_name} {item.student.last_name}
                  </Title>
                  <Text size="sm" c="dimmed">
                    {formatRubles(item.upfront_price_kopecks)} +{" "}
                    {item.success_fee_percent}% после оффера
                  </Text>
                  <Text mt="sm">{item.motivation}</Text>
                </div>
                <Badge>{transitionLabels[item.status]}</Badge>
              </Group>
              {item.status === "submitted" && (
                <Textarea
                  label="Комментарий к решению"
                  value={transitionNotes[item.id] ?? ""}
                  onChange={(event) =>
                    setTransitionNotes((current) => ({
                      ...current,
                      [item.id]: event.currentTarget.value,
                    }))
                  }
                />
              )}
              {item.status !== "submitted" && item.admin_note && (
                <Text size="sm" c="dimmed">
                  Комментарий: {item.admin_note}
                </Text>
              )}
              <Group justify="flex-end">
                {item.status === "submitted" && (
                  <Group>
                    <Button
                      loading={transitionMutation.isPending}
                      onClick={() =>
                        transitionMutation.mutate(
                          {
                            id: item.id,
                            approved: true,
                            admin_note: transitionNotes[item.id] || null,
                          },
                          { onError: error },
                        )
                      }
                    >
                      Одобрить
                    </Button>
                    <Button
                      color="red"
                      variant="light"
                      onClick={() =>
                        transitionMutation.mutate(
                          {
                            id: item.id,
                            approved: false,
                            admin_note: transitionNotes[item.id] || null,
                          },
                          { onError: error },
                        )
                      }
                    >
                      Отклонить
                    </Button>
                  </Group>
                )}
              </Group>
            </Stack>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}
