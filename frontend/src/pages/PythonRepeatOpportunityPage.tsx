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
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
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
import type { PythonRepeatApplicationStatus } from "../types/api";
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
    received_at: new Date().toISOString().slice(0, 16),
    expected_start_date: new Date().toISOString().slice(0, 16),
  });
  const current = query.data?.application;
  useEffect(() => {
    if (!current || current.status !== "needs_clarification") return;
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
          <Text size="sm">4 платежа по 25%</Text>
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

      {(!current || current.status === "needs_clarification") && (
        <Card withBorder>
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
              />
              <NumberInput
                label="Целевая зарплата"
                suffix=" ₽"
                min={1}
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
                min={1}
                max={80}
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
              minRows={4}
              required
              value={application.technical_gaps}
              onChange={(event) =>
                setApplication({
                  ...application,
                  technical_gaps: event.currentTarget.value,
                })
              }
            />
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
              disabled={
                !data.eligibility.eligible ||
                application.technical_gaps.trim().length < 10
              }
              loading={
                createApplication.isPending || updateApplication.isPending
              }
              onClick={() => {
                const payload = {
                    ...application,
                    target_salary_kopecks: Math.round(
                      application.target_salary_rubles * 100,
                    ),
                    last_interview_at: null,
                    desired_start_date: null,
                  };
                if (current) {
                  updateApplication.mutate(
                    { id: current.id, payload },
                    { onError: mutationError },
                  );
                } else {
                  createApplication.mutate(payload, { onError: mutationError });
                }
              }}
            >
              {current ? "Сохранить уточнения" : "Сохранить заявку"}
            </Button>
          </Stack>
        </Card>
      )}

      {current && (
        <Card withBorder>
          <Stack>
            <Group justify="space-between">
              <Title order={2}>Ваша заявка</Title>
              <Badge>{statusLabels[current.status]}</Badge>
            </Group>
            <Text>Цель: {current.target_position}</Text>
            {current.admin_comment && (
              <Alert color="blue" title="Комментарий команды">
                {current.admin_comment}
              </Alert>
            )}
            {current.status === "draft" && (
              <Button
                loading={submitApplication.isPending}
                onClick={() =>
                  submitApplication.mutate(current.id, {
                    onError: mutationError,
                  })
                }
              >
                Отправить на рассмотрение
              </Button>
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
                  color="yellow"
                  title={`Условия, версия ${current.terms_version}`}
                >
                  {formatRubles(
                    Number(current.terms_snapshot?.upfront_price_kopecks ?? 0),
                  )}{" "}
                  + {Number(current.terms_snapshot?.success_fee_percent ?? 0)}%
                  от подтверждённой зарплаты, четырьмя платежами.
                </Alert>
                <Checkbox
                  checked={accepted}
                  onChange={(event) => setAccepted(event.currentTarget.checked)}
                  label="Я ознакомился и принимаю условия повторного менторства по Python"
                />
                <Button
                  disabled={!accepted}
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
              <Button
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

      {data.enrollment && data.offers.length === 0 && (
        <Card withBorder>
          <Stack>
            <Title order={2}>Новый оффер</Title>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <TextInput
                label="Компания"
                required
                value={offer.company}
                onChange={(event) =>
                  setOffer({ ...offer, company: event.currentTarget.value })
                }
              />
              <TextInput
                label="Должность"
                required
                value={offer.position}
                onChange={(event) =>
                  setOffer({ ...offer, position: event.currentTarget.value })
                }
              />
              <NumberInput
                label="Фиксированная зарплата на руки"
                suffix=" ₽"
                min={1}
                value={offer.salaryRubles}
                onChange={(value) =>
                  setOffer({ ...offer, salaryRubles: Number(value) || 0 })
                }
              />
              <TextInput
                label="Формат трудоустройства"
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
                value={offer.received_at}
                onChange={(event) =>
                  setOffer({ ...offer, received_at: event.currentTarget.value })
                }
              />
              <TextInput
                type="datetime-local"
                label="Плановая дата выхода"
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
              disabled={!offer.company.trim()}
              loading={createOffer.isPending}
              onClick={() =>
                createOffer.mutate(
                  {
                    position: offer.position,
                    company: offer.company,
                    fixed_monthly_salary_kopecks: Math.round(
                      offer.salaryRubles * 100,
                    ),
                    employment_type: offer.employment_type,
                    received_at: new Date(offer.received_at).toISOString(),
                    expected_start_date: new Date(
                      offer.expected_start_date,
                    ).toISOString(),
                  },
                  { onError: mutationError },
                )
              }
            >
              Сохранить оффер
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
            <Badge>{item.status}</Badge>
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
                  <Badge>{item.status}</Badge>
                  {(item.status === "scheduled" ||
                    item.status === "pending") && (
                    <Button
                      loading={checkoutInstallment.isPending}
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
