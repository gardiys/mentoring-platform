import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { InlineInterviewMediaPlayer } from "../src/components/InlineInterviewMediaPlayer";
import { renderPage } from "./render";

it.each([
  ["video/mp4", "mock.mp4", "Видео: mock.mp4", "video"],
  ["audio/mpeg", "mock.mp3", "Аудио: mock.mp3", "audio"],
])(
  "лениво открывает запись мок-собеседования во встроенном плеере: %s",
  async (contentType, filename, label, tagName) => {
    const loadUrl = vi
      .fn()
      .mockResolvedValue(`https://s3.example.test/${filename}`);
    renderPage(
      <InlineInterviewMediaPlayer
        media={{ filename, content_type: contentType }}
        loadUrl={loadUrl}
      />,
    );

    expect(loadUrl).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", {
        name: new RegExp(`запись: ${filename}`, "i"),
      }),
    );

    const player = await screen.findByLabelText(label);
    expect(player.tagName.toLowerCase()).toBe(tagName);
    expect(player).toHaveAttribute("preload", "metadata");
    expect(player).toHaveAttribute(
      "controlslist",
      "nodownload noremoteplayback",
    );
    expect(player).toHaveAttribute(
      "src",
      `https://s3.example.test/${filename}`,
    );
    expect(loadUrl).toHaveBeenCalledTimes(1);
  },
);
