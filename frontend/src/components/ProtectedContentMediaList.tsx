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
import { useEffect, useState } from "react";

import { useProtectedContentMediaPlayback } from "../features/media/queries";
import type {
  ContentMediaPlayback,
  ProtectedContentMediaRead,
} from "../types/api";

interface Props {
  media: ProtectedContentMediaRead[];
  resourceKey: string;
  loadPlayback: (mediaId: string) => Promise<ContentMediaPlayback>;
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
  const [opened, setOpened] = useState(false);
  const playback = useProtectedContentMediaPlayback(resourceKey, item.id, () =>
    loadPlayback(item.id),
  );
  const [opening, setOpening] = useState(false);
  const [failed, setFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const displayTitle = item.title || item.filename;
  const playbackData = playback.data;
  const playbackDataUpdatedAt = playback.dataUpdatedAt;
  const refetchPlayback = playback.refetch;

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

  const restorePlayback = async () => {
    const result = await playback.refetch();
    if (!result.data) return;
    setFailed(false);
    setReloadKey((current) => current + 1);
  };

  const togglePlayback = async () => {
    if (opened) {
      setOpened(false);
      setFailed(false);
      return;
    }
    setOpened(true);
    setFailed(false);
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
            <Text fw={600}>{displayTitle}</Text>
          </Group>
          <Button
            type="button"
            size="xs"
            variant="light"
            loading={opening}
            onClick={() => void togglePlayback()}
          >
            {opened ? "Скрыть запись" : "Открыть запись"}
          </Button>
        </Group>

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
                aria-label={`Видео: ${displayTitle}`}
                controls
                controlsList="nodownload noremoteplayback"
                disablePictureInPicture
                draggable={false}
                preload="metadata"
                src={playback.data.url}
                onContextMenu={(event) => event.preventDefault()}
                onDragStart={(event) => event.preventDefault()}
                onError={() => setFailed(true)}
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
                aria-label={`Аудио: ${displayTitle}`}
                controls
                controlsList="nodownload noremoteplayback"
                draggable={false}
                preload="metadata"
                src={playback.data.url}
                onContextMenu={(event) => event.preventDefault()}
                onDragStart={(event) => event.preventDefault()}
                onError={() => setFailed(true)}
                style={{ width: "100%" }}
              />
            )}
          </div>
        ) : null}

        {failed && (
          <Alert color="yellow" title="Сессия воспроизведения завершилась">
            <Group justify="space-between" align="center">
              <Text size="sm">
                Обновите защищённый доступ и продолжите воспроизведение.
              </Text>
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
