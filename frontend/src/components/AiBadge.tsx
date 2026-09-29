import { Badge } from "@mantine/core";

export function AiBadge({ label = "Сгенерировано AI" }: { label?: string }) {
  return (
    <Badge color="brandAi" variant="light">
      {label}
    </Badge>
  );
}
