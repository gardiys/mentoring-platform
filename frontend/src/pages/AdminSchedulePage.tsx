import {
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminTracks } from "../features/admin/queries";
import {
  ADMIN_SCHEDULE_PAGE_SIZE,
  useAdminSchedule,
  useDeleteAdminScheduleEvent,
  useSaveAdminScheduleEvent,
} from "../features/schedule/queries";
import type {
  AdminScheduleEventMutation,
  ScheduleEventKind,
  ScheduleEventRead,
} from "../types/api";
import {
  TIMEZONE_OPTIONS,
  WEEKDAY_OPTIONS,
  isoToMoscowInput,
  moscowInputToIso,
  scheduleEventTiming,
} from "../utils/schedule";

interface EventFormState {
  trackId: string | null;
  kind: ScheduleEventKind;
  title: string;
  description: string;
  meetingUrl: string;
  weekday: string;
  startsAtTime: string;
  timezone: string;
  startsAt: string;
}

function emptyEvent(trackId: string | null): EventFormState {
  return {
    trackId,
    kind: "weekly_call",
    title: "Групповой созвон",
    description: "",
    meetingUrl: "",
    weekday: "0",
    startsAtTime: "",
    timezone: "Europe/Moscow",
    startsAt: "",
  };
}

function eventForm(event: ScheduleEventRead): EventFormState {
  return {
    trackId: event.track.id,
    kind: event.kind,
    title: event.title,
    description: event.description ?? "",
    meetingUrl: event.meeting_url ?? "",
    weekday: String(event.weekday ?? 0),
    startsAtTime: event.starts_at_time?.slice(0, 5) ?? "",
    timezone: event.timezone ?? "Europe/Moscow",
    startsAt: isoToMoscowInput(event.starts_at),
  };
}

function validHttpUrl(value: string) {
  if (!value) return true;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function AdminSchedulePage() {
  const [searchParams] = useSearchParams();
  const tracks = useAdminTracks();
  const [trackId, setTrackId] = useState<string | null>(
    searchParams.get("track_id"),
  );
  const [kind, setKind] = useState<ScheduleEventKind | null>(null);
  const [page, setPage] = useState(1);
  const query = useAdminSchedule({ trackId, kind, page });
  const saveEvent = useSaveAdminScheduleEvent();
  const deleteEvent = useDeleteAdminScheduleEvent();
  const [opened, setOpened] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<EventFormState>(() => emptyEvent(trackId));

  function updateFormField<Key extends keyof EventFormState>(
    field: Key,
    value: EventFormState[Key],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  if (tracks.isPending) return <LoadingState label="Загружаем направления…" />;
  if (tracks.isError) {
    return (
      <ErrorState error={tracks.error} retry={() => void tracks.refetch()} />
    );
  }

  const trackOptions = tracks.data.map((track) => ({
    value: track.id,
    label: track.title,
  }));
  const openCreate = () => {
    setEditingId(null);
    setForm(emptyEvent(trackId ?? tracks.data[0]?.id ?? null));
    setOpened(true);
  };
  const openEdit = (event: ScheduleEventRead) => {
    setEditingId(event.id);
    setForm(eventForm(event));
    setOpened(true);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const weekly = form.kind === "weekly_call";
    if (
      !form.trackId ||
      !form.title.trim() ||
      (!weekly && !form.startsAt) ||
      (weekly && !form.meetingUrl.trim()) ||
      !validHttpUrl(form.meetingUrl.trim())
    ) {
      return;
    }
    const payload: AdminScheduleEventMutation = {
      track_id: form.trackId,
      kind: form.kind,
      title: form.title.trim(),
      description: form.description.trim() || null,
      meeting_url: form.meetingUrl.trim() || null,
      weekday: weekly ? Number(form.weekday) : null,
      starts_at_time: weekly ? form.startsAtTime || null : null,
      timezone: weekly ? form.timezone : null,
      starts_at: weekly ? null : moscowInputToIso(form.startsAt),
    };
    saveEvent.mutate(
      { eventId: editingId ?? undefined, payload },
      {
        onSuccess: () => {
          setOpened(false);
          notifications.show({
            color: "green",
            message: editingId ? "Событие обновлено" : "Событие добавлено",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const remove = (event: ScheduleEventRead) => {
    if (!window.confirm(`Удалить событие «${event.title}»?`)) return;
    deleteEvent.mutate(event.id, {
      onSuccess: () =>
        notifications.show({ color: "green", message: "Событие удалено" }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const totalPages = Math.max(
    1,
    Math.ceil((query.data?.total ?? 0) / ADMIN_SCHEDULE_PAGE_SIZE),
  );

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Расписание"
          title="События направлений"
          description="Добавляйте регулярные созвоны и разовые встречи сразу для всех учеников Python или Go."
        />
        <Button onClick={openCreate} disabled={tracks.data.length === 0}>
          + Добавить событие
        </Button>
      </Group>

      <Card withBorder>
        <Group align="flex-end">
          <Select
            label="Направление"
            placeholder="Все направления"
            clearable
            data={trackOptions}
            value={trackId}
            onChange={(value) => {
              setTrackId(value);
              setPage(1);
            }}
            w={{ base: "100%", sm: 260 }}
          />
          <Select
            label="Тип события"
            placeholder="Все типы"
            clearable
            data={[
              { value: "weekly_call", label: "Регулярный созвон" },
              { value: "meeting", label: "Разовая встреча" },
            ]}
            value={kind}
            onChange={(value) => {
              setKind((value as ScheduleEventKind | null) ?? null);
              setPage(1);
            }}
            w={{ base: "100%", sm: 260 }}
          />
        </Group>
      </Card>

      {query.isPending ? (
        <LoadingState label="Загружаем расписание…" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <Text c="dimmed">Событий с выбранными фильтрами пока нет.</Text>
      ) : (
        <>
          <Table.ScrollContainer minWidth={900}>
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Направление</Table.Th>
                  <Table.Th>Событие</Table.Th>
                  <Table.Th>Расписание</Table.Th>
                  <Table.Th>Ссылка</Table.Th>
                  <Table.Th aria-label="Действия" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {query.data.items.map((event) => (
                  <Table.Tr key={event.id}>
                    <Table.Td>
                      <Badge variant="light">{event.track.title}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <Text fw={600}>{event.title}</Text>
                        <Badge
                          size="xs"
                          color={event.kind === "meeting" ? "blue" : "yellow"}
                        >
                          {event.kind === "meeting" ? "Встреча" : "Еженедельно"}
                        </Badge>
                      </Group>
                      {event.description && (
                        <Text size="xs" c="dimmed" lineClamp={2}>
                          {event.description}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>{scheduleEventTiming(event)}</Table.Td>
                    <Table.Td>
                      {event.meeting_url ? (
                        <Text
                          component="a"
                          href={event.meeting_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          c="blue"
                        >
                          Открыть
                        </Text>
                      ) : (
                        <Text c="dimmed" size="sm">
                          Не указана
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" justify="flex-end" wrap="nowrap">
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() => openEdit(event)}
                        >
                          Изменить
                        </Button>
                        <Button
                          size="xs"
                          variant="subtle"
                          color="red"
                          loading={deleteEvent.isPending}
                          onClick={() => remove(event)}
                        >
                          Удалить
                        </Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {totalPages > 1 && (
            <Pagination value={page} onChange={setPage} total={totalPages} />
          )}
        </>
      )}

      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={editingId ? "Изменить событие" : "Новое событие направления"}
        centered
      >
        <form onSubmit={submit}>
          <Stack>
            <Select
              label="Направление"
              required
              data={trackOptions}
              value={form.trackId}
              onChange={(value) => updateFormField("trackId", value)}
            />
            <Select
              label="Тип события"
              required
              data={[
                { value: "weekly_call", label: "Регулярный созвон" },
                { value: "meeting", label: "Разовая встреча" },
              ]}
              value={form.kind}
              onChange={(value) =>
                updateFormField(
                  "kind",
                  (value as ScheduleEventKind) ?? "weekly_call",
                )
              }
            />
            <TextInput
              label="Название"
              required
              value={form.title}
              onChange={(event) =>
                updateFormField("title", event.currentTarget.value)
              }
            />

            {form.kind === "weekly_call" ? (
              <>
                <Group grow align="flex-start">
                  <Select
                    label="День недели"
                    required
                    data={WEEKDAY_OPTIONS}
                    value={form.weekday}
                    onChange={(value) =>
                      updateFormField("weekday", value ?? "0")
                    }
                  />
                  <TextInput
                    label="Время"
                    description="Можно оставить пустым"
                    type="time"
                    value={form.startsAtTime}
                    onChange={(event) =>
                      updateFormField("startsAtTime", event.currentTarget.value)
                    }
                  />
                </Group>
                <Select
                  label="Часовой пояс"
                  data={[...TIMEZONE_OPTIONS]}
                  value={form.timezone}
                  onChange={(value) =>
                    updateFormField("timezone", value ?? "Europe/Moscow")
                  }
                />
              </>
            ) : (
              <TextInput
                label="Дата и время встречи"
                description="Указывается по московскому времени"
                required
                type="datetime-local"
                value={form.startsAt}
                onChange={(event) =>
                  updateFormField("startsAt", event.currentTarget.value)
                }
              />
            )}

            <TextInput
              label="Ссылка на онлайн-встречу"
              required={form.kind === "weekly_call"}
              type="url"
              placeholder="https://meet.google.com/..."
              value={form.meetingUrl}
              error={
                form.meetingUrl && !validHttpUrl(form.meetingUrl)
                  ? "Укажите полную ссылку"
                  : undefined
              }
              onChange={(event) =>
                updateFormField("meetingUrl", event.currentTarget.value)
              }
            />
            <Textarea
              label="Описание"
              minRows={3}
              value={form.description}
              onChange={(event) =>
                updateFormField("description", event.currentTarget.value)
              }
            />
            <Group justify="flex-end">
              <Button
                type="button"
                variant="subtle"
                onClick={() => setOpened(false)}
              >
                Отмена
              </Button>
              <Button type="submit" loading={saveEvent.isPending}>
                {editingId ? "Сохранить" : "Добавить событие"}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
