import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import { useMe } from "../features/auth/queries";
import {
  useConfirmAdminPayment,
  useSetStudentEmployment,
  useStudentPayments,
  useTerminateStudentEmployment,
  useUpdateStudentPaymentDays,
} from "../features/payments/queries";
import { formatRubles } from "../utils/money";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { PaymentSchedule } from "./PaymentSchedule";

export function StudentPaymentsPanel({ studentId }: { studentId: string }) {
  const me = useMe();
  const query = useStudentPayments(studentId);
  const employmentMutation = useSetStudentEmployment(studentId);
  const terminationMutation = useTerminateStudentEmployment(studentId);
  const daysMutation = useUpdateStudentPaymentDays(studentId);
  const confirmMutation = useConfirmAdminPayment();
  const [companyName, setCompanyName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [endedAt, setEndedAt] = useState(new Date().toISOString().slice(0, 10));
  const [endReason, setEndReason] = useState("");

  useEffect(() => {
    if (!query.data?.employment) {
      setCompanyName("");
      setStartDate("");
      setSalary("");
      return;
    }
    setCompanyName(query.data.employment.company_name);
    setStartDate(query.data.employment.start_date);
    setSalary(query.data.employment.net_salary_kopecks / 100);
  }, [query.data?.employment]);

  if (query.isPending)
    return <LoadingState label="Загружаем платежи ученика…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  const dashboard = query.data;
  const isAdmin = me.data?.role === "admin";
  const currentEmploymentHasPaidPayments = Boolean(
    dashboard.employment &&
    dashboard.installments.some(
      (installment) =>
        installment.employment_id === dashboard.employment?.id &&
        installment.status === "paid",
    ),
  );
  const salaryChanged = Boolean(
    dashboard.employment &&
    typeof salary === "number" &&
    Math.round(salary * 100) !== dashboard.employment.net_salary_kopecks,
  );
  const validEmployment =
    companyName.trim().length > 0 &&
    Boolean(startDate) &&
    typeof salary === "number" &&
    salary > 0;

  return (
    <Stack gap="xl">
      <Card withBorder>
        <Stack>
          <div>
            <Title order={3}>
              {dashboard.employment
                ? "Данные трудоустройства"
                : "Зафиксировать трудоустройство"}
            </Title>
            <Text size="sm" c="dimmed">
              Зарплата указывается на руки, после вычета налогов. Процент
              ученика — {Number(dashboard.repayment_percent)}%, осталось к
              выплате {Number(dashboard.summary.remaining_salary_percent)}%.
            </Text>
          </div>
          {dashboard.mentor_reward_percent === null && (
            <Alert color="yellow" title="Доля ментора не настроена">
              Начисление вознаграждения не будет создано при оплате.
              Администратор может указать процент в карточке ученика.
            </Alert>
          )}
          {currentEmploymentHasPaidPayments && (
            <Alert color="blue" title="Можно скорректировать зарплату">
              Компания и дата выхода зафиксированы после первого платежа.
              Укажите фактическую зарплату на руки — уже полученные платежи
              сохранятся, а оставшаяся сумма и будущий график будут пересчитаны.
            </Alert>
          )}
          <Group grow align="flex-start">
            <TextInput
              label="Компания"
              required
              value={companyName}
              disabled={currentEmploymentHasPaidPayments}
              onChange={(event) => setCompanyName(event.currentTarget.value)}
            />
            <TextInput
              label="Дата выхода"
              type="date"
              required
              value={startDate}
              disabled={currentEmploymentHasPaidPayments}
              onChange={(event) => setStartDate(event.currentTarget.value)}
            />
            <NumberInput
              label="Зарплата на руки"
              suffix=" ₽"
              thousandSeparator=" "
              min={1}
              decimalScale={2}
              required
              value={salary}
              onChange={(value) =>
                setSalary(typeof value === "number" ? value : "")
              }
            />
          </Group>
          {typeof salary === "number" && salary > 0 && (
            <Text size="sm" c="dimmed">
              Общая сумма выплат:{" "}
              {formatRubles(
                Math.round(
                  salary * 100 * (Number(dashboard.repayment_percent) / 100),
                ),
              )}
            </Text>
          )}
          <Button
            loading={employmentMutation.isPending}
            disabled={!validEmployment}
            onClick={() => {
              if (!validEmployment || typeof salary !== "number") return;
              if (
                currentEmploymentHasPaidPayments &&
                salaryChanged &&
                !window.confirm(
                  "Скорректировать зарплату? Оплаченные суммы сохранятся, старые платёжные ссылки перестанут учитываться автоматически, а будущие платежи пересчитаются.",
                )
              )
                return;
              employmentMutation.mutate(
                {
                  company_name: companyName.trim(),
                  company_id: dashboard.employment?.company_id ?? null,
                  start_date: startDate,
                  net_salary_rubles: salary,
                },
                {
                  onSuccess: () =>
                    notifications.show({
                      color: "green",
                      message: "Трудоустройство и график платежей сохранены",
                    }),
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                },
              );
            }}
          >
            {currentEmploymentHasPaidPayments && salaryChanged
              ? "Скорректировать зарплату"
              : dashboard.employment
                ? "Обновить данные"
                : "Создать график платежей"}
          </Button>
          {dashboard.employment && (
            <Card withBorder>
              <Stack>
                <div>
                  <Title order={4}>Завершить трудоустройство</Title>
                  <Text size="sm" c="dimmed">
                    Неоплаченные взносы будут отменены. Уже выплаченный процент
                    сохранится и уменьшит график на следующем месте работы.
                  </Text>
                </div>
                <Group grow align="flex-start">
                  <TextInput
                    label="Дата увольнения"
                    type="date"
                    required
                    value={endedAt}
                    onChange={(event) => setEndedAt(event.currentTarget.value)}
                  />
                  <Textarea
                    label="Причина"
                    placeholder="Например, сокращение"
                    value={endReason}
                    onChange={(event) =>
                      setEndReason(event.currentTarget.value)
                    }
                    autosize
                    minRows={1}
                  />
                </Group>
                <Button
                  color="red"
                  variant="light"
                  loading={terminationMutation.isPending}
                  disabled={!endedAt}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "Закрыть трудоустройство и отменить все оставшиеся платежи?",
                      )
                    )
                      return;
                    terminationMutation.mutate(
                      { ended_at: endedAt, reason: endReason.trim() || null },
                      {
                        onSuccess: () =>
                          notifications.show({
                            color: "green",
                            message:
                              "Трудоустройство закрыто, платежи отменены",
                          }),
                        onError: (error) =>
                          notifications.show({
                            color: "red",
                            message: error.message,
                          }),
                      },
                    );
                  }}
                >
                  Уволен — отменить оставшиеся платежи
                </Button>
              </Stack>
            </Card>
          )}
        </Stack>
      </Card>

      <PaymentSchedule
        dashboard={dashboard}
        onSaveDays={
          isAdmin
            ? async (days) => {
                await daysMutation.mutateAsync(days);
                notifications.show({
                  color: "green",
                  message: "Даты обновлены",
                });
              }
            : undefined
        }
        savingDays={daysMutation.isPending}
        confirmingInstallmentId={
          confirmMutation.isPending ? confirmMutation.variables : null
        }
        onConfirm={
          isAdmin
            ? (installmentId) => {
                if (
                  !window.confirm(
                    "Подтвердить получение этого платежа вручную?",
                  )
                ) {
                  return;
                }
                confirmMutation.mutate(installmentId, {
                  onSuccess: () => {
                    void query.refetch();
                    notifications.show({
                      color: "green",
                      message: "Платёж подтверждён",
                    });
                  },
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                });
              }
            : undefined
        }
      />
    </Stack>
  );
}
