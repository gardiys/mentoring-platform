import {
  Badge,
  Button,
  Card,
  Group,
  Pagination,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AdminPaymentsNavigation } from "../components/AdminPaymentsNavigation";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminOverduePayments,
  useConfirmAdminPayment,
} from "../features/payments/queries";
import { formatRubles } from "../utils/money";

const PAGE_SIZE = 50;

export function AdminOverduePaymentsPage() {
  const [page, setPage] = useState(1);
  const query = useAdminOverduePayments(page);
  const confirm = useConfirmAdminPayment();

  if (query.isPending)
    return <LoadingState label="Ищем просроченные платежи…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }
  const data = query.data;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование · финансы"
        title="Просроченные платежи"
        description="Все неоплаченные взносы, срок которых уже наступил. Из списка можно перейти к ученику или подтвердить полученный платёж вручную."
      />
      <AdminPaymentsNavigation active="overdue" />
      <Group align="stretch">
        <Card withBorder style={{ borderColor: "var(--mantine-color-red-6)" }}>
          <Text className="technical-label">Просрочено</Text>
          <Title order={3} c="red">
            {formatRubles(data.overdue_kopecks)}
          </Title>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Платежей</Text>
          <Title order={3}>{data.total}</Title>
        </Card>
      </Group>

      <Card withBorder p={0}>
        <ScrollArea type="auto">
          <Table verticalSpacing="md" horizontalSpacing="lg" miw={1000}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Ученик</Table.Th>
                <Table.Th>Компания</Table.Th>
                <Table.Th>Срок</Table.Th>
                <Table.Th>Сумма</Table.Th>
                <Table.Th>Ментор</Table.Th>
                <Table.Th ta="right">Действия</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((item) => (
                <Table.Tr
                  key={item.installment_id}
                  style={{
                    boxShadow: "inset 0 0 0 2px var(--mantine-color-red-6)",
                  }}
                >
                  <Table.Td>
                    <Text fw={700}>{item.student_name}</Text>
                    {item.student_telegram_username && (
                      <Text size="xs" c="dimmed">
                        @{item.student_telegram_username}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>{item.company_name}</Table.Td>
                  <Table.Td>
                    <Badge color="red" variant="light">
                      {dateLabel(item.due_date)}
                    </Badge>
                  </Table.Td>
                  <Table.Td fw={700} c="red">
                    {formatRubles(item.amount_kopecks)}
                  </Table.Td>
                  <Table.Td>{item.mentor_name ?? "Не назначен"}</Table.Td>
                  <Table.Td ta="right">
                    <Group justify="flex-end" gap="xs" wrap="nowrap">
                      <Button
                        component={Link}
                        to={`/admin/payments/students/${item.student_id}`}
                        size="xs"
                        variant="light"
                      >
                        Открыть ученика
                      </Button>
                      <Button
                        size="xs"
                        loading={
                          confirm.isPending &&
                          confirm.variables === item.installment_id
                        }
                        onClick={() => {
                          if (
                            !window.confirm(
                              "Подтвердить получение платежа вручную?",
                            )
                          )
                            return;
                          confirm.mutate(item.installment_id, {
                            onSuccess: () =>
                              notifications.show({
                                color: "green",
                                message: "Платёж подтверждён",
                              }),
                            onError: (error) =>
                              notifications.show({
                                color: "red",
                                message: error.message,
                              }),
                          });
                        }}
                      >
                        Подтвердить
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        {data.items.length === 0 && (
          <Text c="dimmed" p="xl">
            Просроченных платежей нет.
          </Text>
        )}
      </Card>
      {data.total > PAGE_SIZE && (
        <Pagination
          value={page}
          onChange={setPage}
          total={Math.ceil(data.total / PAGE_SIZE)}
          mx="auto"
        />
      )}
    </Stack>
  );
}

function dateLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU");
}
