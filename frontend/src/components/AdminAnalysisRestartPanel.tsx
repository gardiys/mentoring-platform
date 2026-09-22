import { Button, Card, Checkbox, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { api } from "../api/endpoints";
import { useAdminRestartIntelligenceInterview } from "../features/interviews/intelligenceQueries";
import type { IntelligenceInterviewDetail } from "../types/api";

export function AdminAnalysisRestartPanel({
  interview,
}: {
  interview: IntelligenceInterviewDetail;
}) {
  const restart = useAdminRestartIntelligenceInterview();
  const [downloading, setDownloading] = useState<string | null>(null);
  const [force, setForce] = useState(false);
  const [economy, setEconomy] = useState(false);
  const canRestart =
    ["ready", "failed"].includes(interview.processing_status) &&
    interview.transcript.some((row) => row.speaker_role === "candidate");

  const download = async (archiveId: string, revision: number) => {
    setDownloading(archiveId);
    try {
      const snapshot = await api.adminIntelligenceArchive(
        interview.id,
        archiveId,
      );
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(snapshot, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `analysis-${interview.id}-v${revision}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось скачать архив",
      });
    } finally {
      setDownloading(null);
    }
  };

  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Text fw={700}>Повторный AI-разбор</Text>
          <Button
            variant="light"
            disabled={!canRestart}
            loading={restart.isPending}
            onClick={() => {
              if (
                !window.confirm(
                  (force
                    ? "Полностью пересчитать AI-разбор? Все AI-этапы разбора будут выполнены заново. "
                    : "Обновить AI-разбор? Неизменённые результаты будут использованы повторно. ") +
                    "Предыдущая версия с ручными рецензиями сохранится в архиве; опубликованные карточки останутся в базе.",
                )
              )
                return;
              restart.mutate(
                { id: interview.id, force, economy },
                {
                  onSuccess: () =>
                    notifications.show({
                      color: "green",
                      message: "Пересчёт AI-разбора запущен",
                    }),
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                },
              );
            }}
          >
            Пересчитать AI-разбор
          </Button>
        </Group>
        <Text size="sm" c="dimmed">
          Обновит разбор по текущей транскрибации и правилам оценки.
          Неизменённые результаты используются повторно без нового запроса к AI.
          Предыдущие оценки и ручные рецензии сохранятся в архиве для
          скачивания. Повторный запуск доступен после завершения обработки или
          ошибки.
        </Text>
        <Checkbox
          label="Полностью пересчитать все этапы"
          description="Запросить новые результаты AI, даже если исходные данные не изменились. Это увеличит расходы."
          checked={force}
          disabled={!canRestart || restart.isPending}
          onChange={(event) => setForce(event.currentTarget.checked)}
        />
        <Checkbox
          label="Экономичный разбор (Flex)"
          description="Более дешёвая обработка той же моделью. Может занять больше времени; при ожидании готовые этапы сохраняются."
          checked={economy}
          disabled={!canRestart || restart.isPending}
          onChange={(event) => setEconomy(event.currentTarget.checked)}
        />
        {interview.ai_service_tier === "flex" && (
          <Text size="sm" c="dimmed">
            Текущий разбор: экономичный режим Flex.
          </Text>
        )}
        {(interview.analysis_archives ?? []).map((archive) => (
          <Button
            key={archive.id}
            variant="subtle"
            w="fit-content"
            disabled={downloading !== null}
            loading={downloading === archive.id}
            onClick={() => void download(archive.id, archive.revision)}
          >
            Скачать разбор №{archive.revision} ·{" "}
            {new Date(archive.created_at).toLocaleDateString("ru-RU")}
          </Button>
        ))}
      </Stack>
    </Card>
  );
}
