import {
  Badge,
  Button,
  Card,
  Pagination,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AdminPaymentsNavigation } from "../components/AdminPaymentsNavigation";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminPaymentStudents } from "../features/payments/queries";
import { formatRubles } from "../utils/money";

const PAGE_SIZE = 50;

export function AdminPaymentsPage() {
  const [page, setPage] = useState(1);
  const query = useAdminPaymentStudents(page);

  if (query.isPending)
    return <LoadingState label="Загружаем учеников с офферами…" />;
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
        title="Ученики с офферами"
        description="Активные трудоустройства, по которым ученикам ещё нужно выполнить обязательства перед платформой."
      />
      <AdminPaymentsNavigation active="students" />

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Metric title="Учеников платят" value={String(data.total)} />
        <Metric
          title="Осталось получить"
          value={formatRubles(data.total_remaining_kopecks)}
        />
        <Metric
          title="Уже получено"
          value={formatRubles(data.total_paid_kopecks)}
        />
        <Metric
          title="Просрочено"
          value={formatRubles(data.total_overdue_kopecks)}
          danger={data.total_overdue_kopecks > 0}
        />
      </SimpleGrid>

      <Card withBorder p={0}>
        <ScrollArea type="auto">
          <Table verticalSpacing="md" horizontalSpacing="lg" miw={1220}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Ученик</Table.Th>
                <Table.Th>Трудоустройство</Table.Th>
                <Table.Th>Зарплата</Table.Th>
                <Table.Th>Выплачено</Table.Th>
                <Table.Th>Осталось</Table.Th>
                <Table.Th>Просрочено</Table.Th>
                <Table.Th>Следующий платёж</Table.Th>
                <Table.Th>Ментор</Table.Th>
                <Table.Th ta="right">Действие</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((item) => {
                const overdue = item.overdue_kopecks > 0;
                return (
                  <Table.Tr
                    key={item.student_id}
                    style={
                      overdue
                        ? {
                            boxShadow:
                              "inset 0 0 0 2px var(--mantine-color-red-6)",
                          }
                        : undefined
                    }
                  >
                    <Table.Td>
                      <Text fw={700}>{item.student_name}</Text>
                      {item.student_telegram_username && (
                        <Text size="xs" c="dimmed">
                          @{item.student_telegram_username}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text fw={700}>{item.company_name}</Text>
                      <Text size="xs" c="dimmed">
                        С {dateLabel(item.employment_start_date)} · к выплате{" "}
                        {Number(item.repayment_percent)}%
                      </Text>
                    </Table.Td>
                    <Table.Td>{formatRubles(item.net_salary_kopecks)}</Table.Td>
                    <Table.Td>
                      <Text fw={700}>{formatRubles(item.paid_kopecks)}</Text>
                      <Text size="xs" c="dimmed">
                        {item.paid_installments} из {item.total_installments}
                      </Text>
                    </Table.Td>
                    <Table.Td fw={700}>
                      {formatRubles(item.remaining_kopecks)}
                    </Table.Td>
                    <Table.Td>
                      {overdue ? (
                        <Badge color="red" variant="light">
                          {item.overdue_payments} ·{" "}
                          {formatRubles(item.overdue_kopecks)}
                        </Badge>
                      ) : (
                        <Badge color="green" variant="light">
                          Нет
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {item.next_payment_date
                        ? dateLabel(item.next_payment_date)
                        : "—"}
                    </Table.Td>
                    <Table.Td>{item.mentor_name ?? "Не назначен"}</Table.Td>
                    <Table.Td ta="right">
                      <Button
                        component={Link}
                        to={`/admin/payments/students/${item.student_id}`}
                        size="xs"
                        variant="light"
                      >
                        Открыть платежи
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        {data.items.length === 0 && (
          <Text c="dimmed" p="xl">
            Нет активных трудоустройств с непогашенными обязательствами.
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

function Metric({
  title,
  value,
  danger = false,
}: {
  title: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <Card
      withBorder
      style={danger ? { borderColor: "var(--mantine-color-red-6)" } : undefined}
    >
      <Text className="technical-label">{title}</Text>
      <Title order={3} c={danger ? "red" : undefined}>
        {value}
      </Title>
    </Card>
  );
}

function dateLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("ru-RU");
}
