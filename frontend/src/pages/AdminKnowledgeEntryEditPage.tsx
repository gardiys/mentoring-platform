import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  Select,
  Stack,
  Switch,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminKnowledgeEntry,
  useSaveAdminKnowledgeEntry,
} from "../features/admin/knowledgeQueries";
import type {
  AdminKnowledgeEntryMutation,
  AdminKnowledgeEntryRead,
} from "../types/api";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function EntryForm({
  topicId,
  entry,
}: {
  topicId: string;
  entry?: AdminKnowledgeEntryRead;
}) {
  const navigate = useNavigate();
  const mutation = useSaveAdminKnowledgeEntry();
  const [form, setForm] = useState<AdminKnowledgeEntryMutation>({
    id: entry?.id,
    kind: entry?.kind ?? "article",
    slug: entry?.slug ?? "",
    title: entry?.title ?? "",
    summary: entry?.summary ?? null,
    content_markdown:
      entry?.content_markdown ?? "# Новый материал\n\nДобавьте содержание.",
    position: entry?.position ?? 0,
    is_published: entry?.is_published ?? false,
  });
  const valid =
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    form.content_markdown.trim().length > 0;
  const back = `/admin/knowledge/${topicId}/edit`;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || mutation.isPending) return;
    mutation.mutate(
      { topicId, entryId: entry?.id, payload: form },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: entry ? "Материал сохранён" : "Материал создан",
          });
          navigate(back);
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };
  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow="Knowledge base · одна запись"
          title={entry ? "Редактирование материала" : "Новый материал"}
          description="Редактор загружает только выбранную статью или вопрос."
        />
        <Card withBorder>
          <Stack>
            {mutation.error && (
              <Alert color="red">{mutation.error.message}</Alert>
            )}
            <Group grow align="flex-start">
              <Select
                label="Тип"
                data={[
                  { value: "article", label: "Статья" },
                  { value: "question", label: "Вопрос" },
                ]}
                value={form.kind}
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    kind: value === "question" ? "question" : "article",
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
            <Textarea
              label="Краткое описание"
              value={form.summary ?? ""}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  summary: event.currentTarget.value || null,
                }))
              }
            />
            <Textarea
              label="Содержание (Markdown)"
              required
              autosize
              minRows={16}
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
              <Switch
                label="Опубликован"
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
  );
}

export function AdminKnowledgeEntryEditPage() {
  const { topicId = "", entryId } = useParams();
  const query = useAdminKnowledgeEntry(topicId, entryId);
  if (entryId && query.isPending)
    return <LoadingState label="Загружаем материал…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  return (
    <EntryForm key={entryId ?? "new"} topicId={topicId} entry={query.data} />
  );
}
