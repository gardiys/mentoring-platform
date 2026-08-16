import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { CardAutomationNavigation } from "../features/cardAutomation/CardAutomationNavigation";
import {
  useCardAutomationSettings,
  useUpdateCardAutomationSettings,
} from "../features/cardAutomation/queries";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import type {
  CardAutomationSettingsMutation,
  CardAutomationSettingsRead,
} from "../types/api";

function initialForm(
  settings: CardAutomationSettingsRead,
): CardAutomationSettingsMutation {
  return {
    direction_id: settings.direction_id,
    expected_version: settings.version,
    enabled: settings.enabled,
    shadow_mode: settings.shadow_mode,
    auto_ignore_noise_enabled: settings.auto_ignore_noise_enabled,
    auto_link_exact_enabled: settings.auto_link_exact_enabled,
    auto_link_alias_enabled: settings.auto_link_alias_enabled,
    auto_link_semantic_enabled: settings.auto_link_semantic_enabled,
    semantic_similarity_threshold: settings.semantic_similarity_threshold,
    pairwise_judge_confidence_threshold:
      settings.pairwise_judge_confidence_threshold,
    candidate_score_gap_threshold: settings.candidate_score_gap_threshold,
    cluster_match_threshold: settings.cluster_match_threshold,
    min_distinct_interviews_for_promotion:
      settings.min_distinct_interviews_for_promotion,
    min_distinct_companies_for_promotion:
      settings.min_distinct_companies_for_promotion,
    min_failed_answers_for_promotion: settings.min_failed_answers_for_promotion,
    audit_sample_percent: settings.audit_sample_percent,
    personal_review_enabled: settings.personal_review_enabled,
    global_auto_publish_enabled: false,
    cluster_moderation_enabled: settings.cluster_moderation_enabled,
    legacy_queue_enabled: settings.legacy_queue_enabled,
  };
}

interface SettingsFormProps {
  settings: CardAutomationSettingsRead;
  reload: () => Promise<unknown>;
}

type BooleanSettingField =
  | "enabled"
  | "shadow_mode"
  | "auto_ignore_noise_enabled"
  | "auto_link_exact_enabled"
  | "auto_link_alias_enabled"
  | "auto_link_semantic_enabled"
  | "personal_review_enabled"
  | "cluster_moderation_enabled"
  | "legacy_queue_enabled";

function SettingsForm({ settings, reload }: SettingsFormProps) {
  const mutation = useUpdateCardAutomationSettings();
  const initial = useMemo(() => initialForm(settings), [settings]);
  const [form, setForm] = useState(initial);
  const dirty = JSON.stringify(form) !== JSON.stringify(initial);
  useUnsavedChanges(dirty);
  const conflict =
    mutation.error instanceof ApiError && mutation.error.status === 409;

  const submit = (
    payload: CardAutomationSettingsMutation,
    successMessage = `Настройки «${settings.direction_title}» сохранены`,
  ) => {
    if (mutation.isPending) return;
    mutation.mutate(payload, {
      onSuccess: () =>
        notifications.show({
          color: "green",
          message: successMessage,
        }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const save = () => {
    if (!dirty) return;
    submit(form);
  };

  const updateBooleanSetting = (
    field: BooleanSettingField,
    checked: boolean,
  ) => {
    setForm((current) => ({ ...current, [field]: checked }));
  };

  const enableSafeShadowMode = () => {
    if (
      !window.confirm(
        `Включить безопасный shadow-режим для «${settings.direction_title}»? ` +
          "Автоматические связи, личные вопросы и новая модерация останутся выключены.",
      )
    ) {
      return;
    }
    const safeForm: CardAutomationSettingsMutation = {
      ...form,
      enabled: true,
      shadow_mode: true,
      auto_ignore_noise_enabled: false,
      auto_link_exact_enabled: false,
      auto_link_alias_enabled: false,
      auto_link_semantic_enabled: false,
      personal_review_enabled: false,
      global_auto_publish_enabled: false,
      cluster_moderation_enabled: false,
      legacy_queue_enabled: true,
    };
    setForm(safeForm);
    submit(
      safeForm,
      `Безопасный shadow-режим «${settings.direction_title}» включён`,
    );
  };

  return (
    <Stack gap="lg">
      <Card
        withBorder
        p="sm"
        style={{ position: "sticky", top: 12, zIndex: 20 }}
      >
        <Group justify="space-between" align="center">
          <Group gap="sm">
            <Badge
              color={
                !form.enabled ? "gray" : form.shadow_mode ? "blue" : "orange"
              }
              variant="light"
            >
              {!form.enabled
                ? "Автоматизация выключена"
                : form.shadow_mode
                  ? "Shadow mode"
                  : "Рабочий режим"}
            </Badge>
            {dirty && (
              <Text size="sm" c="orange" fw={600}>
                Есть несохранённые изменения
              </Text>
            )}
          </Group>
          <Group gap="sm">
            {!form.enabled && (
              <Button
                variant="light"
                onClick={enableSafeShadowMode}
                loading={mutation.isPending}
              >
                Включить безопасный shadow-режим
              </Button>
            )}
            <Button
              onClick={save}
              loading={mutation.isPending}
              disabled={!dirty}
            >
              Сохранить настройки
            </Button>
          </Group>
        </Group>
      </Card>

      {form.shadow_mode && (
        <Alert color="blue" title="Теневой режим">
          Pipeline записывает предложения и аудит, но не применяет
          автоматические связи к общей базе.
        </Alert>
      )}
      {mutation.error && (
        <Alert
          color={conflict ? "yellow" : "red"}
          title={
            conflict
              ? "Настройки изменены в другой сессии"
              : "Не удалось сохранить настройки"
          }
        >
          <Stack align="flex-start" gap="sm">
            <Text>{mutation.error.message}</Text>
            {conflict && (
              <Button
                variant="light"
                onClick={() => {
                  if (
                    window.confirm(
                      "Загрузить актуальные настройки? Текущие изменения будут потеряны.",
                    )
                  ) {
                    mutation.reset();
                    void reload();
                  }
                }}
              >
                Загрузить актуальную версию
              </Button>
            )}
          </Stack>
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <Card withBorder>
          <Stack>
            <Title order={3}>Режим запуска</Title>
            <Switch
              label="Автоматизация включена"
              description="Разрешает pipeline для этого направления"
              checked={form.enabled}
              onChange={(event) =>
                updateBooleanSetting("enabled", event.currentTarget.checked)
              }
            />
            <Switch
              label="Shadow mode"
              description="Считать решения без изменения рабочих данных"
              checked={form.shadow_mode}
              onChange={(event) =>
                updateBooleanSetting("shadow_mode", event.currentTarget.checked)
              }
            />
            <Switch
              label="Новая модерация кластеров"
              checked={form.cluster_moderation_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "cluster_moderation_enabled",
                  event.currentTarget.checked,
                )
              }
            />
            <Switch
              label="Старая очередь доступна"
              description="Безопасный путь возврата во время rollout"
              checked={form.legacy_queue_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "legacy_queue_enabled",
                  event.currentTarget.checked,
                )
              }
            />
            <Switch
              label="Личные вопросы учеников"
              checked={form.personal_review_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "personal_review_enabled",
                  event.currentTarget.checked,
                )
              }
            />
          </Stack>
        </Card>

        <Card withBorder>
          <Stack>
            <Title order={3}>Безопасные автоматические действия</Title>
            <Switch
              label="Исключать явный шум"
              checked={form.auto_ignore_noise_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "auto_ignore_noise_enabled",
                  event.currentTarget.checked,
                )
              }
            />
            <Switch
              label="Связывать точные совпадения"
              checked={form.auto_link_exact_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "auto_link_exact_enabled",
                  event.currentTarget.checked,
                )
              }
            />
            <Switch
              label="Связывать подтверждённые aliases"
              checked={form.auto_link_alias_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "auto_link_alias_enabled",
                  event.currentTarget.checked,
                )
              }
            />
            <Switch
              label="Semantic-связывание"
              description="Использует retrieval, pairwise judge и gap"
              checked={form.auto_link_semantic_enabled}
              onChange={(event) =>
                updateBooleanSetting(
                  "auto_link_semantic_enabled",
                  event.currentTarget.checked,
                )
              }
            />
            <Divider />
            <Switch
              label="Глобальная автопубликация"
              description="Зарезервировано: общие карточки всегда подтверждает человек"
              checked={false}
              disabled
              readOnly
            />
          </Stack>
        </Card>
      </SimpleGrid>

      <Card withBorder>
        <Stack>
          <Title order={3}>Пороги уверенности</Title>
          <Text size="sm" c="dimmed">
            Значения 0–1. Чем выше порог, тем меньше автоматических действий и
            ниже риск ложного объединения.
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput
              label="Semantic similarity"
              min={0}
              max={1}
              step={0.01}
              decimalScale={3}
              value={form.semantic_similarity_threshold}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  semantic_similarity_threshold: value,
                }))
              }
            />
            <NumberInput
              label="Pairwise judge confidence"
              min={0}
              max={1}
              step={0.01}
              decimalScale={3}
              value={form.pairwise_judge_confidence_threshold}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  pairwise_judge_confidence_threshold: value,
                }))
              }
            />
            <NumberInput
              label="Минимальный gap кандидатов"
              min={0}
              max={1}
              step={0.01}
              decimalScale={3}
              value={form.candidate_score_gap_threshold}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  candidate_score_gap_threshold: value,
                }))
              }
            />
            <NumberInput
              label="Совпадение с кластером"
              min={0}
              max={1}
              step={0.01}
              decimalScale={3}
              value={form.cluster_match_threshold}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  cluster_match_threshold: value,
                }))
              }
            />
          </SimpleGrid>
        </Stack>
      </Card>

      <Card withBorder>
        <Stack>
          <Title order={3}>Зрелость кластера и аудит</Title>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
            <NumberInput
              label="Минимум интервью"
              min={1}
              value={form.min_distinct_interviews_for_promotion}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  min_distinct_interviews_for_promotion: value,
                }))
              }
            />
            <NumberInput
              label="Минимум компаний"
              min={1}
              value={form.min_distinct_companies_for_promotion}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  min_distinct_companies_for_promotion: value,
                }))
              }
            />
            <NumberInput
              label="Минимум плохих ответов"
              min={1}
              value={form.min_failed_answers_for_promotion}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  min_failed_answers_for_promotion: value,
                }))
              }
            />
            <NumberInput
              label="Выборочный аудит, %"
              min={0}
              max={100}
              step={1}
              value={form.audit_sample_percent}
              onChange={(value) =>
                typeof value === "number" &&
                setForm((current) => ({
                  ...current,
                  audit_sample_percent: value,
                }))
              }
            />
          </SimpleGrid>
        </Stack>
      </Card>

      <Group justify="flex-start">
        <Text size="sm" c="dimmed">
          Версия {settings.version} · обновлено{" "}
          {new Date(settings.updated_at).toLocaleString("ru-RU")}
        </Text>
      </Group>
    </Stack>
  );
}

export function AdminCardAutomationSettingsPage() {
  const query = useCardAutomationSettings();
  const [searchParams, setSearchParams] = useSearchParams();

  if (query.isPending) return <LoadingState label="Загружаем настройки…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const requestedDirectionId = searchParams.get("direction_id");
  const settings =
    query.data.items.find(
      (item) => item.direction_id === requestedDirectionId,
    ) ?? query.data.items[0];

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование · rollout"
        title="Настройки автоматизации"
        description="Параметры разделены по направлениям. Общая автопубликация намеренно заблокирована на текущем этапе."
      />
      <CardAutomationNavigation />

      {query.data.items.length === 0 || !settings ? (
        <Card withBorder>
          <Text fw={600}>Настройки направлений ещё не созданы</Text>
          <Text size="sm" c="dimmed" mt={4}>
            Они появятся после инициализации card automation для учебных треков.
          </Text>
        </Card>
      ) : (
        <>
          <Select
            label="Направление"
            value={settings.direction_id}
            data={query.data.items.map((item) => ({
              value: item.direction_id,
              label: item.direction_title,
            }))}
            onChange={(value) => {
              if (!value) return;
              setSearchParams({ direction_id: value }, { replace: true });
            }}
            maw={420}
          />
          <SettingsForm
            key={`${settings.direction_id}:${settings.version}`}
            settings={settings}
            reload={() => query.refetch()}
          />
        </>
      )}
    </Stack>
  );
}
