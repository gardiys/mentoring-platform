import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { useProtectedContentMediaPlayback } from "../features/media/queries";
import type {
  ContentMediaPlayback,
  ProtectedContentMediaRead,
} from "../types/api";
import {
  contentMediaPlaybackAvailable,
  contentMediaProcessingStatus,
} from "../utils/contentMedia";

interface Props {
  media: ProtectedContentMediaRead[];
  resourceKey: string;
  loadPlayback: (mediaId: string) => Promise<ContentMediaPlayback>;
}

const MEDIA_ERR_NETWORK = 2;
const MEDIA_ERR_DECODE = 3;
const MEDIA_ERR_SRC_NOT_SUPPORTED = 4;

const PREPARATION_STATUS = {
  queued: {
    color: "yellow",
    label: "Ожидает подготовки",
    description: "Видео ожидает подготовки для быстрой загрузки в плеере.",
  },
  processing: {
    color: "blue",
    label: "Подготавливается",
    description:
      "Оптимизируем видео для быстрой загрузки. Обычно это занимает несколько минут.",
  },
  ready: { color: "green", label: "Готово", description: null },
  failed: {
    color: "red",
    label: "Временно недоступно",
    description:
      "Видео не удалось подготовить. Администратор может запустить подготовку повторно.",
  },
} as const;

function playbackFailureMessage(
  element: HTMLMediaElement,
  kind: ProtectedContentMediaRead["kind"],
) {
  switch (element.error?.code) {
    case MEDIA_ERR_NETWORK:
      return "Соединение с хранилищем прервалось. Обновите доступ и продолжите просмотр.";
    case MEDIA_ERR_DECODE:
      return "Браузер не смог декодировать запись. Возможно, файл повреждён или использует неподдерживаемый кодек.";
    case MEDIA_ERR_SRC_NOT_SUPPORTED:
      return kind === "video"
        ? "Файл доступен, но браузер не поддерживает его формат или кодек. Используйте MP4 с H.264/AAC и Fast Start либо WebM с VP8/VP9."
        : "Файл доступен, но браузер не поддерживает его аудиоформат или кодек. Используйте MP3, M4A/AAC или WebM/Opus.";
    default:
      return "Не удалось воспроизвести запись. Обновите доступ и попробуйте ещё раз.";
  }
}

function ProtectedContentMediaPlayer({
  item,
  resourceKey,
  loadPlayback,
}: {
  item: ProtectedContentMediaRead;
  resourceKey: string;
  loadPlayback: (mediaId: string) => Promise<ContentMediaPlayback>;
}) {
  const processingStatus = contentMediaProcessingStatus(item);
  const playbackAvailable = contentMediaPlaybackAvailable(item);
  const [opened, setOpened] = useState(playbackAvailable);
  const playback = useProtectedContentMediaPlayback(resourceKey, item.id, () =>
    loadPlayback(item.id),
  );
  const [opening, setOpening] = useState(false);
  const [failureMessage, setFailureMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const mediaElementRef = useRef<HTMLMediaElement | null>(null);
  const resumeTimeRef = useRef(0);
  const resumePlaybackRef = useRef(false);
  const automaticRecoveryAttemptedRef = useRef(false);
  const initialPlaybackRequestedRef = useRef(false);
  const displayTitle = item.title || item.filename;
  const isReady = processingStatus === "ready";
  const preparation = PREPARATION_STATUS[processingStatus];
  const playbackData = playback.data;
  const playbackDataUpdatedAt = playback.dataUpdatedAt;
  const refetchPlayback = playback.refetch;

  useEffect(() => {
    if (!playbackAvailable || initialPlaybackRequestedRef.current) return;
    initialPlaybackRequestedRef.current = true;
    setOpened(true);
    setOpening(true);
    void refetchPlayback().finally(() => setOpening(false));
  }, [playbackAvailable, refetchPlayback]);

  useEffect(() => {
    if (!opened || !playbackData) return;
    let active = true;
    let timer: number | undefined;
    const ttlMilliseconds = Math.max(1, playbackData.expires_in) * 1000;
    const retryMilliseconds = Math.min(
      15_000,
      Math.max(1_000, Math.floor(ttlMilliseconds / 10)),
    );

    const refresh = async () => {
      const result = await refetchPlayback();
      if (active && result.isError) {
        timer = window.setTimeout(() => void refresh(), retryMilliseconds);
      }
    };
    timer = window.setTimeout(
      () => void refresh(),
      Math.max(100, Math.floor(ttlMilliseconds * 0.8)),
    );
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [opened, playbackData, playbackDataUpdatedAt, refetchPlayback]);

  const renewPlaybackSource = async () => {
    const element = mediaElementRef.current;
    if (element) {
      resumeTimeRef.current = Number.isFinite(element.currentTime)
        ? element.currentTime
        : 0;
      resumePlaybackRef.current = !element.paused && !element.ended;
    }
    const result = await playback.refetch();
    if (!result.data) {
      setFailureMessage(
        "Не удалось обновить доступ к записи. Проверьте соединение и повторите попытку.",
      );
      return;
    }
    setFailureMessage(null);
    setReloadKey((current) => current + 1);
  };

  const restorePlayback = async () => {
    automaticRecoveryAttemptedRef.current = true;
    await renewPlaybackSource();
  };

  const handlePlaybackError = (element: HTMLMediaElement) => {
    if (!automaticRecoveryAttemptedRef.current) {
      automaticRecoveryAttemptedRef.current = true;
      void renewPlaybackSource();
      return;
    }
    setFailureMessage(playbackFailureMessage(element, item.kind));
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

  const handleCanPlay = () => {
    automaticRecoveryAttemptedRef.current = false;
    setFailureMessage(null);
  };

  const togglePlayback = async () => {
    if (!playbackAvailable) return;
    if (opened) {
      setOpened(false);
      setFailureMessage(null);
      automaticRecoveryAttemptedRef.current = false;
      return;
    }
    setOpened(true);
    setFailureMessage(null);
    automaticRecoveryAttemptedRef.current = false;
    setOpening(true);
    try {
      await playback.refetch();
    } finally {
      setOpening(false);
    }
  };

  return (
    <Card withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Group gap="xs">
            <Badge variant="light">
              {item.kind === "video" ? "Видео" : "Аудио"}
            </Badge>
            {!isReady && (
              <Badge color={preparation.color} variant="light">
                {preparation.label}
              </Badge>
            )}
            <Text fw={600}>{displayTitle}</Text>
          </Group>
          <Button
            type="button"
            size="xs"
            variant="light"
            loading={opening}
            disabled={!playbackAvailable}
            onClick={() => void togglePlayback()}
          >
            {opened
              ? "Скрыть запись"
              : playbackAvailable
                ? "Открыть запись"
                : preparation.label}
          </Button>
        </Group>

        {!isReady && preparation.description && (
          <Text size="sm" c={processingStatus === "failed" ? "red" : "dimmed"}>
            {preparation.description}
            {playbackAvailable
              ? processingStatus === "failed"
                ? " Исходная запись остаётся доступна для просмотра."
                : " Пока подготовка идёт, можно смотреть исходную запись."
              : null}
          </Text>
        )}

        {opened && opening ? (
          <Text size="sm" c="dimmed">
            Подготавливаем защищённый плеер…
          </Text>
        ) : opened && playback.isError ? (
          <Alert color="red" title="Не удалось открыть запись">
            <Stack gap="xs">
              <Text size="sm">{playback.error.message}</Text>
              <Button
                type="button"
                size="xs"
                variant="light"
                loading={playback.isFetching}
                onClick={() => void playback.refetch()}
              >
                Повторить
              </Button>
            </Stack>
          </Alert>
        ) : opened && playback.data ? (
          <div onContextMenu={(event) => event.preventDefault()}>
            {item.kind === "video" ? (
              <video
                key={reloadKey}
                ref={(element) => {
                  mediaElementRef.current = element;
                }}
                aria-label={`Видео: ${displayTitle}`}
                controls
                controlsList="nodownload noremoteplayback"
                disablePictureInPicture
                draggable={false}
                preload="metadata"
                src={playback.data.url}
                onContextMenu={(event) => event.preventDefault()}
                onDragStart={(event) => event.preventDefault()}
                onError={(event) => handlePlaybackError(event.currentTarget)}
                onLoadedMetadata={(event) =>
                  handleLoadedMetadata(event.currentTarget)
                }
                onCanPlay={handleCanPlay}
                style={{
                  display: "block",
                  width: "100%",
                  maxHeight: 640,
                  borderRadius: 12,
                  background: "#07182a",
                }}
              />
            ) : (
              <audio
                key={reloadKey}
                ref={(element) => {
                  mediaElementRef.current = element;
                }}
                aria-label={`Аудио: ${displayTitle}`}
                controls
                controlsList="nodownload noremoteplayback"
                draggable={false}
                preload="metadata"
                src={playback.data.url}
                onContextMenu={(event) => event.preventDefault()}
                onDragStart={(event) => event.preventDefault()}
                onError={(event) => handlePlaybackError(event.currentTarget)}
                onLoadedMetadata={(event) =>
                  handleLoadedMetadata(event.currentTarget)
                }
                onCanPlay={handleCanPlay}
                style={{ width: "100%" }}
              />
            )}
          </div>
        ) : null}

        {failureMessage && (
          <Alert color="yellow" title="Запись не удалось воспроизвести">
            <Group justify="space-between" align="center">
              <Text size="sm">{failureMessage}</Text>
              <Button
                type="button"
                size="xs"
                variant="light"
                loading={playback.isFetching}
                onClick={() => void restorePlayback()}
              >
                Обновить доступ
              </Button>
            </Group>
          </Alert>
        )}
      </Stack>
    </Card>
  );
}

export function ProtectedContentMediaList({
  media,
  resourceKey,
  loadPlayback,
}: Props) {
  if (media.length === 0) return null;
  return (
    <Stack gap="md">
      <div>
        <Title order={2} size="h3">
          Аудио и видео
        </Title>
        <Text c="dimmed" size="sm">
          Записи доступны только во встроенном плеере платформы.
        </Text>
      </div>
      {media.map((item) => (
        <ProtectedContentMediaPlayer
          key={item.id}
          item={item}
          resourceKey={resourceKey}
          loadPlayback={loadPlayback}
        />
      ))}
    </Stack>
  );
}
