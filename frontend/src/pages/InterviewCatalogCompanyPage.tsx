import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  interviewCatalogFiltersFromParams,
  useCreateInterviewCatalogComment,
  useDeleteInterviewCatalogComment,
  useInterviewCatalogCompany,
} from "../features/interviews/catalogQueries";
import type {
  InterviewCatalogAuthorRead,
  InterviewCatalogStageRead,
  InterviewStageType,
} from "../types/api";

const stageLabels: Record<InterviewStageType, string> = {
  screening: "Скрининг",
  technical_screening: "Технический скрининг",
  technical_interview: "Техническое интервью",
  system_design: "Системный дизайн",
  final_interview: "Финальное интервью",
  other: "Иное",
};

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSize(value: number) {
  if (value <= 0) return "размер не указан";
  return value >= 1024 * 1024
    ? `${(value / 1024 / 1024).toFixed(1)} МБ`
    : `${Math.ceil(value / 1024)} КБ`;
}

function formatAuthor(author: InterviewCatalogAuthorRead) {
  const username = author.telegram_username?.replace(/^@+/, "");
  return username ? `${author.name} · @${username}` : author.name;
}

async function downloadFile(request: Promise<string>, filename: string) {
  try {
    const url = await request;
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = "noopener";
    anchor.click();
  } catch (error) {
    notifications.show({
      color: "red",
      message:
        error instanceof Error ? error.message : "Не удалось скачать файл",
    });
  }
}

async function openFile(request: Promise<string>) {
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

function CatalogStage({
  companyId,
  stage,
}: {
  companyId: string;
  stage: InterviewCatalogStageRead;
}) {
  const [playerUrl, setPlayerUrl] = useState<string | null>(null);
  const [playerLoading, setPlayerLoading] = useState(false);
  const [comment, setComment] = useState("");
  const commentMutation = useCreateInterviewCatalogComment(companyId);
  const deleteMutation = useDeleteInterviewCatalogComment(companyId);

  const togglePlayer = async () => {
    if (playerUrl) {
      setPlayerUrl(null);
      return;
    }
    setPlayerLoading(true);
    try {
      const url = await api.interviewCatalogStageMedia(stage.id);
      setPlayerUrl(`${url}?playback=${Date.now()}`);
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    } finally {
      setPlayerLoading(false);
    }
  };

  const submitComment = () => {
    if (!comment.trim()) return;
    commentMutation.mutate(
      { stageId: stage.id, body: comment.trim() },
      {
        onSuccess: () => {
          setComment("");
          notifications.show({
            color: "green",
            message: "Комментарий добавлен",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between" align="flex-start">
          <div>
            <Badge variant="light">{stageLabels[stage.stage_type]}</Badge>
            <Title order={3} mt="xs">
              {formatDate(stage.scheduled_at)}
            </Title>
          </div>
        </Group>

        {stage.description ? (
          <Text style={{ whiteSpace: "pre-wrap" }}>{stage.description}</Text>
        ) : (
          <Text c="dimmed" size="sm">
            Автор не добавил описание этого этапа.
          </Text>
        )}

        {stage.media && (
          <Stack gap="xs">
            <Group justify="space-between">
              <Text fw={600} size="sm">
                Запись: {stage.media.filename} · {formatSize(stage.media.size)}
              </Text>
              <Group gap="xs">
                <Button
                  size="xs"
                  variant="light"
                  loading={playerLoading}
                  onClick={() => void togglePlayer()}
                >
                  {playerUrl
                    ? "Скрыть"
                    : stage.media.content_type.startsWith("video/")
                      ? "Посмотреть"
                      : "Прослушать"}
                </Button>
              </Group>
            </Group>
            {playerUrl && stage.media.content_type.startsWith("video/") && (
              <div
                style={{
                  position: "relative",
                  overflow: "hidden",
                  borderRadius: 12,
                  background: "#07182a",
                }}
              >
                <video
                  controls
                  controlsList="nodownload noremoteplayback"
                  disablePictureInPicture
                  draggable={false}
                  preload="metadata"
                  src={playerUrl}
                  onContextMenu={(event) => event.preventDefault()}
                  onDragStart={(event) => event.preventDefault()}
                  onError={() => {
                    setPlayerUrl(null);
                    notifications.show({
                      color: "yellow",
                      message:
                        "Сессия просмотра завершилась. Нажмите «Посмотреть», чтобы продолжить.",
                    });
                  }}
                  style={{
                    display: "block",
                    width: "100%",
                    maxHeight: 560,
                  }}
                />
                <Text
                  aria-hidden="true"
                  size="xs"
                  c="white"
                  style={{
                    position: "absolute",
                    top: 12,
                    right: 12,
                    padding: "5px 8px",
                    borderRadius: 6,
                    background: "rgba(7, 24, 42, 0.58)",
                    opacity: 0.72,
                    pointerEvents: "none",
                    userSelect: "none",
                  }}
                >
                  Персональный просмотр · Копирование запрещено
                </Text>
              </div>
            )}
            {playerUrl && stage.media.content_type.startsWith("audio/") && (
              <audio
                controls
                controlsList="nodownload noremoteplayback"
                preload="metadata"
                src={playerUrl}
                onContextMenu={(event) => event.preventDefault()}
                onError={() => {
                  setPlayerUrl(null);
                  notifications.show({
                    color: "yellow",
                    message:
                      "Не удалось воспроизвести аудио. Нажмите «Прослушать», чтобы повторить.",
                  });
                }}
                style={{ width: "100%" }}
              />
            )}
            <Text size="xs" c="dimmed">
              Запись доступна только во встроенном плеере. Прямая ссылка на
              хранилище и скачивание отключены.
            </Text>
          </Stack>
        )}

        {stage.attachments.length > 0 && (
          <Stack gap="xs">
            <Text fw={600} size="sm">
              Материалы
            </Text>
            {stage.attachments.map((attachment) => {
              const canOpen =
                attachment.content_type.startsWith("image/") ||
                attachment.content_type === "application/pdf";
              return (
                <Group key={attachment.id} justify="space-between">
                  <Text size="sm">
                    {attachment.filename} · {formatSize(attachment.size)}
                  </Text>
                  <Group gap="xs">
                    {canOpen && (
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() =>
                          void openFile(
                            api.interviewCatalogStageAttachment(
                              stage.id,
                              attachment.id,
                              true,
                            ),
                          )
                        }
                      >
                        Открыть
                      </Button>
                    )}
                    <Button
                      size="xs"
                      variant="subtle"
                      onClick={() =>
                        void downloadFile(
                          api.interviewCatalogStageAttachment(
                            stage.id,
                            attachment.id,
                          ),
                          attachment.filename,
                        )
                      }
                    >
                      Скачать
                    </Button>
                  </Group>
                </Group>
              );
            })}
          </Stack>
        )}

        <Stack gap="xs" mt="sm">
          <Text fw={600}>Обсуждение</Text>
          {stage.comments.length === 0 ? (
            <Text c="dimmed" size="sm">
              Комментариев пока нет. Поделитесь замечанием или полезным советом.
            </Text>
          ) : (
            stage.comments.map((item) => (
              <Card
                key={item.id}
                withBorder
                padding="sm"
                style={
                  item.is_mentor_feedback
                    ? {
                        borderColor: "var(--mantine-color-blue-6)",
                        boxShadow: "inset 3px 0 var(--mantine-color-blue-6)",
                      }
                    : undefined
                }
              >
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text fw={600} size="sm">
                      {formatAuthor(item.author)}
                    </Text>
                    {item.is_mentor_feedback && (
                      <Badge size="xs" variant="light" mt={4}>
                        Фидбек ментора
                      </Badge>
                    )}
                    <Text size="xs" c="dimmed">
                      {formatDate(item.created_at)}
                    </Text>
                  </div>
                  {item.is_own && (
                    <Button
                      size="compact-xs"
                      color="red"
                      variant="subtle"
                      loading={deleteMutation.isPending}
                      onClick={() =>
                        deleteMutation.mutate(item.id, {
                          onError: (error) =>
                            notifications.show({
                              color: "red",
                              message: error.message,
                            }),
                        })
                      }
                    >
                      Удалить
                    </Button>
                  )}
                </Group>
                <Text mt="xs" style={{ whiteSpace: "pre-wrap" }}>
                  {item.body}
                </Text>
              </Card>
            ))
          )}
          <Textarea
            label="Ваш комментарий"
            placeholder="Оставьте фидбек, замечание или совет по подготовке"
            minRows={3}
            maxLength={5000}
            value={comment}
            onChange={(event) => setComment(event.currentTarget.value)}
          />
          <Button
            variant="light"
            disabled={!comment.trim()}
            loading={commentMutation.isPending}
            onClick={submitComment}
          >
            Отправить комментарий
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
}

export function InterviewCatalogCompanyPage() {
  const { companyId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const filters = interviewCatalogFiltersFromParams(searchParams);
  const query = useInterviewCatalogCompany(companyId, filters);

  if (query.isPending) return <LoadingState label="Загружаем собеседования…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  const company = query.data;

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Каталог собеседований"
          title={company.name}
          description={`${company.tracks.length} треков учеников с описаниями, записями и материалами.`}
        />
        <Button
          component={Link}
          to={{
            pathname: "/interviews/catalog",
            search: searchParams.toString()
              ? `?${searchParams.toString()}`
              : "",
          }}
          variant="subtle"
        >
          ← Все компании
        </Button>
      </Group>

      {company.tracks.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">Для этой компании пока нет доступных треков.</Text>
        </Card>
      ) : (
        company.tracks.map((track) => (
          <Card key={track.id} withBorder padding="lg">
            <Stack>
              <Group justify="space-between" align="flex-start">
                <div>
                  <Text className="brand-eyebrow">Автор трека</Text>
                  <Title order={2}>{formatAuthor(track.author)}</Title>
                  <Text size="sm" c="dimmed" mt={4}>
                    Трек создан {formatDate(track.created_at)}
                  </Text>
                  <Badge variant="outline" mt="xs">
                    {track.track_title}
                  </Badge>
                  {track.recruiter_telegram_usernames.length > 0 && (
                    <Group gap="xs" mt="sm">
                      <Text size="sm" c="dimmed">
                        Рекрутеры:
                      </Text>
                      {track.recruiter_telegram_usernames.map((username) => (
                        <Anchor
                          key={username}
                          href={`https://t.me/${username}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          size="sm"
                        >
                          @{username}
                        </Anchor>
                      ))}
                    </Group>
                  )}
                </div>
                <Badge
                  color={
                    track.status === "active"
                      ? "green"
                      : track.status === "offer"
                        ? "brandYellow"
                        : "gray"
                  }
                  c={track.status === "offer" ? "brandNavy.9" : undefined}
                >
                  {track.status === "active"
                    ? "Активный"
                    : track.status === "offer"
                      ? "Получен оффер"
                      : "Закрыт"}
                </Badge>
              </Group>
              {track.close_reason && (
                <Alert color="gray" title="Результат процесса">
                  {track.close_reason}
                </Alert>
              )}
              {track.stages.length === 0 ? (
                <Text c="dimmed">В этом треке пока нет собеседований.</Text>
              ) : (
                <Stack>
                  {track.stages.map((stage) => (
                    <CatalogStage
                      key={stage.id}
                      companyId={companyId}
                      stage={stage}
                    />
                  ))}
                </Stack>
              )}
            </Stack>
          </Card>
        ))
      )}
    </Stack>
  );
}
