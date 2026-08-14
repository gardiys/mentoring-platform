import {
  Accordion,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, type UploadStatus } from "../api/client";
import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { InlineInterviewMediaPlayer } from "../components/InlineInterviewMediaPlayer";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ProgressBar } from "../components/ProgressBar";
import { TelegramChatLink } from "../components/TelegramChatLink";
import { StudentPaymentsPanel } from "../components/StudentPaymentsPanel";
import { TopicStatusBadge } from "../components/TopicStatusBadge";
import { UploadProgressPanel } from "../components/UploadProgressPanel";
import {
  useCompleteMockInterview,
  useCreateMentorNote,
  useCreateMockInterview,
  useDeleteMentorNote,
  useMentorStudent,
  useSetMentorDocumentText,
  useUpdateMentorStudentState,
  useUploadMentorDocument,
  useUploadMockInterviewMedia,
} from "../features/mentor/queries";
import type {
  MentorDocumentKind,
  MentorDocumentRead,
  MockInterviewRead,
  StudentLearningStatus,
  StudentStrengthLevel,
} from "../types/api";
import { AUDIO_MAX_BYTES, VIDEO_MAX_BYTES, mediaKind } from "../utils/media";
import { openExternalResource } from "../utils/openExternalResource";

const statusOptions = [
  { value: "learning", label: "Учится" },
  { value: "interviewing", label: "Ходит на собеседования" },
  { value: "probation", label: "Работает на испыталке" },
  { value: "finished", label: "Закончили обучение" },
];

const levelOptions = [
  { value: "weak", label: "Слабый" },
  { value: "medium", label: "Средний" },
  { value: "strong", label: "Сильный" },
];

function statusLabel(status: StudentLearningStatus): string {
  return statusOptions.find((item) => item.value === status)?.label ?? status;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

async function openUrl(request: Promise<string>) {
  try {
    await openExternalResource(request);
  } catch (error) {
    notifications.show({
      color: "red",
      message:
        error instanceof Error ? error.message : "Не удалось открыть файл",
    });
  }
}

function DocumentEditor({
  studentId,
  kind,
  document,
}: {
  studentId: string;
  kind: MentorDocumentKind;
  document?: MentorDocumentRead;
}) {
  const [text, setText] = useState(document?.text_content ?? "");
  const [savedText, setSavedText] = useState(document?.text_content ?? "");
  const [file, setFile] = useState<File | null>(null);
  const initializedFor = useRef<string | null>(null);
  const save = useSetMentorDocumentText(studentId);
  const upload = useUploadMentorDocument(studentId);
  const title = kind === "resume" ? "Резюме" : "Легенда";

  useEffect(() => {
    const editorKey = `${studentId}:${kind}`;
    if (initializedFor.current === editorKey) return;
    initializedFor.current = editorKey;
    const initialText = document?.text_content ?? "";
    setText(initialText);
    setSavedText(initialText);
  }, [document?.text_content, kind, studentId]);

  const normalizedText = text.trim();
  const textChanged = normalizedText !== savedText.trim();

  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between">
          <Title order={3}>{title}</Title>
          {document?.file && (
            <Button
              size="xs"
              variant="light"
              onClick={() =>
                void openUrl(api.openMentorDocument(studentId, kind))
              }
            >
              Открыть {document.file.filename}
            </Button>
          )}
        </Group>
        <Textarea
          label={`${title} текстом`}
          minRows={8}
          autosize
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
        />
        {textChanged && (
          <Text size="xs" c="orange" role="status">
            Есть несохранённые изменения
          </Text>
        )}
        <Button
          variant="light"
          loading={save.isPending}
          disabled={!textChanged}
          onClick={() =>
            save.mutate(
              { kind, text: normalizedText || null },
              {
                onSuccess: (updatedDocument) => {
                  const updatedText = updatedDocument.text_content ?? "";
                  setText(updatedText);
                  setSavedText(updatedText);
                  notifications.show({
                    color: "green",
                    message: `${title} сохранено`,
                  });
                },
                onError: (error) =>
                  notifications.show({ color: "red", message: error.message }),
              },
            )
          }
        >
          Сохранить текст
        </Button>
        <FileInput
          label="Файл"
          description="PDF, Word, текст или изображение — до 50 МБ"
          value={file}
          onChange={setFile}
          clearable
        />
        <Button
          disabled={!file}
          loading={upload.isPending}
          onClick={() => {
            if (!file) return;
            upload.mutate(
              { kind, file },
              {
                onSuccess: () => {
                  setFile(null);
                  notifications.show({
                    color: "green",
                    message: "Файл загружен",
                  });
                },
                onError: (error) =>
                  notifications.show({ color: "red", message: error.message }),
              },
            );
          }}
        >
          Загрузить файл
        </Button>
      </Stack>
    </Card>
  );
}

function MockInterviewCard({
  studentId,
  mock,
}: {
  studentId: string;
  mock: MockInterviewRead;
}) {
  const [feedback, setFeedback] = useState(mock.feedback ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const uploadController = useRef<AbortController | null>(null);
  const complete = useCompleteMockInterview(studentId);
  const upload = useUploadMockInterviewMedia(studentId);

  useEffect(
    () => () => {
      uploadController.current?.abort();
    },
    [],
  );

  const uploadMedia = () => {
    if (!file) return;
    const kind = mediaKind(file.type, file.name);
    if (!kind) {
      notifications.show({
        color: "red",
        message: "Выберите корректный аудио- или видеофайл",
      });
      return;
    }
    const maxBytes = kind === "video" ? VIDEO_MAX_BYTES : AUDIO_MAX_BYTES;
    if (file.size > maxBytes) {
      notifications.show({
        color: "red",
        message:
          kind === "video"
            ? "Видео должно быть не больше 2 ГБ"
            : "Аудио должно быть не больше 500 МБ",
      });
      return;
    }

    const controller = new AbortController();
    uploadController.current = controller;
    upload.mutate(
      {
        mockId: mock.id,
        file,
        onProgress: (percent) =>
          setUploadStatus((current) =>
            current?.phase === "uploading" ? { ...current, percent } : current,
          ),
        onStatus: setUploadStatus,
        signal: controller.signal,
      },
      {
        onSuccess: () => {
          setFile(null);
          notifications.show({ color: "green", message: "Запись загружена" });
        },
        onError: (error) =>
          notifications.show({
            color:
              error instanceof ApiError && error.code === "request_aborted"
                ? "yellow"
                : "red",
            message: error.message,
          }),
        onSettled: () => {
          uploadController.current = null;
          setUploadStatus(null);
        },
      },
    );
  };

  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between">
          <div>
            <Text fw={700}>{formatDate(mock.scheduled_at)}</Text>
            {mock.description && <Text c="dimmed">{mock.description}</Text>}
          </div>
          <Badge color={mock.status === "completed" ? "green" : "blue"}>
            {mock.status === "completed" ? "Проведено" : "Запланировано"}
          </Badge>
        </Group>
        <Textarea
          label="Фидбек ученику"
          minRows={4}
          value={feedback}
          onChange={(event) => setFeedback(event.currentTarget.value)}
        />
        <Button
          variant="light"
          disabled={!feedback.trim()}
          loading={complete.isPending}
          onClick={() =>
            complete.mutate(
              { mockId: mock.id, feedback: feedback.trim() },
              {
                onSuccess: () =>
                  notifications.show({
                    color: "green",
                    message: "Фидбек опубликован",
                  }),
                onError: (error) =>
                  notifications.show({ color: "red", message: error.message }),
              },
            )
          }
        >
          {mock.status === "completed"
            ? "Обновить фидбек"
            : "Завершить и опубликовать"}
        </Button>
        {mock.media && (
          <InlineInterviewMediaPlayer
            media={mock.media}
            loadUrl={() => api.openMockInterviewMedia(studentId, mock.id)}
          />
        )}
        <Group align="flex-end" className="upload-control-row">
          <FileInput
            label="Запись мок-собеседования"
            description="Видео до 2 ГБ, аудио до 500 МБ"
            accept="audio/*,video/*"
            value={file}
            onChange={setFile}
            disabled={upload.isPending}
            style={{ flex: 1 }}
          />
          <Button
            disabled={!file}
            loading={upload.isPending}
            onClick={uploadMedia}
          >
            Загрузить
          </Button>
        </Group>
        {upload.isPending && uploadStatus && (
          <UploadProgressPanel
            status={uploadStatus}
            onCancel={() => uploadController.current?.abort()}
          />
        )}
      </Stack>
    </Card>
  );
}

export function MentorStudentPage() {
  const { studentId = "" } = useParams();
  const query = useMentorStudent(studentId);
  const updateState = useUpdateMentorStudentState(studentId);
  const createNote = useCreateMentorNote(studentId);
  const deleteNote = useDeleteMentorNote(studentId);
  const createMock = useCreateMockInterview(studentId);
  const [learningStatus, setLearningStatus] =
    useState<StudentLearningStatus>("learning");
  const [strengthLevel, setStrengthLevel] =
    useState<StudentStrengthLevel | null>(null);
  const [note, setNote] = useState("");
  const [mockDate, setMockDate] = useState("");
  const [mockDescription, setMockDescription] = useState("");

  useEffect(() => {
    if (!query.data) return;
    setLearningStatus(query.data.learning_status);
    setStrengthLevel(query.data.strength_level);
  }, [query.data]);

  if (query.isPending) return <LoadingState />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const student = query.data;
  const currentStatusPeriod = student.status_history.find(
    (period) => period.ended_at === null,
  );

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow={
          student.is_overdue
            ? "Карточка ученика · есть просрочки"
            : "Карточка ученика"
        }
        title={[student.first_name, student.last_name]
          .filter(Boolean)
          .join(" ")}
        description={student.email ?? "Email не указан"}
      />

      <Card
        withBorder
        style={
          student.is_overdue
            ? { borderColor: "var(--mantine-color-red-6)" }
            : undefined
        }
      >
        <Stack>
          <div>
            <Text className="technical-label">Связь с учеником</Text>
            <TelegramChatLink username={student.telegram_username} />
          </div>
          <Group align="flex-end">
            <Select
              label="Текущий статус"
              data={statusOptions}
              value={learningStatus}
              onChange={(value) =>
                value && setLearningStatus(value as StudentLearningStatus)
              }
              style={{ flex: 1 }}
            />
            <Select
              label="Уровень"
              placeholder="Не выставлен"
              clearable
              data={levelOptions}
              value={strengthLevel}
              onChange={(value) =>
                setStrengthLevel(value as StudentStrengthLevel | null)
              }
              style={{ flex: 1 }}
            />
            <Button
              loading={updateState.isPending}
              onClick={() =>
                updateState.mutate(
                  { learningStatus, strengthLevel },
                  {
                    onSuccess: () =>
                      notifications.show({
                        color: "green",
                        message: "Статус обновлён",
                      }),
                    onError: (error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  },
                )
              }
            >
              Сохранить
            </Button>
          </Group>
        </Stack>
      </Card>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <Card withBorder>
          <Text className="technical-label">За последние 7 дней</Text>
          <Title order={2}>{student.completed_topics_this_week} тем</Title>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Проведено моков</Text>
          <Title order={2}>{student.mock_interview_count}</Title>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Последняя активность</Text>
          <Text fw={700}>{formatDate(student.last_progress_at)}</Text>
        </Card>
        <Card withBorder>
          <Text className="technical-label">В текущем статусе</Text>
          <Title order={2}>{currentStatusPeriod?.days ?? 0} дн.</Title>
          <Text size="xs" c="dimmed">
            {statusLabel(student.learning_status)}
          </Text>
        </Card>
      </SimpleGrid>

      <Card withBorder>
        <Stack>
          <div>
            <Title order={3}>История статусов</Title>
            <Text size="sm" c="dimmed">
              Сколько времени ученик провёл на каждом этапе программы.
            </Text>
          </div>
          {student.status_history.length === 0 ? (
            <Text c="dimmed">
              История начнёт собираться после смены статуса.
            </Text>
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
              {student.status_history.map((period) => (
                <Card
                  key={`${period.status}-${period.started_at}`}
                  withBorder
                  padding="sm"
                >
                  <Stack gap={4}>
                    <Group justify="space-between" wrap="nowrap">
                      <Text fw={700} size="sm">
                        {statusLabel(period.status)}
                      </Text>
                      {period.ended_at === null && (
                        <Badge color="blue" variant="light" size="xs">
                          Сейчас
                        </Badge>
                      )}
                    </Group>
                    <Title order={3}>{period.days} дн.</Title>
                    <Text size="xs" c="dimmed">
                      {formatDate(period.started_at)} —{" "}
                      {period.ended_at ? formatDate(period.ended_at) : "сейчас"}
                    </Text>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      </Card>

      <Tabs defaultValue="progress" keepMounted={false}>
        <ScrollArea type="auto" scrollbarSize={6} offsetScrollbars>
          <Tabs.List className="responsive-tabs">
            <Tabs.Tab value="progress">Прогресс</Tabs.Tab>
            <Tabs.Tab value="interviews">
              Собеседования ({student.interviews.length})
            </Tabs.Tab>
            <Tabs.Tab value="mocks">
              Моки ({student.mock_interviews.length})
            </Tabs.Tab>
            <Tabs.Tab value="documents">Резюме и легенда</Tabs.Tab>
            <Tabs.Tab value="notes">Заметки ({student.notes.length})</Tabs.Tab>
            <Tabs.Tab value="payments">Платежи</Tabs.Tab>
          </Tabs.List>
        </ScrollArea>

        <Tabs.Panel value="progress" pt="lg">
          <Stack gap="xl">
            {student.current_topics.length > 0 && (
              <Card withBorder>
                <Stack>
                  <Title order={3}>Текущие темы</Title>
                  {student.current_topics.map((topic) => (
                    <Group key={topic.id} justify="space-between">
                      <div>
                        <Text fw={600}>{topic.title}</Text>
                        <Text size="sm" c="dimmed">
                          {topic.roadmap_title} · {topic.section_title}
                        </Text>
                      </div>
                      <Badge color={topic.is_overdue ? "red" : "blue"}>
                        На теме {topic.days_in_topic} дн.
                      </Badge>
                    </Group>
                  ))}
                </Stack>
              </Card>
            )}
            {student.roadmaps.length === 0 && (
              <Text c="dimmed">Роадмапы не назначены.</Text>
            )}
            {student.roadmaps.map((roadmap) => (
              <Stack key={roadmap.id} className="student-roadmap">
                <Title order={2}>{roadmap.title}</Title>
                <ProgressBar
                  completed={roadmap.completed_topics}
                  total={roadmap.total_topics}
                  percent={roadmap.progress_percent}
                />
                <Accordion multiple className="brand-accordion">
                  {roadmap.sections.map((section) => {
                    const overdue =
                      section.deadline_at !== null &&
                      new Date(section.deadline_at) < new Date() &&
                      section.topics.some(
                        (topic) => topic.status !== "completed",
                      );
                    return (
                      <Accordion.Item key={section.id} value={section.id}>
                        <Accordion.Control>
                          <Group justify="space-between" pr="md">
                            <span>{section.title}</span>
                            {overdue && <Badge color="red">Просрочено</Badge>}
                          </Group>
                        </Accordion.Control>
                        <Accordion.Panel>
                          <Text
                            size="xs"
                            c={overdue ? "red" : "dimmed"}
                            mb="sm"
                          >
                            Дедлайн: {formatDate(section.deadline_at)}
                          </Text>
                          <Stack>
                            {section.topics.map((topic) => (
                              <div key={topic.id} className="topic-row">
                                <Group justify="space-between">
                                  <Text fw={600}>{topic.title}</Text>
                                  <TopicStatusBadge status={topic.status} />
                                </Group>
                                <Text size="xs" c="dimmed">
                                  Первое завершение:{" "}
                                  {formatDate(topic.first_completed_at)} ·
                                  Последнее:{" "}
                                  {formatDate(topic.last_completed_at)}
                                </Text>
                              </div>
                            ))}
                          </Stack>
                        </Accordion.Panel>
                      </Accordion.Item>
                    );
                  })}
                </Accordion>
              </Stack>
            ))}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="interviews" pt="lg">
          <Stack>
            {student.interviews.length === 0 ? (
              <Text c="dimmed">Ученик ещё не добавлял собеседования.</Text>
            ) : (
              student.interviews.map((interview) => (
                <Card key={interview.id} withBorder>
                  <Group justify="space-between" align="flex-start">
                    <div>
                      <Group gap="xs" mb={4}>
                        <Title order={3}>{interview.company_name}</Title>
                        <Badge
                          color={
                            interview.status === "offer"
                              ? "green"
                              : interview.status === "closed"
                                ? "gray"
                                : "blue"
                          }
                        >
                          {interview.status === "offer"
                            ? "Получен оффер"
                            : interview.status === "closed"
                              ? "Завершён"
                              : "Активный"}
                        </Badge>
                        {interview.has_offer_file && (
                          <Badge color="green" variant="outline">
                            Файл оффера
                          </Badge>
                        )}
                      </Group>
                      <Text c="dimmed" size="sm">
                        {interview.track_title} · {interview.stage_count} этапов
                        · обновлено {formatDate(interview.updated_at)}
                      </Text>
                      {interview.next_stage_at && (
                        <Text c="dimmed" size="sm">
                          Следующий этап: {formatDate(interview.next_stage_at)}
                        </Text>
                      )}
                      {interview.recruiter_telegram_usernames.length > 0 && (
                        <Text c="dimmed" size="sm">
                          Рекрутеры:{" "}
                          {interview.recruiter_telegram_usernames
                            .map((username) => `@${username}`)
                            .join(", ")}
                        </Text>
                      )}
                      {interview.close_reason && (
                        <Text c="dimmed" size="sm">
                          Причина завершения: {interview.close_reason}
                        </Text>
                      )}
                    </div>
                    <Button
                      component={Link}
                      to={`/mentor/students/${studentId}/interviews/${interview.id}`}
                      variant="light"
                    >
                      Все этапы и материалы
                    </Button>
                  </Group>
                </Card>
              ))
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="mocks" pt="lg">
          <Stack>
            <Card withBorder>
              <Stack>
                <Title order={3}>Запланировать мок-собеседование</Title>
                <TextInput
                  type="datetime-local"
                  label="Дата и время"
                  value={mockDate}
                  onChange={(event) => setMockDate(event.currentTarget.value)}
                />
                <Textarea
                  label="Описание"
                  value={mockDescription}
                  onChange={(event) =>
                    setMockDescription(event.currentTarget.value)
                  }
                />
                <Button
                  disabled={!mockDate}
                  loading={createMock.isPending}
                  onClick={() =>
                    createMock.mutate(
                      {
                        scheduled_at: new Date(mockDate).toISOString(),
                        description: mockDescription.trim() || null,
                      },
                      {
                        onSuccess: () => {
                          setMockDate("");
                          setMockDescription("");
                          notifications.show({
                            color: "green",
                            message: "Мок запланирован",
                          });
                        },
                        onError: (error) =>
                          notifications.show({
                            color: "red",
                            message: error.message,
                          }),
                      },
                    )
                  }
                >
                  Создать мок
                </Button>
              </Stack>
            </Card>
            {student.mock_interviews.map((mock) => (
              <MockInterviewCard
                key={mock.id}
                studentId={studentId}
                mock={mock}
              />
            ))}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="documents" pt="lg">
          <SimpleGrid cols={{ base: 1, lg: 2 }}>
            {(["resume", "legend"] as const).map((kind) => (
              <DocumentEditor
                key={kind}
                studentId={studentId}
                kind={kind}
                document={student.documents.find((item) => item.kind === kind)}
              />
            ))}
          </SimpleGrid>
        </Tabs.Panel>

        <Tabs.Panel value="notes" pt="lg">
          <Stack>
            <Card withBorder>
              <Stack>
                <Textarea
                  label="Новая приватная заметка"
                  description="Её видите только вы и администраторы платформы"
                  minRows={4}
                  value={note}
                  onChange={(event) => setNote(event.currentTarget.value)}
                />
                <Button
                  disabled={!note.trim()}
                  loading={createNote.isPending}
                  onClick={() =>
                    createNote.mutate(note.trim(), {
                      onSuccess: () => {
                        setNote("");
                        notifications.show({
                          color: "green",
                          message: "Заметка сохранена",
                        });
                      },
                      onError: (error) =>
                        notifications.show({
                          color: "red",
                          message: error.message,
                        }),
                    })
                  }
                >
                  Добавить заметку
                </Button>
              </Stack>
            </Card>
            {student.notes.map((item) => (
              <Card key={item.id} withBorder>
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text style={{ whiteSpace: "pre-wrap" }}>{item.body}</Text>
                    <Text size="xs" c="dimmed" mt="sm">
                      {item.author_name} · {formatDate(item.updated_at)}
                    </Text>
                  </div>
                  <Button
                    size="xs"
                    color="red"
                    variant="subtle"
                    loading={
                      deleteNote.isPending && deleteNote.variables === item.id
                    }
                    onClick={() => {
                      if (!window.confirm("Удалить приватную заметку?")) return;
                      deleteNote.mutate(item.id, {
                        onError: (error) =>
                          notifications.show({
                            color: "red",
                            message: error.message,
                          }),
                      });
                    }}
                  >
                    Удалить
                  </Button>
                </Group>
              </Card>
            ))}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="payments" pt="lg">
          <StudentPaymentsPanel studentId={studentId} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
