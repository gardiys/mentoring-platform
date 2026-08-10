import {
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  Progress,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import type { StudentPaymentDashboard } from "../types/api";
import { formatRubles } from "../utils/money";

const statusLabels = {
  scheduled: { label: "Запланирован", color: "gray" },
  pending: { label: "Ожидает оплаты", color: "blue" },
  paid: { label: "Оплачен", color: "green" },
  cancelled: { label: "Отменён", color: "red" },
} as const;

function dateLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU");
}

function isOverdue(dueDate: string, status: string) {
  if (status !== "scheduled" && status !== "pending") return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(`${dueDate}T00:00:00`) < today;
}

interface Props {
  dashboard: StudentPaymentDashboard;
  onSaveDays?: (days: number[]) => Promise<unknown>;
  savingDays?: boolean;
  onPay?: (installmentId: string) => void;
  payingInstallmentId?: string | null;
  onConfirm?: (installmentId: string) => void;
  confirmingInstallmentId?: string | null;
  onRevoke?: (installmentId: string) => void;
  revokingInstallmentId?: string | null;
}

export function PaymentSchedule({
  dashboard,
  onSaveDays,
  savingDays,
  onPay,
  payingInstallmentId,
  onConfirm,
  confirmingInstallmentId,
  onRevoke,
  revokingInstallmentId,
}: Props) {
  const [firstDay, setFirstDay] = useState<number | "">(
    dashboard.employment?.payment_days[0] ?? 10,
  );
  const [secondDay, setSecondDay] = useState<number | "">(
    dashboard.employment?.payment_days[1] ?? 25,
  );

  useEffect(() => {
    setFirstDay(dashboard.employment?.payment_days[0] ?? 10);
    setSecondDay(dashboard.employment?.payment_days[1] ?? 25);
  }, [dashboard.employment?.payment_days]);

  if (!dashboard.employment && dashboard.employment_history.length === 0) {
    return (
      <Card withBorder>
        <Title order={3}>График ещё не создан</Title>
        <Text c="dimmed" mt="xs">
          Ментор или администратор должен зафиксировать трудоустройство,
          зарплату на руки и дату выхода.
        </Text>
      </Card>
    );
  }

  const employment = dashboard.employment;
  const percent =
    Number(dashboard.repayment_percent) > 0
      ? Math.round(
          (Number(dashboard.summary.paid_salary_percent) /
            Number(dashboard.repayment_percent)) *
            100,
        )
      : 0;
  const validDays =
    typeof firstDay === "number" &&
    typeof secondDay === "number" &&
    firstDay !== secondDay &&
    firstDay >= 1 &&
    firstDay <= 28 &&
    secondDay >= 1 &&
    secondDay <= 28;

  return (
    <Stack gap="xl">
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Card withBorder>
          <Text className="technical-label">Обязательство</Text>
          <Title order={3}>
            {formatRubles(dashboard.summary.total_owed_kopecks)}
          </Title>
          <Text size="sm" c="dimmed">
            Выплачено {Number(dashboard.summary.paid_salary_percent)}% из{" "}
            {Number(dashboard.repayment_percent)}%
          </Text>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Оплачено</Text>
          <Title order={3}>
            {formatRubles(dashboard.summary.paid_kopecks)}
          </Title>
          <Text size="sm" c="dimmed">
            {dashboard.summary.paid_installments} из{" "}
            {dashboard.summary.total_installments}
          </Text>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Осталось</Text>
          <Title order={3}>
            {formatRubles(dashboard.summary.remaining_kopecks)}
          </Title>
        </Card>
        <Card
          withBorder
          style={
            dashboard.summary.overdue_kopecks > 0
              ? { borderColor: "var(--mantine-color-red-6)" }
              : undefined
          }
        >
          <Text className="technical-label">Просрочено</Text>
          <Title
            order={3}
            c={dashboard.summary.overdue_kopecks > 0 ? "red" : undefined}
          >
            {formatRubles(dashboard.summary.overdue_kopecks)}
          </Title>
        </Card>
      </SimpleGrid>

      {employment ? (
        <Card withBorder>
          <Stack>
            <Group justify="space-between" align="flex-start">
              <div>
                <Title order={3}>{employment.company_name}</Title>
                <Text c="dimmed" size="sm">
                  Выход {dateLabel(employment.start_date)} · зарплата на руки{" "}
                  {formatRubles(employment.net_salary_kopecks)}
                </Text>
              </div>
              <Badge variant="light">
                Осталось {Number(dashboard.summary.remaining_salary_percent)}%
              </Badge>
            </Group>
            <Progress value={percent} size="lg" radius="xl" />
          </Stack>
        </Card>
      ) : (
        <Card withBorder>
          <Title order={3}>Текущее трудоустройство закрыто</Title>
          <Text c="dimmed" mt="xs">
            Оставшиеся платежи отменены. После нового трудоустройства график
            будет рассчитан на оставшиеся{" "}
            {Number(dashboard.summary.remaining_salary_percent)}%.
          </Text>
        </Card>
      )}

      {dashboard.employment_history.some(
        (item) => item.status === "terminated",
      ) && (
        <Card withBorder>
          <Title order={3} mb="sm">
            История трудоустройств
          </Title>
          <Stack gap="xs">
            {dashboard.employment_history
              .filter((item) => item.status === "terminated")
              .map((item) => (
                <Group key={item.id} justify="space-between" align="flex-start">
                  <div>
                    <Text fw={700}>{item.company_name}</Text>
                    <Text size="sm" c="dimmed">
                      {dateLabel(item.start_date)} —{" "}
                      {item.ended_at ? dateLabel(item.ended_at) : "закрыто"}
                      {item.end_reason ? ` · ${item.end_reason}` : ""}
                    </Text>
                  </div>
                  <Badge color="gray" variant="light">
                    График отменён
                  </Badge>
                </Group>
              ))}
          </Stack>
        </Card>
      )}

      {employment && onSaveDays && dashboard.can_manage_payment_days && (
        <Card withBorder>
          <Stack>
            <div>
              <Title order={3}>Даты ежемесячных платежей</Title>
              <Text c="dimmed" size="sm">
                Нужно выбрать два разных дня с 1-го по 28-е число. Будущие
                неоплаченные взносы будут перенесены автоматически.
              </Text>
            </div>
            <Group align="flex-end">
              <NumberInput
                label="Первый день"
                min={1}
                max={28}
                allowDecimal={false}
                value={firstDay}
                onChange={(value) =>
                  setFirstDay(typeof value === "number" ? value : "")
                }
              />
              <NumberInput
                label="Второй день"
                min={1}
                max={28}
                allowDecimal={false}
                value={secondDay}
                onChange={(value) =>
                  setSecondDay(typeof value === "number" ? value : "")
                }
              />
              <Button
                loading={savingDays}
                disabled={!validDays}
                onClick={() => {
                  if (!validDays) return;
                  void onSaveDays([Number(firstDay), Number(secondDay)]).catch(
                    (error: Error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  );
                }}
              >
                Сохранить даты
              </Button>
            </Group>
          </Stack>
        </Card>
      )}

      <Card withBorder p={0}>
        <ScrollArea type="auto">
          <Table verticalSpacing="md" horizontalSpacing="lg" miw={720}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>№</Table.Th>
                <Table.Th>Дата</Table.Th>
                <Table.Th>Компания</Table.Th>
                <Table.Th>Сумма</Table.Th>
                <Table.Th>Статус</Table.Th>
                <Table.Th ta="right">Действие</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {dashboard.installments.map((installment) => {
                const status = statusLabels[installment.status];
                const overdue = isOverdue(
                  installment.due_date,
                  installment.status,
                );
                return (
                  <Table.Tr
                    key={installment.id}
                    style={
                      overdue
                        ? {
                            boxShadow:
                              "inset 0 0 0 2px var(--mantine-color-red-6)",
                            background: "var(--mantine-color-red-light)",
                          }
                        : undefined
                    }
                  >
                    <Table.Td>{installment.sequence_number}</Table.Td>
                    <Table.Td>{dateLabel(installment.due_date)}</Table.Td>
                    <Table.Td>{installment.company_name}</Table.Td>
                    <Table.Td fw={700}>
                      {formatRubles(installment.amount_kopecks)}
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={overdue ? "red" : status.color}
                        variant="light"
                      >
                        {overdue ? "Просрочен" : status.label}
                      </Badge>
                      {installment.revoked_at &&
                        installment.revocation_reason && (
                          <Text size="xs" c="orange" mt={4}>
                            Подтверждение отменено:{" "}
                            {installment.revocation_reason}
                          </Text>
                        )}
                    </Table.Td>
                    <Table.Td ta="right">
                      {installment.status !== "paid" &&
                        onPay &&
                        installment.can_pay && (
                          <Button
                            size="xs"
                            loading={payingInstallmentId === installment.id}
                            onClick={() => onPay(installment.id)}
                          >
                            Оплатить
                          </Button>
                        )}
                      {(installment.status === "scheduled" ||
                        installment.status === "pending") &&
                        onConfirm && (
                          <Button
                            size="xs"
                            variant="light"
                            loading={confirmingInstallmentId === installment.id}
                            onClick={() => onConfirm(installment.id)}
                          >
                            Подтвердить вручную
                          </Button>
                        )}
                      {installment.status === "paid" && installment.paid_at && (
                        <Stack gap={4} align="flex-end">
                          <Text size="xs" c="dimmed">
                            {new Date(installment.paid_at).toLocaleString(
                              "ru-RU",
                            )}
                          </Text>
                          {onRevoke && (
                            <Button
                              size="compact-xs"
                              color="red"
                              variant="subtle"
                              loading={revokingInstallmentId === installment.id}
                              onClick={() => onRevoke(installment.id)}
                            >
                              Отменить подтверждение
                            </Button>
                          )}
                        </Stack>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Card>
    </Stack>
  );
}
