import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  MultiSelect,
  NumberInput,
  Select,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../components/PageHeader";
import type {
  AdminKnowledgeEntryMutation,
  AdminKnowledgeTopicMutation,
  AdminKnowledgeTopicRead,
  KnowledgeEntryKind,
} from "../../types/api";
import {
  useCreateAdminKnowledgeTopic,
  useUpdateAdminKnowledgeTopic,
} from "./knowledgeQueries";
import { useAdminStudentOptions } from "./studentQueries";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const emptyTopic: AdminKnowledgeTopicMutation = {
  slug: "",
  title: "",
  description: null,
  position: 0,
  is_published: false,
  track_ids: [],
  entries: [],
};

function emptyEntry(
  kind: KnowledgeEntryKind,
  position: number,
): AdminKnowledgeEntryMutation {
  return {
    kind,
    slug: "",
    title: "",
    summary: null,
    content_markdown:
      kind === "question"
        ? "# Краткий ответ\n\nОпишите ключевую идею и пример хорошего ответа."
        : "# Новый материал\n\nДобавьте содержание статьи.",
    position,
    is_published: false,
  };
}

function toMutation(
  topic: AdminKnowledgeTopicRead,
): AdminKnowledgeTopicMutation {
  return {
    slug: topic.slug,
    title: topic.title,
    description: topic.description,
    position: topic.position,
    is_published: topic.is_published,
    track_ids: topic.track_ids,
    entries: topic.entries.map((entry) => ({
      id: entry.id,
      kind: entry.kind,
      slug: entry.slug,
      title: entry.title,
      summary: entry.summary,
      content_markdown: entry.content_markdown,
      position: entry.position,
      is_published: entry.is_published,
    })),
  };
}

interface Props {
  topic?: AdminKnowledgeTopicRead;
}

export function AdminKnowledgeTopicForm({ topic }: Props) {
  const [form, setForm] = useState<AdminKnowledgeTopicMutation>(
    topic ? toMutation(topic) : emptyTopic,
  );
  const createMutation = useCreateAdminKnowledgeTopic();
  const updateMutation = useUpdateAdminKnowledgeTopic();
  const navigate = useNavigate();
  const options = useAdminStudentOptions();
  const editing = topic !== undefined;
  const entries = form.entries ?? [];
  const pending = createMutation.isPending || updateMutation.isPending;
  const error = createMutation.error ?? updateMutation.error;
  const valid =
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    form.track_ids.length > 0 &&
    entries.every(
      (entry) =>
        entry.title.trim().length > 0 &&
        SLUG_PATTERN.test(entry.slug) &&
        entry.content_markdown.trim().length > 0,
    );

  const updateEntry = (
    index: number,
    patch: Partial<AdminKnowledgeEntryMutation>,
  ) => {
    setForm((current) => ({
      ...current,
      entries: (current.entries ?? []).map((entry, entryIndex) =>
        entryIndex === index ? { ...entry, ...patch } : entry,
      ),
    }));
  };

  const addEntry = (kind: KnowledgeEntryKind) => {
    setForm((current) => ({
      ...current,
      entries: [
        ...(current.entries ?? []),
        emptyEntry(kind, current.entries?.length ?? 0),
      ],
    }));
  };

  const removeEntry = (index: number) => {
    setForm((current) => ({
      ...current,
      entries: (current.entries ?? [])
        .filter((_, entryIndex) => entryIndex !== index)
        .map((entry, position) => ({ ...entry, position })),
    }));
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || pending) return;
    const handlers = {
      onSuccess: () => {
        notifications.show({
          color: "green",
          message: editing ? "Тема базы знаний обновлена" : "Тема создана",
        });
        navigate("/admin/knowledge");
      },
      onError: (mutationError: Error) => {
        notifications.show({ color: "red", message: mutationError.message });
      },
    };
    if (topic) {
      updateMutation.mutate({ id: topic.id, payload: form }, handlers);
    } else {
      createMutation.mutate(form, handlers);
    }
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow={
            editing
              ? "Knowledge base · редактирование"
              : "Knowledge base · новая тема"
          }
          title={editing ? topic.title : "Новая тема базы знаний"}
          description="Внутри темы можно смешивать подробные статьи и короткие вопросы для обсуждения."
        />
        {error && (
          <Alert color="red" title="Не удалось сохранить">
            {error.message}
          </Alert>
        )}
        <Card withBorder>
          <Stack>
            <Title order={2}>Настройки темы</Title>
            <TextInput
              label="Название темы"
              required
              value={form.title}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({
                  ...current,
                  title: value,
                }));
              }}
            />
            <TextInput
              label="Slug темы"
              description="Латинские строчные буквы, цифры и дефисы"
              required
              value={form.slug}
              error={
                form.slug && !SLUG_PATTERN.test(form.slug)
                  ? "Некорректный slug"
                  : null
              }
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({
                  ...current,
                  slug: value,
                }));
              }}
            />
            <Textarea
              label="Описание"
              value={form.description ?? ""}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({
                  ...current,
                  description: value || null,
                }));
              }}
            />
            <MultiSelect
              required
              searchable
              label="Направления"
              description="Тема будет доступна ученикам и менторам этих направлений"
              data={(options.data?.tracks ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              value={form.track_ids}
              onChange={(track_ids) =>
                setForm((current) => ({ ...current, track_ids }))
              }
            />
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
              label="Тема опубликована"
              checked={form.is_published}
              onChange={(event) => {
                const checked = event.currentTarget.checked;
                setForm((current) => ({
                  ...current,
                  is_published: checked,
                }));
              }}
            />
          </Stack>
        </Card>

        <Group justify="space-between">
          <div>
            <Title order={2}>Материалы</Title>
            <Text c="dimmed" size="sm">
              Поиск автоматически переиндексирует материал после сохранения.
            </Text>
          </div>
          <Group>
            <Button
              type="button"
              variant="light"
              onClick={() => addEntry("article")}
            >
              + Статья
            </Button>
            <Button
              type="button"
              color="brandYellow"
              c="brandNavy.9"
              onClick={() => addEntry("question")}
            >
              + Вопрос
            </Button>
          </Group>
        </Group>

        {entries.length === 0 && (
          <Card withBorder>
            <Text c="dimmed">Добавьте первую статью или вопрос.</Text>
          </Card>
        )}
        {entries.map((entry, index) => (
          <Card
            key={entry.id ?? `${entry.kind}-${index}`}
            withBorder
            className="builder-topic-card"
          >
            <Stack>
              <Group justify="space-between">
                <Group>
                  <Badge
                    color={
                      entry.kind === "question" ? "brandYellow" : "brandBlue"
                    }
                  >
                    {entry.kind === "question" ? "Вопрос" : "Статья"}
                  </Badge>
                  <Text className="technical-label">Материал {index + 1}</Text>
                </Group>
                <Button
                  type="button"
                  variant="subtle"
                  color="red"
                  onClick={() => removeEntry(index)}
                >
                  Удалить
                </Button>
              </Group>
              <Divider />
              <Select
                label="Тип материала"
                data={[
                  { value: "article", label: "Статья / разбор" },
                  { value: "question", label: "Вопрос для обсуждения" },
                ]}
                value={entry.kind}
                allowDeselect={false}
                onChange={(value) =>
                  updateEntry(index, {
                    kind: (value ?? "article") as KnowledgeEntryKind,
                  })
                }
              />
              <TextInput
                label="Заголовок"
                required
                value={entry.title}
                onChange={(event) =>
                  updateEntry(index, { title: event.currentTarget.value })
                }
              />
              <TextInput
                label="Slug материала"
                required
                value={entry.slug}
                error={
                  entry.slug && !SLUG_PATTERN.test(entry.slug)
                    ? "Некорректный slug"
                    : null
                }
                onChange={(event) =>
                  updateEntry(index, { slug: event.currentTarget.value })
                }
              />
              <Textarea
                label="Краткое описание"
                description="Используется в списках и результатах поиска"
                value={entry.summary ?? ""}
                onChange={(event) =>
                  updateEntry(index, {
                    summary: event.currentTarget.value || null,
                  })
                }
              />
              <Textarea
                label="Markdown-содержимое"
                required
                minRows={12}
                autosize
                value={entry.content_markdown}
                onChange={(event) =>
                  updateEntry(index, {
                    content_markdown: event.currentTarget.value,
                  })
                }
              />
              <Group grow>
                <NumberInput
                  label="Позиция"
                  min={0}
                  value={entry.position}
                  onChange={(value) =>
                    updateEntry(index, {
                      position: typeof value === "number" ? value : 0,
                    })
                  }
                />
                <Switch
                  label="Материал опубликован"
                  checked={entry.is_published}
                  onChange={(event) =>
                    updateEntry(index, {
                      is_published: event.currentTarget.checked,
                    })
                  }
                />
              </Group>
            </Stack>
          </Card>
        ))}

        <Group justify="flex-end">
          <Button
            type="button"
            variant="subtle"
            onClick={() => navigate("/admin/knowledge")}
          >
            Отмена
          </Button>
          <Button type="submit" loading={pending} disabled={!valid}>
            {editing ? "Сохранить тему" : "Создать тему"}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
