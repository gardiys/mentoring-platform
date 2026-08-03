import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
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
import { type FormEvent, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import {
  useAdminRoadmap,
  useUpdateAdminRoadmapSettings,
} from "../features/admin/queries";
import type { AdminRoadmapOutline } from "../types/api";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function RoadmapEditor({ roadmap }: { roadmap: AdminRoadmapOutline }) {
  const [form, setForm] = useState({
    slug: roadmap.slug,
    title: roadmap.title,
    description: roadmap.description,
    position: roadmap.position,
    is_published: roadmap.is_published,
  });
  const initial = useRef(form);
  const mutation = useUpdateAdminRoadmapSettings();
  const valid = form.title.trim().length > 0 && SLUG_PATTERN.test(form.slug);
  useUnsavedChanges(JSON.stringify(form) !== JSON.stringify(initial.current));
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || mutation.isPending) return;
    mutation.mutate(
      { id: roadmap.id, payload: form },
      {
        onSuccess: () => {
          initial.current = form;
          notifications.show({
            color: "green",
            message: "Настройки роадмапа сохранены",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Конструктор · редактирование"
        title={roadmap.title}
        description="Разделы и темы представлены таблицами; Markdown загружается только для выбранной темы."
      />
      <form onSubmit={submit}>
        <Card withBorder>
          <Stack>
            <Title order={2}>Настройки роадмапа</Title>
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
                label="Роадмап опубликован"
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

      <Group justify="space-between">
        <div>
          <Title order={2}>Разделы и темы</Title>
          <Text c="dimmed" size="sm">
            Редактирование одной строки не затрагивает весь роадмап.
          </Text>
        </div>
        <Button
          component={Link}
          to={`/admin/roadmaps/${roadmap.id}/sections/new`}
        >
          + Добавить раздел
        </Button>
      </Group>
      {roadmap.sections.map((section) => (
        <Card key={section.id} withBorder>
          <Stack>
            <Group justify="space-between">
              <div>
                <Title order={3}>{section.title}</Title>
                <Text size="sm" c="dimmed">
                  Позиция {section.position}
                  {section.duration_days
                    ? ` · ${section.duration_days} дн.`
                    : ""}
                </Text>
              </div>
              <Group>
                <Button
                  component={Link}
                  to={`/admin/roadmaps/${roadmap.id}/sections/${section.id}/topics/new`}
                  size="xs"
                >
                  + Тема
                </Button>
                <Button
                  component={Link}
                  to={`/admin/roadmaps/${roadmap.id}/sections/${section.id}/edit`}
                  variant="light"
                  size="xs"
                >
                  Настройки раздела
                </Button>
              </Group>
            </Group>
            <Table.ScrollContainer minWidth={650}>
              <Table striped highlightOnHover verticalSpacing="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Тема</Table.Th>
                    <Table.Th>Позиция</Table.Th>
                    <Table.Th>Время</Table.Th>
                    <Table.Th>Статус</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {section.topics.map((topic) => (
                    <Table.Tr key={topic.id}>
                      <Table.Td>
                        <Text fw={600}>{topic.title}</Text>
                        <Text size="xs" c="dimmed">
                          /{topic.slug}
                        </Text>
                      </Table.Td>
                      <Table.Td>{topic.position}</Table.Td>
                      <Table.Td>
                        {topic.estimated_minutes
                          ? `${topic.estimated_minutes} мин.`
                          : "—"}
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          color={topic.is_published ? "brandYellow" : "gray"}
                        >
                          {topic.is_published ? "Опубликована" : "Черновик"}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Button
                          component={Link}
                          to={`/admin/roadmaps/${roadmap.id}/sections/${section.id}/topics/${topic.id}/edit`}
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
            {section.topics.length === 0 && (
              <Text c="dimmed">В разделе пока нет тем.</Text>
            )}
          </Stack>
        </Card>
      ))}
      {roadmap.sections.length === 0 && (
        <Text c="dimmed">Разделов пока нет.</Text>
      )}
    </Stack>
  );
}

export function AdminRoadmapEditPage() {
  const { roadmapId = "" } = useParams();
  const query = useAdminRoadmap(roadmapId);
  if (query.isPending) return <LoadingState label="Загружаем структуру…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return <RoadmapEditor key={query.data.id} roadmap={query.data} />;
}
