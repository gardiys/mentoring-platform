import { Button, Stack } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { mediaKind } from "../utils/media";

interface Props {
  media: {
    filename: string;
    content_type: string;
  };
  loadUrl: () => Promise<string>;
}

export function InlineInterviewMediaPlayer({ media, loadUrl }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const kind = mediaKind(media.content_type, media.filename);

  const toggle = async () => {
    if (url) {
      setUrl(null);
      return;
    }
    if (!kind) {
      notifications.show({
        color: "yellow",
        message: "Формат записи не поддерживается встроенным плеером",
      });
      return;
    }
    setLoading(true);
    try {
      setUrl(await loadUrl());
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleError = () => {
    setUrl(null);
    notifications.show({
      color: "yellow",
      message: "Не удалось воспроизвести запись. Откройте её повторно.",
    });
  };

  return (
    <Stack gap="xs">
      <Button
        type="button"
        size="xs"
        variant="light"
        loading={loading}
        onClick={() => void toggle()}
      >
        {url
          ? "Скрыть запись"
          : `${kind === "audio" ? "Прослушать" : "Посмотреть"} запись: ${media.filename}`}
      </Button>
      {url && kind === "video" && (
        <video
          aria-label={`Видео: ${media.filename}`}
          controls
          controlsList="nodownload noremoteplayback"
          disablePictureInPicture
          playsInline
          preload="metadata"
          src={url}
          onContextMenu={(event) => event.preventDefault()}
          onError={handleError}
          style={{ width: "100%", maxHeight: 560, borderRadius: 12 }}
        />
      )}
      {url && kind === "audio" && (
        <audio
          aria-label={`Аудио: ${media.filename}`}
          controls
          controlsList="nodownload noremoteplayback"
          preload="metadata"
          src={url}
          onContextMenu={(event) => event.preventDefault()}
          onError={handleError}
          style={{ width: "100%" }}
        />
      )}
    </Stack>
  );
}
