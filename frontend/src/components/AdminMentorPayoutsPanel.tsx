import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/endpoints";
import {
  useAdminMentorPayouts,
  useCancelAdminMentorPayout,
  useCreateAdminMentorPayout,
  useMarkAdminMentorPayoutPaid,
} from "../features/payments/queries";
import type {
  AdminMentorPayoutBalanceRead,
  MentorPayoutRead,
} from "../types/api";
import { formatRubles } from "../utils/money";
import { openExternalResource } from "../utils/openExternalResource";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { AdminMentorPayoutActions } from "./AdminMentorPayoutActions";

const payoutStatus = {
  requested: { label: "Запрошена", color: "yellow" },
  paid: { label: "Выплачена", color: "green" },
  cancelled: { label: "Отменена", color: "gray" },
} as const;

export function AdminMentorPayoutsPanel() {
  const query = useAdminMentorPayouts();
  const createPayout = useCreateAdminMentorPayout();
  const markPaid = useMarkAdminMentorPayoutPaid();
  const cancelPayout = useCancelAdminMentorPayout();
  const [amounts, setAmounts] = useState<Record<string, number | string>>({});
  const [references, setReferences] = useState<Record<string, string>>({});

  if (query.isPending) return <LoadingState label="Считаем баланс менторов…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  const pending = query.data.payouts.filter(
    (item) => item.status === "requested",
  );
  const history = query.data.payouts.filter(
    (item) => item.status !== "requested",
  );

  const pay = (balance: AdminMentorPayoutBalanceRead, all: boolean) => {
    const amountRubles = all
      ? balance.available_kopecks / 100
      : Number(amounts[balance.mentor_id]);
    if (!Number.isFinite(amountRubles) || amountRubles <= 0) {
      notifications.show({ color: "red", message: "Укажите сумму выплаты" });
      return;
    }
    if (amountRubles * 100 > balance.available_kopecks) {
      notifications.show({
        color: "red",
        message: "Сумма больше доступного баланса",
      });
      return;
    }
    if (
      !window.confirm(
        `Подтвердить выплату ${formatRubles(amountRubles * 100)}?`,
      )
    ) {
      return;
    }
    createPayout.mutate(
      {
        mentorId: balance.mentor_id,
        amountRubles,
        paymentReference: references[balance.mentor_id]?.trim() || null,
      },
      {
        onSuccess: () => {
          setAmounts((current) => ({ ...current, [balance.mentor_id]: "" }));
          notifications.show({
            color: "green",
            message: "Выплата зафиксирована",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <div>
        <Title order={2}>Выплаты менторам</Title>
        <Text c="dimmed" mt={4}>
          Зарплатная часть начисляется только с подтверждённых платежей
          учеников. Заявки менторов резервируют сумму, поэтому её нельзя
          выплатить повторно.
        </Text>
      </div>

      {pending.length > 0 && (
        <Stack gap="md">
          <Title order={3}>Запросы на выплату</Title>
          <Alert color="blue" variant="light">
            Укажите номер акта или комментарий и подтвердите выплату одной
            кнопкой.
          </Alert>
          {pending.map((payout) => (
            <PendingPayoutCard
              key={payout.id}
              payout={payout}
              reference={references[payout.id] ?? ""}
              onReferenceChange={(value) =>
                setReferences((current) => ({ ...current, [payout.id]: value }))
              }
              paying={
                markPaid.isPending && markPaid.variables?.payoutId === payout.id
              }
              cancelling={
                cancelPayout.isPending &&
                cancelPayout.variables?.payoutId === payout.id
              }
              onPay={() =>
                markPaid.mutate(
                  {
                    payoutId: payout.id,
                    paymentReference: references[payout.id]?.trim() || null,
                  },
                  {
                    onSuccess: () =>
                      notifications.show({
                        color: "green",
                        message: "Заявка отмечена выплаченной",
                      }),
                    onError: (error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  },
                )
              }
              onCancel={() => {
                if (
                  !window.confirm(
                    "Отклонить заявку и освободить зарезервированную сумму?",
                  )
                ) {
                  return;
                }
                cancelPayout.mutate(
                  { payoutId: payout.id },
                  {
                    onSuccess: () =>
                      notifications.show({ message: "Заявка отменена" }),
                    onError: (error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  },
                );
              }}
            />
          ))}
        </Stack>
      )}

      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        {query.data.balances.map((balance) => (
          <Card withBorder key={balance.mentor_id}>
            <Stack gap="md">
              <div>
                <Title order={3}>{balance.mentor_name}</Title>
                {balance.mentor_telegram_username && (
                  <Text size="sm" c="dimmed">
                    @{balance.mentor_telegram_username}
                  </Text>
                )}
              </div>
              <SimpleGrid cols={2}>
                <BalanceMetric
                  title="Доступно"
                  value={balance.available_kopecks}
                />
                <BalanceMetric
                  title="Зарезервировано"
                  value={balance.reserved_kopecks}
                />
                <BalanceMetric
                  title="Всего начислено"
                  value={balance.accrued_kopecks}
                />
                <BalanceMetric
                  title="Уже выплачено"
                  value={balance.paid_kopecks}
                />
              </SimpleGrid>
              <NumberInput
                label="Сумма частичной выплаты, ₽"
                min={0.01}
                max={balance.available_kopecks / 100}
                decimalScale={2}
                thousandSeparator=" "
                value={amounts[balance.mentor_id] ?? ""}
                onChange={(value) =>
                  setAmounts((current) => ({
                    ...current,
                    [balance.mentor_id]: value,
                  }))
                }
                disabled={balance.available_kopecks === 0}
              />
              <TextInput
                label="Номер акта / комментарий"
                placeholder="Необязательно"
                value={references[balance.mentor_id] ?? ""}
                onChange={(event) =>
                  setReferences((current) => ({
                    ...current,
                    [balance.mentor_id]: event.currentTarget.value,
                  }))
                }
              />
              <Group>
                <Button
                  disabled={balance.available_kopecks === 0}
                  loading={
                    createPayout.isPending &&
                    createPayout.variables?.mentorId === balance.mentor_id
                  }
                  onClick={() => pay(balance, false)}
                >
                  Выплатить сумму
                </Button>
                <Button
                  variant="light"
                  disabled={balance.available_kopecks === 0}
                  loading={
                    createPayout.isPending &&
                    createPayout.variables?.mentorId === balance.mentor_id
                  }
                  onClick={() => pay(balance, true)}
                >
                  Выплатить всё
                </Button>
                <Button
                  component={Link}
                  to={`/admin/payments/mentors/${balance.mentor_id}`}
                  variant="subtle"
                >
                  Открыть детализацию
                </Button>
              </Group>
            </Stack>
          </Card>
        ))}
      </SimpleGrid>
      {query.data.balances.length === 0 && (
        <Card withBorder>
          <Text c="dimmed">Начислений менторам пока нет.</Text>
        </Card>
      )}

      <Card withBorder p={0}>
        <div style={{ padding: "var(--mantine-spacing-lg)" }}>
          <Title order={3}>История выплат</Title>
          <Text size="sm" c="dimmed">
            Чеки самозанятых появятся здесь после загрузки ментором.
          </Text>
        </div>
        <ScrollArea type="auto">
          <Table miw={1080} verticalSpacing="md" horizontalSpacing="lg">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Ментор</Table.Th>
                <Table.Th>Сумма</Table.Th>
                <Table.Th>Дата</Table.Th>
                <Table.Th>Источник</Table.Th>
                <Table.Th>Статус</Table.Th>
                <Table.Th>Акт / комментарий</Table.Th>
                <Table.Th>Чек</Table.Th>
                <Table.Th>Действия</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {history.map((payout) => {
                const status = payoutStatus[payout.status];
                return (
                  <Table.Tr key={payout.id}>
                    <Table.Td>{payout.mentor_name}</Table.Td>
                    <Table.Td fw={700}>
                      {formatRubles(payout.amount_kopecks)}
                    </Table.Td>
                    <Table.Td>
                      {formatDate(
                        payout.status === "cancelled"
                          ? payout.cancelled_at
                          : payout.paid_at,
                      )}
                    </Table.Td>
                    <Table.Td>
                      {payout.origin === "mentor_request"
                        ? "Заявка ментора"
                        : "Администратор"}
                    </Table.Td>
                    <Table.Td>
                      <Badge color={status.color} variant="light">
                        {status.label}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <Text size="sm">
                          {payout.status === "cancelled"
                            ? (payout.cancellation_reason ?? "—")
                            : (payout.payment_reference ?? "—")}
                        </Text>
                        {payout.edited_at && (
                          <Text size="xs" c="dimmed">
                            Изменено: {payout.edit_reason}
                          </Text>
                        )}
                      </Stack>
                    </Table.Td>
                    <Table.Td>
                      {payout.receipt_filename ? (
                        <Button
                          size="compact-sm"
                          variant="subtle"
                          onClick={() =>
                            void openExternalResource(
                              api.openMentorPayoutReceipt(payout.id),
                            ).catch((error: Error) =>
                              notifications.show({
                                color: "red",
                                message: error.message,
                              }),
                            )
                          }
                        >
                          Открыть чек
                        </Button>
                      ) : (
                        <Text size="sm" c="dimmed">
                          Не загружен
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <AdminMentorPayoutActions payout={payout} />
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        {history.length === 0 && (
          <Text c="dimmed" p="lg">
            Выплат пока нет.
          </Text>
        )}
      </Card>
    </Stack>
  );
}

function PendingPayoutCard({
  payout,
  reference,
  paying,
  cancelling,
  onReferenceChange,
  onPay,
  onCancel,
}: {
  payout: MentorPayoutRead;
  reference: string;
  paying: boolean;
  cancelling: boolean;
  onReferenceChange: (value: string) => void;
  onPay: () => void;
  onCancel: () => void;
}) {
  return (
    <Card withBorder>
      <Group justify="space-between" align="flex-start">
        <div>
          <Text fw={700}>{payout.mentor_name}</Text>
          <Title order={3}>{formatRubles(payout.amount_kopecks)}</Title>
          <Text size="sm" c="dimmed">
            Запрошено {formatDate(payout.created_at)}
          </Text>
        </div>
        <Badge color="yellow" variant="light">
          Ожидает выплаты
        </Badge>
      </Group>
      <TextInput
        mt="md"
        label="Номер акта / комментарий"
        placeholder="Например: Акт №12 от 10.08.2026"
        value={reference}
        onChange={(event) => onReferenceChange(event.currentTarget.value)}
      />
      <Group mt="md">
        <Button loading={paying} onClick={onPay}>
          Выплатить и подтвердить
        </Button>
        <Button
          color="red"
          variant="subtle"
          loading={cancelling}
          onClick={onCancel}
        >
          Отклонить
        </Button>
      </Group>
    </Card>
  );
}

function BalanceMetric({ title, value }: { title: string; value: number }) {
  return (
    <div>
      <Text size="xs" c="dimmed">
        {title}
      </Text>
      <Text fw={700}>{formatRubles(value)}</Text>
    </div>
  );
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}
