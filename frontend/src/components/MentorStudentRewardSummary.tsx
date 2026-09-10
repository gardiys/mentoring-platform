import { Card, ScrollArea, Table, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";

import type { MentorRewardRead } from "../types/api";
import { formatRubles } from "../utils/money";

type StudentTotal = Pick<
  MentorRewardRead,
  | "student_id"
  | "student_name"
  | "student_telegram_username"
  | "amount_kopecks"
  | "paid_kopecks"
  | "reserved_kopecks"
  | "available_kopecks"
>;

export function MentorStudentRewardSummary({
  rewards,
}: {
  rewards: MentorRewardRead[];
}) {
  const totals = new Map<string, StudentTotal>();
  for (const reward of rewards) {
    const total = totals.get(reward.student_id);
    if (total) {
      total.amount_kopecks += reward.amount_kopecks;
      total.paid_kopecks += reward.paid_kopecks;
      total.reserved_kopecks += reward.reserved_kopecks;
      total.available_kopecks += reward.available_kopecks;
    } else {
      totals.set(reward.student_id, { ...reward });
    }
  }

  return (
    <Card withBorder p={0}>
      <div style={{ padding: "var(--mantine-spacing-lg)" }}>
        <Title order={3}>Сводка по ученикам</Title>
        <Text size="sm" c="dimmed">
          Суммы вознаграждения ментора по всем начислениям каждого ученика.
        </Text>
      </div>
      <ScrollArea type="auto">
        <Table
          aria-label="Сводка по ученикам"
          verticalSpacing="md"
          horizontalSpacing="lg"
          miw={720}
        >
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Ученик</Table.Th>
              <Table.Th>Начислено</Table.Th>
              <Table.Th>Выплачено</Table.Th>
              <Table.Th>В заявках</Table.Th>
              <Table.Th>Можно выплатить</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {Array.from(totals.values()).map((student) => (
              <Table.Tr key={student.student_id}>
                <Table.Td>
                  <Text
                    component={Link}
                    to={`/admin/payments/students/${student.student_id}`}
                    fw={700}
                    c="blue"
                  >
                    {student.student_name}
                  </Text>
                  {student.student_telegram_username && (
                    <Text size="xs" c="dimmed">
                      @{student.student_telegram_username}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>{formatRubles(student.amount_kopecks)}</Table.Td>
                <Table.Td>{formatRubles(student.paid_kopecks)}</Table.Td>
                <Table.Td>{formatRubles(student.reserved_kopecks)}</Table.Td>
                <Table.Td fw={700}>
                  {formatRubles(student.available_kopecks)}
                </Table.Td>
              </Table.Tr>
            ))}
            {totals.size === 0 && (
              <Table.Tr>
                <Table.Td colSpan={5}>
                  <Text c="dimmed">Начислений по ученикам пока нет.</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Card>
  );
}
