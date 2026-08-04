import { Button, Group, Progress, Stack, Text } from "@mantine/core";

import type { UploadStatus } from "../api/client";

interface Props {
  status: UploadStatus;
  detail?: string;
  onCancel?: () => void;
}

function formatSpeed(bytesPerSecond: number) {
  if (bytesPerSecond >= 1024 * 1024) {
    return `${(bytesPerSecond / 1024 / 1024).toFixed(1)} МБ/с`;
  }
  return `${Math.max(1, Math.round(bytesPerSecond / 1024))} КБ/с`;
}

function formatEta(seconds: number) {
  const rounded = Math.max(1, Math.ceil(seconds));
  if (rounded < 60) return `около ${rounded} сек.`;
  const minutes = Math.ceil(rounded / 60);
  if (minutes < 60) return `около ${minutes} мин.`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return `около ${hours} ч${remainder ? ` ${remainder} мин.` : ""}`;
}

export function UploadProgressPanel({ status, detail, onCancel }: Props) {
  const isFinalizing = status.phase === "finalizing";
  const title =
    status.phase === "preparing"
      ? "Подготавливаем загрузку…"
      : isFinalizing
        ? "Проверяем и сохраняем…"
        : `Загружаем файл… ${status.percent}%`;

  return (
    <Stack gap={6} role="status" aria-live="polite">
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Text size="sm" fw={600}>
            {title}
          </Text>
          {detail && (
            <Text size="xs" c="dimmed">
              {detail}
            </Text>
          )}
          {status.phase === "uploading" && status.bytesPerSecond && (
            <Text size="xs" c="dimmed">
              {formatSpeed(status.bytesPerSecond)}
              {status.etaSeconds !== null && status.etaSeconds > 0
                ? ` · осталось ${formatEta(status.etaSeconds)}`
                : ""}
            </Text>
          )}
          {isFinalizing && (
            <Text size="xs" c="dimmed">
              Файл уже загружен. Не закрывайте страницу до завершения проверки.
            </Text>
          )}
        </div>
        {onCancel && !isFinalizing && (
          <Button
            type="button"
            size="compact-sm"
            variant="subtle"
            color="red"
            onClick={onCancel}
          >
            Отменить
          </Button>
        )}
      </Group>
      <Progress value={status.percent} animated aria-label={title} />
    </Stack>
  );
}
