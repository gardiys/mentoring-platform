import { Center, Loader, Stack, Text } from "@mantine/core";

export function LoadingState({ label = "Загрузка…" }: { label?: string }) {
  return (
    <Center className="loading-state" py="xl" role="status" aria-label={label}>
      <Stack
        align="center"
        gap="sm"
        className="loading-state-indicator"
        aria-hidden="true"
      >
        <Loader size="sm" />
        <Text c="dimmed" size="sm">
          {label}
        </Text>
      </Stack>
    </Center>
  );
}
