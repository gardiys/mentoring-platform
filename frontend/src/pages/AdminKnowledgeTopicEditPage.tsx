import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  MultiSelect,
  NumberInput,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminKnowledgeTopic,
  useUpdateAdminKnowledgeTopicSettings,
} from "../features/admin/knowledgeQueries";
import { useAdminStudentOptions } from "../features/admin/studentQueries";
import type { AdminKnowledgeTopicOutline } from "../types/api";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function TopicEditor({ topic }: { topic: AdminKnowledgeTopicOutline }) {
  const [form, setForm] = useState({
    slug: topic.slug,
    title: topic.title,
    description: topic.description,
    position: topic.position,
    is_published: topic.is_published,
    track_ids: topic.track_ids,
  });
  const options = useAdminStudentOptions();
  const mutation = useUpdateAdminKnowledgeTopicSettings();
  const valid =
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    form.track_ids.length > 0;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || mutation.isPending) return;
    mutation.mutate(
      { id: topic.id, payload: form },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message: "Настройки темы сохранены",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Knowledge base · редактирование"
        title={topic.title}
        description="Материалы показаны компактной таблицей и редактируются по одному."
      />
      <form onSubmit={submit}>
        <Card withBorder>
          <Stack>
            <Title order={2}>Настройки темы</Title>
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
              label="Описание"
              value={form.description ?? ""}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.currentTarget.value || null,
                }))
              }
            />
            <MultiSelect
              required
              searchable
              label="Направления"
              description="Тема видна пользователям только выбранных направлений"
              data={(options.data?.tracks ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              value={form.track_ids}
              onChange={(track_ids) =>
                setForm((current) => ({ ...current, track_ids }))
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
            <Button
              type="submit"
              loading={mutation.isPending}
              disabled={!valid}
            >
              Сохранить настройки
            </Button>
          </Stack>
        </Card>
      </form>

      <Card withBorder>
        <Stack>
          <Group justify="space-between">
            <div>
              <Title order={2}>Материалы</Title>
              <Text c="dimmed" size="sm">
                Markdown-содержимое загружается только при открытии записи.
              </Text>
            </div>
            <Button
              component={Link}
              to={`/admin/knowledge/${topic.id}/entries/new`}
            >
              + Добавить материал
            </Button>
          </Group>
          <Table.ScrollContainer minWidth={700}>
            <Table striped highlightOnHover verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Название</Table.Th>
                  <Table.Th>Тип</Table.Th>
                  <Table.Th>Позиция</Table.Th>
                  <Table.Th>Статус</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {topic.entries.map((entry) => (
                  <Table.Tr key={entry.id}>
                    <Table.Td>
                      <Text fw={600}>{entry.title}</Text>
                      <Text size="xs" c="dimmed">
                        /{entry.slug}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={
                          entry.kind === "article" ? "brandBlue" : "brandYellow"
                        }
                      >
                        {entry.kind === "article" ? "Статья" : "Вопрос"}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{entry.position}</Table.Td>
                    <Table.Td>
                      {entry.is_published ? "Опубликован" : "Черновик"}
                    </Table.Td>
                    <Table.Td>
                      <Button
                        component={Link}
                        to={`/admin/knowledge/${topic.id}/entries/${entry.id}/edit`}
                        variant="subtle"
                        size="xs"
                      >
                        Редактировать
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {topic.entries.length === 0 && (
            <Text c="dimmed">Материалов пока нет.</Text>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}

export function AdminKnowledgeTopicEditPage() {
  const { topicId = "" } = useParams();
  const query = useAdminKnowledgeTopic(topicId);
  if (query.isPending) return <LoadingState label="Загружаем материалы…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  return <TopicEditor key={query.data.id} topic={query.data} />;
}
