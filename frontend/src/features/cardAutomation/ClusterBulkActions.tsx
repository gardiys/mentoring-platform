import {
  Alert,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { ApiError } from "../../api/client";
import type {
  QuestionClusterBulkAction,
  QuestionClusterBulkResult,
  QuestionClusterSummary,
} from "../../types/api";
import { useBulkQuestionClusters } from "./queries";

const bulkActions: Array<{
  value: QuestionClusterBulkAction;
  label: string;
}> = [
  { value: "confirm_exact_matches", label: "Подтвердить точные совпадения" },
  {
    value: "confirm_high_confidence_matches",
    label: "Подтвердить high-confidence совпадения",
  },
  { value: "ignore_noise", label: "Исключить выбранный шум" },
  { value: "defer_singletons", label: "Отложить одноразовые кластеры" },
  { value: "link_card", label: "Связать с одной карточкой" },
];

interface ClusterBulkActionsProps {
  selected: QuestionClusterSummary[];
  clearSelection: () => void;
  reload: () => Promise<unknown>;
}

export function ClusterBulkActions({
  selected,
  clearSelection,
  reload,
}: ClusterBulkActionsProps) {
  const mutation = useBulkQuestionClusters();
  const [opened, setOpened] = useState(false);
  const [action, setAction] = useState<QuestionClusterBulkAction | null>(null);
  const [reason, setReason] = useState("");
  const [cardId, setCardId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<QuestionClusterBulkResult | null>(null);
  const conflict =
    mutation.error instanceof ApiError && mutation.error.status === 409;
  const needsCard = action === "link_card";
  const ready =
    selected.length > 0 &&
    Boolean(action) &&
    Boolean(reason.trim()) &&
    confirmed &&
    (!needsCard || Boolean(cardId.trim()));

  const close = () => {
    if (mutation.isPending) return;
    setOpened(false);
    mutation.reset();
    setAction(null);
    setReason("");
    setCardId("");
    setConfirmed(false);
  };

  const submit = () => {
    if (!action || !ready) return;
    mutation.mutate(
      {
        action,
        cluster_ids: selected.map((cluster) => cluster.id),
        expected_versions: Object.fromEntries(
          selected.map((cluster) => [cluster.id, cluster.version]),
        ),
        confirmation: true,
        reason: reason.trim(),
        card_id: needsCard ? cardId.trim() : null,
        topic_name: null,
      },
      {
        onSuccess: (response) => {
          setResult(response);
          clearSelection();
          close();
          notifications.show({
            color: response.failed_count > 0 ? "yellow" : "green",
            message: `Обработано: ${response.succeeded_count} из ${response.requested_count}`,
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <>
      <Card withBorder>
        <Group justify="space-between">
          <div>
            <Text fw={700}>Выбрано кластеров: {selected.length}</Text>
            <Text size="sm" c="dimmed">
              Сервер повторно проверит версии и допустимость каждого действия.
            </Text>
          </div>
          <Group>
            <Button
              variant="default"
              disabled={selected.length === 0}
              onClick={clearSelection}
            >
              Снять выбор
            </Button>
            <Button
              disabled={selected.length === 0}
              onClick={() => {
                setResult(null);
                setOpened(true);
              }}
            >
              Массовое действие
            </Button>
          </Group>
        </Group>
      </Card>

      {result && (
        <Alert
          color={result.failed_count > 0 ? "yellow" : "green"}
          title={`Успешно: ${result.succeeded_count}, с ошибкой: ${result.failed_count}`}
          withCloseButton
          onClose={() => setResult(null)}
        >
          {result.items
            .filter((item) => !item.succeeded)
            .map((item) => (
              <Text key={item.cluster_id} size="sm">
                {item.cluster_id}: {item.error_message ?? item.error_code}
              </Text>
            ))}
        </Alert>
      )}

      <Modal
        opened={opened}
        onClose={close}
        title={`Массовое действие · ${selected.length} кластеров`}
        size="lg"
      >
        <Stack>
          <Alert color="yellow">
            Действие создаст отдельные audit records и может изменить сразу
            несколько кластеров. Частичный результат будет показан после
            выполнения.
          </Alert>
          <Select
            label="Действие"
            placeholder="Выберите действие"
            value={action}
            data={bulkActions}
            onChange={(value) => {
              setAction(value as QuestionClusterBulkAction | null);
              setConfirmed(false);
            }}
          />
          {needsCard && (
            <TextInput
              label="ID существующей карточки"
              required
              value={cardId}
              onChange={(event) => setCardId(event.currentTarget.value)}
            />
          )}
          <Textarea
            label="Причина"
            description="Будет сохранена в журнале аудита"
            required
            minRows={3}
            value={reason}
            onChange={(event) => setReason(event.currentTarget.value)}
          />
          <Checkbox
            label={`Я подтверждаю действие для ${selected.length} кластеров`}
            checked={confirmed}
            onChange={(event) => setConfirmed(event.currentTarget.checked)}
          />
          {mutation.error && (
            <Alert
              color={conflict ? "yellow" : "red"}
              title={conflict ? "Версии кластеров изменились" : undefined}
            >
              <Stack align="flex-start" gap="sm">
                <Text>{mutation.error.message}</Text>
                {conflict && (
                  <Button
                    variant="light"
                    onClick={() => {
                      if (
                        !window.confirm(
                          "Закрыть форму, снять выбор и загрузить актуальные версии?",
                        )
                      )
                        return;
                      clearSelection();
                      close();
                      void reload();
                    }}
                  >
                    Обновить кластеры
                  </Button>
                )}
              </Stack>
            </Alert>
          )}
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={close}
              disabled={mutation.isPending}
            >
              Отмена
            </Button>
            <Button
              color="orange"
              onClick={submit}
              loading={mutation.isPending}
              disabled={!ready}
            >
              Подтвердить массовое действие
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
