import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  NumberInput,
  Paper,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../components/PageHeader";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import type {
  AdminTrackMutation,
  AdminTrackOptions,
  AdminTrackRead,
} from "../../types/api";
import {
  useCreateAdminTrack,
  useSetAdminTrackAccess,
  useUpdateAdminTrack,
} from "./queries";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const emptyTrack: AdminTrackMutation = {
  slug: "",
  title: "",
  description: null,
  position: 0,
  is_published: false,
  roadmap_ids: [],
};

interface Props {
  options: AdminTrackOptions;
  track?: AdminTrackRead;
}

function trackPayload(track: AdminTrackRead): AdminTrackMutation {
  return {
    slug: track.slug,
    title: track.title,
    description: track.description,
    position: track.position,
    is_published: track.is_published,
    roadmap_ids: track.roadmaps.map((roadmap) => roadmap.id),
  };
}

export function AdminTrackForm({ options, track }: Props) {
  const [form, setForm] = useState<AdminTrackMutation>(
    track ? trackPayload(track) : emptyTrack,
  );
  const initial = useRef(form);
  const createMutation = useCreateAdminTrack();
  const updateMutation = useUpdateAdminTrack();
  const accessMutation = useSetAdminTrackAccess();
  const navigate = useNavigate();
  const editing = track !== undefined;
  const pending = createMutation.isPending || updateMutation.isPending;
  const error = createMutation.error ?? updateMutation.error;
  const roadmapIds = form.roadmap_ids ?? [];
  const assignedStudents = new Set(track?.student_ids ?? []);
  const valid = form.title.trim().length > 0 && SLUG_PATTERN.test(form.slug);
  const allowNavigation = useUnsavedChanges(
    JSON.stringify(form) !== JSON.stringify(initial.current),
  );

  const toggleRoadmap = (roadmapId: string, checked: boolean) => {
    setForm((current) => ({
      ...current,
      roadmap_ids: checked
        ? [...(current.roadmap_ids ?? []), roadmapId]
        : (current.roadmap_ids ?? []).filter((id) => id !== roadmapId),
    }));
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || pending) return;
    const handlers = {
      onSuccess: () => {
        allowNavigation();
        notifications.show({
          color: "green",
          message: editing ? "Трек обновлён" : "Трек создан",
        });
        navigate("/admin/tracks");
      },
      onError: (mutationError: Error) => {
        notifications.show({ color: "red", message: mutationError.message });
      },
    };
    if (track) {
      updateMutation.mutate({ id: track.id, payload: form }, handlers);
    } else {
      createMutation.mutate(form, handlers);
    }
  };

  const setStudentAccess = (studentId: string, granted: boolean) => {
    if (!track) return;
    accessMutation.mutate(
      { trackId: track.id, studentId, granted },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: granted ? "Доступ выдан" : "Доступ отозван",
          });
        },
        onError: (mutationError) => {
          notifications.show({ color: "red", message: mutationError.message });
        },
      },
    );
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow={editing ? "Треки · редактирование" : "Треки · новый"}
          title={editing ? `Трек ${track.title}` : "Новый трек обучения"}
          description="Трек объединяет несколько роадмапов и является единицей доступа после оплаты."
        />

        {error && (
          <Alert color="red" title="Не удалось сохранить трек">
            {error.message}
          </Alert>
        )}

        <Card withBorder>
          <Stack>
            <Title order={2}>Основные данные</Title>
            <TextInput
              label="Название трека"
              placeholder="Python"
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
              label="Slug трека"
              description="Это значение бот передаёт как track_slug"
              placeholder="python"
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
              label="Трек опубликован и доступен ученикам"
              checked={form.is_published}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  is_published: event.currentTarget.checked,
                }))
              }
            />
          </Stack>
        </Card>

        <Card withBorder>
          <Stack>
            <div>
              <Title order={2}>Роадмапы трека</Title>
              <Text c="dimmed" size="sm" mt={4}>
                Черновики можно включить заранее — ученик увидит их только после
                публикации.
              </Text>
            </div>
            <Divider />
            {options.roadmaps.length === 0 ? (
              <Text c="dimmed">Сначала создайте хотя бы один роадмап.</Text>
            ) : (
              options.roadmaps.map((roadmap) => (
                <Paper key={roadmap.id} withBorder p="md">
                  <Checkbox
                    checked={roadmapIds.includes(roadmap.id)}
                    onChange={(event) =>
                      toggleRoadmap(roadmap.id, event.currentTarget.checked)
                    }
                    label={
                      <Group gap="sm">
                        <Text fw={600}>{roadmap.title}</Text>
                        <Badge
                          size="sm"
                          color={
                            roadmap.is_published ? "brandYellow" : "brandSand"
                          }
                          c="brandNavy.9"
                        >
                          {roadmap.is_published ? "Опубликован" : "Черновик"}
                        </Badge>
                        <Text className="roadmap-slug">/{roadmap.slug}</Text>
                      </Group>
                    }
                  />
                </Paper>
              ))
            )}
          </Stack>
        </Card>

        {track && (
          <Card withBorder>
            <Stack>
              <div>
                <Title order={2}>Доступ учеников</Title>
                <Text c="dimmed" size="sm" mt={4}>
                  Изменение применяется сразу. Прогресс сохраняется даже после
                  отзыва доступа.
                </Text>
              </div>
              <Divider />
              {options.students.length === 0 ? (
                <Text c="dimmed">Учеников пока нет.</Text>
              ) : (
                options.students.map((student) => {
                  const name = [student.first_name, student.last_name]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <Paper key={student.id} withBorder p="md">
                      <Checkbox
                        checked={assignedStudents.has(student.id)}
                        disabled={accessMutation.isPending}
                        onChange={(event) =>
                          setStudentAccess(
                            student.id,
                            event.currentTarget.checked,
                          )
                        }
                        label={
                          <div>
                            <Text fw={600}>{name}</Text>
                            <Text size="xs" c="dimmed">
                              {student.email ??
                                (student.telegram_id
                                  ? `Telegram ID: ${student.telegram_id}`
                                  : "Без контактных данных")}
                            </Text>
                          </div>
                        }
                      />
                    </Paper>
                  );
                })
              )}
            </Stack>
          </Card>
        )}

        <Group justify="flex-end">
          <Button
            variant="subtle"
            type="button"
            onClick={() => navigate("/admin/tracks")}
          >
            Отмена
          </Button>
          <Button type="submit" loading={pending} disabled={!valid}>
            {editing ? "Сохранить трек" : "Создать трек"}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
