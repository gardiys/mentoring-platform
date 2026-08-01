import {
  Accordion,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
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
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ProgressBar } from "../components/ProgressBar";
import { TopicStatusBadge } from "../components/TopicStatusBadge";
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

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

async function openUrl(request: Promise<string>) {
  try {
    window.open(await request, "_blank", "noopener,noreferrer");
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
  const [file, setFile] = useState<File | null>(null);
  const save = useSetMentorDocumentText(studentId);
  const upload = useUploadMentorDocument(studentId);
  const title = kind === "resume" ? "Резюме" : "Легенда";

  useEffect(() => setText(document?.text_content ?? ""), [document]);

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
        <Button
          variant="light"
          loading={save.isPending}
          disabled={!text.trim() && !document?.file}
          onClick={() =>
            save.mutate(
              { kind, text: text.trim() || null },
              {
                onSuccess: () =>
                  notifications.show({
                    color: "green",
                    message: `${title} сохранено`,
                  }),
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
  const complete = useCompleteMockInterview(studentId);
  const upload = useUploadMockInterviewMedia(studentId);

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
          <Button
            size="xs"
            variant="subtle"
            onClick={() =>
              void openUrl(api.openMockInterviewMedia(studentId, mock.id))
            }
          >
            Открыть запись: {mock.media.filename}
          </Button>
        )}
        <Group align="flex-end">
          <FileInput
            label="Запись мок-собеседования"
            accept="audio/*,video/*"
            value={file}
            onChange={setFile}
            style={{ flex: 1 }}
          />
          <Button
            disabled={!file}
            loading={upload.isPending}
            onClick={() => {
              if (!file) return;
              upload.mutate(
                { mockId: mock.id, file },
                {
                  onSuccess: () => {
                    setFile(null);
                    notifications.show({
                      color: "green",
                      message: "Запись загружена",
                    });
                  },
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                },
              );
            }}
          >
            Загрузить
          </Button>
        </Group>
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
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  const student = query.data;

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
      </Card>

      <SimpleGrid cols={{ base: 1, sm: 3 }}>
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
      </SimpleGrid>

      <Tabs defaultValue="progress" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="progress">Прогресс</Tabs.Tab>
          <Tabs.Tab value="interviews">
            Собеседования ({student.interviews.length})
          </Tabs.Tab>
          <Tabs.Tab value="mocks">
            Моки ({student.mock_interviews.length})
          </Tabs.Tab>
          <Tabs.Tab value="documents">Резюме и легенда</Tabs.Tab>
          <Tabs.Tab value="notes">Заметки ({student.notes.length})</Tabs.Tab>
        </Tabs.List>

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
                  <Group justify="space-between">
                    <div>
                      <Title order={3}>{interview.company_name}</Title>
                      <Text c="dimmed" size="sm">
                        {interview.track_title} · {interview.stage_count} этапов
                        · обновлено {formatDate(interview.updated_at)}
                      </Text>
                    </div>
                    <Button
                      component={Link}
                      to={`/mentor/students/${studentId}/interviews/${interview.id}`}
                      variant="light"
                    >
                      Открыть и дать фидбек
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
                    loading={deleteNote.isPending}
                    onClick={() => deleteNote.mutate(item.id)}
                  >
                    Удалить
                  </Button>
                </Group>
              </Card>
            ))}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
