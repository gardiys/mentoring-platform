import {
  Alert,
  Button,
  Card,
  Divider,
  Group,
  NumberInput,
  Paper,
  Stack,
  Switch,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  useCreateAdminRoadmap,
  useUpdateAdminRoadmap,
} from "../features/admin/queries";
import type {
  AdminRoadmapCreate,
  AdminRoadmapUpdate,
  AdminSectionUpdate,
  AdminTopicUpdate,
} from "../types/api";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function emptyTopic(position: number): AdminTopicUpdate {
  return {
    slug: "",
    title: "",
    description: null,
    content_markdown: "# Новая тема\n\nДобавьте учебный материал.",
    position,
    estimated_minutes: null,
    is_published: false,
  };
}

function emptySection(position: number): AdminSectionUpdate {
  return {
    title: "",
    description: null,
    position,
    duration_days: null,
    topics: [emptyTopic(0)],
  };
}

const initialRoadmap: AdminRoadmapUpdate = {
  slug: "",
  title: "",
  description: null,
  position: 0,
  is_published: false,
  sections: [emptySection(0)],
};

interface Props {
  initialValue?: AdminRoadmapUpdate;
  roadmapId?: string;
}

function toCreatePayload(form: AdminRoadmapUpdate): AdminRoadmapCreate {
  return {
    slug: form.slug,
    title: form.title,
    description: form.description,
    position: form.position,
    is_published: form.is_published,
    sections: form.sections.map((section) => ({
      title: section.title,
      description: section.description,
      position: section.position,
      duration_days: section.duration_days,
      topics: section.topics.map((topic) => ({
        slug: topic.slug,
        title: topic.title,
        description: topic.description,
        content_markdown: topic.content_markdown,
        position: topic.position,
        estimated_minutes: topic.estimated_minutes,
        is_published: topic.is_published,
      })),
    })),
  };
}

export function AdminRoadmapCreatePage({
  initialValue,
  roadmapId,
}: Props = {}) {
  const [form, setForm] = useState<AdminRoadmapUpdate>(
    initialValue ?? initialRoadmap,
  );
  const initial = useRef(form);
  const createMutation = useCreateAdminRoadmap();
  const updateMutation = useUpdateAdminRoadmap();
  const navigate = useNavigate();
  const editing = roadmapId !== undefined;
  const isPending = createMutation.isPending || updateMutation.isPending;
  const mutationError = createMutation.error ?? updateMutation.error;
  const allowNavigation = useUnsavedChanges(
    JSON.stringify(form) !== JSON.stringify(initial.current),
  );

  const updateSection = (
    sectionIndex: number,
    patch: Partial<AdminSectionUpdate>,
  ) => {
    setForm((current) => ({
      ...current,
      sections: current.sections.map((section, index) =>
        index === sectionIndex ? { ...section, ...patch } : section,
      ),
    }));
  };

  const updateTopic = (
    sectionIndex: number,
    topicIndex: number,
    patch: Partial<AdminTopicUpdate>,
  ) => {
    const section = form.sections[sectionIndex];
    if (!section) return;
    updateSection(sectionIndex, {
      topics: section.topics.map((topic, index) =>
        index === topicIndex ? { ...topic, ...patch } : topic,
      ),
    });
  };

  const addSection = () => {
    setForm((current) => ({
      ...current,
      sections: [...current.sections, emptySection(current.sections.length)],
    }));
  };

  const removeSection = (sectionIndex: number) => {
    setForm((current) => ({
      ...current,
      sections: current.sections
        .filter((_, index) => index !== sectionIndex)
        .map((section, position) => ({ ...section, position })),
    }));
  };

  const addTopic = (sectionIndex: number) => {
    const section = form.sections[sectionIndex];
    if (!section) return;
    updateSection(sectionIndex, {
      topics: [...section.topics, emptyTopic(section.topics.length)],
    });
  };

  const removeTopic = (sectionIndex: number, topicIndex: number) => {
    const section = form.sections[sectionIndex];
    if (!section) return;
    updateSection(sectionIndex, {
      topics: section.topics
        .filter((_, index) => index !== topicIndex)
        .map((topic, position) => ({ ...topic, position })),
    });
  };

  const valid =
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    form.sections.every(
      (section) =>
        section.title.trim().length > 0 &&
        section.topics.every(
          (topic) =>
            topic.title.trim().length > 0 &&
            SLUG_PATTERN.test(topic.slug) &&
            topic.content_markdown.trim().length > 0,
        ),
    );

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || isPending) return;
    const callbacks = {
      onSuccess: () => {
        allowNavigation();
        notifications.show({
          color: "green",
          message: editing ? "Роадмап обновлён" : "Роадмап создан",
        });
        navigate("/admin/roadmaps");
      },
      onError: (error: Error) =>
        notifications.show({
          color: "red",
          message:
            error instanceof Error
              ? error.message
              : "Не удалось сохранить роадмап",
        }),
    };
    if (roadmapId) {
      updateMutation.mutate({ id: roadmapId, payload: form }, callbacks);
    } else {
      createMutation.mutate(toCreatePayload(form), callbacks);
    }
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow={
            editing
              ? "Конструктор · режим редактирования"
              : "Конструктор · новый трек"
          }
          title={editing ? "Редактирование роадмапа" : "Новый роадмап"}
          description="Порядок разделов и тем задаёт их позицию. Сохранённые элементы нельзя удалить, чтобы не потерять прогресс учеников."
        />
        {mutationError && (
          <Alert color="red" title="Роадмап не сохранён">
            {mutationError.message}
          </Alert>
        )}
        <Card withBorder className="builder-section-card">
          <Stack>
            <Title order={2}>Основные данные</Title>
            <TextInput
              label="Название роадмапа"
              required
              value={form.title}
              onChange={(event) => {
                const title = event.currentTarget.value;
                setForm((current) => ({ ...current, title }));
              }}
            />
            <TextInput
              label="Slug роадмапа"
              description="Латинские строчные буквы, цифры и дефисы"
              required
              value={form.slug}
              error={
                form.slug && !SLUG_PATTERN.test(form.slug)
                  ? "Некорректный slug"
                  : undefined
              }
              onChange={(event) => {
                const slug = event.currentTarget.value;
                setForm((current) => ({ ...current, slug }));
              }}
            />
            <Textarea
              label="Описание роадмапа"
              value={form.description ?? ""}
              onChange={(event) => {
                const description = event.currentTarget.value || null;
                setForm((current) => ({
                  ...current,
                  description,
                }));
              }}
            />
            <NumberInput
              label="Позиция в общем списке"
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
              label="Опубликовать роадмап"
              checked={form.is_published}
              onChange={(event) => {
                const isPublished = event.currentTarget.checked;
                setForm((current) => ({
                  ...current,
                  is_published: isPublished,
                }));
              }}
            />
          </Stack>
        </Card>

        {form.sections.map((section, sectionIndex) => (
          <Card
            key={section.id ?? `section-${sectionIndex}`}
            withBorder
            className="builder-section-card"
          >
            <Stack>
              <Group justify="space-between">
                <Title order={2}>Раздел {sectionIndex + 1}</Title>
                <Button
                  type="button"
                  color="red"
                  variant="subtle"
                  disabled={form.sections.length === 1 || section.id != null}
                  onClick={() => removeSection(sectionIndex)}
                  aria-label={`Удалить раздел ${sectionIndex + 1}`}
                >
                  Удалить раздел
                </Button>
              </Group>
              <TextInput
                label="Название раздела"
                required
                value={section.title}
                onChange={(event) =>
                  updateSection(sectionIndex, {
                    title: event.currentTarget.value,
                  })
                }
              />
              <Textarea
                label="Описание раздела"
                value={section.description ?? ""}
                onChange={(event) =>
                  updateSection(sectionIndex, {
                    description: event.currentTarget.value || null,
                  })
                }
              />
              <NumberInput
                label="Плановая длительность, дней"
                description="Используется для расчёта персонального дедлайна раздела"
                min={1}
                value={section.duration_days ?? ""}
                onChange={(value) =>
                  updateSection(sectionIndex, {
                    duration_days: typeof value === "number" ? value : null,
                  })
                }
              />
              <Divider />

              {section.topics.map((topic, topicIndex) => (
                <Paper
                  key={topic.id ?? `topic-${topicIndex}`}
                  withBorder
                  p="md"
                  className="builder-topic-card"
                >
                  <Stack>
                    <Group justify="space-between">
                      <Title order={3}>Тема {topicIndex + 1}</Title>
                      <Button
                        type="button"
                        color="red"
                        variant="subtle"
                        disabled={
                          section.topics.length === 1 || topic.id != null
                        }
                        onClick={() => removeTopic(sectionIndex, topicIndex)}
                        aria-label={`Удалить тему ${topicIndex + 1} раздела ${sectionIndex + 1}`}
                      >
                        Удалить тему
                      </Button>
                    </Group>
                    <TextInput
                      label="Название темы"
                      required
                      value={topic.title}
                      onChange={(event) =>
                        updateTopic(sectionIndex, topicIndex, {
                          title: event.currentTarget.value,
                        })
                      }
                    />
                    <TextInput
                      label="Slug темы"
                      required
                      description="Slug темы уникален на всей платформе"
                      value={topic.slug}
                      error={
                        topic.slug && !SLUG_PATTERN.test(topic.slug)
                          ? "Некорректный slug"
                          : undefined
                      }
                      onChange={(event) =>
                        updateTopic(sectionIndex, topicIndex, {
                          slug: event.currentTarget.value,
                        })
                      }
                    />
                    <Textarea
                      label="Описание темы"
                      value={topic.description ?? ""}
                      onChange={(event) =>
                        updateTopic(sectionIndex, topicIndex, {
                          description: event.currentTarget.value || null,
                        })
                      }
                    />
                    <Textarea
                      label="Markdown-материал"
                      required
                      autosize
                      minRows={8}
                      value={topic.content_markdown}
                      onChange={(event) =>
                        updateTopic(sectionIndex, topicIndex, {
                          content_markdown: event.currentTarget.value,
                        })
                      }
                    />
                    <NumberInput
                      label="Примерное время, минут"
                      min={1}
                      value={topic.estimated_minutes ?? ""}
                      onChange={(value) =>
                        updateTopic(sectionIndex, topicIndex, {
                          estimated_minutes:
                            typeof value === "number" ? value : null,
                        })
                      }
                    />
                    <Switch
                      label="Опубликовать тему"
                      checked={topic.is_published}
                      onChange={(event) =>
                        updateTopic(sectionIndex, topicIndex, {
                          is_published: event.currentTarget.checked,
                        })
                      }
                    />
                  </Stack>
                </Paper>
              ))}
              <Button
                type="button"
                variant="light"
                onClick={() => addTopic(sectionIndex)}
              >
                Добавить тему
              </Button>
            </Stack>
          </Card>
        ))}

        <Button type="button" variant="light" onClick={addSection}>
          Добавить раздел
        </Button>
        <Group justify="flex-end">
          <Button
            type="button"
            variant="default"
            onClick={() => navigate("/admin/roadmaps")}
          >
            Отмена
          </Button>
          <Button
            type="submit"
            disabled={!valid || isPending}
            loading={isPending}
          >
            {editing ? "Сохранить изменения" : "Создать роадмап"}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
