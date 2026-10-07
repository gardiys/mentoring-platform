import { useMantineColorScheme } from "@mantine/core";
import { useEffect } from "react";

export function ThemeMetadata() {
  const { colorScheme } = useMantineColorScheme();

  useEffect(() => {
    const scheme = colorScheme === "light" ? "light" : "dark";
    document
      .querySelector('meta[name="color-scheme"]')
      ?.setAttribute("content", scheme);
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute(
        "content",
        getComputedStyle(document.documentElement)
          .getPropertyValue("--c-bg")
          .trim(),
      );
  }, [colorScheme]);

  return null;
}
