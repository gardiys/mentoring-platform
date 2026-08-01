import {
  Badge,
  Button,
  Card,
  Group,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { Link, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  interviewCatalogFiltersFromParams,
  useInterviewCatalogAuthors,
  useInterviewCatalogCompanies,
  useInterviewCatalogDirections,
} from "../features/interviews/catalogQueries";
import type {
  InterviewCatalogMediaKind,
  InterviewStageType,
} from "../types/api";

const stageOptions = [
  { value: "screening", label: "Скрининг" },
  { value: "technical_screening", label: "Технический скрининг" },
  { value: "technical_interview", label: "Техническое интервью" },
  { value: "system_design", label: "Системный дизайн" },
  { value: "final_interview", label: "Финальное интервью" },
  { value: "other", label: "Иное" },
];

const mediaOptions = [
  { value: "any", label: "Есть видео или аудио" },
  { value: "video", label: "Есть видеозапись" },
  { value: "audio", label: "Есть аудиозапись" },
];

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function InterviewCatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentFilters = interviewCatalogFiltersFromParams(searchParams);
  const [debouncedSearch] = useDebouncedValue(currentFilters.query.trim(), 250);
  const filters = { ...currentFilters, query: debouncedSearch };
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const directions = useInterviewCatalogDirections();
  const authors = useInterviewCatalogAuthors();
  const query = useInterviewCatalogCompanies(filters, page);
  const hasFilters = Boolean(
    currentFilters.query ||
    currentFilters.authorId ||
    currentFilters.trackId ||
    currentFilters.stageType ||
    currentFilters.hasOffer ||
    currentFilters.mediaKind,
  );

  const updateFilter = (name: string, value: string | null) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(name, value);
        else next.delete(name);
        if (name !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Собеседования · опыт учеников"
          title="Каталог компаний"
          description="Изучайте реальные этапы собеседований, записи, материалы и обратную связь учеников."
        />
        <Button component={Link} to="/interviews" variant="subtle">
          ← К собеседованиям
        </Button>
      </Group>

      <Card withBorder>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            <TextInput
              label="Найти компанию"
              placeholder="Яндекс, Yandex, Т-банк…"
              value={currentFilters.query}
              onChange={(event) => updateFilter("q", event.currentTarget.value)}
            />
            <Select
              clearable
              label="Направление"
              placeholder="Все мои направления"
              data={(directions.data ?? []).map((direction) => ({
                value: direction.id,
                label: direction.title,
              }))}
              value={currentFilters.trackId}
              disabled={directions.isPending || directions.isError}
              onChange={(value) => updateFilter("track_id", value)}
            />
            <Select
              clearable
              searchable
              label="Автор"
              placeholder="Все авторы"
              data={(authors.data ?? []).map((author) => ({
                value: author.id,
                label: author.telegram_username
                  ? `${author.name} · @${author.telegram_username}`
                  : author.name,
              }))}
              value={currentFilters.authorId}
              disabled={authors.isPending || authors.isError}
              onChange={(value) => updateFilter("author_id", value)}
            />
            <Select
              clearable
              label="Этап собеседования"
              placeholder="Все этапы"
              data={stageOptions}
              value={currentFilters.stageType}
              onChange={(value) =>
                updateFilter("stage_type", value as InterviewStageType | null)
              }
            />
            <Select
              clearable
              label="Запись"
              placeholder="Все собеседования"
              data={mediaOptions}
              value={currentFilters.mediaKind}
              onChange={(value) =>
                updateFilter(
                  "media_kind",
                  value as InterviewCatalogMediaKind | null,
                )
              }
            />
            <Stack gap="xs" justify="flex-end">
              <Switch
                label="Только треки с оффером"
                checked={currentFilters.hasOffer}
                onChange={(event) =>
                  updateFilter(
                    "has_offer",
                    event.currentTarget.checked ? "true" : null,
                  )
                }
              />
              <Button
                size="compact-sm"
                variant="subtle"
                disabled={!hasFilters}
                onClick={() => setSearchParams({}, { replace: true })}
              >
                Сбросить фильтры
              </Button>
            </Stack>
          </SimpleGrid>
          {hasFilters && (
            <Text size="xs" c="dimmed">
              Все выбранные условия применяются одновременно к одному треку.
            </Text>
          )}
        </Stack>
      </Card>

      {query.isPending ? (
        <LoadingState label="Загружаем компании…" />
      ) : query.isError ? (
        <ErrorState retry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <Card withBorder>
          <Text fw={600}>Компании не найдены</Text>
          <Text c="dimmed" size="sm" mt={4}>
            Попробуйте другое написание или вернитесь позже, когда ученики
            добавят новые собеседования.
          </Text>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          {query.data.items.map((company) => (
            <Card key={company.id} withBorder>
              <Stack h="100%">
                <Group justify="space-between">
                  <Badge variant="light">{company.track_count} треков</Badge>
                  <Text className="technical-label">
                    {company.interview_count} интервью
                  </Text>
                </Group>
                <Title order={2}>{company.name}</Title>
                <Text c="dimmed" size="sm">
                  {company.last_interview_at
                    ? `Последнее интервью: ${formatDate(company.last_interview_at)}`
                    : "В треках пока нет этапов"}
                </Text>
                <Button
                  component={Link}
                  to={{
                    pathname: `/interviews/catalog/${company.id}`,
                    search: searchParams.toString()
                      ? `?${searchParams.toString()}`
                      : "",
                  }}
                  variant="light"
                  mt="auto"
                >
                  Смотреть собеседования
                </Button>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
      {(query.data?.total ?? 0) > 24 && (
        <Pagination
          value={page}
          onChange={(nextPage) => updateFilter("page", String(nextPage))}
          total={Math.ceil((query.data?.total ?? 0) / 24)}
          mx="auto"
        />
      )}
    </Stack>
  );
}
