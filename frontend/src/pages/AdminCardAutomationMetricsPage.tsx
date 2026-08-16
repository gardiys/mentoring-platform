import {
  Alert,
  Button,
  Card,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminTracks } from "../features/admin/queries";
import { CardAutomationNavigation } from "../features/cardAutomation/CardAutomationNavigation";
import { useCardAutomationMetrics } from "../features/cardAutomation/queries";
import type { CardAutomationMetricsRead } from "../types/api";

function dateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultPeriod() {
  const periodTo = new Date();
  const periodFrom = new Date(periodTo);
  periodFrom.setDate(periodFrom.getDate() - 29);
  return {
    periodFrom: dateInputValue(periodFrom),
    periodTo: dateInputValue(periodTo),
  };
}

function validDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const parsed = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  return dateInputValue(parsed) === value;
}

function count(value: number) {
  return value.toLocaleString("ru-RU");
}

function ratio(value: number) {
  return `${(value * 100).toLocaleString("ru-RU", {
    maximumFractionDigits: 1,
  })}%`;
}

function duration(value: number) {
  if (value < 60) return `${Math.round(value)} сек`;
  if (value < 3600) return `${Math.round(value / 60)} мин`;
  if (value < 86_400)
    return `${(value / 3600).toLocaleString("ru-RU", {
      maximumFractionDigits: 1,
    })} ч`;
  return `${(value / 86_400).toLocaleString("ru-RU", {
    maximumFractionDigits: 1,
  })} дн`;
}

function money(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? `$${parsed.toLocaleString("ru-RU", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
      })}`
    : value;
}

function MetricCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description?: string;
}) {
  return (
    <Card withBorder>
      <Text className="technical-label">{label}</Text>
      <Title order={2} mt={4}>
        {value}
      </Title>
      {description && (
        <Text size="xs" c="dimmed" mt={4}>
          {description}
        </Text>
      )}
    </Card>
  );
}

function Metrics({ data }: { data: CardAutomationMetricsRead }) {
  return (
    <Stack gap="xl">
      {data.extracted_questions_total === 0 && (
        <Alert color="blue" title="За выбранный период данных пока нет">
          Новые показатели появятся после обработки интервью. Можно расширить
          период или выбрать другое направление.
        </Alert>
      )}

      <section aria-labelledby="funnel-title">
        <Title id="funnel-title" order={3} mb="md">
          Воронка автоматизации
        </Title>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <MetricCard
            label="Извлечено вопросов"
            value={count(data.extracted_questions_total)}
          />
          <MetricCard
            label="Отсеяно как шум"
            value={count(data.routed_as_noise_total)}
          />
          <MetricCard
            label="Не для карточек"
            value={count(data.routed_as_non_flashcard_total)}
          />
          <MetricCard
            label="Создано теневых кластеров"
            value={count(data.shadow_clusters_created_total)}
          />
          <MetricCard
            label="Связано точно"
            value={count(data.auto_linked_exact_total)}
          />
          <MetricCard
            label="Связано по алиасу"
            value={count(data.auto_linked_alias_total)}
          />
          <MetricCard
            label="Связано семантически"
            value={count(data.auto_linked_semantic_total)}
          />
          <MetricCard
            label="Создано личных вопросов"
            value={count(data.personal_review_items_created_total)}
          />
        </SimpleGrid>
      </section>

      <section aria-labelledby="moderation-title">
        <Title id="moderation-title" order={3} mb="md">
          Ручная модерация
        </Title>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <MetricCard
            label="Поднято кластеров"
            value={count(data.clusters_promoted_total)}
          />
          <MetricCard
            label="Проверено кластеров"
            value={count(data.clusters_reviewed_total)}
          />
          <MetricCard
            label="Задач на 100 интервью"
            value={data.manual_tasks_per_100_interviews.toLocaleString(
              "ru-RU",
              { maximumFractionDigits: 1 },
            )}
          />
          <MetricCard
            label="Среднее время модерации"
            value={duration(data.average_cluster_moderation_time)}
          />
          <MetricCard
            label="Возраст старейшей задачи"
            value={duration(data.oldest_moderation_task_age)}
          />
        </SimpleGrid>
      </section>

      <section aria-labelledby="quality-title">
        <Title id="quality-title" order={3} mb="md">
          Качество решений
        </Title>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          <MetricCard
            label="Ручные отмены автоматики"
            value={ratio(data.automatic_decision_override_rate)}
          />
          <MetricCard
            label="Ошибочные объединения"
            value={ratio(data.false_merge_rate)}
          />
          <MetricCard
            label="False positive шума"
            value={ratio(data.noise_false_positive_rate)}
          />
        </SimpleGrid>
      </section>

      <section aria-labelledby="cost-title">
        <Title id="cost-title" order={3} mb="md">
          Стоимость AI
        </Title>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          <MetricCard
            label="На интервью"
            value={money(data.average_ai_cost_per_interview)}
          />
          <MetricCard
            label="На вопрос"
            value={money(data.average_ai_cost_per_question)}
          />
          <MetricCard
            label="На promoted-кластер"
            value={money(data.average_ai_cost_per_promoted_cluster)}
          />
        </SimpleGrid>
      </section>

      <Text size="xs" c="dimmed">
        Рассчитано {new Date(data.generated_at).toLocaleString("ru-RU")}
      </Text>
    </Stack>
  );
}

export function AdminCardAutomationMetricsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const defaults = defaultPeriod();
  const periodFrom = searchParams.get("period_from") ?? defaults.periodFrom;
  const periodTo = searchParams.get("period_to") ?? defaults.periodTo;
  const directionId = searchParams.get("direction_id");
  const periodIsValid =
    validDate(periodFrom) && validDate(periodTo) && periodFrom <= periodTo;
  const filters = { periodFrom, periodTo, directionId };
  const query = useCardAutomationMetrics(filters, periodIsValid);
  const tracks = useAdminTracks();

  const updateFilter = (name: string, value: string | null) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(name, value);
        else next.delete(name);
        return next;
      },
      { replace: true },
    );
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование · наблюдаемость"
        title="Метрики автоматизации карточек"
        description="Воронка, нагрузка на модерацию, качество автоматических решений и стоимость AI за выбранный период."
      />
      <CardAutomationNavigation scope="admin" />

      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <TextInput
            type="date"
            label="Период с"
            value={periodFrom}
            onChange={(event) =>
              updateFilter("period_from", event.currentTarget.value)
            }
          />
          <TextInput
            type="date"
            label="Период до"
            value={periodTo}
            onChange={(event) =>
              updateFilter("period_to", event.currentTarget.value)
            }
          />
          <Select
            label="Направление"
            placeholder="Все направления"
            clearable
            searchable
            disabled={tracks.isPending || tracks.isError}
            value={directionId}
            data={(tracks.data ?? []).map((track) => ({
              value: track.id,
              label: track.title,
            }))}
            onChange={(value) => updateFilter("direction_id", value)}
          />
          <Group align="flex-end">
            <Button
              variant="subtle"
              onClick={() => setSearchParams({}, { replace: true })}
              disabled={searchParams.size === 0}
            >
              Последние 30 дней
            </Button>
          </Group>
        </SimpleGrid>
      </Card>

      {!periodIsValid ? (
        <Alert color="red" title="Проверьте период">
          Обе даты должны быть корректными, а дата начала — не позже даты
          окончания.
        </Alert>
      ) : query.isPending ? (
        <LoadingState label="Рассчитываем метрики…" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <Metrics data={query.data} />
      )}
    </Stack>
  );
}
