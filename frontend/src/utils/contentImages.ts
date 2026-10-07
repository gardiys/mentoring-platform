import { inferFileContentType } from "./media";

export const CONTENT_IMAGE_MAX_BYTES = 10 * 1024 * 1024;
export const CONTENT_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "image/avif",
]);
export const CONTENT_IMAGE_ACCEPT = [...CONTENT_IMAGE_TYPES].join(",");

export function contentImageSource(id: string) {
  return `/content-images/${id}`;
}

export function contentImageId(source: string) {
  return /^\/content-images\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(
    source,
  )?.[1];
}

export function validateContentImage(file: File) {
  if (!CONTENT_IMAGE_TYPES.has(inferFileContentType(file).toLowerCase())) {
    throw new Error("Выберите изображение PNG, JPG, WebP, GIF или AVIF.");
  }
  if (file.size === 0) throw new Error("Выбранный файл пуст.");
  if (file.size > CONTENT_IMAGE_MAX_BYTES) {
    throw new Error("Изображение должно быть не больше 10 МБ.");
  }
}

export function insertMarkdownImages(
  value: string,
  start: number,
  end: number,
  images: { source: string; name: string }[],
) {
  const before = value.slice(0, start);
  const after = value.slice(end);
  const prefix =
    before && !before.endsWith("\n\n")
      ? before.endsWith("\n")
        ? "\n"
        : "\n\n"
      : "";
  const suffix =
    after && !after.startsWith("\n\n")
      ? after.startsWith("\n")
        ? "\n"
        : "\n\n"
      : "";
  const markup = images
    .map(
      ({ name, source }) =>
        `![${name.replace(/[[\]\\\r\n]/g, " ")}](${source})`,
    )
    .join("\n\n");
  const insertion = prefix + markup + suffix;
  return {
    value: before + insertion + after,
    cursor: start + insertion.length,
  };
}
