import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
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
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import { OpportunityFlow } from "../features/opportunities/OpportunityFlow";
import {
  useAcceptPythonRepeatTerms,
  useCheckoutPythonRepeat,
  useCheckoutPythonRepeatInstallment,
  useCreatePythonRepeatApplication,
  useCreatePythonRepeatOffer,
  usePythonRepeat,
  useSubmitPythonRepeatApplication,
  useUpdatePythonRepeatApplication,
  useSubmitPythonRepeatOffer,
} from "../features/opportunities/queries";
import type {
  PythonRepeatApplicationStatus,
  PythonRepeatDashboard,
} from "../types/api";
import {
  dateToLocalDateTimeInput,
  localDateTimeInputToIso,
} from "../utils/dateTimeInput";
import { formatRubles } from "../utils/money";
import { openExternalResource } from "../utils/openExternalResource";

const statusLabels: Record<PythonRepeatApplicationStatus, string> = {
  draft: "Черновик",
  submitted: "Заявка отправлена",
  under_review: "На рассмотрении",
  needs_diagnostic: "Нужна диагностика",
  needs_clarification: "Нужно уточнение",
  approved: "Условия одобрены",
  rejected: "Заявка отклонена",
  terms_accepted: "Условия приняты",
  payment_pending: "Ожидает оплаты",
  paid: "Оплачено",
  enrolled: "Повторное менторство активно",
  cancelled: "Отменено",
  expired: "Срок предложения истёк",
};

const statusColors: Record<PythonRepeatApplicationStatus, string> = {
  draft: "gray",
  submitted: "blue",
  under_review: "blue",
  needs_diagnostic: "yellow",
  needs_clarification: "yellow",
  approved: "yellow",
  rejected: "red",
  terms_accepted: "blue",
  payment_pending: "yellow",
  paid: "green",
  enrolled: "green",
  cancelled: "gray",
  expired: "red",
};

const offerStatusLabels: Record<string, string> = {
  draft: "Черновик",
  submitted: "На проверке",
  under_review: "Проверяется",
  verified: "Подтверждён",
  rejected: "Отклонён",
  cancelled: "Отменён",
};

const offerStatusColors: Record<string, string> = {
  draft: "gray",
  submitted: "blue",
  under_review: "blue",
  verified: "green",
  rejected: "red",
  cancelled: "gray",
};

const installmentStatusLabels: Record<string, string> = {
  scheduled: "Запланирован",
  pending: "Ожидает оплаты",
  paid: "Оплачен",
  refunded: "Возвращён",
  cancelled: "Отменён",
};

const installmentStatusColors: Record<string, string> = {
  scheduled: "blue",
  pending: "yellow",
  paid: "green",
  refunded: "gray",
  cancelled: "gray",
};

const employmentOptions = [
  { value: "employed", label: "Работаю" },
  { value: "unemployed", label: "Не работаю" },
  { value: "on_probation", label: "На испытательном сроке" },
  { value: "notice_period", label: "Увольняюсь" },
  { value: "career_break", label: "Перерыв в карьере" },
  { value: "other", label: "Иное" },
];

const reasonOptions = [
  { value: "lost_job", label: "Потерял работу" },
  { value: "failed_probation", label: "Не прошёл испытательный срок" },
  { value: "wants_higher_salary", label: "Хочу повысить зарплату" },
  { value: "wants_new_company", label: "Хочу сменить компанию" },
  { value: "returning_after_break", label: "Возвращаюсь после перерыва" },
  {
    value: "technical_refresh",
    label: "Нужно обновить технические знания",
  },
  { value: "other", label: "Иное" },
];

export function PythonRepeatOpportunityPage() {
  const query = usePythonRepeat();
  const me = useMe();
  const createApplication = useCreatePythonRepeatApplication();
  const updateApplication = useUpdatePythonRepeatApplication();
  const submitApplication = useSubmitPythonRepeatApplication();
  const acceptTerms = useAcceptPythonRepeatTerms();
  const checkout = useCheckoutPythonRepeat();
  const createOffer = useCreatePythonRepeatOffer();
  const submitOffer = useSubmitPythonRepeatOffer();
  const checkoutInstallment = useCheckoutPythonRepeatInstallment();
  const [accepted, setAccepted] = useState(false);
  const [application, setApplication] = useState({
    employment_status: "employed",
    reason: "wants_higher_salary",
    current_position: "",
    current_company: "",
    current_stack: "",
    target_position: "Python Backend Developer",
    target_salary_rubles: 250_000,
    technical_gaps: "",
    hours_per_week: 10,
    search_mode: "search_while_employed",
    additional_comment: "",
  });
  const [offer, setOffer] = useState({
    position: "Python Backend Developer",
    company: "",
    salaryRubles: 250_000,
    employment_type: "Трудовой договор",
    received_at: dateToLocalDateTimeInput(new Date()),
    expected_start_date: dateToLocalDateTimeInput(new Date()),
  });
  const initializedApplicationKey = useRef<string | null>(null);
  const current = query.data?.application;
  useEffect(() => {
    if (
      !current ||
      !(["draft", "needs_clarification"] as string[]).includes(current.status)
    ) {
      initializedApplicationKey.current = null;
      return;
    }
    const initializationKey = `${current.id}:${current.status}`;
    if (initializedApplicationKey.current === initializationKey) return;
    initializedApplicationKey.current = initializationKey;
    setApplication({
      employment_status: current.employment_status,
      reason: current.reason,
      current_position: current.current_position ?? "",
      current_company: current.current_company ?? "",
      current_stack: current.current_stack ?? "",
      target_position: current.target_position,
      target_salary_rubles: (current.target_salary_kopecks ?? 0) / 100,
      technical_gaps: current.technical_gaps,
      hours_per_week: current.hours_per_week,
      search_mode: current.search_mode,
      additional_comment: current.additional_comment ?? "",
    });
  }, [current]);

  if (query.isPending) return <LoadingState label="Загружаем условия…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const data = query.data;
  const mutationError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });
  const refresh = () => void query.refetch();
  const technicalGapsLength = application.technical_gaps.trim().length;
  const applicationValid =
    application.target_position.trim().length > 0 &&
    application.target_salary_rubles > 0 &&
    application.hours_per_week >= 1 &&
    application.hours_per_week <= 80 &&
    technicalGapsLength >= 10;
  const offerValid =
    offer.company.trim().length >= 2 &&
    offer.position.trim().length >= 2 &&
    offer.salaryRubles > 0 &&
    offer.employment_type.trim().length > 0 &&
    Boolean(offer.received_at) &&
    Boolean(offer.expected_start_date) &&
    offer.expected_start_date >= offer.received_at;
  const canCreateOffer =
    Boolean(data.enrollment) &&
    !data.offers.some(
      (item) => !["rejected", "cancelled"].includes(item.status),
    );
  const hasPaymentEmail = Boolean(me.data?.email);
  const termsExpired = Boolean(
    current?.offer_expires_at &&
    new Date(current.offer_expires_at).getTime() <= Date.now(),
  );

  const saveApplication = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data.eligibility.eligible || !applicationValid) return;
    const payload = {
      ...application,
      target_salary_kopecks: Math.round(application.target_salary_rubles * 100),
      last_interview_at: null,
      desired_start_date: null,
    };
    if (current) {
      updateApplication.mutate(
        { id: current.id, payload },
        {
          onSuccess: () => {
            if (
              current.status === "draft" ||
              current.status === "needs_clarification"
            ) {
              submitApplication.mutate(current.id, {
                onSuccess: () =>
                  notifications.show({
                    color: "green",
                    message:
                      current.status === "needs_clarification"
                        ? "Уточнения сохранены, заявка отправлена повторно"
                        : "Изменения сохранены, заявка отправлена на рассмотрение",
                  }),
                onError: mutationError,
              });
              return;
            }
            notifications.show({
              color: "green",
              message: "Черновик обновлён",
            });
          },
          onError: mutationError,
        },
      );
      return;
    }
    createApplication.mutate(payload, {
      onSuccess: () =>
        notifications.show({
          color: "green",
          message: "Черновик заявки сохранён",
        }),
      onError: mutationError,
    });
  };

  const saveOffer = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!offerValid) return;
    const receivedAt = localDateTimeInputToIso(offer.received_at);
    const expectedStartDate = localDateTimeInputToIso(
      offer.expected_start_date,
    );
    if (!receivedAt || !expectedStartDate) return;
    createOffer.mutate(
      {
        position: offer.position.trim(),
        company: offer.company.trim(),
        fixed_monthly_salary_kopecks: Math.round(offer.salaryRubles * 100),
        employment_type: offer.employment_type.trim(),
        received_at: receivedAt,
        expected_start_date: expectedStartDate,
      },
      {
        onSuccess: (dashboard) => {
          const createdDraft = (dashboard as PythonRepeatDashboard).offers
            .filter((item) => item.status === "draft")
            .sort(
              (left, right) =>
                new Date(right.created_at).getTime() -
                new Date(left.created_at).getTime(),
            )[0];
          if (!createdDraft) {
            notifications.show({
              color: "red",
              message:
                "Оффер сохранён, но не удалось отправить его автоматически. Обновите страницу и повторите отправку.",
            });
            return;
          }
          submitOffer.mutate(createdDraft.id, {
            onSuccess: () =>
              notifications.show({
                color: "green",
                message: "Оффер сохранён и отправлен на проверку",
              }),
            onError: mutationError,
          });
        },
        onError: mutationError,
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
        eyebrow="Новый карьерный цикл"
        title="Повторное менторство по Python"
        description="Точечная диагностика, персональный план и поддержка до нового подтверждённого Python Backend оффера. Старый прогресс остаётся в истории."
      />
      {current && (
        <Alert
          color={statusColors[current.status]}
          title={`Текущий статус: ${statusLabels[current.status]}`}
        >
          <Group justify="space-between" align="center" mt="xs">
            <Text size="sm">
              Все условия, комментарии команды и следующее доступное действие
              собраны в вашей заявке.
            </Text>
            <Button
              component="a"
              href="#python-repeat-application"
              variant="light"
              size="sm"
            >
              Перейти к заявке
            </Button>
          </Group>
        </Alert>
      )}
      <OpportunityFlow
        steps={[
          {
            title: "Заполните заявку",
            description: "Цель, текущая ситуация и пробелы в знаниях",
          },
          {
            title: "Пройдите диагностику",
            description: "Команда уточнит подходящий план возврата",
          },
          {
            title: "Примите условия",
            description: "Сумма и процент фиксируются в заявке",
          },
          {
            title: "Оплатите и начните",
            description: "Старый прогресс останется в истории",
          },
        ]}
      />
      <SimpleGrid cols={{ base: 1, md: 3 }}>
        <Card withBorder>
          <Text c="dimmed">Вступительный платёж</Text>
          <Title order={2}>
            {formatRubles(data.product.upfront_price_kopecks)}
          </Title>
        </Card>
        <Card withBorder>
          <Text c="dimmed">После нового оффера</Text>
          <Title order={2}>{data.product.success_fee_percent}% зарплаты</Title>
          <Text size="sm">
            Равными платежами: {data.product.success_fee_installments_count}
          </Text>
        </Card>
        <Card withBorder>
          <Text c="dimmed">Поддержка</Text>
          <Title order={2}>{data.product.active_support_months} месяца</Title>
          <Text size="sm">
            {data.product.included_mock_interviews} мок-собеседования ·{" "}
            {data.product.probation_support_days} дней испыталки
          </Text>
        </Card>
      </SimpleGrid>

      {(!current ||
        current.status === "draft" ||
        current.status === "needs_clarification") && (
        <Card withBorder component="form" onSubmit={saveApplication}>
          <Stack>
            <Title order={2}>Заявка</Title>
            <Alert color={data.eligibility.eligible ? "blue" : "gray"}>
              {data.eligibility.message}
            </Alert>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Select
                label="Текущая занятость"
                data={employmentOptions}
                value={application.employment_status}
                onChange={(value) =>
                  value &&
                  setApplication({ ...application, employment_status: value })
                }
              />
              <Select
                label="Почему возвращаетесь"
                data={reasonOptions}
                value={application.reason}
                onChange={(value) =>
                  value && setApplication({ ...application, reason: value })
                }
              />
              <TextInput
                label="Текущая должность"
                value={application.current_position}
                onChange={(event) =>
                  setApplication({
                    ...application,
                    current_position: event.currentTarget.value,
                  })
                }
              />
              <TextInput
                label="Текущая компания"
                value={application.current_company}
                onChange={(event) =>
                  setApplication({
                    ...application,
                    current_company: event.currentTarget.value,
                  })
                }
              />
              <TextInput
                label="Целевая должность"
                value={application.target_position}
                onChange={(event) =>
                  setApplication({
                    ...application,
                    target_position: event.currentTarget.value,
                  })
                }
                required
                error={
                  application.target_position.length > 0 &&
                  !application.target_position.trim()
                    ? "Укажите должность"
                    : undefined
                }
              />
              <NumberInput
                label="Целевая зарплата"
                description="Желаемая сумма на руки в месяц"
                suffix=" ₽"
                min={1}
                required
                value={application.target_salary_rubles}
                onChange={(value) =>
                  setApplication({
                    ...application,
                    target_salary_rubles: Number(value) || 0,
                  })
                }
              />
              <NumberInput
                label="Часов в неделю"
                description="Реалистичная нагрузка от 1 до 80 часов"
                min={1}
                max={80}
                required
                value={application.hours_per_week}
                onChange={(value) =>
                  setApplication({
                    ...application,
                    hours_per_week: Number(value) || 0,
                  })
                }
              />
              <Select
                label="Режим поиска"
                data={[
                  { value: "active_search", label: "Активно ищу" },
                  {
                    value: "search_while_employed",
                    label: "Ищу параллельно работе",
                  },
                  {
                    value: "not_ready_to_search",
                    label: "Пока не готов искать",
                  },
                ]}
                value={application.search_mode}
                onChange={(value) =>
                  value &&
                  setApplication({ ...application, search_mode: value })
                }
              />
            </SimpleGrid>
            <Textarea
              label="Текущий стек"
              value={application.current_stack}
              onChange={(event) =>
                setApplication({
                  ...application,
                  current_stack: event.currentTarget.value,
                })
              }
            />
            <Textarea
              label="Какие пробелы хотите закрыть"
              description="Минимум 10 символов — это поможет подготовить диагностику"
              minRows={4}
              minLength={10}
              maxLength={5000}
              required
              value={application.technical_gaps}
              onChange={(event) =>
                setApplication({
                  ...application,
                  technical_gaps: event.currentTarget.value,
                })
              }
              error={
                application.technical_gaps.length > 0 &&
                technicalGapsLength < 10
                  ? "Опишите цель чуть подробнее"
                  : undefined
              }
            />
            <Text size="xs" c="dimmed" ta="right">
              {technicalGapsLength} / 5000
            </Text>
            <Textarea
              label="Дополнительный комментарий"
              value={application.additional_comment}
              onChange={(event) =>
                setApplication({
                  ...application,
                  additional_comment: event.currentTarget.value,
                })
              }
            />
            <Button
              type="submit"
              disabled={!data.eligibility.eligible || !applicationValid}
              loading={
                createApplication.isPending ||
                updateApplication.isPending ||
                ((current?.status === "draft" ||
                  current?.status === "needs_clarification") &&
                  submitApplication.isPending)
              }
            >
              {current?.status === "needs_clarification"
                ? "Сохранить и отправить повторно"
                : current?.status === "draft"
                  ? "Сохранить и отправить на рассмотрение"
                  : "Сохранить заявку"}
            </Button>
          </Stack>
        </Card>
      )}

      {current && (
        <Card
          withBorder
          id="python-repeat-application"
          style={{ scrollMarginTop: 24 }}
          className="opportunity-request-card"
          data-complete={["paid", "enrolled"].includes(current.status)}
        >
          <Stack>
            <Group justify="space-between">
              <Title order={2}>Ваша заявка</Title>
              <Badge color={statusColors[current.status]}>
                {statusLabels[current.status]}
              </Badge>
            </Group>
            <Text>Цель: {current.target_position}</Text>
            <Text size="sm" c="dimmed">
              Создана {new Date(current.created_at).toLocaleDateString("ru-RU")}
            </Text>
            {current.admin_comment && (
              <Alert color="blue" title="Комментарий команды">
                {current.admin_comment}
              </Alert>
            )}
            {current.status === "needs_clarification" && (
              <Text size="sm" c="dimmed">
                Исправьте данные в форме выше, сохраните уточнения, затем
                отправьте заявку повторно.
              </Text>
            )}
            {current.status === "approved" && (
              <Stack>
                <Alert
                  color={termsExpired ? "red" : "yellow"}
                  title={`Условия, версия ${current.terms_version}`}
                >
                  <Stack gap={4}>
                    <Text>
                      {formatRubles(
                        Number(
                          current.terms_snapshot?.upfront_price_kopecks ?? 0,
                        ),
                      )}{" "}
                      +{" "}
                      {Number(current.terms_snapshot?.success_fee_percent ?? 0)}
                      % от подтверждённой зарплаты. Количество платежей:{" "}
                      {Number(
                        current.terms_snapshot
                          ?.success_fee_installments_count ??
                          data.product.success_fee_installments_count,
                      )}
                      .
                    </Text>
                    {current.offer_expires_at && (
                      <Text size="sm">
                        {termsExpired
                          ? "Срок принятия условий истёк. Свяжитесь с командой, чтобы получить актуальное предложение."
                          : `Принять до ${new Date(current.offer_expires_at).toLocaleString("ru-RU")}`}
                      </Text>
                    )}
                  </Stack>
                </Alert>
                <Checkbox
                  disabled={termsExpired}
                  checked={accepted}
                  onChange={(event) => setAccepted(event.currentTarget.checked)}
                  label="Я ознакомился и принимаю условия повторного менторства по Python"
                />
                <Button
                  disabled={termsExpired || !accepted}
                  loading={acceptTerms.isPending}
                  onClick={() =>
                    acceptTerms.mutate(current.id, { onError: mutationError })
                  }
                >
                  Принять условия
                </Button>
              </Stack>
            )}
            {(current.status === "terms_accepted" ||
              current.status === "payment_pending") && (
              <Stack align="flex-start">
                {!hasPaymentEmail && <PaymentEmailAlert />}
                <Button
                  disabled={!hasPaymentEmail}
                  loading={checkout.isPending}
                  onClick={() =>
                    void openExternalResource(
                      checkout
                        .mutateAsync(current.id)
                        .then((value) => value.payment_url),
                    ).catch(mutationError)
                  }
                >
                  Оплатить{" "}
                  {formatRubles(
                    Number(current.terms_snapshot?.upfront_price_kopecks ?? 0),
                  )}
                </Button>
              </Stack>
            )}
          </Stack>
        </Card>
      )}

      {data.enrollment && (
        <Card withBorder>
          <Stack>
            <Group justify="space-between">
              <Title order={2}>Новое участие</Title>
              <Badge color="green">Активно</Badge>
            </Group>
            <Text>
              Старый прогресс сохранён. После диагностики ментор сформирует
              персональный план.
            </Text>
            {data.enrollment.mentor_id ? (
              <Text>Ментор назначен</Text>
            ) : (
              <Alert color="yellow">Команда назначает ментора</Alert>
            )}
          </Stack>
        </Card>
      )}

      {canCreateOffer && (
        <Card withBorder component="form" onSubmit={saveOffer}>
          <Stack>
            <Title order={2}>Новый оффер</Title>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <TextInput
                label="Компания"
                required
                minLength={2}
                value={offer.company}
                onChange={(event) =>
                  setOffer({ ...offer, company: event.currentTarget.value })
                }
                error={
                  offer.company.length > 0 && offer.company.trim().length < 2
                    ? "Укажите название компании"
                    : undefined
                }
              />
              <TextInput
                label="Должность"
                required
                minLength={2}
                value={offer.position}
                onChange={(event) =>
                  setOffer({ ...offer, position: event.currentTarget.value })
                }
                error={
                  offer.position.length > 0 && offer.position.trim().length < 2
                    ? "Укажите должность"
                    : undefined
                }
              />
              <NumberInput
                label="Фиксированная зарплата на руки"
                description="Сумма после налогов и обязательных комиссий"
                suffix=" ₽"
                min={1}
                required
                value={offer.salaryRubles}
                onChange={(value) =>
                  setOffer({ ...offer, salaryRubles: Number(value) || 0 })
                }
              />
              <TextInput
                label="Формат трудоустройства"
                required
                value={offer.employment_type}
                onChange={(event) =>
                  setOffer({
                    ...offer,
                    employment_type: event.currentTarget.value,
                  })
                }
              />
              <TextInput
                type="datetime-local"
                label="Оффер получен"
                description="Время отображается в вашем часовом поясе"
                required
                value={offer.received_at}
                onChange={(event) =>
                  setOffer({ ...offer, received_at: event.currentTarget.value })
                }
              />
              <TextInput
                type="datetime-local"
                label="Плановая дата выхода"
                description="Время отображается в вашем часовом поясе"
                required
                error={
                  offer.expected_start_date < offer.received_at
                    ? "Дата выхода не может быть раньше получения оффера"
                    : undefined
                }
                value={offer.expected_start_date}
                onChange={(event) =>
                  setOffer({
                    ...offer,
                    expected_start_date: event.currentTarget.value,
                  })
                }
              />
            </SimpleGrid>
            <Button
              type="submit"
              disabled={!offerValid}
              loading={createOffer.isPending || submitOffer.isPending}
            >
              Сохранить и отправить на проверку
            </Button>
          </Stack>
        </Card>
      )}

      {data.offers.map((item) => (
        <Card withBorder key={item.id}>
          <Group justify="space-between">
            <div>
              <Title order={3}>{item.company}</Title>
              <Text>
                {item.position} ·{" "}
                {formatRubles(item.fixed_monthly_salary_kopecks)}
              </Text>
            </div>
            <Badge color={offerStatusColors[item.status] ?? "gray"}>
              {offerStatusLabels[item.status] ?? item.status}
            </Badge>
          </Group>
          {item.status === "draft" && (
            <Button
              mt="md"
              loading={submitOffer.isPending}
              onClick={() =>
                submitOffer.mutate(item.id, { onError: mutationError })
              }
            >
              Отправить оффер на проверку
            </Button>
          )}
          {item.verification_comment && (
            <Alert
              mt="md"
              color={item.status === "rejected" ? "red" : "blue"}
              title="Комментарий команды"
            >
              {item.verification_comment}
            </Alert>
          )}
        </Card>
      ))}

      {data.obligation && (
        <Card withBorder>
          <Stack>
            <Title order={2}>График постоплаты</Title>
            <Text>
              Всего {formatRubles(data.obligation.total_amount_kopecks)} ·
              оплачено{" "}
              {formatRubles(
                data.obligation.installments
                  .filter((item) => item.status === "paid")
                  .reduce(
                    (sum, item) => sum + (item.actual_received_kopecks ?? 0),
                    0,
                  ),
              )}
            </Text>
            {!hasPaymentEmail &&
              data.obligation.installments.some((item) =>
                ["scheduled", "pending"].includes(item.status),
              ) && <PaymentEmailAlert />}
            {data.obligation.installments.map((item) => (
              <Group key={item.id} justify="space-between">
                <div>
                  <Text fw={700}>
                    Платёж {item.sequence_number}:{" "}
                    {formatRubles(item.amount_kopecks)}
                  </Text>
                  <Text size="sm" c="dimmed">
                    до {new Date(item.due_at).toLocaleDateString("ru-RU")}
                  </Text>
                </div>
                <Group>
                  <Badge color={installmentStatusColors[item.status] ?? "gray"}>
                    {installmentStatusLabels[item.status] ?? item.status}
                  </Badge>
                  {(item.status === "scheduled" ||
                    item.status === "pending") && (
                    <Button
                      disabled={!hasPaymentEmail}
                      loading={
                        checkoutInstallment.isPending &&
                        checkoutInstallment.variables === item.id
                      }
                      onClick={() =>
                        void openExternalResource(
                          checkoutInstallment
                            .mutateAsync(item.id)
                            .then((value) => value.payment_url),
                        ).catch(mutationError)
                      }
                    >
                      Оплатить
                    </Button>
                  )}
                </Group>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
      <Button variant="subtle" onClick={refresh}>
        Обновить данные
      </Button>
    </Stack>
  );
}

function PaymentEmailAlert() {
  return (
    <Alert color="orange" title="Нужен email для чека">
      <Stack gap="xs">
        <Text size="sm">
          Сохраните email в платёжном профиле, после этого станет доступна
          оплата.
        </Text>
        <Button component={Link} to="/payments" variant="light" size="xs">
          Указать email
        </Button>
      </Stack>
    </Alert>
  );
}
