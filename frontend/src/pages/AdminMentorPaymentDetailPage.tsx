import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AdminPaymentsNavigation } from "../components/AdminPaymentsNavigation";
import { AdminMentorPayoutActions } from "../components/AdminMentorPayoutActions";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminMentorPayoutDetail,
  useCreateAdminMentorPayout,
  useVoidAdminMentorReward,
} from "../features/payments/queries";
import type { MentorRewardRead } from "../types/api";
import { formatRubles } from "../utils/money";

export function AdminMentorPaymentDetailPage() {
  const { mentorId = "" } = useParams();
  const query = useAdminMentorPayoutDetail(mentorId);
  const createPayout = useCreateAdminMentorPayout();
  const voidReward = useVoidAdminMentorReward();
  const [amount, setAmount] = useState<number | string>("");
  const [reference, setReference] = useState("");
  const [rewardToVoid, setRewardToVoid] = useState<MentorRewardRead | null>(
    null,
  );
  const [voidReason, setVoidReason] = useState("");

  if (query.isPending) return <LoadingState label="Считаем выплаты ментора…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }
  const data = query.data;
  const openRequest = data.payouts.find((item) => item.status === "requested");

  const pay = (payAll: boolean) => {
    const amountRubles = payAll ? data.available_kopecks / 100 : Number(amount);
    if (!Number.isFinite(amountRubles) || amountRubles <= 0) {
      notifications.show({ color: "red", message: "Укажите сумму выплаты" });
      return;
    }
    if (amountRubles * 100 > data.available_kopecks) {
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
        mentorId,
        amountRubles,
        paymentReference: reference.trim() || null,
      },
      {
        onSuccess: () => {
          setAmount("");
          setReference("");
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
      <PageHeader
        eyebrow="Финансы · ментор"
        title={data.mentor_name}
        description={
          data.mentor_telegram_username
            ? `@${data.mentor_telegram_username} · подробный состав начислений и выплат`
            : "Подробный состав начислений и выплат"
        }
      />
      <AdminPaymentsNavigation active="mentors" />
      <Button
        component={Link}
        to="/admin/payments/mentors"
        variant="subtle"
        w="fit-content"
      >
        ← Ко всем менторам
      </Button>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Metric title="Начислено" value={data.accrued_kopecks} />
        <Metric title="Выплачено" value={data.paid_kopecks} />
        <Metric title="В заявках" value={data.reserved_kopecks} />
        <Metric title="Можно выплатить" value={data.available_kopecks} />
      </SimpleGrid>

      {openRequest && (
        <Alert color="yellow" variant="light" title="Есть запрос на выплату">
          Ментор запросил {formatRubles(openRequest.amount_kopecks)}. Эта сумма
          уже зарезервирована и не входит в доступный баланс.
        </Alert>
      )}

      <Card withBorder>
        <Stack gap="md">
          <div>
            <Title order={3}>Зафиксировать выплату</Title>
            <Text size="sm" c="dimmed">
              В доступный баланс попадает только доля от уже подтверждённых
              платежей учеников. Можно выплатить весь баланс или его часть.
            </Text>
          </div>
          <NumberInput
            label="Сумма, ₽"
            min={0.01}
            max={data.available_kopecks / 100}
            decimalScale={2}
            thousandSeparator=" "
            value={amount}
            onChange={setAmount}
            disabled={data.available_kopecks === 0}
          />
          <TextInput
            label="Номер акта / комментарий"
            value={reference}
            onChange={(event) => setReference(event.currentTarget.value)}
          />
          <Group>
            <Button
              disabled={data.available_kopecks === 0}
              loading={createPayout.isPending}
              onClick={() => pay(false)}
            >
              Выплатить сумму
            </Button>
            <Button
              variant="light"
              disabled={data.available_kopecks === 0}
              loading={createPayout.isPending}
              onClick={() => pay(true)}
            >
              Выплатить всё
            </Button>
          </Group>
        </Stack>
      </Card>

      <Card withBorder p={0}>
        <div style={{ padding: "var(--mantine-spacing-lg)" }}>
          <Title order={3}>Из чего сложилась сумма</Title>
          <Text size="sm" c="dimmed">
            Зарплатное вознаграждение появляется только после платежа ученика.
            Например, платёж 25% при ставках ученика 200% и ментора 60% даёт
            ментору 7,5% зарплаты.
          </Text>
        </div>
        <ScrollArea type="auto">
          <Table verticalSpacing="md" horizontalSpacing="lg" miw={1320}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Дата</Table.Th>
                <Table.Th>Ученик</Table.Th>
                <Table.Th>Источник</Table.Th>
                <Table.Th>База расчёта</Table.Th>
                <Table.Th>Доля ментора</Table.Th>
                <Table.Th>Начислено</Table.Th>
                <Table.Th>Выплачено</Table.Th>
                <Table.Th>Доступно</Table.Th>
                <Table.Th>Действия</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.rewards.map((reward) => (
                <Table.Tr key={reward.id}>
                  <Table.Td>{dateTimeLabel(reward.created_at)}</Table.Td>
                  <Table.Td>
                    <Text
                      component={Link}
                      to={`/admin/payments/students/${reward.student_id}`}
                      fw={700}
                      c="blue"
                    >
                      {reward.student_name}
                    </Text>
                    {reward.student_telegram_username && (
                      <Text size="xs" c="dimmed">
                        @{reward.student_telegram_username}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>{rewardSource(reward)}</Table.Td>
                  <Table.Td>
                    {reward.basis_kopecks === null
                      ? "—"
                      : formatRubles(reward.basis_kopecks)}
                  </Table.Td>
                  <Table.Td>
                    {reward.reward_percent === null
                      ? "—"
                      : `${Number(reward.reward_percent)}%`}
                  </Table.Td>
                  <Table.Td fw={700}>
                    {formatRubles(reward.amount_kopecks)}
                  </Table.Td>
                  <Table.Td>{formatRubles(reward.paid_kopecks)}</Table.Td>
                  <Table.Td>
                    <Badge
                      color={reward.available_kopecks > 0 ? "blue" : "green"}
                      variant="light"
                    >
                      {formatRubles(reward.available_kopecks)}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {reward.paid_kopecks > 0 ? (
                      <Text size="xs" c="dimmed">
                        Сначала отмените связанную выплату
                      </Text>
                    ) : reward.reserved_kopecks > 0 ? (
                      <Text size="xs" c="dimmed">
                        Сначала отмените заявку ментора
                      </Text>
                    ) : (
                      <Button
                        size="compact-sm"
                        color="red"
                        variant="subtle"
                        onClick={() => {
                          setVoidReason("");
                          setRewardToVoid(reward);
                        }}
                      >
                        Удалить ошибочное
                      </Button>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Card>

      <Modal
        opened={rewardToVoid !== null}
        onClose={() => {
          if (voidReward.isPending) return;
          setRewardToVoid(null);
          setVoidReason("");
        }}
        title="Удалить ошибочное начисление"
        centered
      >
        <Stack>
          <Alert color="red" variant="light">
            {rewardToVoid
              ? `${formatRubles(rewardToVoid.amount_kopecks)} по ученику «${rewardToVoid.student_name}» исчезнут из баланса и списка ментора. Запись сохранится только в аудите.`
              : null}
          </Alert>
          <Textarea
            label="Причина удаления"
            description="Например: уже рассчитались с ментором по архивным данным. Минимум 3 символа."
            minRows={3}
            maxLength={500}
            value={voidReason}
            onChange={(event) => setVoidReason(event.currentTarget.value)}
            required
          />
          <Group justify="flex-end">
            <Button
              variant="subtle"
              disabled={voidReward.isPending}
              onClick={() => {
                setRewardToVoid(null);
                setVoidReason("");
              }}
            >
              Не удалять
            </Button>
            <Button
              color="red"
              loading={voidReward.isPending}
              disabled={voidReason.trim().length < 3}
              onClick={() => {
                if (!rewardToVoid) return;
                voidReward.mutate(
                  {
                    rewardId: rewardToVoid.id,
                    reason: voidReason.trim(),
                  },
                  {
                    onSuccess: () => {
                      setRewardToVoid(null);
                      setVoidReason("");
                      notifications.show({
                        color: "green",
                        message:
                          "Ошибочное начисление удалено из баланса ментора",
                      });
                    },
                    onError: (error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  },
                );
              }}
            >
              Удалить начисление
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Card withBorder p={0}>
        <div style={{ padding: "var(--mantine-spacing-lg)" }}>
          <Title order={3}>История выплат ментору</Title>
        </div>
        <ScrollArea type="auto">
          <Table verticalSpacing="md" horizontalSpacing="lg" miw={1040}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Дата</Table.Th>
                <Table.Th>Сумма</Table.Th>
                <Table.Th>Статус</Table.Th>
                <Table.Th>Источник</Table.Th>
                <Table.Th>Акт / комментарий</Table.Th>
                <Table.Th>Действия</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.payouts.map((payout) => (
                <Table.Tr key={payout.id}>
                  <Table.Td>
                    {dateTimeLabel(
                      payout.status === "cancelled"
                        ? (payout.cancelled_at ?? payout.created_at)
                        : (payout.paid_at ?? payout.created_at),
                    )}
                  </Table.Td>
                  <Table.Td fw={700}>
                    {formatRubles(payout.amount_kopecks)}
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      color={
                        payout.status === "paid"
                          ? "green"
                          : payout.status === "requested"
                            ? "yellow"
                            : "gray"
                      }
                      variant="light"
                    >
                      {payout.status === "paid"
                        ? "Выплачена"
                        : payout.status === "requested"
                          ? "Запрошена"
                          : "Отменена"}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {payout.origin === "mentor_request"
                      ? "Заявка ментора"
                      : "Администратор"}
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
                    <AdminMentorPayoutActions payout={payout} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Card>
    </Stack>
  );
}

function Metric({ title, value }: { title: string; value: number }) {
  return (
    <Card withBorder>
      <Text className="technical-label">{title}</Text>
      <Title order={3}>{formatRubles(value)}</Title>
    </Card>
  );
}

function rewardSource(reward: MentorRewardRead) {
  if (reward.kind === "entry_payment") return "Вступительный платёж";
  if (reward.kind === "program_exclusion") return "Исключение из программы";
  if (reward.kind === "legacy_fixed") return "Архив: вступление / исключение";
  return reward.company_name
    ? `Платёж после трудоустройства · ${reward.company_name}`
    : "Платёж после трудоустройства";
}

function dateTimeLabel(value: string) {
  return new Date(value).toLocaleDateString("ru-RU");
}
