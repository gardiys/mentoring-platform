import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SDK_FILE = "public/vendor/telegram-web-app-2026-07-14.js";
const CURRENT_SDK_SHA256 =
  "cbdb82c293e40edc90f8727d0d31fff81f0b847df4ae61e80dd268721e29b11e";

describe("vendored Telegram Web App SDK", () => {
  it("matches the reviewed repository snapshot", () => {
    const source = readFileSync(resolve(process.cwd(), SDK_FILE));
    const hash = createHash("sha256").update(source).digest("hex");

    expect(hash).toBe(CURRENT_SDK_SHA256);
  });

  it("documents the hash enforced by the test", () => {
    const readme = readFileSync(
      resolve(process.cwd(), "public/vendor/README.md"),
      "utf8",
    );

    expect(readme).toContain(
      `Current repository SHA-256: \`${CURRENT_SDK_SHA256}\``,
    );
  });
});
