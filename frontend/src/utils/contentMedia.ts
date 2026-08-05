import type {
  ContentMediaProcessingStatus,
  ProtectedContentMediaRead,
} from "../types/api";

export function contentMediaProcessingStatus(
  item: ProtectedContentMediaRead,
): ContentMediaProcessingStatus {
  const status = (item as { processing_status?: unknown }).processing_status;
  if (
    status === "queued" ||
    status === "processing" ||
    status === "ready" ||
    status === "failed"
  ) {
    return status;
  }

  // During a rolling deploy an older backend may omit the field. Those media
  // items predate normalization and remain playable. Unknown future states are
  // kept unavailable instead of crashing the whole content section.
  return status == null ? "ready" : "failed";
}

export function contentMediaPlaybackAvailable(
  item: ProtectedContentMediaRead,
): boolean {
  const available = (item as { playback_available?: unknown })
    .playback_available;
  if (typeof available === "boolean") return available;

  // Older API responses do not carry an explicit availability flag. Only
  // their ready/legacy media is safe to open; unknown processing states stay
  // unavailable until a current backend response is received.
  return contentMediaProcessingStatus(item) === "ready";
}

export function hasPreparingContentMedia(
  media: ProtectedContentMediaRead[] | undefined,
) {
  return Boolean(
    media?.some((item) => {
      const status = contentMediaProcessingStatus(item);
      return status === "queued" || status === "processing";
    }),
  );
}
