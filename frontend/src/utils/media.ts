export type MediaKind = "audio" | "video";

export const VIDEO_MAX_BYTES = 2 * 1024 * 1024 * 1024;
export const CONTENT_VIDEO_MAX_BYTES = 5 * 1024 * 1024 * 1024;
export const AUDIO_MAX_BYTES = 500 * 1024 * 1024;

const AUDIO_EXTENSIONS = new Set([
  "aac",
  "flac",
  "m4a",
  "mp3",
  "oga",
  "ogg",
  "opus",
  "wav",
  "weba",
]);
const VIDEO_EXTENSIONS = new Set(["avi", "m4v", "mkv", "mov", "mp4", "webm"]);

const CONTENT_TYPES_BY_EXTENSION: Record<string, string> = {
  aac: "audio/aac",
  flac: "audio/flac",
  m4a: "audio/mp4",
  mp3: "audio/mpeg",
  oga: "audio/ogg",
  ogg: "audio/ogg",
  opus: "audio/ogg",
  wav: "audio/wav",
  weba: "audio/webm",
  avi: "video/x-msvideo",
  m4v: "video/mp4",
  mkv: "video/x-matroska",
  mov: "video/quicktime",
  mp4: "video/mp4",
  webm: "video/webm",
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  pdf: "application/pdf",
};

function fileExtension(filename?: string | null): string | undefined {
  return filename?.split(/[?#]/, 1)[0]?.split(".").pop()?.toLowerCase();
}

export function inferFileContentType(file: File): string {
  if (file.type && file.type !== "application/octet-stream") return file.type;
  const extension = fileExtension(file.name);
  return (
    (extension && CONTENT_TYPES_BY_EXTENSION[extension]) ||
    "application/octet-stream"
  );
}

export function mediaKind(
  contentType: string | null | undefined,
  filename?: string | null,
): MediaKind | null {
  const normalizedType = contentType?.split(";", 1)[0]?.trim().toLowerCase();
  if (normalizedType?.startsWith("audio/")) return "audio";
  if (normalizedType?.startsWith("video/")) return "video";

  const extension = fileExtension(filename);
  if (extension && AUDIO_EXTENSIONS.has(extension)) return "audio";
  if (extension && VIDEO_EXTENSIONS.has(extension)) return "video";
  return null;
}
