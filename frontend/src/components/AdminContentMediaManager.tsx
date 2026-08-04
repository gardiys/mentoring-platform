import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  NumberInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import type { UseMutationResult } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiError, type UploadStatus } from "../api/client";
import type { ProtectedContentMediaRead } from "../types/api";
import {
  AUDIO_MAX_BYTES,
  CONTENT_VIDEO_MAX_BYTES,
  inferFileContentType,
} from "../utils/media";
import type { ContentMediaUploadVariables } from "../features/media/queries";
import { UploadProgressPanel } from "./UploadProgressPanel";

interface Props {
  media: ProtectedContentMediaRead[];
  disabledReason?: string;
  upload: UseMutationResult<
    ProtectedContentMediaRead,
    Error,
    ContentMediaUploadVariables
  >;
  remove: UseMutationResult<void, Error, string>;
}

const SUPPORTED_AUDIO_TYPES = new Set([
  "audio/aac",
  "audio/flac",
  "audio/mp4",
  "audio/mpeg",
  "audio/ogg",
  "audio/wav",
  "audio/webm",
  "audio/x-m4a",
]);
const SUPPORTED_VIDEO_TYPES = new Set([
  "video/mp4",
  "video/ogg",
  "video/quicktime",
  "video/webm",
  "video/x-matroska",
]);
const MAX_POSITION = 2_147_483_647;
const ACCEPTED_MEDIA = [
  ...SUPPORTED_AUDIO_TYPES,
  ...SUPPORTED_VIDEO_TYPES,
  ".aac",
  ".flac",
  ".m4a",
  ".mp3",
  ".oga",
  ".ogg",
  ".wav",
  ".weba",
  ".mkv",
  ".mov",
  ".mp4",
  ".webm",
].join(",");

function formatSize(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} КБ`;
  if (value < 1024 * 1024 * 1024)
    return `${(value / (1024 * 1024)).toFixed(1)} МБ`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} ГБ`;
}

function nextMediaPosition(media: ProtectedContentMediaRead[]) {
  return Math.min(
    MAX_POSITION,
    media.reduce((maximum, item) => Math.max(maximum, item.position), -1) + 1,
  );
}

export function AdminContentMediaManager({
  media,
  disabledReason,
  upload,
  remove,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [position, setPosition] = useState<number | string>(() =>
    nextMediaPosition(media),
  );
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const uploadController = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      uploadController.current?.abort();
    },
    [],
  );

  const startUpload = () => {
    if (
      !file ||
      typeof position !== "number" ||
      !Number.isInteger(position) ||
      position < 0 ||
      position > MAX_POSITION
    )
      return;
    const uploadPosition = position;
    const contentType = (inferFileContentType(file).split(";", 1)[0] ?? "")
      .trim()
      .toLowerCase();
    const kind = SUPPORTED_VIDEO_TYPES.has(contentType)
      ? "video"
      : SUPPORTED_AUDIO_TYPES.has(contentType)
        ? "audio"
        : null;
    if (!kind) {
      notifications.show({
        color: "red",
        message:
          "Формат не поддерживается. Используйте MP4/WebM для видео или MP3/M4A/WAV для аудио.",
      });
      return;
    }
    if (file.size <= 0) {
      notifications.show({ color: "red", message: "Выбранный файл пуст" });
      return;
    }
    const maxBytes =
      kind === "video" ? CONTENT_VIDEO_MAX_BYTES : AUDIO_MAX_BYTES;
    if (file.size > maxBytes) {
      notifications.show({
        color: "red",
        message: `${kind === "video" ? "Видео" : "Аудио"} превышает лимит ${formatSize(maxBytes)}`,
      });
      return;
    }

    const controller = new AbortController();
    uploadController.current = controller;
    upload.mutate(
      {
        file,
        title: title.trim() || null,
        position: uploadPosition,
        options: {
          signal: controller.signal,
          onProgress: (percent) =>
            setUploadStatus((current) =>
              current?.phase === "uploading"
                ? { ...current, percent }
                : current,
            ),
          onStatus: setUploadStatus,
        },
      },
      {
        onSuccess: () => {
          setFile(null);
          setTitle("");
          setPosition(
            Math.min(
              MAX_POSITION,
              Math.max(nextMediaPosition(media), uploadPosition + 1),
            ),
          );
          notifications.show({ color: "green", message: "Медиа добавлено" });
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

  const deleteMedia = (item: ProtectedContentMediaRead) => {
    if (!window.confirm(`Удалить «${item.title || item.filename}»?`)) return;
    remove.mutate(item.id, {
      onSuccess: () =>
        notifications.show({ color: "green", message: "Медиа удалено" }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={2} size="h3">
            Аудио и видео
          </Title>
          <Text c="dimmed" size="sm">
            Файлы хранятся приватно и открываются ученикам только во встроенном
            защищённом плеере.
          </Text>
        </div>

        {disabledReason ? (
          <Alert color="blue" title="Сначала сохраните материал">
            {disabledReason}
          </Alert>
        ) : (
          <>
            {media.length === 0 ? (
              <Text c="dimmed" size="sm">
                Вложений пока нет.
              </Text>
            ) : (
              <Stack gap="xs">
                {media.map((item) => (
                  <Group
                    key={item.id}
                    justify="space-between"
                    align="flex-start"
                    wrap="nowrap"
                  >
                    <div>
                      <Group gap="xs">
                        <Badge variant="light">
                          {item.kind === "video" ? "Видео" : "Аудио"}
                        </Badge>
                        <Text fw={600}>{item.title || item.filename}</Text>
                      </Group>
                      <Text size="xs" c="dimmed" mt={4}>
                        {item.filename} · {formatSize(item.size)} · позиция{" "}
                        {item.position}
                      </Text>
                    </div>
                    <Button
                      type="button"
                      size="xs"
                      variant="subtle"
                      color="red"
                      loading={remove.isPending && remove.variables === item.id}
                      onClick={() => deleteMedia(item)}
                    >
                      Удалить
                    </Button>
                  </Group>
                ))}
              </Stack>
            )}

            <FileInput
              label="Аудио- или видеофайл"
              description="Для гарантированного воспроизведения: MP4 (H.264/AAC, Fast Start) или WebM (VP8/VP9). Видео — до 5 ГБ, аудио — до 500 МБ."
              placeholder="Выберите файл"
              accept={ACCEPTED_MEDIA}
              clearable
              value={file}
              disabled={upload.isPending}
              onChange={setFile}
            />
            <Group grow align="flex-start">
              <TextInput
                label="Название для ученика"
                description="Необязательно"
                maxLength={240}
                value={title}
                disabled={upload.isPending}
                onChange={(event) => setTitle(event.currentTarget.value)}
              />
              <NumberInput
                label="Позиция"
                description="Меньший номер показывается раньше"
                min={0}
                max={MAX_POSITION}
                allowDecimal={false}
                value={position}
                disabled={upload.isPending}
                onChange={setPosition}
              />
            </Group>
            {upload.isPending && uploadStatus && (
              <UploadProgressPanel
                status={uploadStatus}
                onCancel={() => uploadController.current?.abort()}
              />
            )}
            <Group justify="flex-end">
              <Button
                type="button"
                loading={upload.isPending}
                disabled={
                  !file ||
                  typeof position !== "number" ||
                  !Number.isInteger(position) ||
                  position < 0 ||
                  position > MAX_POSITION
                }
                onClick={startUpload}
              >
                Загрузить медиа
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Card>
  );
}
