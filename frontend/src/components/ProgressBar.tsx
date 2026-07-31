import { Group, Progress, Stack, Text } from "@mantine/core";

interface Props {
  completed: number;
  total: number;
  percent: number;
}

export function ProgressBar({ completed, total, percent }: Props) {
  return (
    <Stack gap={6} className="brand-progress">
      <Group justify="space-between">
        <Text size="sm" c="dimmed" fw={500}>
          {completed} из {total} тем
        </Text>
        <Text className="progress-percent">{percent}%</Text>
      </Group>
      <Progress
        value={percent}
        color="brandBlue"
        size={9}
        aria-label={`Прогресс ${percent}%`}
      />
    </Stack>
  );
}
