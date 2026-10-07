import { TableSkeleton } from "../components/TableSkeleton";
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
import { type FormEvent, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { MarkdownImageEditor } from "../components/MarkdownImageEditor";
import { useContentImages } from "../hooks/useContentImages";
import { ErrorState } from "../components/ErrorState";
import { AdminContentMediaManager } from "../components/AdminContentMediaManager";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import {
  useAdminKnowledgeEntry,
  useSaveAdminKnowledgeEntry,
} from "../features/admin/knowledgeQueries";
import type {
  AdminKnowledgeEntryMutation,
  AdminKnowledgeEntryRead,
} from "../types/api";
import { useAdminKnowledgeMedia } from "../features/media/queries";

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
  const [entryId, setEntryId] = useState(entry?.id);
  const [saving, setSaving] = useState(false);
  const images = useContentImages();
  const media = useAdminKnowledgeMedia(topicId, entryId);
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
  const initial = useRef(form);
  const allowNavigation = useUnsavedChanges(
    JSON.stringify(form) !== JSON.stringify(initial.current),
  );
  const valid =
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    form.content_markdown.trim().length > 0;
  const back = `/admin/knowledge/${topicId}/edit`;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || saving) return;
    setSaving(true);
    try {
      let id = entryId;
      if (!id && images.hasPending(form.content_markdown)) {
        const draft = await mutation.mutateAsync({
          topicId,
          payload: {
            ...form,
            is_published: false,
            content_markdown: images.draftMarkdown(form.content_markdown),
          },
        });
        id = draft.id;
        setEntryId(id);
      }
      const content = await images.prepare(
        form.content_markdown,
        (file, options) =>
          api.uploadAdminKnowledgeMedia(
            topicId,
            id!,
            file,
            { title: null, position: 0 },
            options,
          ),
      );
      await mutation.mutateAsync({
        topicId,
        entryId: id,
        payload: { ...form, content_markdown: content },
      });
      allowNavigation();
      notifications.show({
        color: "green",
        message: entry ? "Материал сохранён" : "Материал создан",
      });
      navigate(back);
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось сохранить материал.",
      });
    } finally {
      setSaving(false);
    }
  };
  return (
    <Stack gap="xl">
      <form onSubmit={submit}>
        <fieldset
          disabled={saving}
          style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
        >
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
                <MarkdownImageEditor
                  minRows={16}
                  value={form.content_markdown}
                  disabled={saving}
                  queueImage={images.queue}
                  previews={images.previews(form.content_markdown)}
                  onChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      content_markdown: value,
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
                  <Button type="submit" loading={saving} disabled={!valid}>
                    Сохранить
                  </Button>
                </Group>
              </Stack>
            </Card>
          </Stack>
        </fieldset>
      </form>
      <AdminContentMediaManager
        media={entry?.media ?? []}
        disabledReason={
          entry
            ? undefined
            : "Создайте материал, затем снова откройте его для редактирования и загрузите аудио или видео."
        }
        upload={media.upload}
        remove={media.remove}
        retry={media.retry}
      />
    </Stack>
  );
}

export function AdminKnowledgeEntryEditPage() {
  const { topicId = "", entryId } = useParams();
  const query = useAdminKnowledgeEntry(topicId, entryId);
  if (entryId && query.isPending)
    return <TableSkeleton label="Загружаем материал…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <EntryForm key={entryId ?? "new"} topicId={topicId} entry={query.data} />
  );
}
