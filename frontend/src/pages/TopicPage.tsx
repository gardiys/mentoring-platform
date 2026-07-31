import {
  Anchor,
  Breadcrumbs,
  Button,
  Group,
  Paper,
  Stack,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { TopicStatusBadge } from "../components/TopicStatusBadge";
import { useUpdateProgress } from "../features/progress/mutations";
import { useTopic } from "../features/roadmaps/queries";
import { usePlatform } from "../platform/usePlatform";
import type { ProgressStatus } from "../types/api";

export function TopicPage() {
  const { topicId = "" } = useParams();
  const query = useTopic(topicId);
  const platform = usePlatform();
  const mutation = useUpdateProgress(topicId, query.data?.roadmap.slug ?? "");

  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  const changeStatus = (status: ProgressStatus) => {
    mutation.mutate(status, {
      onSuccess: () => {
        platform.triggerSuccessFeedback();
        notifications.show({ color: "green", message: "Статус темы обновлён" });
      },
      onError: () =>
        notifications.show({
          color: "red",
          message: "Не удалось обновить статус",
        }),
    });
  };

  return (
    <Stack>
      <Breadcrumbs>
        <Anchor component={Link} to="/roadmaps">
          Роадмапы
        </Anchor>
        <Anchor component={Link} to={`/roadmaps/${query.data.roadmap.slug}`}>
          {query.data.roadmap.title}
        </Anchor>
        <Text>{query.data.title}</Text>
      </Breadcrumbs>
      <PageHeader
        eyebrow={`Материал · ${query.data.roadmap.slug}`}
        title={query.data.title}
        description={query.data.description}
      />
      <Group>
        <TopicStatusBadge status={query.data.status} />
        {query.data.estimated_minutes && (
          <Text className="technical-label">
            ≈ {query.data.estimated_minutes} мин на изучение
          </Text>
        )}
      </Group>
      <Paper
        withBorder
        p={{ base: "md", sm: "xl" }}
        className="markdown-content"
      >
        <ReactMarkdown
          components={{
            a: ({ children, href, title }) => (
              <a
                href={href}
                title={title}
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            ),
          }}
        >
          {query.data.content_markdown}
        </ReactMarkdown>
      </Paper>
      <Group>
        {query.data.status === "not_started" && (
          <Button
            disabled={mutation.isPending}
            onClick={() => changeStatus("in_progress")}
          >
            Начать изучение
          </Button>
        )}
        {query.data.status !== "completed" && (
          <Button
            color="brandYellow"
            c="brandNavy.9"
            disabled={mutation.isPending}
            loading={mutation.isPending}
            onClick={() => changeStatus("completed")}
          >
            Отметить пройденной
          </Button>
        )}
        {query.data.status === "completed" && (
          <Button
            variant="light"
            color="red"
            disabled={mutation.isPending}
            loading={mutation.isPending}
            onClick={() => changeStatus("not_started")}
          >
            Снять отметку
          </Button>
        )}
      </Group>
    </Stack>
  );
}
