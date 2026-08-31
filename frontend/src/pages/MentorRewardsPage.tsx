import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  NumberInput,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useRef, useState } from "react";

import { api } from "../api/endpoints";
import type { UploadStatus } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { UploadProgressPanel } from "../components/UploadProgressPanel";
import {
  useCancelMentorPayout,
  useDeleteMentorPayoutReceipt,
  useMentorRewards,
  useRequestMentorPayout,
  useUploadMentorPayoutReceipt,
} from "../features/payments/queries";
import type { MentorPayoutRead } from "../types/api";
import { formatRubles } from "../utils/money";
import { openExternalResource } from "../utils/openExternalResource";

const RECEIPT_MAX_BYTES = 20 * 1024 * 1024;

export function MentorRewardsPage() {
  const query = useMentorRewards();
  const requestPayout = useRequestMentorPayout();
  const cancelPayout = useCancelMentorPayout();
  const uploadReceipt = useUploadMentorPayoutReceipt();
  const deleteReceipt = useDeleteMentorPayoutReceipt();
  const [amount, setAmount] = useState<number | string>("");
  const [receiptFiles, setReceiptFiles] = useState<Record<string, File | null>>(
    {},
  );
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const uploadController = useRef<AbortController | null>(null);

  if (query.isPending) return <LoadingState label="Считаем вознаграждения…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }
  const data = query.data;
  const openRequest = data.payouts.find((item) => item.status === "requested");

  const createRequest = () => {
    const amountRubles = Number(amount);
    if (!Number.isFinite(amountRubles) || amountRubles <= 0) {
      notifications.show({ color: "red", message: "Укажите сумму заявки" });
      return;
    }
    if (amountRubles * 100 > data.available_kopecks) {
      notifications.show({
        color: "red",
        message: "Сумма больше доступного баланса",
      });
      return;
    }
    requestPayout.mutate(amountRubles, {
      onSuccess: () => {
        setAmount("");
        notifications.show({
          color: "green",
          message: "Заявка отправлена администратору",
        });
      },
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const upload = (payout: MentorPayoutRead) => {
    const file = receiptFiles[payout.id];
    if (!file) return;
    if (file.size > RECEIPT_MAX_BYTES) {
      notifications.show({
        color: "red",
        message: "Чек должен быть не больше 20 МБ",
      });
      return;
    }
    const controller = new AbortController();
    uploadController.current = controller;
    setUploadStatus(null);
    uploadReceipt.mutate(
      {
        payoutId: payout.id,
        file,
        options: { signal: controller.signal, onStatus: setUploadStatus },
      },
      {
        onSuccess: () => {
          setReceiptFiles((current) => ({ ...current, [payout.id]: null }));
          setUploadStatus(null);
          notifications.show({ color: "green", message: "Чек загружен" });
        },
        onError: (error) => {
          setUploadStatus(null);
          if (controller.signal.aborted) return;
          notifications.show({ color: "red", message: error.message });
        },
      },
    );
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Финансы"
        title="Мои вознаграждения"
        description="Доступная зарплатная часть рассчитывается только из уже подтверждённых платежей учеников. После выплаты при необходимости приложите чек самозанятого."
      />
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Metric title="Начислено" value={data.accrued_kopecks} />
        <Metric title="Выплачено" value={data.paid_kopecks} />
        <Metric title="В заявке" value={data.reserved_kopecks} />
        <Metric title="Доступно к выплате" value={data.available_kopecks} />
      </SimpleGrid>

      <Card withBorder>
        <Stack gap="md">
          <div>
            <Title order={3}>Запросить выплату</Title>
            <Text size="sm" c="dimmed">
              Заявка резервирует выбранную сумму. Одновременно может быть
              открыта одна заявка.
            </Text>
          </div>
          {openRequest ? (
            <Alert
              color="yellow"
              variant="light"
              title="Заявка ожидает выплаты"
            >
              <Group justify="space-between" align="center">
                <Text fw={700}>{formatRubles(openRequest.amount_kopecks)}</Text>
                <Button
                  size="compact-sm"
                  color="red"
                  variant="subtle"
                  loading={cancelPayout.isPending}
                  onClick={() =>
                    cancelPayout.mutate(openRequest.id, {
                      onSuccess: () =>
                        notifications.show({ message: "Заявка отменена" }),
                      onError: (error) =>
                        notifications.show({
                          color: "red",
                          message: error.message,
                        }),
                    })
                  }
                >
                  Отменить заявку
                </Button>
              </Group>
            </Alert>
          ) : (
            <Group align="flex-end">
              <NumberInput
                label="Сумма, ₽"
                description={`Доступно ${formatRubles(data.available_kopecks)}`}
                min={0.01}
                max={data.available_kopecks / 100}
                decimalScale={2}
                thousandSeparator=" "
                value={amount}
                onChange={setAmount}
                style={{ flex: 1 }}
              />
              <Button
                disabled={data.available_kopecks === 0}
                loading={requestPayout.isPending}
                onClick={createRequest}
              >
                Отправить заявку
              </Button>
            </Group>
          )}
        </Stack>
      </Card>

      <Card withBorder p={0}>
        <div style={{ padding: "var(--mantine-spacing-lg)" }}>
          <Title order={3}>Выплаты и чеки</Title>
          <Text size="sm" c="dimmed">
            Чек необязателен. Если вы работаете как самозанятый, приложите PDF
            или изображение после выплаты.
          </Text>
        </div>
        <ScrollArea type="auto">
          <Table verticalSpacing="md" horizontalSpacing="lg" miw={900}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Дата</Table.Th>
                <Table.Th>Сумма</Table.Th>
                <Table.Th>Статус</Table.Th>
                <Table.Th>Акт / комментарий</Table.Th>
                <Table.Th>Чек</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.payouts.map((payout) => (
                <Table.Tr key={payout.id}>
                  <Table.Td>
                    {formatDate(payout.paid_at ?? payout.created_at)}
                  </Table.Td>
                  <Table.Td fw={700}>
                    {formatRubles(payout.amount_kopecks)}
                  </Table.Td>
                  <Table.Td>
                    <PayoutBadge payout={payout} />
                  </Table.Td>
                  <Table.Td>
                    {payout.payment_reference ??
                      payout.cancellation_reason ??
                      "—"}
                  </Table.Td>
                  <Table.Td>
                    {payout.status !== "paid" ? (
                      <Text size="sm" c="dimmed">
                        После выплаты
                      </Text>
                    ) : payout.receipt_filename ? (
                      <Group gap="xs" wrap="nowrap">
                        <Button
                          size="compact-sm"
                          variant="light"
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
                          Открыть
                        </Button>
                        <Button
                          size="compact-sm"
                          color="red"
                          variant="subtle"
                          loading={
                            deleteReceipt.isPending &&
                            deleteReceipt.variables === payout.id
                          }
                          onClick={() => deleteReceipt.mutate(payout.id)}
                        >
                          Удалить
                        </Button>
                      </Group>
                    ) : (
                      <Stack gap="xs">
                        <Group align="flex-end" wrap="nowrap">
                          <FileInput
                            aria-label="Файл чека"
                            placeholder="PDF или изображение"
                            accept="application/pdf,image/*"
                            value={receiptFiles[payout.id] ?? null}
                            onChange={(file) =>
                              setReceiptFiles((current) => ({
                                ...current,
                                [payout.id]: file,
                              }))
                            }
                            style={{ minWidth: 220 }}
                          />
                          <Button
                            size="compact-sm"
                            disabled={!receiptFiles[payout.id]}
                            loading={
                              uploadReceipt.isPending &&
                              uploadReceipt.variables?.payoutId === payout.id
                            }
                            onClick={() => upload(payout)}
                          >
                            Загрузить
                          </Button>
                        </Group>
                        {uploadReceipt.isPending &&
                          uploadReceipt.variables?.payoutId === payout.id &&
                          uploadStatus && (
                            <UploadProgressPanel
                              status={uploadStatus}
                              onCancel={() => uploadController.current?.abort()}
                            />
                          )}
                      </Stack>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        {data.payouts.length === 0 && (
          <Text c="dimmed" p="lg">
            Выплат пока нет.
          </Text>
        )}
      </Card>

      <Card withBorder>
        <Title order={3} mb="md">
          Из чего сложился баланс
        </Title>
        {data.rewards.length === 0 ? (
          <Text c="dimmed">Подтверждённых начислений пока нет.</Text>
        ) : (
          <ScrollArea type="auto">
            <Table verticalSpacing="md" miw={820}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Ученик</Table.Th>
                  <Table.Th>Основание</Table.Th>
                  <Table.Th>Начислено</Table.Th>
                  <Table.Th>Выплачено</Table.Th>
                  <Table.Th>Доступно</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.rewards.map((item) => (
                  <Table.Tr key={item.id}>
                    <Table.Td>{item.student_name}</Table.Td>
                    <Table.Td>
                      {rewardTitle(item.kind, item.company_name)}
                    </Table.Td>
                    <Table.Td>{formatRubles(item.amount_kopecks)}</Table.Td>
                    <Table.Td>{formatRubles(item.paid_kopecks)}</Table.Td>
                    <Table.Td>{formatRubles(item.available_kopecks)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Card>
    </Stack>
  );
}

function PayoutBadge({ payout }: { payout: MentorPayoutRead }) {
  const value =
    payout.status === "requested"
      ? { label: "Запрошена", color: "yellow" }
      : payout.status === "paid"
        ? { label: "Выплачена", color: "green" }
        : { label: "Отменена", color: "gray" };
  return (
    <Badge color={value.color} variant="light">
      {value.label}
    </Badge>
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

function rewardTitle(kind: string, company: string | null) {
  if (kind === "entry_payment") return "Вступительный платёж";
  if (kind === "program_exclusion") return "Исключение из программы";
  if (kind === "legacy_fixed") return "Архив: вступление / исключение";
  if (kind === "consultation") return "Консультация выпускника";
  return `Платёж после трудоустройства${company ? ` · ${company}` : ""}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU");
}
