import { expect, it } from "vitest";

import { inferFileContentType, mediaKind } from "../src/utils/media";

it("распознаёт импортированную MP3-запись даже с общим MIME-типом", () => {
  expect(mediaKind("application/octet-stream", "recording.MP3")).toBe("audio");
});

it("восстанавливает MIME-тип файла по расширению, если браузер его не передал", () => {
  const file = new File(["audio"], "recording.mp3", { type: "" });

  expect(inferFileContentType(file)).toBe("audio/mpeg");
});
