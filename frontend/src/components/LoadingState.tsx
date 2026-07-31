import { Center, Loader, Stack, Text } from "@mantine/core";

export function LoadingState({ label = "Загрузка…" }: { label?: string }) {
  return (
    <Center py="xl" role="status">
      <Stack align="center" gap="sm">
        <Loader color="brandBlue" type="dots" />
        <Text c="dimmed" className="technical-label">
          {label}
        </Text>
      </Stack>
    </Center>
  );
}
