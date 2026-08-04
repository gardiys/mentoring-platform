import {
  Badge,
  Button,
  Card,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminMentorCandidates,
  useAdminMentors,
  useCreateAdminMentor,
  usePromoteAdminStudent,
  useRemoveAdminMentor,
  useReassignAdminMentorStudent,
  useUpdateAdminMentorProfile,
  useUpdateAdminMentorDirections,
} from "../features/admin/mentorQueries";
import { useAdminStudentOptions } from "../features/admin/studentQueries";
import type {
  AdminMentorListItem,
  AdminMentorMutation,
  AdminMentorProfileMutation,
} from "../types/api";
import {
  isValidTelegramUsername,
  normalizeTelegramUsername,
} from "../utils/telegram";

const emptyForm: AdminMentorMutation = {
  telegram_id: 0,
  telegram_username: null,
  first_name: "",
  last_name: null,
  email: null,
  track_ids: [],
};

function fullName(firstName: string, lastName: string | null) {
  return [firstName, lastName].filter(Boolean).join(" ");
}

function MentorCard({
  mentor,
  mentors,
  trackOptions,
  onRemove,
  removePending,
}: {
  mentor: AdminMentorListItem;
  mentors: AdminMentorListItem[];
  trackOptions: Array<{ value: string; label: string }>;
  onRemove: (mentorId: string, name: string) => void;
  removePending: boolean;
}) {
  const name = fullName(mentor.first_name, mentor.last_name);
  const isAdmin = mentor.role === "admin";
  const [trackIds, setTrackIds] = useState(
    mentor.tracks.map((track) => track.id),
  );
  const [targets, setTargets] = useState<Record<string, string | null>>({});
  const [profileOpened, profileModal] = useDisclosure(false);
  const [profile, setProfile] = useState<AdminMentorProfileMutation>({
    first_name: mentor.first_name,
    last_name: mentor.last_name,
    email: mentor.email,
    telegram_username: mentor.telegram_username,
  });
  const updateDirections = useUpdateAdminMentorDirections();
  const updateProfile = useUpdateAdminMentorProfile();
  const reassign = useReassignAdminMentorStudent();

  const openProfile = () => {
    setProfile({
      first_name: mentor.first_name,
      last_name: mentor.last_name,
      email: mentor.email,
      telegram_username: mentor.telegram_username,
    });
    profileModal.open();
  };

  const saveProfile = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !profile.first_name.trim() ||
      !isValidTelegramUsername(profile.telegram_username)
    ) {
      return;
    }
    updateProfile.mutate(
      {
        mentorId: mentor.id,
        payload: {
          first_name: profile.first_name.trim(),
          last_name: profile.last_name?.trim() || null,
          email: profile.email?.trim() || null,
          telegram_username: normalizeTelegramUsername(
            profile.telegram_username,
          ),
        },
      },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: "Данные ментора обновлены",
          });
          profileModal.close();
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const saveDirections = () => {
    if (trackIds.length === 0) return;
    updateDirections.mutate(
      { mentorId: mentor.id, trackIds },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message: "Направления сохранены",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between">
          <Group gap="sm">
            <Title order={2}>{name}</Title>
            {isAdmin && (
              <Badge color="brandYellow" c="brandNavy.9">
                Администратор · ментор
              </Badge>
            )}
          </Group>
          <Badge variant="light">{mentor.student_count} учеников</Badge>
        </Group>
        <Text size="sm">{mentor.email ?? "Email не указан"}</Text>
        <Text size="sm" c="dimmed">
          {mentor.telegram_username
            ? `@${mentor.telegram_username}`
            : mentor.telegram_id
              ? `Telegram ID: ${mentor.telegram_id}`
              : "Telegram не указан"}
        </Text>
        <Button variant="subtle" onClick={openProfile}>
          Редактировать данные
        </Button>
        {isAdmin ? (
          <Stack gap="xs">
            <Text fw={600} size="sm">
              Направления наставничества
            </Text>
            <Group gap="xs">
              {mentor.tracks.map((track) => (
                <Badge key={track.id} variant="light">
                  {track.title}
                </Badge>
              ))}
            </Group>
            <Text size="xs" c="dimmed">
              Администратор может брать учеников со всех доступных направлений.
            </Text>
          </Stack>
        ) : (
          <>
            <MultiSelect
              label="Направления ментора"
              data={trackOptions}
              value={trackIds}
              onChange={setTrackIds}
              searchable
              required
            />
            <Button
              variant="light"
              disabled={trackIds.length === 0}
              loading={updateDirections.isPending}
              onClick={saveDirections}
            >
              Сохранить направления
            </Button>
          </>
        )}

        {mentor.students.length > 0 && (
          <Stack gap="xs">
            <Text fw={700}>Ученики</Text>
            {mentor.students.map((student) => (
              <Card key={student.id} withBorder padding="sm">
                <Stack gap="xs">
                  <Text fw={600} size="sm">
                    {fullName(student.first_name, student.last_name)}
                    {student.telegram_username
                      ? ` · @${student.telegram_username}`
                      : ""}
                  </Text>
                  <Group align="flex-end">
                    <Select
                      label="Переназначить"
                      placeholder="Другой ментор"
                      data={mentors
                        .filter((item) => item.id !== mentor.id)
                        .map((item) => ({
                          value: item.id,
                          label: `${fullName(item.first_name, item.last_name)}${item.role === "admin" ? " · администратор" : ""}`,
                        }))}
                      value={targets[student.id] ?? null}
                      onChange={(value) =>
                        setTargets((current) => ({
                          ...current,
                          [student.id]: value,
                        }))
                      }
                      style={{ flex: 1 }}
                    />
                    <Button
                      size="sm"
                      disabled={!targets[student.id]}
                      loading={reassign.isPending}
                      onClick={() => {
                        const mentorId = targets[student.id];
                        if (!mentorId) return;
                        reassign.mutate(
                          { studentId: student.id, mentorId },
                          {
                            onSuccess: () =>
                              notifications.show({
                                color: "green",
                                message: "Ученик переназначен",
                              }),
                            onError: (error) =>
                              notifications.show({
                                color: "red",
                                message: error.message,
                              }),
                          },
                        );
                      }}
                    >
                      Переназначить
                    </Button>
                  </Group>
                </Stack>
              </Card>
            ))}
          </Stack>
        )}
        {isAdmin ? (
          <Text size="xs" c="dimmed">
            Основная роль администратора сохраняется и не может быть снята из
            этого раздела.
          </Text>
        ) : (
          <>
            <Button
              color="red"
              variant="light"
              disabled={mentor.student_count > 0}
              title={
                mentor.student_count > 0
                  ? "Сначала переназначьте учеников другому ментору"
                  : undefined
              }
              loading={removePending}
              onClick={() => onRemove(mentor.id, name)}
            >
              Убрать из менторов
            </Button>
            {mentor.student_count > 0 && (
              <Text size="xs" c="dimmed">
                Перед удалением роли переназначьте учеников.
              </Text>
            )}
          </>
        )}
        <Modal
          opened={profileOpened}
          onClose={profileModal.close}
          title={`Данные ментора · ${name}`}
          centered
        >
          <form onSubmit={saveProfile}>
            <Stack>
              <TextInput
                required
                label="Имя ментора"
                value={profile.first_name}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setProfile((current) => ({
                    ...current,
                    first_name: value,
                  }));
                }}
              />
              <TextInput
                label="Фамилия ментора"
                value={profile.last_name ?? ""}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setProfile((current) => ({
                    ...current,
                    last_name: value || null,
                  }));
                }}
              />
              <TextInput
                type="email"
                label="Email ментора"
                value={profile.email ?? ""}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setProfile((current) => ({
                    ...current,
                    email: value || null,
                  }));
                }}
              />
              <TextInput
                label="Telegram username ментора"
                description="Можно указать с @ — при сохранении он будет удалён"
                placeholder="username"
                value={profile.telegram_username ?? ""}
                error={
                  isValidTelegramUsername(profile.telegram_username)
                    ? undefined
                    : "От 5 до 32 латинских букв, цифр или _, первый символ — буква"
                }
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setProfile((current) => ({
                    ...current,
                    telegram_username: value || null,
                  }));
                }}
              />
              <Group justify="flex-end">
                <Button
                  type="button"
                  variant="subtle"
                  onClick={profileModal.close}
                >
                  Отмена
                </Button>
                <Button
                  type="submit"
                  loading={updateProfile.isPending}
                  disabled={
                    !profile.first_name.trim() ||
                    !isValidTelegramUsername(profile.telegram_username)
                  }
                >
                  Сохранить данные
                </Button>
              </Group>
            </Stack>
          </form>
        </Modal>
      </Stack>
    </Card>
  );
}

export function AdminMentorsPage() {
  const mentors = useAdminMentors();
  const options = useAdminStudentOptions();
  const [candidateSearch, setCandidateSearch] = useState("");
  const [debouncedCandidateSearch] = useDebouncedValue(
    candidateSearch.trim(),
    250,
  );
  const candidates = useAdminMentorCandidates(debouncedCandidateSearch);
  const create = useCreateAdminMentor();
  const promote = usePromoteAdminStudent();
  const remove = useRemoveAdminMentor();
  const [opened, { open, close }] = useDisclosure(false);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [form, setForm] = useState<AdminMentorMutation>(emptyForm);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !form.telegram_id ||
      !form.first_name.trim() ||
      !isValidTelegramUsername(form.telegram_username) ||
      form.track_ids.length === 0
    )
      return;
    create.mutate(
      {
        ...form,
        first_name: form.first_name.trim(),
        last_name: form.last_name?.trim() || null,
        email: form.email?.trim() || null,
        telegram_username: normalizeTelegramUsername(form.telegram_username),
      },
      {
        onSuccess: () => {
          notifications.show({ color: "green", message: "Ментор добавлен" });
          setForm(emptyForm);
          close();
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const promoteCandidate = () => {
    if (!candidateId) return;
    promote.mutate(candidateId, {
      onSuccess: () => {
        notifications.show({
          color: "green",
          message: "Ученик переведён в менторы",
        });
        setCandidateId(null);
      },
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const removeMentor = (mentorId: string, name: string) => {
    if (!window.confirm(`Убрать роль ментора у ${name}?`)) return;
    remove.mutate(mentorId, {
      onSuccess: () =>
        notifications.show({
          color: "green",
          message: "Пользователь переведён в ученики",
        }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Команда"
          title="Менторы"
          description="Добавляйте менторов, назначайте ученикам администратора и контролируйте распределение."
        />
        <Button onClick={open}>+ Добавить нового ментора</Button>
      </Group>

      <Card withBorder>
        <Stack>
          <Title order={2}>Перевести ученика в менторы</Title>
          <Text size="sm" c="dimmed">
            Учебный прогресс и история собеседований сохранятся. Текущее
            назначение его ментора будет снято.
          </Text>
          <Group align="flex-end">
            <Select
              searchable
              clearable
              label="Ученик"
              placeholder="Выберите пользователя"
              value={candidateId}
              onChange={setCandidateId}
              searchValue={candidateSearch}
              onSearchChange={setCandidateSearch}
              data={(candidates.data ?? []).map((candidate) => ({
                value: candidate.id,
                label: candidate.telegram_username
                  ? `${fullName(candidate.first_name, candidate.last_name)} · @${candidate.telegram_username}`
                  : fullName(candidate.first_name, candidate.last_name),
              }))}
              style={{ flex: 1 }}
              disabled={candidates.isPending || candidates.isError}
            />
            <Button
              disabled={!candidateId}
              loading={promote.isPending}
              onClick={promoteCandidate}
            >
              Перевести
            </Button>
          </Group>
        </Stack>
      </Card>

      {mentors.isPending || options.isPending ? (
        <LoadingState label="Загружаем менторов…" />
      ) : mentors.isError || options.isError ? (
        <ErrorState
          error={mentors.error ?? options.error}
          retry={() => {
            void mentors.refetch();
            void options.refetch();
          }}
        />
      ) : mentors.data.length === 0 ? (
        <Text c="dimmed">Менторы пока не добавлены.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {mentors.data.map((mentor) => (
            <MentorCard
              key={mentor.id}
              mentor={mentor}
              mentors={mentors.data}
              trackOptions={(options.data?.tracks ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              onRemove={removeMentor}
              removePending={remove.isPending}
            />
          ))}
        </SimpleGrid>
      )}

      <Modal opened={opened} onClose={close} title="Новый ментор" centered>
        <form onSubmit={submit}>
          <Stack>
            <TextInput
              required
              label="Имя"
              value={form.first_name}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  first_name: event.currentTarget.value,
                }))
              }
            />
            <MultiSelect
              required
              label="Направления"
              placeholder="Python, Go"
              data={(options.data?.tracks ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              value={form.track_ids}
              onChange={(track_ids) =>
                setForm((current) => ({ ...current, track_ids }))
              }
            />
            <TextInput
              label="Фамилия"
              value={form.last_name ?? ""}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  last_name: event.currentTarget.value || null,
                }))
              }
            />
            <TextInput
              type="email"
              label="Email"
              value={form.email ?? ""}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  email: event.currentTarget.value || null,
                }))
              }
            />
            <NumberInput
              required
              min={1}
              allowDecimal={false}
              label="Telegram ID"
              value={form.telegram_id || ""}
              onChange={(value) =>
                setForm((current) => ({
                  ...current,
                  telegram_id: typeof value === "number" ? value : 0,
                }))
              }
            />
            <TextInput
              label="Telegram username"
              placeholder="username без @"
              value={form.telegram_username ?? ""}
              error={
                isValidTelegramUsername(form.telegram_username)
                  ? undefined
                  : "От 5 до 32 латинских букв, цифр или _, первый символ — буква"
              }
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  telegram_username: event.currentTarget.value || null,
                }))
              }
            />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={close} type="button">
                Отмена
              </Button>
              <Button
                type="submit"
                loading={create.isPending}
                disabled={
                  !form.telegram_id ||
                  !form.first_name.trim() ||
                  !isValidTelegramUsername(form.telegram_username) ||
                  form.track_ids.length === 0
                }
              >
                Добавить
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
