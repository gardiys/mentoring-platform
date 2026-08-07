import {
  Badge,
  Button,
  Card,
  Group,
  Pagination,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useInterviewCatalogHistory } from "../features/interviews/catalogQueries";
import type { InterviewStageType } from "../types/api";

const stageLabels: Record<InterviewStageType, string> = {
  screening: "Скрининг",
  technical_screening: "Технический скрининг",
  technical_interview: "Техническое интервью",
  system_design: "Системный дизайн",
  final_interview: "Финальное интервью",
  other: "Иное",
};

const PAGE_SIZE = 50;

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function InterviewCatalogHistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const query = useInterviewCatalogHistory(page);

  if (query.isPending)
    return <LoadingState label="Загружаем историю просмотров…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Каталог собеседований"
          title="История просмотров"
          description="Записи и этапы собеседований, которые вы уже открывали или отметили просмотренными."
        />
        <Button component={Link} to="/interviews/catalog" variant="subtle">
          ← К каталогу
        </Button>
      </Group>

      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text fw={600}>Вы пока ничего не смотрели</Text>
          <Text c="dimmed" size="sm" mt={4}>
            Откройте запись собеседования или отметьте этап просмотренным —
            он появится здесь.
          </Text>
        </Card>
      ) : (
        <Stack>
          {query.data.items.map((item) => (
            <Card key={item.stage_id} withBorder>
              <Group
                justify="space-between"
                align="flex-start"
                wrap="nowrap"
                className="responsive-card-header"
              >
                <div className="min-width-zero">
                  <Badge variant="light">{stageLabels[item.stage_type]}</Badge>
                  <Title order={3} mt="xs">
                    {item.company_name}
                  </Title>
                  <Text size="sm" c="dimmed" mt={4}>
                    {item.track_title} · этап от {formatDate(item.scheduled_at)}
                  </Text>
                  {item.description && (
                    <Text size="sm" mt="xs" lineClamp={2}>
                      {item.description}
                    </Text>
                  )}
                </div>
                <Stack gap={4} align="flex-end">
                  <Badge color="brandGreen" variant="light">
                    Просмотрено {formatDate(item.last_viewed_at)}
                  </Badge>
                  <Button
                    component={Link}
                    to={`/interviews/catalog/${item.company_id}?stage=${item.stage_id}`}
                    size="compact-sm"
                    variant="light"
                  >
                    Открыть
                  </Button>
                </Stack>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
      {(query.data?.total ?? 0) > PAGE_SIZE && (
        <Pagination
          value={page}
          onChange={(nextPage) =>
            setSearchParams(
              (current) => {
                const next = new URLSearchParams(current);
                next.set("page", String(nextPage));
                return next;
              },
              { replace: true },
            )
          }
          total={Math.ceil((query.data?.total ?? 0) / PAGE_SIZE)}
          mx="auto"
        />
      )}
    </Stack>
  );
}
