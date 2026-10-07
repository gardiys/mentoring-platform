import { ActionIcon, useMantineColorScheme } from "@mantine/core";

import { HeaderIcon } from "./HeaderIcon";

export function ThemeToggle() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const isLight = colorScheme === "light";
  const label = isLight ? "Включить тёмную тему" : "Включить светлую тему";

  return (
    <ActionIcon
      type="button"
      variant="light"
      size="lg"
      className="theme-toggle"
      onClick={() => setColorScheme(isLight ? "dark" : "light")}
      aria-label={label}
      title={label}
    >
      <HeaderIcon name={isLight ? "moon" : "sun"} />
    </ActionIcon>
  );
}
