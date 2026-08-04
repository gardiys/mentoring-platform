import { Anchor, Text } from "@mantine/core";

import { normalizeTelegramUsername } from "../utils/telegram";

interface TelegramChatLinkProps {
  username: string | null | undefined;
}

export function TelegramChatLink({ username }: TelegramChatLinkProps) {
  const normalizedUsername = normalizeTelegramUsername(username);

  if (!normalizedUsername) {
    return (
      <Text c="dimmed" size="sm">
        Telegram не указан
      </Text>
    );
  }

  return (
    <Anchor
      href={`https://t.me/${normalizedUsername}`}
      target="_blank"
      rel="noopener noreferrer"
      size="sm"
    >
      Написать в Telegram · @{normalizedUsername}
    </Anchor>
  );
}
