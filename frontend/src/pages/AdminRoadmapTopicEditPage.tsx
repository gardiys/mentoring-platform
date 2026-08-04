import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  Stack,
  Switch,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { AdminContentMediaManager } from "../components/AdminContentMediaManager";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import {
  useAdminRoadmapTopic,
  useSaveAdminRoadmapTopic,
} from "../features/admin/queries";
import { useAdminRoadmapTopicMedia } from "../features/media/queries";
import type { AdminTopicCreate, AdminTopicRead } from "../types/api";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function TopicForm({
  roadmapId,
  sectionId,
  topic,
}: {
  roadmapId: string;
  sectionId: string;
  topic?: AdminTopicRead;
}) {
  const navigate = useNavigate();
  const mutation = useSaveAdminRoadmapTopic();
  const media = useAdminRoadmapTopicMedia(roadmapId, sectionId, topic?.id);
  const [form, setForm] = useState<AdminTopicCreate>({
    slug: topic?.slug ?? "",
    title: topic?.title ?? "",
    description: topic?.description ?? null,
    content_markdown:
      topic?.content_markdown ?? "# Новая тема\n\nДобавьте учебный материал.",
    position: topic?.position ?? 0,
    estimated_minutes: topic?.estimated_minutes ?? null,
    is_published: topic?.is_published ?? false,
  });
  const initial = useRef(form);
  const allowNavigation = useUnsavedChanges(
    JSON.stringify(form) !== JSON.stringify(initial.current),
  );
  const valid =
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    form.content_markdown.trim().length > 0;
  const back = `/admin/roadmaps/${roadmapId}/edit`;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || mutation.isPending) return;
    mutation.mutate(
      { roadmapId, sectionId, topicId: topic?.id, payload: form },
      {
        onSuccess: () => {
          allowNavigation();
          notifications.show({
            color: "green",
            message: topic ? "Тема сохранена" : "Тема создана",
          });
          navigate(back);
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };
  return (
    <Stack gap="xl">
      <form onSubmit={submit}>
        <Stack gap="xl">
          <PageHeader
            eyebrow="Роадмап · одна тема"
            title={topic ? "Редактирование темы" : "Новая тема"}
            description="На странице находится только один Markdown-редактор."
          />
          <Card withBorder>
            <Stack>
              {mutation.error && (
                <Alert color="red">{mutation.error.message}</Alert>
              )}
              <Group grow align="flex-start">
                <TextInput
                  label="Название"
                  required
                  value={form.title}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      title: event.currentTarget.value,
                    }))
                  }
                />
                <TextInput
                  label="Slug"
                  required
                  value={form.slug}
                  error={
                    form.slug && !SLUG_PATTERN.test(form.slug)
                      ? "Некорректный slug"
                      : null
                  }
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      slug: event.currentTarget.value,
                    }))
                  }
                />
              </Group>
              <Textarea
                label="Краткое описание"
                value={form.description ?? ""}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    description: event.currentTarget.value || null,
                  }))
                }
              />
              <Textarea
                label="Содержание (Markdown)"
                required
                autosize
                minRows={18}
                value={form.content_markdown}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    content_markdown: event.currentTarget.value,
                  }))
                }
              />
              <Group grow>
                <NumberInput
                  label="Позиция"
                  min={0}
                  value={form.position}
                  onChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      position: typeof value === "number" ? value : 0,
                    }))
                  }
                />
                <NumberInput
                  label="Оценка времени, минут"
                  min={1}
                  value={form.estimated_minutes ?? ""}
                  onChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      estimated_minutes:
                        typeof value === "number" ? value : null,
                    }))
                  }
                />
                <Switch
                  label="Тема опубликована"
                  checked={form.is_published}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      is_published: event.currentTarget.checked,
                    }))
                  }
                />
              </Group>
              <Group justify="flex-end">
                <Button variant="subtle" onClick={() => navigate(back)}>
                  Отмена
                </Button>
                <Button
                  type="submit"
                  loading={mutation.isPending}
                  disabled={!valid}
                >
                  Сохранить
                </Button>
              </Group>
            </Stack>
          </Card>
        </Stack>
      </form>
      <AdminContentMediaManager
        media={topic?.media ?? []}
        disabledReason={
          topic
            ? undefined
            : "Создайте тему, затем снова откройте её для редактирования и загрузите аудио или видео."
        }
        upload={media.upload}
        remove={media.remove}
      />
    </Stack>
  );
}

export function AdminRoadmapTopicEditPage() {
  const { roadmapId = "", sectionId = "", topicId } = useParams();
  const query = useAdminRoadmapTopic(roadmapId, sectionId, topicId);
  if (topicId && query.isPending)
    return <LoadingState label="Загружаем тему…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <TopicForm
      key={topicId ?? "new"}
      roadmapId={roadmapId}
      sectionId={sectionId}
      topic={query.data}
    />
  );
}
