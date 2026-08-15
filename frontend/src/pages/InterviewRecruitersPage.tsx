import {
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import { useInterviewCatalogDirections } from "../features/interviews/catalogQueries";
import {
  useDeleteRecruiterFeedback,
  useOpenRecruiterContact,
  useRecruiters,
  useSetRecruiterFeedback,
} from "../features/interviews/recruiterQueries";
import type {
  RecruiterContactRead,
  RecruiterFeedbackKind,
  RecruiterSort,
} from "../types/api";
import { openExternalResource } from "../utils/openExternalResource";

const issueOptions: { value: RecruiterFeedbackKind; label: string }[] = [
  { value: "ignores", label: "Не отвечает / игнорирует" },
  { value: "no_longer_works", label: "Больше не работает рекрутером" },
  { value: "account_missing", label: "Telegram-аккаунта не существует" },
  { value: "other", label: "Другая причина" },
];

const feedbackLabels: Record<RecruiterFeedbackKind, string> = {
  helpful: "Активно отвечает",
  ignores: "Не отвечает",
  no_longer_works: "Больше не работает",
  account_missing: "Аккаунт не существует",
  other: "Есть замечание",
};

const feedbackAuthorRoles = {
  student: "Ученик",
  mentor: "Ментор",
  admin: "Администратор",
} as const;

function formatLastContact(value: string | null) {
  if (!value) return "Контакт ещё не открывали";
  return `Последний переход: ${new Date(value).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function InterviewRecruitersPage() {
  const me = useMe();
  const directions = useInterviewCatalogDirections();
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search.trim(), 350);
  const [trackId, setTrackId] = useState<string | null>(null);
  const [contactFilter, setContactFilter] = useState<string | null>(null);
  const [sort, setSort] = useState<RecruiterSort>("recommended");
  const [page, setPage] = useState(1);
  const [reportedRecruiter, setReportedRecruiter] =
    useState<RecruiterContactRead | null>(null);
  const [issueKind, setIssueKind] = useState<RecruiterFeedbackKind>("ignores");
  const [reason, setReason] = useState("");
  const contacted =
    contactFilter === "contacted"
      ? true
      : contactFilter === "not_contacted"
        ? false
        : null;
  const recruiters = useRecruiters(
    debouncedSearch,
    trackId,
    contacted,
    sort,
    page,
  );
  const openContact = useOpenRecruiterContact();
  const setFeedback = useSetRecruiterFeedback();
  const deleteFeedback = useDeleteRecruiterFeedback();
  const canRate =
    me.data?.role === "student" ||
    me.data?.role === "mentor" ||
    me.data?.role === "admin";

  useEffect(() => setPage(1), [debouncedSearch, trackId, contactFilter, sort]);

  const handleContact = async (recruiterId: string) => {
    try {
      await openExternalResource(
        openContact.mutateAsync(recruiterId).then((result) => result.url),
      );
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось открыть контакт рекрутера",
      });
    }
  };

  const markHelpful = async (recruiterId: string) => {
    try {
      await setFeedback.mutateAsync({
        recruiterId,
        payload: { kind: "helpful", reason: null },
      });
      notifications.show({
        color: "green",
        message: "Спасибо, оценка сохранена",
      });
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось сохранить оценку",
      });
    }
  };

  const submitIssue = async () => {
    if (!reportedRecruiter) return;
    if (issueKind === "other" && !reason.trim()) {
      notifications.show({
        color: "yellow",
        message: "Опишите, что случилось",
      });
      return;
    }
    try {
      await setFeedback.mutateAsync({
        recruiterId: reportedRecruiter.id,
        payload: { kind: issueKind, reason: reason.trim() || null },
      });
      setReportedRecruiter(null);
      setReason("");
      notifications.show({ message: "Информация о контакте сохранена" });
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось сохранить отметку",
      });
    }
  };

  const clearFeedback = async (recruiterId: string) => {
    try {
      await deleteFeedback.mutateAsync(recruiterId);
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось удалить оценку",
      });
    }
  };

  if (me.isPending || directions.isPending) {
    return <LoadingState label="Загружаем контакты рекрутеров…" />;
  }
  if (me.isError || directions.isError) {
    return (
      <ErrorState
        error={me.error ?? directions.error}
        retry={() => {
          void me.refetch();
          void directions.refetch();
        }}
      />
    );
  }

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Собеседования · база контактов"
        title="Рекрутеры"
        description="Ищите контакты по Telegram или компании. Переходы и оценки помогают понять, какие контакты действительно актуальны."
      />

      <Group>
        <Button component={Link} to="/interviews" variant="light">
          ← К собеседованиям
        </Button>
        <Button component={Link} to="/interviews/catalog" variant="subtle">
          Каталог записей
        </Button>
      </Group>

      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <TextInput
            label="Поиск"
            placeholder="@username или название компании"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
          />
          <Select
            label="Направление"
            placeholder="Все доступные направления"
            clearable
            value={trackId}
            onChange={setTrackId}
            data={(directions.data ?? []).map((track) => ({
              value: track.id,
              label: track.title,
            }))}
          />
          {canRate && (
            <Select
              label="Мои контакты"
              placeholder="Все рекрутеры"
              clearable
              value={contactFilter}
              onChange={setContactFilter}
              data={[
                { value: "not_contacted", label: "Ещё не писал" },
                { value: "contacted", label: "Уже открывал контакт" },
              ]}
            />
          )}
          <Select
            label="Сортировка"
            value={sort}
            allowDeselect={false}
            onChange={(value) =>
              setSort((value as RecruiterSort | null) ?? "recommended")
            }
            data={[
              { value: "recommended", label: "Сначала рекомендуемые" },
              { value: "most_helpful", label: "Больше хороших отзывов" },
              { value: "most_contacted", label: "Больше контактов" },
              { value: "recently_contacted", label: "Недавние контакты" },
              { value: "username", label: "По Telegram username" },
            ]}
          />
        </SimpleGrid>
      </Card>

      {recruiters.isPending ? (
        <LoadingState label="Ищем рекрутеров…" />
      ) : recruiters.isError ? (
        <ErrorState
          error={recruiters.error}
          retry={() => void recruiters.refetch()}
        />
      ) : recruiters.data.items.length === 0 ? (
        <Card withBorder>
          <Title order={3}>Контактов не найдено</Title>
          <Text c="dimmed" mt="xs">
            Попробуйте изменить запрос или направление. Контакты появляются
            здесь после добавления Telegram username рекрутера в трек
            собеседований.
          </Text>
        </Card>
      ) : (
        <>
          <Group justify="space-between">
            <Text c="dimmed">
              Найдено компаний: <b>{recruiters.data.total}</b>
            </Text>
          </Group>
          <Stack gap="xl">
            {recruiters.data.items.map((companyGroup) => (
              <Stack key={companyGroup.company.id} gap="md">
                <Group justify="space-between">
                  <div>
                    <Text className="brand-eyebrow">Компания</Text>
                    <Title order={2}>{companyGroup.company.name}</Title>
                  </div>
                  <Badge variant="light">
                    {companyGroup.recruiters.length} рекрутеров
                  </Badge>
                </Group>
                <SimpleGrid cols={{ base: 1, lg: 2 }}>
                  {companyGroup.recruiters.map((recruiter) => {
                    const issueCount =
                      recruiter.ignores_count +
                      recruiter.no_longer_works_count +
                      recruiter.account_missing_count +
                      recruiter.other_issue_count;
                    return (
                      <Card key={recruiter.id} withBorder>
                        <Stack h="100%" gap="md">
                          <Group justify="space-between" align="flex-start">
                            <div>
                              <Text className="brand-eyebrow">
                                Telegram-контакт
                              </Text>
                              <Title order={3}>
                                @{recruiter.telegram_username}
                              </Title>
                            </div>
                            {recruiter.helpful_count > 0 && (
                              <Badge color="green" variant="light">
                                Отвечает · {recruiter.helpful_count}
                              </Badge>
                            )}
                          </Group>

                          <Group gap="xs">
                            {recruiter.tracks.map((track) => (
                              <Badge key={track.id} variant="outline">
                                {track.title}
                              </Badge>
                            ))}
                          </Group>

                          {recruiter.has_contacted && (
                            <Badge color="blue" variant="light" w="fit-content">
                              Вы открывали этот контакт
                            </Badge>
                          )}

                          <Card withBorder padding="sm">
                            <Group justify="space-between" align="flex-start">
                              <div>
                                <Text fw={700}>
                                  {recruiter.total_contact_opens} пользователей
                                  открыли контакт
                                </Text>
                                <Text size="xs" c="dimmed">
                                  Из них учеников:{" "}
                                  {recruiter.students_contacted_count}
                                </Text>
                              </div>
                              <Text size="xs" c="dimmed" ta="right">
                                {formatLastContact(recruiter.last_contacted_at)}
                              </Text>
                            </Group>
                          </Card>

                          {issueCount > 0 && (
                            <Group gap="xs">
                              {recruiter.ignores_count > 0 && (
                                <Badge color="yellow" variant="light">
                                  Не отвечает · {recruiter.ignores_count}
                                </Badge>
                              )}
                              {recruiter.no_longer_works_count > 0 && (
                                <Badge color="orange" variant="light">
                                  Больше не работает ·{" "}
                                  {recruiter.no_longer_works_count}
                                </Badge>
                              )}
                              {recruiter.account_missing_count > 0 && (
                                <Badge color="red" variant="light">
                                  Аккаунт не существует ·{" "}
                                  {recruiter.account_missing_count}
                                </Badge>
                              )}
                              {recruiter.other_issue_count > 0 && (
                                <Badge color="gray" variant="light">
                                  Другие замечания ·{" "}
                                  {recruiter.other_issue_count}
                                </Badge>
                              )}
                            </Group>
                          )}
                          {recruiter.issue_comments.length > 0 && (
                            <Card withBorder padding="sm">
                              <Stack gap="sm">
                                <Text fw={700} size="sm">
                                  Комментарии к проблемам
                                </Text>
                                {recruiter.issue_comments.map((comment) => (
                                  <Stack
                                    key={`${comment.author_id}-${comment.updated_at}`}
                                    gap={4}
                                  >
                                    <Group gap="xs">
                                      <Badge color="yellow" variant="light">
                                        {feedbackLabels[comment.kind]}
                                      </Badge>
                                      <Text size="xs" c="dimmed">
                                        {comment.author_first_name}
                                        {comment.author_telegram_username
                                          ? ` · @${comment.author_telegram_username}`
                                          : ""}{" "}
                                        ·{" "}
                                        {
                                          feedbackAuthorRoles[
                                            comment.author_role
                                          ]
                                        }
                                      </Text>
                                    </Group>
                                    <Text size="sm">{comment.reason}</Text>
                                  </Stack>
                                ))}
                                {recruiter.issue_comments_total >
                                  recruiter.issue_comments.length && (
                                  <Text size="xs" c="dimmed">
                                    Показаны последние{" "}
                                    {recruiter.issue_comments.length} из{" "}
                                    {recruiter.issue_comments_total}{" "}
                                    комментариев
                                  </Text>
                                )}
                              </Stack>
                            </Card>
                          )}
                          {recruiter.my_feedback && (
                            <Group gap="xs">
                              <Text size="sm" c="dimmed">
                                Ваша отметка:{" "}
                                {feedbackLabels[recruiter.my_feedback.kind]}
                              </Text>
                              <Button
                                size="compact-xs"
                                variant="subtle"
                                color="gray"
                                onClick={() => void clearFeedback(recruiter.id)}
                                loading={deleteFeedback.isPending}
                              >
                                Убрать
                              </Button>
                            </Group>
                          )}

                          <Stack gap="xs" mt="auto">
                            <Button
                              fullWidth
                              onClick={() => void handleContact(recruiter.id)}
                              loading={
                                openContact.isPending &&
                                openContact.variables === recruiter.id
                              }
                            >
                              Написать в Telegram ↗
                            </Button>
                            {canRate && (
                              <SimpleGrid cols={{ base: 1, xs: 2 }}>
                                <Button
                                  variant={
                                    recruiter.my_feedback?.kind === "helpful"
                                      ? "filled"
                                      : "light"
                                  }
                                  color="green"
                                  onClick={() => void markHelpful(recruiter.id)}
                                  loading={setFeedback.isPending}
                                >
                                  Хороший контакт
                                </Button>
                                <Button
                                  variant="light"
                                  color="yellow"
                                  onClick={() => {
                                    setReportedRecruiter(recruiter);
                                    setIssueKind(
                                      recruiter.my_feedback?.kind !==
                                        "helpful" && recruiter.my_feedback
                                        ? recruiter.my_feedback.kind
                                        : "ignores",
                                    );
                                    setReason(
                                      recruiter.my_feedback?.reason ?? "",
                                    );
                                  }}
                                >
                                  Сообщить о проблеме
                                </Button>
                              </SimpleGrid>
                            )}
                          </Stack>
                        </Stack>
                      </Card>
                    );
                  })}
                </SimpleGrid>
              </Stack>
            ))}
          </Stack>
          {recruiters.data.total > recruiters.data.limit && (
            <Pagination
              value={page}
              onChange={setPage}
              total={Math.ceil(recruiters.data.total / recruiters.data.limit)}
              withEdges
              mx="auto"
            />
          )}
        </>
      )}

      <Modal
        opened={reportedRecruiter !== null}
        onClose={() => setReportedRecruiter(null)}
        title={`Проблема с @${reportedRecruiter?.telegram_username ?? ""}`}
        centered
      >
        <Stack>
          <Select
            label="Что случилось"
            data={issueOptions}
            value={issueKind}
            allowDeselect={false}
            onChange={(value) =>
              setIssueKind((value as RecruiterFeedbackKind | null) ?? "ignores")
            }
          />
          <Textarea
            label={
              issueKind === "other" ? "Причина" : "Комментарий — необязательно"
            }
            placeholder="Добавьте полезные детали без личных данных"
            minRows={3}
            maxLength={1000}
            value={reason}
            onChange={(event) => setReason(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setReportedRecruiter(null)}>
              Отмена
            </Button>
            <Button
              color="yellow"
              onClick={() => void submitIssue()}
              loading={setFeedback.isPending}
            >
              Сохранить отметку
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
