import {
  Card,
  SimpleGrid,
  Skeleton,
  Stack,
  VisuallyHidden,
} from "@mantine/core";

export function CardGridSkeleton({
  label = "Загружаем карточки…",
}: {
  label?: string;
}) {
  return (
    <SimpleGrid
      cols={{ base: 1, sm: 2 }}
      role="status"
      aria-label={label}
      className="data-skeleton"
    >
      <VisuallyHidden>{label}</VisuallyHidden>
      {[0, 1, 2, 3].map((i) => (
        <Card key={i} withBorder aria-hidden="true">
          <Stack>
            <Skeleton height={24} width="70%" />
            <Skeleton height={16} />
            <Skeleton height={16} width="85%" />
          </Stack>
        </Card>
      ))}
    </SimpleGrid>
  );
}
