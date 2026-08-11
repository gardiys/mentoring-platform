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

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ProtectedContentMediaList } from "../components/ProtectedContentMediaList";
import { TopicStatusBadge } from "../components/TopicStatusBadge";
import { useUpdateProgress } from "../features/progress/mutations";
import { useRoadmap, useTopic } from "../features/roadmaps/queries";
import { usePlatform } from "../platform/usePlatform";
import type { ProgressStatus } from "../types/api";

export function TopicPage() {
  const { topicId = "" } = useParams();
  const query = useTopic(topicId);
  const roadmapQuery = useRoadmap(query.data?.roadmap.slug ?? "");
  const platform = usePlatform();
  const mutation = useUpdateProgress(topicId, query.data?.roadmap.slug ?? "");

  if (query.isPending) return <LoadingState />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

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

  const orderedTopics =
    roadmapQuery.data?.sections.flatMap((section) => section.topics) ?? [];
  const currentTopicIndex = orderedTopics.findIndex(
    (topic) => topic.id === query.data.id,
  );
  const previousTopic =
    currentTopicIndex > 0 ? orderedTopics[currentTopicIndex - 1] : null;
  const nextTopic =
    currentTopicIndex >= 0 && currentTopicIndex < orderedTopics.length - 1
      ? orderedTopics[currentTopicIndex + 1]
      : null;

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
      <ProtectedContentMediaList
        media={query.data.media ?? []}
        resourceKey={`roadmap:${query.data.id}`}
        loadPlayback={(mediaId) =>
          api.roadmapTopicMediaPlayback(query.data.id, mediaId)
        }
      />
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
      <Group gap="md" wrap="wrap" className="roadmap-step-navigation">
        {previousTopic && (
          <Button
            component={Link}
            to={`/topics/${previousTopic.id}`}
            variant="light"
            size="md"
            title={previousTopic.title}
            className="roadmap-step-button roadmap-step-button-previous"
          >
            ← Предыдущий шаг
          </Button>
        )}
        <Button
          component={Link}
          to={`/roadmaps/${query.data.roadmap.slug}`}
          variant="subtle"
          size="md"
          className="roadmap-step-back-link"
        >
          К роадмапу
        </Button>
        {nextTopic && (
          <Button
            component={Link}
            to={`/topics/${nextTopic.id}`}
            size="md"
            title={nextTopic.title}
            className="roadmap-step-button roadmap-step-button-next"
          >
            Следующий шаг →
          </Button>
        )}
      </Group>
    </Stack>
  );
}
