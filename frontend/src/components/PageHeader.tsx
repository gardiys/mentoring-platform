import { Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

interface Props {
  eyebrow?: string;
  order?: 1 | 2;
  title: ReactNode;
  description?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, order = 1 }: Props) {
  return (
    <Stack gap="xs" className="page-heading">
      {eyebrow && <Text className="brand-eyebrow">{eyebrow}</Text>}
      <Title order={order}>{title}</Title>
      {description && (
        <Text c="dimmed" size="lg" maw={720}>
          {description}
        </Text>
      )}
    </Stack>
  );
}
