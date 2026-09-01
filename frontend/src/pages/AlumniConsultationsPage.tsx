import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import {
  useCreateConsultation,
  useCreateConsultationPaymentLink,
  useMyOpportunities,
} from "../features/opportunities/queries";
import { OpportunityFlow } from "../features/opportunities/OpportunityFlow";
import type { ConsultationStatus, ConsultationType } from "../types/api";
import { formatRubles } from "../utils/money";
import { openExternalResource } from "../utils/openExternalResource";

const statusLabels: Record<ConsultationStatus, string> = {
  requested: "На рассмотрении",
  payment_pending: "Ожидает оплаты",
  paid: "Оплачена",
  scheduled: "Запланирована",
  completed: "Завершена",
  cancelled: "Отменена",
};

const statusColors: Record<ConsultationStatus, string> = {
  requested: "blue",
  payment_pending: "yellow",
  paid: "green",
  scheduled: "cyan",
  completed: "green",
  cancelled: "gray",
};

export function AlumniConsultationsPage() {
  const query = useMyOpportunities();
  const me = useMe();
  const create = useCreateConsultation();
  const payment = useCreateConsultationPaymentLink();
  const [mentorId, setMentorId] = useState<string | null>("any");
  const [consultationType, setConsultationType] =
    useState<ConsultationType>("free_topic");
  const [brief, setBrief] = useState("");

  if (query.isPending) return <LoadingState label="Загружаем консультации…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const offer = query.data.opportunities.find(
    (item) => item.code === "ALUMNI_CONSULTATION",
  );
  const typeByCode = new Map(
    query.data.consultation_types.map((item) => [item.code, item]),
  );
  const selectedType = typeByCode.get(consultationType);
  const activeConsultations = query.data.consultations.filter(
    (item) => !["completed", "cancelled"].includes(item.status),
  );
  const briefLength = brief.trim().length;
  const notifyError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });
  const submitConsultation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!offer?.available || briefLength < 10) return;
    if (
      activeConsultations.length > 0 &&
      !window.confirm(
        "У вас уже есть активная заявка. Создать ещё одну консультацию?",
      )
    ) {
      return;
    }
    create.mutate(
      {
        mentor_id: mentorId === "any" ? null : mentorId,
        consultation_type: consultationType,
        brief: brief.trim(),
      },
      {
        onSuccess: () => {
          setBrief("");
          setMentorId("any");
          notifications.show({
            color: "green",
            message: "Заявка отправлена и появилась в разделе ниже",
          });
        },
        onError: notifyError,
      },
    );
  };

  return (
    <Stack gap="xl">
      <Button
        component={Link}
        to="/opportunities/alumni"
        variant="subtle"
        w="fit-content"
      >
        ← В кабинет выпускника
      </Button>
      <PageHeader
        eyebrow="Кабинет выпускника"
        title="Консультации с менторами"
        description="Выберите задачу и специалиста. Длительность зависит от формата; после созвона вы получите письменный итог и план дальнейших действий."
      />
      <OpportunityFlow
        steps={[
          {
            title: "Выберите формат",
            description: "Задачу, длительность и подходящую цену",
          },
          {
            title: "Оставьте заявку",
            description: "Можно выбрать ментора или доверить выбор команде",
          },
          {
            title: "Согласуйте и оплатите",
            description: "Оплата появится после подтверждения заявки",
          },
          {
            title: "Получите результат",
            description: "Созвон, письменный итог и следующие шаги",
          },
        ]}
      />
      {activeConsultations.length > 0 && (
        <Alert color="blue" title="Консультация уже в работе">
          <Group justify="space-between" align="center" mt="xs">
            <Text size="sm">
              Активных заявок: {activeConsultations.length}. Статус и следующее
              действие находятся в разделе «Мои консультации».
            </Text>
            <Button
              component="a"
              href="#my-consultations"
              variant="light"
              size="sm"
            >
              Перейти к заявкам
            </Button>
          </Group>
        </Alert>
      )}
      <Stack gap="md">
        <Title order={2}>Выберите формат</Title>
        <Radio.Group
          label="Формат консультации"
          value={consultationType}
          onChange={(value) => setConsultationType(value as ConsultationType)}
        >
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            {query.data.consultation_types.map((item) => (
              <Radio.Card
                withBorder
                key={item.code}
                value={item.code}
                p="lg"
                radius="md"
                className="opportunity-choice"
                data-selected={consultationType === item.code}
              >
                <Stack gap="xs">
                  <Group justify="space-between" align="flex-start">
                    <Group gap="sm" wrap="nowrap">
                      <Radio.Indicator />
                      <Text fw={700}>{item.title}</Text>
                    </Group>
                    <Badge color="gray" variant="light">
                      {item.duration_minutes} мин
                    </Badge>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {item.description}
                  </Text>
                  <Group gap="xs" align="baseline">
                    <Text fw={700} c="blue">
                      {formatRubles(item.price_kopecks)}
                    </Text>
                    <Text size="sm" td="line-through" c="dimmed">
                      {formatRubles(item.comparison_price_kopecks)}
                    </Text>
                  </Group>
                </Stack>
              </Radio.Card>
            ))}
          </SimpleGrid>
        </Radio.Group>
      </Stack>

      {offer?.available ? (
        <Card withBorder component="form" onSubmit={submitConsultation}>
          <Stack>
            <Title order={2}>Оставить заявку</Title>
            <Select
              label="Ментор"
              description="Если не принципиально, администратор назначит доступного специалиста"
              value={mentorId}
              onChange={setMentorId}
              allowDeselect={false}
              data={[
                { value: "any", label: "Любой ментор" },
                ...query.data.mentors.map((mentor) => ({
                  value: mentor.id,
                  label: [mentor.first_name, mentor.last_name]
                    .filter(Boolean)
                    .join(" "),
                })),
              ]}
            />
            <Textarea
              label="Короткий бриф"
              description="Опишите контекст, цель встречи и что хотите получить в результате"
              minRows={5}
              minLength={10}
              maxLength={5000}
              required
              value={brief}
              onChange={(event) => setBrief(event.currentTarget.value)}
              error={
                brief.length > 0 && briefLength < 10
                  ? "Добавьте немного деталей — минимум 10 символов"
                  : undefined
              }
            />
            <Text size="xs" c="dimmed" ta="right">
              {briefLength} / 5000
            </Text>
            <Alert color="blue" variant="light">
              <Group
                justify="space-between"
                align="baseline"
                className="opportunity-summary-row"
              >
                <Text>{selectedType?.title ?? "Консультация"}</Text>
                <Group gap="xs" align="baseline">
                  <Text fw={700}>
                    {formatRubles(selectedType?.price_kopecks ?? 0)}
                  </Text>
                  <Badge color="yellow">Цена для выпускника</Badge>
                  <Badge color="gray" variant="light">
                    {selectedType?.duration_minutes ?? 0} мин
                  </Badge>
                </Group>
              </Group>
            </Alert>
            <Button
              type="submit"
              disabled={briefLength < 10}
              loading={create.isPending}
            >
              Отправить заявку
            </Button>
          </Stack>
        </Card>
      ) : (
        <Alert color="gray" title="Оформление сейчас недоступно">
          {offer?.unavailable_reason ??
            "Консультации временно отключены. Вы можете изучить форматы и вернуться позже."}
        </Alert>
      )}

      {query.data.consultations.length > 0 && (
        <Stack id="my-consultations" style={{ scrollMarginTop: 24 }}>
          <Title order={2}>Мои консультации</Title>
          {query.data.consultations.map((item) => (
            <Card
              withBorder
              key={item.id}
              className="opportunity-request-card"
              data-complete={item.status === "completed"}
            >
              <Group justify="space-between" align="flex-start" wrap="wrap">
                <div className="opportunity-request-main">
                  <Title order={3}>
                    {typeByCode.get(item.consultation_type)?.title ??
                      "Консультация"}
                  </Title>
                  <Text size="sm" c="dimmed">
                    {item.mentor
                      ? `Ментор: ${[item.mentor.first_name, item.mentor.last_name].filter(Boolean).join(" ")}`
                      : "Ментор будет назначен после рассмотрения заявки"}
                  </Text>
                  <Text
                    mt="xs"
                    style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                  >
                    {item.brief}
                  </Text>
                  <Text size="sm" c="dimmed" mt="xs">
                    Заявка от{" "}
                    {new Date(item.created_at).toLocaleDateString("ru-RU")} ·{" "}
                    {item.duration_minutes} минут
                  </Text>
                  {item.admin_note && (
                    <Alert
                      color={item.status === "cancelled" ? "red" : "blue"}
                      variant="light"
                      mt="sm"
                      title="Комментарий команды"
                    >
                      <Text
                        style={{
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {item.admin_note}
                      </Text>
                    </Alert>
                  )}
                  {item.scheduled_at && (
                    <Text mt="xs">
                      Встреча:{" "}
                      {new Date(item.scheduled_at).toLocaleString("ru-RU")}
                    </Text>
                  )}
                  {item.written_summary && (
                    <Alert
                      color="green"
                      variant="light"
                      mt="sm"
                      title="Итог консультации"
                    >
                      <Text
                        style={{
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {item.written_summary}
                      </Text>
                    </Alert>
                  )}
                </div>
                <Stack align="flex-end" className="opportunity-request-actions">
                  <Badge color={statusColors[item.status]}>
                    {statusLabels[item.status]}
                  </Badge>
                  {item.status === "payment_pending" && (
                    <>
                      {!me.data?.email && (
                        <Alert color="orange" title="Нужен email для чека">
                          <Stack gap="xs">
                            <Text size="sm">
                              Сохраните email, после этого станет доступна
                              оплата.
                            </Text>
                            <Button
                              component={Link}
                              to="/payments"
                              variant="light"
                              size="xs"
                            >
                              Указать email
                            </Button>
                          </Stack>
                        </Alert>
                      )}
                      <Button
                        disabled={!me.data?.email}
                        loading={
                          payment.isPending && payment.variables === item.id
                        }
                        onClick={() =>
                          void openExternalResource(
                            payment
                              .mutateAsync(item.id)
                              .then((result) => result.payment_url),
                          ).catch(notifyError)
                        }
                      >
                        Оплатить {formatRubles(item.price_kopecks)}
                      </Button>
                    </>
                  )}
                </Stack>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
