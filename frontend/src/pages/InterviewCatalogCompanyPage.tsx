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
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  interviewCatalogFiltersFromParams,
  interviewCatalogKeys,
  useCreateInterviewCatalogComment,
  useDeleteInterviewCatalogComment,
  useInterviewCatalogCompany,
  useMarkInterviewCatalogStageViewed,
  useSetInterviewCatalogFavorite,
} from "../features/interviews/catalogQueries";
import type {
  InterviewCatalogAuthorRead,
  InterviewCatalogStageRead,
  InterviewStageType,
} from "../types/api";
import { mediaKind } from "../utils/media";
import { openExternalResource } from "../utils/openExternalResource";

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
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
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
    await openExternalResource(request);
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
  const [playerReloadKey, setPlayerReloadKey] = useState(0);
  const resumeTimeRef = useRef(0);
  const resumePlaybackRef = useRef(false);
  const automaticRecoveryAttemptedRef = useRef(false);
  const [comment, setComment] = useState("");
  const queryClient = useQueryClient();
  const commentMutation = useCreateInterviewCatalogComment(companyId);
  const deleteMutation = useDeleteInterviewCatalogComment(companyId);
  const viewMutation = useMarkInterviewCatalogStageViewed();
  const storedMediaKind = stage.media
    ? mediaKind(stage.media.content_type, stage.media.filename)
    : null;

  const requestPlayerUrl = async (element?: HTMLMediaElement) => {
    if (element) {
      resumeTimeRef.current = Number.isFinite(element.currentTime)
        ? element.currentTime
        : 0;
      resumePlaybackRef.current = !element.paused && !element.ended;
    }
    setPlayerLoading(true);
    try {
      setPlayerUrl(await api.interviewCatalogStageMedia(stage.id));
      setPlayerReloadKey((current) => current + 1);
      await queryClient.invalidateQueries({
        queryKey: interviewCatalogKeys.all,
      });
    } catch (error) {
      if (element) setPlayerUrl(null);
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    } finally {
      setPlayerLoading(false);
    }
  };

  const togglePlayer = async () => {
    if (playerUrl) {
      setPlayerUrl(null);
      automaticRecoveryAttemptedRef.current = false;
      return;
    }
    automaticRecoveryAttemptedRef.current = false;
    await requestPlayerUrl();
  };

  const handlePlayerError = (element: HTMLMediaElement) => {
    if (!automaticRecoveryAttemptedRef.current) {
      automaticRecoveryAttemptedRef.current = true;
      void requestPlayerUrl(element);
      return;
    }
    setPlayerUrl(null);
    notifications.show({
      color: "yellow",
      message:
        storedMediaKind === "video"
          ? "Не удалось воспроизвести запись. Проверьте, что видео использует MP4 H.264/AAC с Fast Start или WebM VP8/VP9."
          : "Не удалось воспроизвести аудио. Проверьте формат записи.",
    });
  };

  const handleLoadedMetadata = (element: HTMLMediaElement) => {
    const resumeTime = resumeTimeRef.current;
    const shouldResume = resumePlaybackRef.current;
    resumeTimeRef.current = 0;
    resumePlaybackRef.current = false;
    if (resumeTime > 0 && Number.isFinite(element.duration)) {
      try {
        element.currentTime = Math.min(resumeTime, element.duration);
      } catch {
        // Some browsers expose metadata before the first seekable range.
      }
    }
    if (shouldResume) void element.play().catch(() => undefined);
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
          <Stack gap="xs" align="flex-end">
            {stage.is_viewed && stage.last_viewed_at ? (
              <Badge color="brandGreen" variant="light">
                Просмотрено {formatDate(stage.last_viewed_at)}
              </Badge>
            ) : (
              <Badge color="brandBlue" variant="light">
                Новое
              </Badge>
            )}
            <Button
              size="compact-xs"
              variant="subtle"
              loading={viewMutation.isPending}
              onClick={() =>
                viewMutation.mutate(stage.id, {
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                })
              }
            >
              Отметить просмотренным
            </Button>
          </Stack>
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
            <Group justify="space-between" className="file-action-row">
              <Text fw={600} size="sm" className="file-name">
                Запись: {stage.media.filename} · {formatSize(stage.media.size)}
              </Text>
              <Group gap="xs" className="file-actions">
                <Button
                  size="xs"
                  variant="light"
                  loading={playerLoading}
                  onClick={() => void togglePlayer()}
                >
                  {playerUrl
                    ? "Скрыть"
                    : storedMediaKind === "video"
                      ? "Посмотреть"
                      : "Прослушать"}
                </Button>
              </Group>
            </Group>
            {playerUrl && storedMediaKind === "video" && (
              <div
                style={{
                  position: "relative",
                  overflow: "hidden",
                  borderRadius: 12,
                  background: "#07182a",
                }}
              >
                <video
                  key={playerReloadKey}
                  controls
                  controlsList="nodownload noremoteplayback"
                  disablePictureInPicture
                  draggable={false}
                  preload="metadata"
                  src={playerUrl}
                  onContextMenu={(event) => event.preventDefault()}
                  onDragStart={(event) => event.preventDefault()}
                  onError={(event) => handlePlayerError(event.currentTarget)}
                  onLoadedMetadata={(event) =>
                    handleLoadedMetadata(event.currentTarget)
                  }
                  onCanPlay={() => {
                    automaticRecoveryAttemptedRef.current = false;
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
            {playerUrl && storedMediaKind === "audio" && (
              <audio
                key={playerReloadKey}
                controls
                controlsList="nodownload noremoteplayback"
                preload="metadata"
                src={playerUrl}
                onContextMenu={(event) => event.preventDefault()}
                onError={(event) => handlePlayerError(event.currentTarget)}
                onLoadedMetadata={(event) =>
                  handleLoadedMetadata(event.currentTarget)
                }
                onCanPlay={() => {
                  automaticRecoveryAttemptedRef.current = false;
                }}
                style={{ width: "100%" }}
              />
            )}
            <Text size="xs" c="dimmed">
              Штатное скачивание отключено: запись открывается по временной
              ссылке только во встроенном плеере. Полностью исключить
              копирование воспроизводимого медиа средствами браузера невозможно.
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
                <Group
                  key={attachment.id}
                  justify="space-between"
                  className="file-action-row"
                >
                  <Text size="sm" className="file-name">
                    {attachment.filename} · {formatSize(attachment.size)}
                  </Text>
                  <Group gap="xs" className="file-actions">
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
                  item.is_ai_feedback
                    ? {
                        borderColor: "var(--mantine-color-violet-6)",
                        boxShadow: "inset 3px 0 var(--mantine-color-violet-6)",
                      }
                    : item.is_mentor_feedback
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
                      {item.is_ai_feedback
                        ? "AI"
                        : item.author
                          ? formatAuthor(item.author)
                          : "Пользователь удалён"}
                    </Text>
                    {item.is_ai_feedback ? (
                      <Badge color="violet" size="xs" variant="light" mt={4}>
                        Автоматический разбор
                      </Badge>
                    ) : item.is_mentor_feedback ? (
                      <Badge size="xs" variant="light" mt={4}>
                        Фидбек ментора
                      </Badge>
                    ) : null}
                    <Text size="xs" c="dimmed">
                      {formatDate(item.created_at)}
                    </Text>
                  </div>
                  {item.is_own && (
                    <Button
                      size="compact-xs"
                      color="red"
                      variant="subtle"
                      loading={
                        deleteMutation.isPending &&
                        deleteMutation.variables === item.id
                      }
                      onClick={() => {
                        if (!window.confirm("Удалить ваш комментарий?")) return;
                        deleteMutation.mutate(item.id, {
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
  const favoriteMutation = useSetInterviewCatalogFavorite();

  if (query.isPending) return <LoadingState label="Загружаем собеседования…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
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
                <Stack gap="xs" align="flex-end">
                  <Button
                    size="compact-xs"
                    variant={track.is_favorite ? "filled" : "light"}
                    color="yellow"
                    loading={
                      favoriteMutation.isPending &&
                      favoriteMutation.variables?.processId === track.id
                    }
                    onClick={() =>
                      favoriteMutation.mutate(
                        { processId: track.id, favorite: !track.is_favorite },
                        {
                          onError: (error) =>
                            notifications.show({
                              color: "red",
                              message: error.message,
                            }),
                        },
                      )
                    }
                  >
                    {track.is_favorite ? "★ В избранном" : "☆ В избранное"}
                  </Button>
                  <Group gap="xs" wrap="wrap" justify="flex-end">
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
                </Stack>
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
