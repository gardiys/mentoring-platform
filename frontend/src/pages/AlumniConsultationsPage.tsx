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
import { useState } from "react";
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
  const notifyError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });

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
        description="Выберите задачу и специалиста. Встреча длится 50–60 минут и включает короткий бриф, созвон, письменный итог и план дальнейших действий."
      />
      <Stack gap="md">
        <Title order={2}>Выберите формат</Title>
        <Radio.Group
          value={consultationType}
          onChange={(value) => setConsultationType(value as ConsultationType)}
        >
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            {query.data.consultation_types.map((item) => (
              <Card withBorder key={item.code} component="label">
                <Stack gap="xs">
                  <Group justify="space-between" align="flex-start">
                    <Radio value={item.code} label={item.title} />
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
              </Card>
            ))}
          </SimpleGrid>
        </Radio.Group>
      </Stack>

      {offer?.available ? (
        <Card withBorder>
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
              description={typeByCode.get(consultationType)?.description}
              minRows={5}
              value={brief}
              onChange={(event) => setBrief(event.currentTarget.value)}
            />
            <Alert color="blue" variant="light">
              <Group justify="space-between" align="baseline">
                <Text>
                  {typeByCode.get(consultationType)?.title ?? "Консультация"}
                </Text>
                <Group gap="xs" align="baseline">
                  <Text fw={700}>
                    {formatRubles(
                      typeByCode.get(consultationType)?.price_kopecks ?? 0,
                    )}
                  </Text>
                  <Badge color="yellow">Цена для выпускника</Badge>
                  <Badge color="gray" variant="light">
                    {typeByCode.get(consultationType)?.duration_minutes ?? 0}{" "}
                    мин
                  </Badge>
                </Group>
              </Group>
            </Alert>
            <Button
              disabled={brief.trim().length < 10}
              loading={create.isPending}
              onClick={() =>
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
                        message: "Заявка отправлена",
                      });
                    },
                    onError: notifyError,
                  },
                )
              }
            >
              Отправить заявку
            </Button>
          </Stack>
        </Card>
      ) : (
        <Alert color="gray">{offer?.unavailable_reason}</Alert>
      )}

      {query.data.consultations.length > 0 && (
        <Stack>
          <Title order={2}>Мои консультации</Title>
          {query.data.consultations.map((item) => (
            <Card withBorder key={item.id}>
              <Group justify="space-between" align="flex-start">
                <div>
                  <Title order={3}>
                    {typeByCode.get(item.consultation_type)?.title ??
                      "Консультация"}
                  </Title>
                  <Text size="sm" c="dimmed">
                    {item.mentor
                      ? `Ментор: ${[item.mentor.first_name, item.mentor.last_name].filter(Boolean).join(" ")}`
                      : "Ментор будет назначен после рассмотрения заявки"}
                  </Text>
                  <Text mt="xs">{item.brief}</Text>
                  <Text size="sm" c="dimmed" mt="xs">
                    Длительность: {item.duration_minutes} минут
                  </Text>
                  {item.scheduled_at && (
                    <Text mt="xs">
                      Встреча:{" "}
                      {new Date(item.scheduled_at).toLocaleString("ru-RU")}
                    </Text>
                  )}
                  {item.written_summary && (
                    <Text mt="xs">Итог: {item.written_summary}</Text>
                  )}
                </div>
                <Stack align="flex-end">
                  <Badge>{statusLabels[item.status]}</Badge>
                  {item.status === "payment_pending" && (
                    <Button
                      disabled={!me.data?.email}
                      loading={payment.isPending}
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
