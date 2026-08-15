import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useCancelMentorWeeklyCallReschedule,
  useDeleteMentorOneOffActivity,
  useDeleteMentorWeeklyCall,
  useMentorProfile,
  useRescheduleMentorWeeklyCall,
  useSaveMentorOneOffActivity,
  useSaveMentorWeeklyCall,
  useUpdateMentorProfile,
} from "../features/schedule/queries";
import type {
  MentorOneOffActivityMutation,
  MentorProfileRead,
  MentorWeeklyCallMutation,
  ScheduleEventKind,
  ScheduleEventRead,
} from "../types/api";
import {
  TIMEZONE_OPTIONS,
  WEEKDAY_OPTIONS,
  formatMoscowDateTime,
  isoToMoscowInput,
  moscowInputToIso,
  scheduleEventTiming,
} from "../utils/schedule";

interface ScheduleFormState {
  kind: ScheduleEventKind;
  trackId: string | null;
  title: string;
  description: string;
  weekday: string;
  startsAtTime: string;
  timezone: string;
  startsAt: string;
  meetingUrl: string;
}

function emptyScheduleForm(trackId: string | null): ScheduleFormState {
  return {
    kind: "weekly_call",
    trackId,
    title: "",
    description: "",
    weekday: "0",
    startsAtTime: "",
    timezone: "Europe/Moscow",
    startsAt: "",
    meetingUrl: "",
  };
}

function scheduleForm(event: ScheduleEventRead): ScheduleFormState {
  return {
    kind: event.kind,
    trackId: event.track.id,
    title: event.title,
    description: event.description ?? "",
    weekday: String(event.weekday ?? 0),
    startsAtTime: event.starts_at_time?.slice(0, 5) ?? "",
    timezone: event.timezone ?? "Europe/Moscow",
    startsAt: isoToMoscowInput(event.starts_at),
    meetingUrl: event.meeting_url ?? "",
  };
}

function validHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:";
  } catch {
    return false;
  }
}

function isFutureMoscowInput(value: string) {
  if (!value) return false;
  const timestamp = Date.parse(moscowInputToIso(value));
  return Number.isFinite(timestamp) && timestamp > Date.now();
}

function moscowInputMin() {
  return isoToMoscowInput(new Date().toISOString());
}

function canCancelEventReschedule(event: ScheduleEventRead) {
  const now = Date.now();
  return Boolean(
    event.is_rescheduled &&
    event.rescheduled_from &&
    event.rescheduled_to &&
    Date.parse(event.rescheduled_from) > now &&
    Date.parse(event.rescheduled_to) > now,
  );
}

function MentorProfileContent({ profile }: { profile: MentorProfileRead }) {
  const [consultationUrl, setConsultationUrl] = useState(
    profile.consultation_url ?? "",
  );
  const [groupCalendarUrls, setGroupCalendarUrls] = useState<
    Record<string, string>
  >(() =>
    Object.fromEntries(
      profile.group_calendars.map((calendar) => [
        calendar.track.id,
        calendar.calendar_url,
      ]),
    ),
  );
  const [eventModalOpened, setEventModalOpened] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [eventSubmitted, setEventSubmitted] = useState(false);
  const [form, setForm] = useState<ScheduleFormState>(() =>
    emptyScheduleForm(profile.tracks[0]?.id ?? null),
  );
  const [rescheduleEvent, setRescheduleEvent] =
    useState<ScheduleEventRead | null>(null);
  const [rescheduleStartsAt, setRescheduleStartsAt] = useState("");
  const [rescheduleSubmitted, setRescheduleSubmitted] = useState(false);
  const updateProfile = useUpdateMentorProfile();
  const saveWeeklyCall = useSaveMentorWeeklyCall();
  const deleteWeeklyCall = useDeleteMentorWeeklyCall();
  const saveOneOffActivity = useSaveMentorOneOffActivity();
  const deleteOneOffActivity = useDeleteMentorOneOffActivity();
  const rescheduleWeeklyCall = useRescheduleMentorWeeklyCall();
  const cancelReschedule = useCancelMentorWeeklyCallReschedule();
  const oneOffActivities = profile.one_off_activities ?? [];
  const scheduleEvents = [...profile.weekly_calls, ...oneOffActivities];

  function updateFormField<Key extends keyof ScheduleFormState>(
    field: Key,
    value: ScheduleFormState[Key],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  const openCreate = () => {
    setEditingId(null);
    setEventSubmitted(false);
    setForm(emptyScheduleForm(profile.tracks[0]?.id ?? null));
    setEventModalOpened(true);
  };

  const openEdit = (event: ScheduleEventRead) => {
    setEditingId(event.id);
    setEventSubmitted(false);
    setForm(scheduleForm(event));
    setEventModalOpened(true);
  };

  const openReschedule = (event: ScheduleEventRead) => {
    setRescheduleEvent(event);
    setRescheduleSubmitted(false);
    setRescheduleStartsAt(
      isoToMoscowInput(
        event.rescheduled_to ??
          event.next_occurrence_at ??
          event.regular_next_occurrence_at,
      ),
    );
  };

  const saveConsultation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const consultation = consultationUrl.trim();
    const calendars = profile.tracks.flatMap((track) => {
      const calendarUrl = (groupCalendarUrls[track.id] ?? "").trim();
      return calendarUrl
        ? [{ track_id: track.id, calendar_url: calendarUrl }]
        : [];
    });
    if (
      (consultation && !validHttpUrl(consultation)) ||
      calendars.some((calendar) => !validHttpUrl(calendar.calendar_url))
    ) {
      return;
    }
    updateProfile.mutate(
      {
        consultation_url: consultation || null,
        group_calendars: calendars,
      },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message: "Профиль ментора сохранён",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const saveScheduleEvent = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setEventSubmitted(true);
    const title = form.title.trim();
    const meetingUrl = form.meetingUrl.trim();
    if (!form.trackId || !title) return;

    const mutationOptions = {
      onSuccess: () => {
        setEventModalOpened(false);
        notifications.show({
          color: "green",
          message: editingId ? "Событие обновлено" : "Событие добавлено",
        });
      },
      onError: (error: Error) =>
        notifications.show({ color: "red", message: error.message }),
    };

    if (form.kind === "weekly_call") {
      if (!validHttpUrl(meetingUrl)) return;
      const payload: MentorWeeklyCallMutation = {
        track_id: form.trackId,
        title,
        description: form.description.trim() || null,
        weekday: Number(form.weekday),
        starts_at_time: form.startsAtTime || null,
        timezone: form.timezone,
        meeting_url: meetingUrl,
      };
      saveWeeklyCall.mutate(
        { eventId: editingId ?? undefined, payload },
        mutationOptions,
      );
      return;
    }

    if (
      !isFutureMoscowInput(form.startsAt) ||
      (meetingUrl && !validHttpUrl(meetingUrl))
    ) {
      return;
    }
    const payload: MentorOneOffActivityMutation = {
      track_id: form.trackId,
      title,
      description: form.description.trim() || null,
      starts_at: moscowInputToIso(form.startsAt),
      meeting_url: meetingUrl || null,
    };
    saveOneOffActivity.mutate(
      { eventId: editingId ?? undefined, payload },
      mutationOptions,
    );
  };

  const removeEvent = (event: ScheduleEventRead) => {
    const kind = event.kind === "meeting" ? "разовую встречу" : "созвон";
    if (!window.confirm(`Удалить ${kind} «${event.title}»?`)) return;
    const mutation =
      event.kind === "meeting" ? deleteOneOffActivity : deleteWeeklyCall;
    mutation.mutate(event.id, {
      onSuccess: () =>
        notifications.show({ color: "green", message: "Событие удалено" }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const saveReschedule = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRescheduleSubmitted(true);
    if (!rescheduleEvent || !isFutureMoscowInput(rescheduleStartsAt)) return;
    rescheduleWeeklyCall.mutate(
      {
        eventId: rescheduleEvent.id,
        startsAt: moscowInputToIso(rescheduleStartsAt),
      },
      {
        onSuccess: () => {
          setRescheduleEvent(null);
          notifications.show({
            color: "green",
            message: "Ближайший созвон перенесён",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const cancelEventReschedule = (event: ScheduleEventRead) => {
    if (!window.confirm(`Отменить перенос созвона «${event.title}»?`)) return;
    cancelReschedule.mutate(event.id, {
      onSuccess: () =>
        notifications.show({ color: "green", message: "Перенос отменён" }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const eventDateError =
    form.kind === "meeting" &&
    (Boolean(form.startsAt) || eventSubmitted) &&
    !isFutureMoscowInput(form.startsAt)
      ? "Выберите будущую дату и время по Москве"
      : undefined;
  const rescheduleDateError =
    (Boolean(rescheduleStartsAt) || rescheduleSubmitted) &&
    !isFutureMoscowInput(rescheduleStartsAt)
      ? "Выберите будущую дату и время по Москве"
      : undefined;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Ментор · Публичный профиль"
        title="Профиль ментора"
        description="Добавьте запись на консультацию, отдельные календари и расписание для каждого направления — ученики увидят только свои направления во вкладке «Мой ментор»."
      />

      <Card withBorder component="form" onSubmit={saveConsultation}>
        <Stack>
          <Title order={2}>Ссылки для учеников</Title>
          <Text size="sm" c="dimmed">
            Подойдёт ссылка на Calendly, YClients, Telegram или другую страницу
            записи.
          </Text>
          <TextInput
            label="Ссылка для записи"
            type="url"
            placeholder="https://..."
            value={consultationUrl}
            error={
              consultationUrl && !validHttpUrl(consultationUrl)
                ? "Укажите полную ссылку с https://"
                : undefined
            }
            onChange={(event) => setConsultationUrl(event.currentTarget.value)}
          />
          {profile.tracks.length === 0 ? (
            <Alert color="blue">
              После назначения направления здесь появится отдельное поле для его
              календаря.
            </Alert>
          ) : (
            profile.tracks.map((track) => {
              const calendarUrl = groupCalendarUrls[track.id] ?? "";
              return (
                <TextInput
                  key={track.id}
                  label={`Календарь общих созвонов · ${track.title}`}
                  description={`Ссылка на календарь группы направления ${track.title}`}
                  type="url"
                  placeholder="https://calendar.google.com/..."
                  value={calendarUrl}
                  error={
                    calendarUrl && !validHttpUrl(calendarUrl)
                      ? "Укажите полную ссылку с https://"
                      : undefined
                  }
                  onChange={(event) => {
                    const nextCalendarUrl = event.currentTarget.value;
                    setGroupCalendarUrls((current) => ({
                      ...current,
                      [track.id]: nextCalendarUrl,
                    }));
                  }}
                />
              );
            })
          )}
          <Group justify="flex-end">
            <Button type="submit" loading={updateProfile.isPending}>
              Сохранить ссылки
            </Button>
          </Group>
        </Stack>
      </Card>

      <Card withBorder>
        <Stack>
          <Group justify="space-between" align="flex-end">
            <div>
              <Title order={2}>Созвоны и встречи</Title>
              <Text size="sm" c="dimmed" mt={4}>
                Событие увидят только ваши ученики выбранного направления.
              </Text>
            </div>
            <Button onClick={openCreate} disabled={profile.tracks.length === 0}>
              + Добавить событие
            </Button>
          </Group>

          {profile.tracks.length === 0 && (
            <Alert color="blue">
              Сначала администратор должен назначить вам хотя бы одно
              направление.
            </Alert>
          )}

          {scheduleEvents.length === 0 ? (
            <Text c="dimmed">Созвоны и встречи пока не добавлены.</Text>
          ) : (
            <Table.ScrollContainer minWidth={1040}>
              <Table verticalSpacing="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Тип</Table.Th>
                    <Table.Th>Направление</Table.Th>
                    <Table.Th>Тема</Table.Th>
                    <Table.Th>Расписание</Table.Th>
                    <Table.Th>Ссылка</Table.Th>
                    <Table.Th aria-label="Действия" />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {scheduleEvents.map((event) => (
                    <Table.Tr key={event.id}>
                      <Table.Td>
                        <Badge
                          variant="light"
                          color={event.kind === "meeting" ? "violet" : "blue"}
                        >
                          {event.kind === "meeting" ? "Разовая" : "Регулярная"}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{event.track.title}</Table.Td>
                      <Table.Td>
                        <Text fw={600}>{event.title}</Text>
                        {event.description && (
                          <Text size="xs" c="dimmed" lineClamp={2}>
                            {event.description}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        {event.kind === "weekly_call" ? (
                          <Stack gap={3}>
                            <Text size="sm">
                              Регулярно: {scheduleEventTiming(event)}
                            </Text>
                            {event.is_rescheduled &&
                              event.next_occurrence_at && (
                                <>
                                  <Badge
                                    color="orange"
                                    variant="light"
                                    size="sm"
                                  >
                                    Ближайший перенесён
                                  </Badge>
                                  <Text size="xs" c="dimmed">
                                    Новая дата:{" "}
                                    {formatMoscowDateTime(
                                      event.next_occurrence_at,
                                    )}
                                  </Text>
                                </>
                              )}
                          </Stack>
                        ) : (
                          scheduleEventTiming(event)
                        )}
                      </Table.Td>
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
                          <Text size="sm" c="dimmed">
                            Не указана
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs" justify="flex-end">
                          <Button
                            size="xs"
                            variant="light"
                            onClick={() => openEdit(event)}
                          >
                            Изменить
                          </Button>
                          {event.kind === "weekly_call" && (
                            <Button
                              size="xs"
                              variant="light"
                              color="orange"
                              disabled={!event.regular_next_occurrence_at}
                              title={
                                event.regular_next_occurrence_at
                                  ? undefined
                                  : "Сначала укажите время регулярного созвона"
                              }
                              onClick={() => openReschedule(event)}
                            >
                              Перенести ближайший
                            </Button>
                          )}
                          {event.kind === "weekly_call" &&
                            canCancelEventReschedule(event) && (
                              <Button
                                size="xs"
                                variant="subtle"
                                color="orange"
                                loading={cancelReschedule.isPending}
                                onClick={() => cancelEventReschedule(event)}
                              >
                                Отменить перенос
                              </Button>
                            )}
                          <Button
                            size="xs"
                            variant="subtle"
                            color="red"
                            loading={
                              deleteWeeklyCall.isPending ||
                              deleteOneOffActivity.isPending
                            }
                            onClick={() => removeEvent(event)}
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
          )}
        </Stack>
      </Card>

      <Modal
        opened={eventModalOpened}
        onClose={() => setEventModalOpened(false)}
        title={editingId ? "Изменить событие" : "Новое событие"}
        centered
      >
        <form onSubmit={saveScheduleEvent}>
          <Stack>
            <Select
              label="Тип"
              required
              disabled={Boolean(editingId)}
              data={[
                { value: "weekly_call", label: "Регулярный созвон" },
                { value: "meeting", label: "Разовая встреча" },
              ]}
              value={form.kind}
              onChange={(value) =>
                updateFormField(
                  "kind",
                  (value as ScheduleEventKind | null) ?? "weekly_call",
                )
              }
            />
            <Select
              label="Направление"
              required
              data={profile.tracks.map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              value={form.trackId}
              onChange={(value) => updateFormField("trackId", value)}
            />
            <TextInput
              label="Тема"
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
                  searchable
                  value={form.timezone}
                  onChange={(value) =>
                    updateFormField("timezone", value ?? "Europe/Moscow")
                  }
                />
              </>
            ) : (
              <TextInput
                label="Дата и время"
                description="По московскому времени (UTC+3)"
                required
                type="datetime-local"
                min={moscowInputMin()}
                value={form.startsAt}
                error={eventDateError}
                onChange={(event) =>
                  updateFormField("startsAt", event.currentTarget.value)
                }
              />
            )}
            <TextInput
              label="Ссылка на онлайн-встречу"
              description={
                form.kind === "meeting" ? "Можно добавить позже" : undefined
              }
              required={form.kind === "weekly_call"}
              type="url"
              placeholder="https://meet.google.com/..."
              value={form.meetingUrl}
              error={
                ((form.kind === "weekly_call" && eventSubmitted) ||
                  form.meetingUrl) &&
                !validHttpUrl(form.meetingUrl)
                  ? "Укажите полную ссылку с https://"
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
                onClick={() => setEventModalOpened(false)}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                loading={
                  saveWeeklyCall.isPending || saveOneOffActivity.isPending
                }
              >
                {editingId ? "Сохранить" : "Добавить событие"}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal
        opened={Boolean(rescheduleEvent)}
        onClose={() => setRescheduleEvent(null)}
        title="Перенести ближайший созвон"
        centered
      >
        <form onSubmit={saveReschedule}>
          <Stack>
            {rescheduleEvent?.regular_next_occurrence_at && (
              <Alert color="blue">
                По расписанию:{" "}
                {formatMoscowDateTime(
                  rescheduleEvent.regular_next_occurrence_at,
                )}
              </Alert>
            )}
            <TextInput
              label="Новая дата и время"
              description="По московскому времени (UTC+3). Перенос действует только на ближайший созвон."
              required
              type="datetime-local"
              min={moscowInputMin()}
              value={rescheduleStartsAt}
              error={rescheduleDateError}
              onChange={(event) =>
                setRescheduleStartsAt(event.currentTarget.value)
              }
            />
            <Group justify="flex-end">
              <Button
                type="button"
                variant="subtle"
                onClick={() => setRescheduleEvent(null)}
              >
                Отмена
              </Button>
              <Button type="submit" loading={rescheduleWeeklyCall.isPending}>
                Сохранить перенос
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}

export function MentorProfilePage() {
  const query = useMentorProfile();
  if (query.isPending) return <LoadingState label="Загружаем профиль…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }
  return (
    <MentorProfileContent key={query.data.mentor_id} profile={query.data} />
  );
}
