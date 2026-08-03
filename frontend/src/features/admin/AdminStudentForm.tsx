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
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../components/PageHeader";
import { useUnsavedChanges } from "../../hooks/useUnsavedChanges";
import type {
  AdminStudentDetail,
  AdminStudentMentorRead,
  AdminStudentMutation,
  AdminStudentOptions,
} from "../../types/api";
import {
  useCreateAdminStudent,
  useSetAdminStudentAccess,
  useUpdateAdminStudent,
} from "./studentQueries";
import { usePromoteAdminStudent } from "./mentorQueries";

interface Props {
  options: AdminStudentOptions;
  student?: AdminStudentDetail;
}

interface StudentFormState extends Omit<AdminStudentMutation, "telegram_id"> {
  telegram_id: number | "";
}

function todayInputValue() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

function initialForm(student?: AdminStudentDetail): StudentFormState {
  return {
    telegram_id: student?.telegram_id ?? "",
    first_name: student?.first_name ?? "",
    last_name: student?.last_name ?? null,
    email: student?.email ?? null,
    learning_start_date: student?.learning_start_date ?? todayInputValue(),
    mentor_id: student?.mentor?.id ?? null,
    track_ids: student?.tracks.map((track) => track.id) ?? [],
  };
}

function mentorOptionLabel(mentor: AdminStudentMentorRead) {
  const name = [mentor.first_name, mentor.last_name].filter(Boolean).join(" ");
  return mentor.role === "admin" ? `${name} · администратор` : name;
}

export function AdminStudentForm({ options, student }: Props) {
  const [form, setForm] = useState<StudentFormState>(() =>
    initialForm(student),
  );
  const initial = useRef(form);
  const createMutation = useCreateAdminStudent();
  const updateMutation = useUpdateAdminStudent();
  const accessMutation = useSetAdminStudentAccess();
  const promoteMutation = usePromoteAdminStudent();
  const navigate = useNavigate();
  const editing = Boolean(student);
  const pending = createMutation.isPending || updateMutation.isPending;
  const error = createMutation.error ?? updateMutation.error;
  const valid =
    typeof form.telegram_id === "number" &&
    form.telegram_id > 0 &&
    form.first_name.trim().length > 0 &&
    Boolean(form.learning_start_date) &&
    Boolean(form.mentor_id);
  const allowNavigation = useUnsavedChanges(
    JSON.stringify(form) !== JSON.stringify(initial.current),
  );

  const toggleTrack = (trackId: string, checked: boolean) => {
    setForm((current) => ({
      ...current,
      track_ids: checked
        ? [...current.track_ids, trackId]
        : current.track_ids.filter((id) => id !== trackId),
    }));
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || pending || typeof form.telegram_id !== "number") return;
    const payload: AdminStudentMutation = {
      ...form,
      telegram_id: form.telegram_id,
      first_name: form.first_name.trim(),
      last_name: form.last_name?.trim() || null,
      email: form.email?.trim() || null,
    };
    const handlers = {
      onSuccess: () => {
        allowNavigation();
        notifications.show({
          color: "green",
          message: editing ? "Данные ученика обновлены" : "Ученик добавлен",
        });
        navigate("/admin/students");
      },
      onError: (mutationError: Error) =>
        notifications.show({ color: "red", message: mutationError.message }),
    };
    if (student) {
      updateMutation.mutate({ id: student.id, payload }, handlers);
    } else {
      createMutation.mutate(payload, handlers);
    }
  };

  const changeAccess = () => {
    if (!student) return;
    const isActive = !student.is_active;
    if (
      !isActive &&
      !window.confirm(
        "Закрыть ученику доступ? Прогресс и назначенные треки сохранятся.",
      )
    ) {
      return;
    }
    accessMutation.mutate(
      { id: student.id, isActive },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message: isActive ? "Доступ открыт" : "Доступ закрыт",
          }),
        onError: (mutationError) =>
          notifications.show({ color: "red", message: mutationError.message }),
      },
    );
  };

  const promoteToMentor = () => {
    if (!student) return;
    if (
      !window.confirm(
        "Перевести ученика в менторы? Его прогресс сохранится, а назначение текущего ментора будет снято.",
      )
    ) {
      return;
    }
    promoteMutation.mutate(student.id, {
      onSuccess: () => {
        allowNavigation();
        notifications.show({
          color: "green",
          message: "Ученик переведён в менторы",
        });
        navigate("/admin/mentors");
      },
      onError: (mutationError) =>
        notifications.show({ color: "red", message: mutationError.message }),
    });
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow={editing ? "Ученики · редактирование" : "Ученики · новый"}
          title={editing ? `Ученик ${student?.first_name}` : "Новый ученик"}
          description="Укажите данные Telegram и выберите доступные ученику направления обучения."
        />

        {error && (
          <Alert color="red" title="Не удалось сохранить ученика">
            {error.message}
          </Alert>
        )}

        {student && (
          <Card withBorder>
            <Group justify="space-between" align="center">
              <div>
                <Group gap="sm">
                  <Title order={2}>Доступ к платформе</Title>
                  <Badge
                    color={student.is_active ? "green" : "red"}
                    variant="light"
                  >
                    {student.is_active ? "Открыт" : "Закрыт"}
                  </Badge>
                </Group>
                <Text c="dimmed" size="sm" mt={4}>
                  При закрытии данные, прогресс и назначенные треки сохраняются.
                </Text>
              </div>
              <Button
                type="button"
                color={student.is_active ? "red" : "green"}
                variant="light"
                loading={accessMutation.isPending}
                onClick={changeAccess}
              >
                {student.is_active ? "Закрыть доступ" : "Открыть доступ"}
              </Button>
              <Button
                type="button"
                variant="light"
                loading={promoteMutation.isPending}
                onClick={promoteToMentor}
              >
                Перевести в менторы
              </Button>
            </Group>
          </Card>
        )}

        <Card withBorder>
          <Stack>
            <Title order={2}>Личные данные</Title>
            <Group grow align="flex-start">
              <TextInput
                label="Имя"
                required
                value={form.first_name}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setForm((current) => ({ ...current, first_name: value }));
                }}
              />
              <TextInput
                label="Фамилия"
                value={form.last_name ?? ""}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setForm((current) => ({
                    ...current,
                    last_name: value || null,
                  }));
                }}
              />
            </Group>
            <TextInput
              label="Email"
              type="email"
              value={form.email ?? ""}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({
                  ...current,
                  email: value || null,
                }));
              }}
            />
            <NumberInput
              label="Telegram ID"
              description="Числовой ID пользователя — нужен для входа через Telegram и Mini App"
              required
              min={1}
              allowDecimal={false}
              value={form.telegram_id}
              onChange={(value) =>
                setForm((current) => ({
                  ...current,
                  telegram_id: typeof value === "number" ? value : "",
                }))
              }
            />
            <Select
              label="Ментор"
              description="У каждого ученика может быть только один ментор"
              placeholder="Выберите ментора"
              required
              searchable
              value={form.mentor_id}
              onChange={(value) =>
                setForm((current) => ({ ...current, mentor_id: value }))
              }
              data={options.mentors.map((mentor) => ({
                value: mentor.id,
                label: mentorOptionLabel(mentor),
              }))}
            />
            <TextInput
              label="Дата начала обучения"
              description="От этой даты рассчитываются дедлайны во всех назначенных роадмапах"
              type="date"
              required
              value={form.learning_start_date ?? ""}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({
                  ...current,
                  learning_start_date: value || null,
                }));
              }}
            />
          </Stack>
        </Card>

        <Card withBorder>
          <Stack>
            <div>
              <Title order={2}>Треки обучения</Title>
              <Text c="dimmed" size="sm" mt={4}>
                Можно назначить несколько направлений. Изменения применяются
                сразу после сохранения.
              </Text>
            </div>
            <Divider />
            {options.tracks.length === 0 ? (
              <Text c="dimmed">Сначала создайте хотя бы один трек.</Text>
            ) : (
              options.tracks.map((track) => (
                <Paper key={track.id} withBorder p="md">
                  <Checkbox
                    checked={form.track_ids.includes(track.id)}
                    onChange={(event) =>
                      toggleTrack(track.id, event.currentTarget.checked)
                    }
                    label={
                      <Group gap="sm">
                        <Text fw={600}>{track.title}</Text>
                        <Badge
                          size="sm"
                          color={track.is_published ? "brandYellow" : "gray"}
                          c={track.is_published ? "brandNavy.9" : undefined}
                        >
                          {track.is_published ? "Опубликован" : "Черновик"}
                        </Badge>
                      </Group>
                    }
                  />
                </Paper>
              ))
            )}
          </Stack>
        </Card>

        <Group justify="flex-end">
          <Button
            type="button"
            variant="subtle"
            onClick={() => navigate("/admin/students")}
          >
            Отмена
          </Button>
          <Button type="submit" loading={pending} disabled={!valid}>
            {editing ? "Сохранить изменения" : "Добавить ученика"}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
