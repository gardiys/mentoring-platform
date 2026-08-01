import {
  Badge,
  Button,
  Card,
  Group,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import { useInterviewDecks } from "../features/interviews/queries";
import { useInterviewProcesses } from "../features/interviews/journalQueries";
import {
  useMyMentorDocuments,
  useMyMockInterviews,
} from "../features/mentor/queries";
import { api } from "../api/endpoints";
import { notifications } from "@mantine/notifications";

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function InterviewsPage() {
  const me = useMe();
  const isStudent = me.data?.role === "student";
  const isAdmin = me.data?.role === "admin";
  const isMentor = me.data?.role === "mentor";
  const canOwnJournal = isStudent || isMentor || isAdmin;
  const query = useInterviewDecks();
  const processes = useInterviewProcesses("all", canOwnJournal);
  const mocks = useMyMockInterviews(isStudent);
  const documents = useMyMentorDocuments(isStudent);
  if (
    me.isPending ||
    query.isPending ||
    (canOwnJournal && processes.isPending)
  ) {
    return <LoadingState label="Загружаем собеседования…" />;
  }
  if (me.isError || query.isError || (canOwnJournal && processes.isError)) {
    return (
      <ErrorState
        retry={() => {
          void query.refetch();
          void processes.refetch();
          void mocks.refetch();
          void documents.refetch();
        }}
      />
    );
  }
  const activeProcesses = (processes.data ?? []).filter(
    (process) => process.status === "active",
  );
  const completedProcesses = (processes.data ?? []).filter(
    (process) => process.status !== "active",
  );

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Подготовка · интервальные повторения"
        title="Собеседования"
        description="Готовьтесь по карточкам и ведите личный дневник процессов по компаниям."
      />

      {canOwnJournal && (
        <Stack gap="md">
          <Group justify="space-between" align="flex-end">
            <div>
              <Text className="brand-eyebrow">Дневник</Text>
              <Title order={2}>Треки по компаниям</Title>
              <Text c="dimmed" mt={4}>
                Храните этапы, даты, записи и результат каждого процесса.
              </Text>
            </div>
            <Group>
              <Button component={Link} to="/interviews/catalog" variant="light">
                Каталог собеседований
              </Button>
              <Button component={Link} to="/interviews/journal/new">
                + Добавить компанию
              </Button>
            </Group>
          </Group>

          {activeProcesses.length === 0 ? (
            <Card withBorder>
              <Text fw={600}>Активных процессов пока нет</Text>
              <Text c="dimmed" size="sm" mt={4}>
                Создайте первый трек и добавьте запланированное собеседование.
              </Text>
            </Card>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {activeProcesses.map((process) => (
                <Card key={process.id} withBorder>
                  <Stack h="100%">
                    <Group justify="space-between">
                      <Badge color="green" variant="light">
                        Активный процесс
                      </Badge>
                      <Text className="technical-label">
                        {process.stage_count} этапов
                      </Text>
                    </Group>
                    <Title order={2}>{process.company_name}</Title>
                    <Badge variant="outline" w="fit-content">
                      {process.track_title}
                    </Badge>
                    {process.recruiter_telegram_usernames.length > 0 && (
                      <Text size="sm">
                        Рекрутеры:{" "}
                        {process.recruiter_telegram_usernames
                          .map((username) => `@${username}`)
                          .join(", ")}
                      </Text>
                    )}
                    <Text c="dimmed" size="sm">
                      {process.next_stage_at
                        ? `Ближайший этап: ${formatDate(process.next_stage_at)}`
                        : "Следующий этап пока не назначен"}
                    </Text>
                    <Button
                      component={Link}
                      to={`/interviews/journal/${process.id}`}
                      variant="light"
                      mt="auto"
                    >
                      Открыть трек
                    </Button>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}

          {completedProcesses.length > 0 && (
            <Card withBorder>
              <Stack>
                <Title order={3}>Завершённые процессы</Title>
                {completedProcesses.map((process) => (
                  <Group key={process.id} justify="space-between">
                    <div>
                      <Text fw={600}>{process.company_name}</Text>
                      <Text size="xs" c="dimmed">
                        {process.status === "offer"
                          ? "Получен оффер"
                          : process.close_reason}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Направление: {process.track_title}
                      </Text>
                      {process.recruiter_telegram_usernames.length > 0 && (
                        <Text size="xs" c="dimmed">
                          Рекрутеры:{" "}
                          {process.recruiter_telegram_usernames
                            .map((username) => `@${username}`)
                            .join(", ")}
                        </Text>
                      )}
                    </div>
                    <Button
                      component={Link}
                      to={`/interviews/journal/${process.id}`}
                      size="xs"
                      variant="subtle"
                    >
                      Открыть
                    </Button>
                  </Group>
                ))}
              </Stack>
            </Card>
          )}

          {isStudent && (mocks.data?.length ?? 0) > 0 && (
            <Stack gap="sm">
              <div>
                <Text className="brand-eyebrow">Практика с ментором</Text>
                <Title order={2}>Мок-собеседования</Title>
              </div>
              {mocks.data?.map((mock) => (
                <Card key={mock.id} withBorder>
                  <Stack>
                    <Group justify="space-between">
                      <div>
                        <Text fw={700}>{formatDate(mock.scheduled_at)}</Text>
                        <Text size="sm" c="dimmed">
                          Ментор: {mock.mentor_name}
                        </Text>
                      </div>
                      <Badge
                        color={mock.status === "completed" ? "green" : "blue"}
                      >
                        {mock.status === "completed"
                          ? "Проведено"
                          : "Запланировано"}
                      </Badge>
                    </Group>
                    {mock.description && <Text>{mock.description}</Text>}
                    {mock.feedback ? (
                      <Card
                        withBorder
                        style={{
                          borderColor: "var(--mantine-color-blue-6)",
                          boxShadow: "inset 3px 0 var(--mantine-color-blue-6)",
                        }}
                      >
                        <Text className="technical-label">Фидбек ментора</Text>
                        <Text style={{ whiteSpace: "pre-wrap" }}>
                          {mock.feedback}
                        </Text>
                      </Card>
                    ) : (
                      <Text c="dimmed" size="sm">
                        Фидбек появится после проведения собеседования.
                      </Text>
                    )}
                    {mock.media && (
                      <Button
                        variant="light"
                        onClick={() =>
                          void api
                            .openMyMockInterviewMedia(mock.id)
                            .then((url) =>
                              window.open(url, "_blank", "noopener,noreferrer"),
                            )
                            .catch((error: unknown) =>
                              notifications.show({
                                color: "red",
                                message:
                                  error instanceof Error
                                    ? error.message
                                    : "Не удалось открыть запись",
                              }),
                            )
                        }
                      >
                        Открыть запись
                      </Button>
                    )}
                  </Stack>
                </Card>
              ))}
            </Stack>
          )}

          {isStudent && (documents.data?.length ?? 0) > 0 && (
            <Stack gap="sm">
              <div>
                <Text className="brand-eyebrow">Материалы от ментора</Text>
                <Title order={2}>Резюме и легенда</Title>
              </div>
              <SimpleGrid cols={{ base: 1, md: 2 }}>
                {documents.data?.map((document) => (
                  <Card key={document.id} withBorder>
                    <Stack>
                      <Title order={3}>
                        {document.kind === "resume" ? "Резюме" : "Легенда"}
                      </Title>
                      {document.text_content && (
                        <Text style={{ whiteSpace: "pre-wrap" }}>
                          {document.text_content}
                        </Text>
                      )}
                      {document.file && (
                        <Button
                          variant="light"
                          onClick={() =>
                            void api
                              .openMyMentorDocument(document.id)
                              .then((url) =>
                                window.open(
                                  url,
                                  "_blank",
                                  "noopener,noreferrer",
                                ),
                              )
                          }
                        >
                          Открыть {document.file.filename}
                        </Button>
                      )}
                    </Stack>
                  </Card>
                ))}
              </SimpleGrid>
            </Stack>
          )}
        </Stack>
      )}

      <div>
        <Text className="brand-eyebrow">Карточки</Text>
        <Title order={2}>Подготовка по вопросам</Title>
      </div>

      {query.data.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">
            Для ваших учебных треков пока нет опубликованных колод.
          </Text>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((deck) => (
            <Card key={deck.id} withBorder className="interview-deck-card">
              <Stack h="100%">
                <Group justify="space-between">
                  <Badge color="brandBlue">{deck.track_title}</Badge>
                  <Text className="technical-label">/{deck.slug}</Text>
                </Group>
                <Title order={2}>{deck.title}</Title>
                {deck.description && <Text c="dimmed">{deck.description}</Text>}
                <Stack gap={6} mt="auto">
                  {deck.stats.selected_categories === 0 ? (
                    <>
                      <Text fw={600}>Выберите пройденные темы</Text>
                      <Text size="sm" c="dimmed">
                        Доступно {deck.stats.available_cards} вопросов в{" "}
                        {deck.stats.total_categories} темах
                      </Text>
                    </>
                  ) : (
                    <>
                      <Group justify="space-between">
                        <Text size="sm" fw={600}>
                          Изучено {deck.stats.learned_cards} из{" "}
                          {deck.stats.total_cards}
                        </Text>
                        <Text className="technical-label">
                          {deck.stats.progress_percent}%
                        </Text>
                      </Group>
                      <Progress
                        value={deck.stats.progress_percent}
                        size="lg"
                        radius="xl"
                      />
                      <Group justify="space-between" mt="xs">
                        <Text size="sm" c="dimmed">
                          Осталось: {deck.stats.remaining_cards}
                        </Text>
                        {deck.stats.due_cards > 0 && (
                          <Badge color="brandYellow" c="brandNavy.9">
                            К повторению: {deck.stats.due_cards}
                          </Badge>
                        )}
                      </Group>
                      <Text size="xs" c="dimmed">
                        Выбрано тем: {deck.stats.selected_categories} из{" "}
                        {deck.stats.total_categories}
                      </Text>
                    </>
                  )}
                </Stack>
                <Button
                  component={Link}
                  to={`/interviews/${deck.slug}`}
                  mt="sm"
                >
                  {deck.stats.selected_categories === 0
                    ? "Выбрать темы"
                    : deck.stats.learned_cards === 0
                      ? "Начать изучение"
                      : "Продолжить"}
                </Button>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
