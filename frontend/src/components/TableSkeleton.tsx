import { Skeleton, Stack, Group, VisuallyHidden } from "@mantine/core";

export function TableSkeleton({
  label = "Загружаем список…",
  rows = 5,
}: {
  label?: string;
  rows?: number;
}) {
  return (
    <Stack gap="md" role="status" aria-label={label} className="data-skeleton">
      <VisuallyHidden>{label}</VisuallyHidden>
      {Array.from({ length: rows }, (_, i) => (
        <Group key={i} grow aria-hidden="true">
          <Skeleton height={32} />
          <Skeleton height={32} />
          <Skeleton height={32} />
        </Group>
      ))}
    </Stack>
  );
}
