import { Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Stack gap="xs" className="empty-state">
      <Text aria-hidden="true" className="empty-state-mark">
        —
      </Text>
      <Title order={3}>{title}</Title>
      {description && (
        <Text c="dimmed" size="sm">
          {description}
        </Text>
      )}
      {action && <div>{action}</div>}
    </Stack>
  );
}
