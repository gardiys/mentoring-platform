import { Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

interface Props {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
}

export function PageHeader({ eyebrow, title, description }: Props) {
  return (
    <Stack gap="xs" className="page-heading">
      <Text className="brand-eyebrow">{eyebrow}</Text>
      <Title order={1}>{title}</Title>
      {description && (
        <Text c="dimmed" size="lg" maw={720}>
          {description}
        </Text>
      )}
    </Stack>
  );
}
