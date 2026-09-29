import { CommunicationProgress } from "../components/CommunicationProgress";
import { CardGridSkeleton } from "../components/CardGridSkeleton";
import { EmptyState } from "../components/EmptyState";
import {
  Badge,
  Button,
  Card,
  Group,
  Pagination,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { InlineInterviewMediaPlayer } from "../components/InlineInterviewMediaPlayer";
import { PageHeader } from "../components/PageHeader";
import { useInterviewDecks } from "../features/interviews/queries";
import { useInterviewProcesses } from "../features/interviews/journalQueries";
import { useIntelligenceInterviews } from "../features/interviews/intelligenceQueries";
import {
  useMyMentorDocuments,
  useMyMockInterviews,
} from "../features/mentor/queries";
import type { InterviewDeckListItem } from "../types/api";
import { openExternalResource } from "../utils/openExternalResource";

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InterviewQuestionDecks({ decks }: { decks: InterviewDeckListItem[] }) {
  return (
    <Stack gap="md">
      {decks.length === 0 ? (
        <Card withBorder>
          <EmptyState
            title="Для твоих учебных треков пока нет опубликованных колод."
            description="Здесь появятся доступные записи. Проверь выбранный раздел или вернись позже."
          />
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, md: Math.min(decks.length, 2) }}>
          {decks.map((deck) => (
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
                      <Text fw={600}>Выбери пройденные темы</Text>
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
                        aria-label={`Прогресс подготовки: ${deck.title}`}
                        value={deck.stats.progress_percent}
                        size="lg"
                        radius="xl"
                      />
                      <Group justify="space-between" mt="xs">
                        <Text size="sm" c="dimmed">
                          Осталось: {deck.stats.remaining_cards}
                        </Text>
                        {deck.stats.due_cards > 0 && (
                          <Badge color="brandYellow">
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
                <Group grow mt="sm" className="interview-deck-actions">
                  <Button
                    component={Link}
                    to={`/interviews/${deck.slug}/questions`}
                  >
                    Таблица вопросов
                  </Button>
                  <Button
                    component={Link}
                    to={`/interviews/${deck.slug}`}
                    variant="light"
                  >
                    {deck.stats.selected_categories === 0
                      ? "Выбрать темы"
                      : deck.stats.learned_cards === 0
                        ? "Учить карточки"
                        : "Продолжить карточки"}
                  </Button>
                </Group>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

export function InterviewsPage() {
  const query = useInterviewDecks();
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Собеседования · подготовка"
        title="Вопросы с собеседований"
        description="Повторяй карточки или работай с таблицей вопросов по выбранному направлению."
      />
      {query.isPending ? (
        <CardGridSkeleton />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <InterviewQuestionDecks decks={query.data} />
      )}
    </Stack>
  );
}
export function InterviewAnalysesPage() {
  const [analysisPage, setAnalysisPage] = useState(1);
  const intelligence = useIntelligenceInterviews(true, analysisPage);
  return (
    <Stack gap="xl" className="brand-ai-scope">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Собеседования · AI"
          title="AI-разборы собеседований"
          description="Расшифровка по спикерам, вопросы и персональный разбор ответов."
        />
        <Button component={Link} to="/interviews/journal/new">
          + Добавить собеседование
        </Button>
      </Group>
      <CommunicationProgress />
      {intelligence.isPending || intelligence.isPlaceholderData ? (
        <CardGridSkeleton label="Загружаем AI-разборы…" />
      ) : intelligence.isError ? (
        <ErrorState
          error={intelligence.error}
          retry={() => void intelligence.refetch()}
        />
      ) : intelligence.data.items.length === 0 ? (
        <Card withBorder>
          <Text fw={600}>Разборов пока нет</Text>
          <Text size="sm" c="dimmed">
            Добавь запись в нужный этап дневника и запусти разбор там.
          </Text>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {intelligence.data.items.map((interview) => (
            <Card key={interview.id} withBorder>
              <Stack h="100%">
                <Group justify="space-between">
                  <Badge>{interview.track_title}</Badge>
                  <Text className="technical-label">
                    {interview.processing_status === "ready"
                      ? "✓ Разобрано"
                      : interview.processing_status === "failed"
                        ? "Ошибка"
                        : interview.processing_status === "uploaded"
                          ? "Ожидает запуска"
                          : "● Анализируется"}
                  </Text>
                </Group>
                <Title order={3}>{interview.company_name}</Title>
                <Text c="dimmed">{interview.position_name}</Text>
                <Text size="sm">{interview.question_count} вопросов</Text>
                <Button
                  component={Link}
                  to={`/interviews/analysis/${interview.id}`}
                  variant="light"
                  mt="auto"
                >
                  Открыть разбор
                </Button>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
      {intelligence.data &&
        intelligence.data.total > intelligence.data.limit && (
          <Pagination
            value={analysisPage}
            onChange={setAnalysisPage}
            total={Math.ceil(intelligence.data.total / intelligence.data.limit)}
            disabled={intelligence.isPlaceholderData}
            withEdges
            mx="auto"
          />
        )}
    </Stack>
  );
}
export function InterviewJournalPage() {
  const processes = useInterviewProcesses("all");
  const activeProcesses = (processes.data ?? []).filter(
    (process) => process.status === "active",
  );
  const completedProcesses = (processes.data ?? []).filter(
    (process) => process.status !== "active",
  );
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Собеседования · дневник"
          title="Дневник собеседований"
          description="Треки по компаниям: этапы, даты, записи и результат каждого процесса."
        />
        <Group>
          <Button component={Link} to="/interviews/recruiters" variant="light">
            База рекрутеров
          </Button>
          <Button component={Link} to="/interviews/catalog" variant="light">
            Каталог собеседований
          </Button>
          <Button component={Link} to="/interviews/journal/new">
            + Добавить компанию
          </Button>
        </Group>
      </Group>

      {processes.isPending ? (
        <CardGridSkeleton />
      ) : processes.isError ? (
        <ErrorState
          error={processes.error}
          retry={() => void processes.refetch()}
        />
      ) : activeProcesses.length === 0 ? (
        <Card withBorder>
          <Text fw={600}>Активных процессов пока нет</Text>
          <Text c="dimmed" size="sm" mt={4}>
            Создай первый трек и добавь запланированное собеседование.
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
    </Stack>
  );
}
export function InterviewMocksPage() {
  const mocks = useMyMockInterviews();
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Собеседования · практика"
        title="Мок-собеседования"
        description="Запланированные встречи с ментором, записи и обратная связь."
      />
      {mocks.data?.length === 0 && (
        <EmptyState
          title="Мок-собеседования пока не назначены"
          description="Договорись с ментором о тренировочном собеседовании."
          action={
            <Button component={Link} to="/my-mentor" variant="light">
              Связаться с ментором
            </Button>
          }
        />
      )}
      {mocks.isPending && (
        <CardGridSkeleton label="Загружаем мок-собеседования…" />
      )}
      {mocks.isError && (
        <ErrorState error={mocks.error} retry={() => void mocks.refetch()} />
      )}
      {(mocks.data?.length ?? 0) > 0 && (
        <Stack gap="sm">
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
                  <Badge color={mock.status === "completed" ? "green" : "blue"}>
                    {mock.status === "completed"
                      ? "Проведено"
                      : "Запланировано"}
                  </Badge>
                </Group>
                {mock.description && <Text>{mock.description}</Text>}
                {mock.feedback ? (
                  <Card withBorder className="layout-interviews-page-14">
                    <Text className="technical-label">Фидбек ментора</Text>
                    <Text className="preserve-lines">{mock.feedback}</Text>
                  </Card>
                ) : (
                  <Text c="dimmed" size="sm">
                    Фидбек появится после проведения собеседования.
                  </Text>
                )}
                {mock.media && (
                  <InlineInterviewMediaPlayer
                    media={mock.media}
                    loadUrl={() => api.openMyMockInterviewMedia(mock.id)}
                  />
                )}
              </Stack>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
export function InterviewMaterialsPage() {
  const documents = useMyMentorDocuments();
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Собеседования · материалы"
        title="Резюме и легенда"
        description="Актуальные файлы и рекомендации, которые подготовил твой ментор."
      />
      {documents.data?.length === 0 && (
        <EmptyState
          title="Материалы пока не добавлены"
          description="Попроси ментора прикрепить резюме и легенду."
          action={
            <Button component={Link} to="/my-mentor" variant="light">
              Связаться с ментором
            </Button>
          }
        />
      )}
      {documents.isPending && (
        <CardGridSkeleton label="Загружаем материалы ментора…" />
      )}
      {documents.isError && (
        <ErrorState
          error={documents.error}
          retry={() => void documents.refetch()}
        />
      )}
      {(documents.data?.length ?? 0) > 0 && (
        <Stack gap="sm">
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            {documents.data?.map((document) => (
              <Card key={document.id} withBorder>
                <Stack>
                  <Title order={3}>
                    {document.kind === "resume" ? "Резюме" : "Легенда"}
                  </Title>
                  {document.text_content && (
                    <Text className="preserve-lines">
                      {document.text_content}
                    </Text>
                  )}
                  {document.file && (
                    <Button
                      variant="light"
                      onClick={() =>
                        void openExternalResource(
                          api.openMyMentorDocument(document.id),
                        ).catch((error: unknown) =>
                          notifications.show({
                            color: "red",
                            message:
                              error instanceof Error
                                ? error.message
                                : "Не удалось открыть файл",
                          }),
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
  );
}
