import { Avatar, Group, Stack, Text } from "@mantine/core";
import { Link } from "react-router-dom";

export function BrandLogo({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to="/roadmaps"
      className="brand-logo"
      aria-label="Потрачено — на главную"
    >
      <Group gap="sm" wrap="nowrap">
        <Avatar
          src="/brand/avatar-public-small.png"
          alt="Геральт"
          size={compact ? 40 : 48}
        />
        <Stack gap={0} className="brand-logo-copy">
          <Text className="brand-wordmark">Потрачено</Text>
          {!compact && (
            <Text className="brand-tagline">Python & Go менторство</Text>
          )}
        </Stack>
      </Group>
    </Link>
  );
}
