import { Badge } from "@mantine/core";

import type { ProgressStatus } from "../types/api";

const labels: Record<ProgressStatus, string> = {
  not_started: "Не начато",
  in_progress: "В процессе",
  completed: "Завершено",
};

const colors: Record<ProgressStatus, string> = {
  not_started: "brandSand",
  in_progress: "brandBlue",
  completed: "brandGreen",
};

export function TopicStatusBadge({ status }: { status: ProgressStatus }) {
  return (
    <Badge
      color={colors[status]}
      variant={status === "completed" ? "filled" : "light"}
      leftSection={status === "completed" ? "✓" : undefined}
    >
      {labels[status]}
    </Badge>
  );
}
