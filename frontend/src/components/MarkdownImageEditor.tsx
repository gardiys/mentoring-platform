import { Button, Group, Stack, Text, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useRef } from "react";

import {
  CONTENT_IMAGE_ACCEPT,
  insertMarkdownImages,
  validateContentImage,
} from "../utils/contentImages";

interface Props {
  value: string;
  onChange: (value: string) => void;
  queueImage: (file: File) => { source: string; name: string };
  previews: { source: string; name: string; url?: string }[];
  disabled?: boolean;
  minRows?: number;
}

export function MarkdownImageEditor({
  value,
  onChange,
  queueImage,
  previews,
  disabled,
  minRows = 16,
}: Props) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const selection = useRef({ start: value.length, end: value.length });

  const insert = (files: File[]) => {
    if (disabled || files.length === 0) return;
    try {
      files.forEach(validateContentImage);
      const result = insertMarkdownImages(
        value,
        selection.current.start,
        selection.current.end,
        files.map(queueImage),
      );
      onChange(result.value);
      selection.current = { start: result.cursor, end: result.cursor };
      requestAnimationFrame(() => {
        textarea.current?.focus();
        textarea.current?.setSelectionRange(result.cursor, result.cursor);
      });
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось добавить изображение.",
      });
    }
  };

  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Button
          type="button"
          variant="light"
          size="xs"
          disabled={disabled}
          onClick={() => fileInput.current?.click()}
        >
          Добавить изображение
        </Button>
        <Text size="xs" c="dimmed">
          PNG, JPG, WebP, GIF или AVIF · до 10 МБ
        </Text>
      </Group>
      <input
        ref={fileInput}
        type="file"
        hidden
        multiple
        accept={CONTENT_IMAGE_ACCEPT}
        aria-label="Выбрать изображения"
        disabled={disabled}
        onChange={(event) => {
          insert(Array.from(event.currentTarget.files ?? []));
          event.currentTarget.value = "";
        }}
      />
      <Textarea
        ref={textarea}
        label="Содержание (Markdown)"
        required
        autosize
        minRows={minRows}
        value={value}
        disabled={disabled}
        description="Картинку можно вставить из буфера обмена или выбрать файл. Изображения загрузятся при сохранении материала."
        onChange={(event) => onChange(event.currentTarget.value)}
        onSelect={(event) => {
          selection.current = {
            start: event.currentTarget.selectionStart,
            end: event.currentTarget.selectionEnd,
          };
        }}
        onPaste={(event) => {
          const items = Array.from(event.clipboardData.items ?? []);
          const files = items
            .filter(
              (item) => item.kind === "file" && item.type.startsWith("image/"),
            )
            .map((item) => item.getAsFile())
            .filter((file): file is File => file !== null);
          const images = files.length
            ? files
            : Array.from(event.clipboardData.files ?? []).filter((file) =>
                file.type.startsWith("image/"),
              );
          if (images.length) {
            event.preventDefault();
            selection.current = {
              start: event.currentTarget.selectionStart,
              end: event.currentTarget.selectionEnd,
            };
            insert(images);
          }
        }}
      />
      {previews.length > 0 && (
        <Group align="flex-start">
          {previews.map((image) => (
            <Stack key={image.source} gap={4} maw={180}>
              {image.url && (
                <img
                  src={image.url}
                  alt={image.name}
                  style={{
                    maxWidth: "100%",
                    maxHeight: 120,
                    objectFit: "contain",
                  }}
                />
              )}
              <Text size="xs" c="dimmed">
                {image.name} · загрузится при сохранении
              </Text>
            </Stack>
          ))}
        </Group>
      )}
    </Stack>
  );
}
