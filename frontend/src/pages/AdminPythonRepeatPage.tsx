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
import {
  useAdminPythonRepeat,
  useAssignAdminPythonRepeatMentor,
  useDecideAdminPythonRepeatOffer,
  useOverrideAdminPythonRepeatEligibility,
  useTransitionAdminPythonRepeat,
} from "../features/opportunities/queries";
import type {
  AdminPythonRepeatApplication,
  PythonRepeatApplicationStatus,
} from "../types/api";
import { formatRubles } from "../utils/money";

const statusLabels: Record<PythonRepeatApplicationStatus, string> = {
  draft: "Черновик",
  submitted: "Подана",
  under_review: "Рассматривается",
  needs_diagnostic: "Нужна диагностика",
  needs_clarification: "Нужно уточнение",
  approved: "Одобрена",
  rejected: "Отклонена",
  terms_accepted: "Условия приняты",
  payment_pending: "Ожидает оплаты",
  paid: "Оплачена",
  enrolled: "Зачислен",
  cancelled: "Отменена",
  expired: "Истекла",
};

function ApplicationCard({ item }: { item: AdminPythonRepeatApplication }) {
  const transition = useTransitionAdminPythonRepeat();
  const override = useOverrideAdminPythonRepeatEligibility();
  const assignMentor = useAssignAdminPythonRepeatMentor();
  const decideOffer = useDecideAdminPythonRepeatOffer();
  const query = useAdminPythonRepeat();
  const [comment, setComment] = useState("");
  const [mentorId, setMentorId] = useState(item.enrollment?.mentor_id ?? null);
  const [salaryByOffer, setSalaryByOffer] = useState<Record<string, number>>(
    {},
  );
  const error = (value: Error) =>
    notifications.show({ color: "red", message: value.message });
  const act = (status: PythonRepeatApplicationStatus) =>
    transition.mutate(
      {
        id: item.id,
        status,
        comment: comment.trim() || "Решение администратора",
        responsible_user_id: null,
      },
      { onError: error },
    );
  const mentorOptions =
    query.data?.mentors.map((mentor) => ({
      value: mentor.id,
      label: [mentor.first_name, mentor.last_name].filter(Boolean).join(" "),
    })) ?? [];
  const paid =
    item.obligation?.installments
      .filter((installment) => installment.status === "paid")
      .reduce(
        (sum, installment) => sum + (installment.actual_received_kopecks ?? 0),
        0,
      ) ?? 0;

  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={3}>
              {item.student.first_name} {item.student.last_name}
            </Title>
            <Text c="dimmed">
              {item.student.telegram_username
                ? `@${item.student.telegram_username}`
                : item.student.email}
            </Text>
          </div>
          <Badge>{statusLabels[item.status]}</Badge>
        </Group>
        <SimpleGrid cols={{ base: 1, md: 3 }}>
          <Text>
            <b>Причина:</b> {item.reason}
          </Text>
          <Text>
            <b>Цель:</b> {item.target_position}
          </Text>
          <Text>
            <b>Нагрузка:</b> {item.hours_per_week} ч/нед.
          </Text>
        </SimpleGrid>
        <Text>
          <b>Стек:</b> {item.current_stack || "не указан"}
        </Text>
        <Text>
          <b>Пробелы:</b> {item.technical_gaps}
        </Text>
        <Alert color={item.eligibility.eligible ? "green" : "yellow"}>
          {item.eligibility.message}
        </Alert>
        <Textarea
          label="Комментарий решения"
          value={comment}
          onChange={(event) => setComment(event.currentTarget.value)}
        />
        {item.status === "submitted" && (
          <Button onClick={() => act("under_review")}>
            Начать рассмотрение
          </Button>
        )}
        {item.status === "under_review" && (
          <Group>
            <Button onClick={() => act("approved")}>Одобрить</Button>
            <Button variant="light" onClick={() => act("needs_diagnostic")}>
              Запросить диагностику
            </Button>
            <Button variant="light" onClick={() => act("needs_clarification")}>
              Запросить уточнение
            </Button>
            <Button color="red" variant="light" onClick={() => act("rejected")}>
              Отклонить
            </Button>
          </Group>
        )}
        {!item.eligibility.eligible && item.eligibility.override_allowed && (
          <Button
            color="yellow"
            variant="light"
            disabled={comment.trim().length < 10}
            onClick={() =>
              override.mutate(
                { id: item.id, reason: comment },
                { onError: error },
              )
            }
          >
            Разрешить исключение с этим комментарием
          </Button>
        )}
        {item.terms_snapshot && (
          <Alert title={`Зафиксированные условия v${item.terms_version}`}>
            {formatRubles(Number(item.terms_snapshot.upfront_price_kopecks))} +{" "}
            {String(item.terms_snapshot.success_fee_percent)}%, 4 платежа. После
            принятия эти значения не меняются.
          </Alert>
        )}
        {item.enrollment && (
          <Card withBorder>
            <Stack>
              <Title order={4}>Повторное enrollment</Title>
              <Select
                label="Ментор"
                data={mentorOptions}
                value={mentorId}
                onChange={setMentorId}
              />
              <Button
                disabled={!mentorId}
                loading={assignMentor.isPending}
                onClick={() =>
                  mentorId &&
                  assignMentor.mutate(
                    { enrollmentId: item.enrollment!.id, mentorId },
                    { onError: error },
                  )
                }
              >
                Назначить ментора
              </Button>
            </Stack>
          </Card>
        )}
        {item.offers.map((offer) => (
          <Card withBorder key={offer.id}>
            <Stack>
              <Group justify="space-between">
                <Title order={4}>
                  {offer.company} · {offer.position}
                </Title>
                <Badge>{offer.status}</Badge>
              </Group>
              <NumberInput
                label="Подтверждённая фиксированная зарплата"
                suffix=" ₽"
                value={
                  salaryByOffer[offer.id] ??
                  offer.fixed_monthly_salary_kopecks / 100
                }
                onChange={(value) =>
                  setSalaryByOffer((current) => ({
                    ...current,
                    [offer.id]: Number(value) || 0,
                  }))
                }
              />
              {offer.status === "submitted" && (
                <Group>
                  <Button
                    onClick={() =>
                      decideOffer.mutate(
                        {
                          offerId: offer.id,
                          verified: true,
                          salary_base_kopecks: Math.round(
                            (salaryByOffer[offer.id] ??
                              offer.fixed_monthly_salary_kopecks / 100) * 100,
                          ),
                          comment:
                            comment || "Python Backend оффер подтверждён",
                        },
                        { onError: error },
                      )
                    }
                  >
                    Подтвердить оффер
                  </Button>
                  <Button
                    color="red"
                    variant="light"
                    onClick={() =>
                      decideOffer.mutate(
                        {
                          offerId: offer.id,
                          verified: false,
                          salary_base_kopecks: null,
                          comment: comment || "Оффер отклонён",
                        },
                        { onError: error },
                      )
                    }
                  >
                    Отклонить
                  </Button>
                </Group>
              )}
            </Stack>
          </Card>
        ))}
        {item.obligation && (
          <Card withBorder>
            <Stack>
              <Title order={4}>Финансы</Title>
              <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }}>
                <div>
                  <Text c="dimmed">Постоплата</Text>
                  <Text fw={700}>
                    {formatRubles(item.obligation.total_amount_kopecks)}
                  </Text>
                </div>
                <div>
                  <Text c="dimmed">Получено постоплаты</Text>
                  <Text fw={700}>{formatRubles(paid)}</Text>
                </div>
                <div>
                  <Text c="dimmed">Вся полученная выручка</Text>
                  <Text fw={700}>
                    {formatRubles(item.revenue_received_kopecks)}
                  </Text>
                </div>
                <div>
                  <Text c="dimmed">Начислено ментору</Text>
                  <Text fw={700}>
                    {formatRubles(item.mentor_accrued_kopecks)}
                  </Text>
                </div>
                <div>
                  <Text c="dimmed">Уже выплачено ментору</Text>
                  <Text fw={700}>{formatRubles(item.mentor_paid_kopecks)}</Text>
                </div>
                <div>
                  <Text c="dimmed">Валовой остаток</Text>
                  <Text fw={700}>
                    {formatRubles(item.gross_remainder_kopecks)}
                  </Text>
                </div>
              </SimpleGrid>
              {item.obligation.installments.map((installment) => (
                <Group key={installment.id} justify="space-between">
                  <Text>
                    #{installment.sequence_number} ·{" "}
                    {formatRubles(installment.amount_kopecks)}
                  </Text>
                  <Badge>{installment.status}</Badge>
                </Group>
              ))}
            </Stack>
          </Card>
        )}
      </Stack>
    </Card>
  );
}

export function AdminPythonRepeatPage() {
  const query = useAdminPythonRepeat();
  if (query.isPending) return <LoadingState label="Загружаем заявки…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <Stack gap="xl">
      <Button
        component={Link}
        to="/admin/opportunities"
        variant="subtle"
        w="fit-content"
      >
        ← К возможностям
      </Button>
      <PageHeader
        eyebrow="Администрирование"
        title="Повторное менторство по Python"
        description="Рассмотрение заявок, неизменяемые условия, зачисление, менторы, офферы и финансовый график."
      />
      {query.data.applications.length === 0 && (
        <Alert color="gray">Заявок пока нет</Alert>
      )}
      {query.data.applications.map((item) => (
        <ApplicationCard item={item} key={item.id} />
      ))}
    </Stack>
  );
}
