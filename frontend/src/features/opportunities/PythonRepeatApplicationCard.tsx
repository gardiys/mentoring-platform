import {
  Alert,
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
  Badge,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  useAssignAdminPythonRepeatMentor,
  useDecideAdminPythonRepeatOffer,
  useOverrideAdminPythonRepeatEligibility,
  useTransitionAdminPythonRepeat,
  opportunityKeys,
} from "./queries";
import { workspaceApi, type RepeatDetail } from "./workspaceApi";
import {
  OpportunityContacts,
  OpportunityStage,
  PrimaryAction,
} from "./OpportunityDetail";
import type { PythonRepeatApplicationStatus } from "../../types/api";
import { formatRubles } from "../../utils/money";
import { opportunityDate } from "./workspaceLabels";

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
const reasons: Record<string, string> = {
  lost_job: "Потеря работы",
  failed_probation: "Не пройден испытательный срок",
  wants_higher_salary: "Рост дохода",
  wants_new_company: "Смена компании",
  returning_after_break: "Возвращение после перерыва",
  technical_refresh: "Обновление технических знаний",
  other: "Другая причина",
};
const offerLabels: Record<string, string> = {
  draft: "Черновик",
  submitted: "На проверке",
  under_review: "Рассматривается",
  verified: "Подтверждён",
  rejected: "Отклонён",
  cancelled: "Отменён",
};
const paymentLabels: Record<string, string> = {
  scheduled: "Запланирован",
  pending: "Ожидает оплаты",
  paid: "Оплачен",
  overdue: "Просрочен",
  cancelled: "Отменён",
  refunded: "Возвращён",
  failed: "Ошибка оплаты",
};

export function PythonRepeatApplicationCard({ item }: { item: RepeatDetail }) {
  const transition = useTransitionAdminPythonRepeat();
  const override = useOverrideAdminPythonRepeatEligibility();
  const assign = useAssignAdminPythonRepeatMentor();
  const decide = useDecideAdminPythonRepeatOffer();
  const settings = useQuery({
    queryKey: [...opportunityKeys.all, "settings"],
    queryFn: workspaceApi.settings,
  });
  const [comments, setComments] = useState<Record<string, string>>({});
  const [mentorId, setMentorId] = useState(item.enrollment?.mentor_id ?? null);
  const [salaries, setSalaries] = useState<Record<string, number>>({});
  const error = (value: Error) =>
    notifications.show({ color: "red", message: value.message });
  const success = (key: string, message: string) => {
    setComments((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    notifications.show({ color: "green", message });
  };
  const messageField = (
    key: string,
    label = "Сообщение выпускнику (придёт в уведомлении)",
  ) => (
    <Textarea
      label={label}
      maxLength={5000}
      value={comments[key] ?? ""}
      onChange={(event) => {
        const value = event.currentTarget.value;
        setComments((current) => ({ ...current, [key]: value }));
      }}
    />
  );
  const act = (status: PythonRepeatApplicationStatus) => {
    if (
      status === "rejected" &&
      !window.confirm(`Отклонить заявку ${item.student.first_name}?`)
    )
      return;
    transition.mutate(
      {
        id: item.id,
        status,
        comment: comments[status]?.trim() || "",
        responsible_user_id: null,
      },
      {
        onError: error,
        onSuccess: () =>
          success(status, `Заявка: ${statusLabels[status].toLowerCase()}`),
      },
    );
  };
  const available: PythonRepeatApplicationStatus[] =
    item.stage === "new"
      ? ["under_review"]
      : item.stage === "review"
        ? ["approved", "needs_diagnostic", "needs_clarification", "rejected"]
        : [];
  const actionLabels: Partial<Record<PythonRepeatApplicationStatus, string>> = {
    under_review: "Начать рассмотрение",
    approved: "Одобрить",
    needs_diagnostic: "Запросить диагностику",
    needs_clarification: "Запросить уточнение",
    rejected: "Отклонить",
  };
  const paid =
    item.obligation?.installments
      .filter((value) => value.status === "paid")
      .reduce((sum, value) => sum + (value.actual_received_kopecks ?? 0), 0) ??
    0;
  const primaryStatus =
    item.stage === "new"
      ? "under_review"
      : item.stage === "review"
        ? "approved"
        : null;
  const primaryOffer = item.offers
    .filter((offer) => offer.status === "submitted")
    .sort(
      (a, b) =>
        new Date(a.submitted_at ?? a.created_at).getTime() -
        new Date(b.submitted_at ?? b.created_at).getTime(),
    )[0];
  const verifyOffer = (offer: RepeatDetail["offers"][number]) =>
    decide.mutate(
      {
        offerId: offer.id,
        verified: true,
        salary_base_kopecks: Math.round(
          (salaries[offer.id] ?? offer.fixed_monthly_salary_kopecks / 100) *
            100,
        ),
        comment: comments[`verify-${offer.id}`]?.trim() || "Оффер подтверждён",
      },
      {
        onError: error,
        onSuccess: () => success(`verify-${offer.id}`, "Оффер подтверждён"),
      },
    );
  const assignSelectedMentor = () =>
    mentorId &&
    assign.mutate(
      { enrollmentId: item.enrollment!.id, mentorId },
      {
        onError: error,
        onSuccess: () =>
          notifications.show({
            color: "green",
            message: "Ментор назначен",
          }),
      },
    );
  return (
    <Stack gap="lg">
      <OpportunityContacts student={item.student} />
      <Group>
        <OpportunityStage stage={item.stage} />
        <Text fw={700}>{item.next_action}</Text>
      </Group>
      <Text size="sm" c="dimmed">
        Создана {opportunityDate(item.created_at)}
      </Text>
      <Text>
        <b>Причина:</b> {reasons[item.reason] ?? "Другая причина"}
      </Text>
      <Text>
        <b>Цель:</b> {item.target_position}
      </Text>
      <Text>
        <b>Нагрузка:</b> {item.hours_per_week} ч/нед.
      </Text>
      <Text>
        <b>Стек:</b> {item.current_stack || "не указан"}
      </Text>
      <Text>
        <b>Пробелы:</b> {item.technical_gaps}
      </Text>
      <Alert color={item.eligibility.eligible ? "green" : "yellow"}>
        {item.eligibility.message}
      </Alert>
      {available.map((status) => (
        <Card withBorder key={status}>
          <Stack gap="xs">
            <Title order={4}>{actionLabels[status]}</Title>
            {messageField(status)}
            {status !== primaryStatus && (
              <Button
                variant="light"
                color={status === "rejected" ? "red" : "blue"}
                loading={
                  transition.isPending &&
                  transition.variables?.status === status
                }
                disabled={transition.isPending}
                onClick={() => act(status)}
              >
                {actionLabels[status]}
              </Button>
            )}
          </Stack>
        </Card>
      ))}
      {!item.eligibility.eligible && item.eligibility.override_allowed && (
        <Card withBorder>
          <Stack>
            {messageField("override", "Причина исключения из правил")}
            <Button
              color="yellow"
              variant="light"
              loading={override.isPending}
              disabled={(comments.override?.trim().length ?? 0) < 10}
              onClick={() =>
                override.mutate(
                  { id: item.id, reason: comments.override ?? "" },
                  {
                    onError: error,
                    onSuccess: () =>
                      success("override", "Исключение разрешено"),
                  },
                )
              }
            >
              Разрешить исключение
            </Button>
          </Stack>
        </Card>
      )}
      {item.terms_snapshot && (
        <Alert title={`Зафиксированные условия v${item.terms_version}`}>
          {formatRubles(Number(item.terms_snapshot.upfront_price_kopecks))} +{" "}
          {String(item.terms_snapshot.success_fee_percent)}%, число платежей:{" "}
          {String(item.terms_snapshot.success_fee_installments_count)}. После
          принятия условия не меняются.
        </Alert>
      )}
      {item.enrollment && (
        <Card withBorder>
          <Stack>
            <Title order={4}>Зачисление</Title>
            <Select
              label="Ментор программы"
              data={(settings.data?.consultation_mentors ?? []).map(
                (mentor) => ({
                  value: mentor.id,
                  label: `${mentor.first_name} ${mentor.last_name ?? ""}`,
                }),
              )}
              value={mentorId}
              onChange={setMentorId}
            />
            {item.stage !== "needs_mentor" && (
              <Button
                variant="light"
                disabled={!mentorId}
                loading={assign.isPending}
                onClick={assignSelectedMentor}
              >
                Назначить ментора
              </Button>
            )}
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
              <Badge>{offerLabels[offer.status] ?? "Оффер"}</Badge>
            </Group>
            {offer.status === "submitted" && (
              <>
                <NumberInput
                  label="Подтверждённая фиксированная зарплата"
                  suffix=" ₽"
                  min={1}
                  value={
                    salaries[offer.id] ??
                    offer.fixed_monthly_salary_kopecks / 100
                  }
                  onChange={(value) =>
                    setSalaries((current) => ({
                      ...current,
                      [offer.id]: Number(value) || 0,
                    }))
                  }
                />
                {messageField(`verify-${offer.id}`)}
                {(item.stage !== "offer_review" ||
                  primaryOffer?.id !== offer.id) && (
                  <Button
                    variant="light"
                    loading={
                      decide.isPending &&
                      decide.variables?.offerId === offer.id &&
                      decide.variables.verified
                    }
                    disabled={
                      decide.isPending ||
                      (salaries[offer.id] ??
                        offer.fixed_monthly_salary_kopecks / 100) <= 0
                    }
                    onClick={() => verifyOffer(offer)}
                  >
                    Подтвердить оффер
                  </Button>
                )}
                {messageField(`reject-${offer.id}`)}
                <Button
                  color="red"
                  variant="light"
                  loading={
                    decide.isPending &&
                    decide.variables?.offerId === offer.id &&
                    !decide.variables.verified
                  }
                  disabled={decide.isPending}
                  onClick={() => {
                    if (window.confirm("Отклонить оффер?"))
                      decide.mutate(
                        {
                          offerId: offer.id,
                          verified: false,
                          salary_base_kopecks: null,
                          comment:
                            comments[`reject-${offer.id}`]?.trim() ||
                            "Оффер отклонён",
                        },
                        {
                          onError: error,
                          onSuccess: () =>
                            success(`reject-${offer.id}`, "Оффер отклонён"),
                        },
                      );
                  }}
                >
                  Отклонить оффер
                </Button>
              </>
            )}
          </Stack>
        </Card>
      ))}
      {item.obligation && (
        <Card withBorder>
          <Stack>
            <Title order={4}>Финансы</Title>
            <SimpleGrid cols={{ base: 2, md: 3 }}>
              {[
                ["Постоплата", item.obligation.total_amount_kopecks],
                ["Получено постоплаты", paid],
                ["Вся полученная выручка", item.revenue_received_kopecks],
                ["Начислено ментору", item.mentor_accrued_kopecks],
                ["Выплачено ментору", item.mentor_paid_kopecks],
                ["Валовой остаток", item.gross_remainder_kopecks],
              ].map(([title, amount]) => (
                <div key={String(title)}>
                  <Text c="dimmed">{title}</Text>
                  <Text fw={700}>{formatRubles(Number(amount))}</Text>
                </div>
              ))}
            </SimpleGrid>
            {item.obligation.installments.map((value) => (
              <Group key={value.id} justify="space-between">
                <Text>
                  #{value.sequence_number} ·{" "}
                  {formatRubles(value.amount_kopecks)}
                </Text>
                <Badge>{paymentLabels[value.status] ?? "Платёж"}</Badge>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
      <Title order={4}>История</Title>
      {item.history.map((event, index) => (
        <Card withBorder key={`${event.created_at}:${index}`}>
          <Text size="sm" c="dimmed">
            {opportunityDate(event.created_at)}
          </Text>
          <Text>
            {statusLabels[event.new_status]}
            {event.comment ? ` · ${event.comment}` : ""}
          </Text>
        </Card>
      ))}
      {primaryStatus ? (
        <PrimaryAction>
          <Button
            loading={transition.isPending}
            disabled={transition.isPending}
            onClick={() => act(primaryStatus)}
          >
            {actionLabels[primaryStatus]}
          </Button>
        </PrimaryAction>
      ) : item.stage === "needs_mentor" && item.enrollment ? (
        <PrimaryAction>
          <Button
            disabled={!mentorId}
            loading={assign.isPending}
            onClick={assignSelectedMentor}
          >
            Назначить ментора
          </Button>
        </PrimaryAction>
      ) : item.stage === "offer_review" && primaryOffer ? (
        <PrimaryAction>
          <Button
            loading={
              decide.isPending &&
              decide.variables?.offerId === primaryOffer.id &&
              decide.variables.verified
            }
            disabled={
              decide.isPending ||
              (salaries[primaryOffer.id] ??
                primaryOffer.fixed_monthly_salary_kopecks / 100) <= 0
            }
            onClick={() => verifyOffer(primaryOffer)}
          >
            Подтвердить оффер
          </Button>
        </PrimaryAction>
      ) : null}
    </Stack>
  );
}
