import { Alert, Badge, ScrollArea, Stack, Table, Text } from "@mantine/core";
import { Link } from "react-router-dom";

import type {
  MentorPayoutAllocationRead,
  MentorPayoutRead,
} from "../types/api";
import { formatRubles } from "../utils/money";

export function MentorPayoutBreakdown({
  payout,
}: {
  payout: MentorPayoutRead;
}) {
  if (payout.allocations.length === 0) {
    return (
      <Alert color="gray" variant="light" mt="md">
        Для этой архивной выплаты детализация по начислениям не сохранилась.
      </Alert>
    );
  }

  return (
    <Stack gap="xs" mt="md">
      <div>
        <Text fw={700}>Состав запроса</Text>
        <Text size="sm" c="dimmed">
          Конкретные начисления, которые ментор включил в эту сумму.
        </Text>
      </div>
      <ScrollArea type="auto">
        <Table
          withTableBorder
          withColumnBorders
          verticalSpacing="sm"
          horizontalSpacing="md"
          miw={820}
        >
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Ученик</Table.Th>
              <Table.Th>За что начислено</Table.Th>
              <Table.Th>База расчёта</Table.Th>
              <Table.Th>Всего начислено</Table.Th>
              <Table.Th>В этом запросе</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {payout.allocations.map((allocation) => (
              <Table.Tr key={allocation.reward_id}>
                <Table.Td>
                  <Text
                    component={Link}
                    to={`/admin/payments/students/${allocation.student_id}`}
                    fw={700}
                    c="blue"
                  >
                    {allocation.student_name}
                  </Text>
                  {allocation.student_telegram_username && (
                    <Text size="xs" c="dimmed">
                      @{allocation.student_telegram_username}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>{allocationSource(allocation)}</Table.Td>
                <Table.Td>
                  <Stack gap={2}>
                    <Text size="sm">
                      {allocation.basis_kopecks === null
                        ? "—"
                        : formatRubles(allocation.basis_kopecks)}
                    </Text>
                    {allocation.reward_percent !== null && (
                      <Text size="xs" c="dimmed">
                        Ставка ментора: {Number(allocation.reward_percent)}%
                      </Text>
                    )}
                  </Stack>
                </Table.Td>
                <Table.Td>
                  {formatRubles(allocation.reward_amount_kopecks)}
                </Table.Td>
                <Table.Td>
                  <Badge color="blue" variant="light" size="lg">
                    {formatRubles(allocation.amount_kopecks)}
                  </Badge>
                  {allocation.amount_kopecks <
                    allocation.reward_amount_kopecks && (
                    <Text size="xs" c="dimmed" mt={4}>
                      Частично
                    </Text>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Th colSpan={4}>Итого к выплате по запросу</Table.Th>
              <Table.Th>{formatRubles(payout.amount_kopecks)}</Table.Th>
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </ScrollArea>
    </Stack>
  );
}

function allocationSource(allocation: MentorPayoutAllocationRead) {
  if (allocation.kind === "entry_payment") return "За вступление ученика";
  if (allocation.kind === "program_exclusion") return "За исключение ученика";
  if (allocation.kind === "legacy_fixed") return "Архивное начисление";
  if (allocation.kind === "consultation") return "Проведённая консультация";
  if (allocation.kind === "python_repeat_fixed") {
    return "Повторное менторство · фиксированная часть";
  }
  if (allocation.kind === "python_repeat_success_fee") {
    return "Повторное менторство · выплата после трудоустройства";
  }
  return allocation.company_name
    ? `Платёж ученика после трудоустройства · ${allocation.company_name}`
    : "Платёж ученика после трудоустройства";
}
