import {
  ActionIcon,
  Box,
  Button,
  Divider,
  Group,
  Indicator,
  Loader,
  Menu,
  ScrollArea,
  Stack,
  Text,
} from "@mantine/core";
import { useNavigate } from "react-router-dom";

import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "../features/notifications/queries";
import type { PlatformNotification } from "../types/api";

function BellIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
      <path d="M10 21h4" />
    </svg>
  );
}

function timestamp(value: string): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function NotificationBell() {
  const navigate = useNavigate();
  const query = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const unread = query.data?.unread_count ?? 0;

  const openNotification = (item: PlatformNotification) => {
    if (!item.read_at) markRead.mutate(item.id);
    if (item.action_url.startsWith("/") && !item.action_url.startsWith("//")) {
      navigate(item.action_url);
    }
  };

  return (
    <Menu
      width="min(390px, calc(100vw - 24px))"
      position="bottom-end"
      shadow="xl"
      withinPortal
      classNames={{ dropdown: "notification-menu" }}
    >
      <Menu.Target>
        <Indicator
          disabled={unread === 0}
          label={unread > 99 ? "99+" : unread}
          size={18}
          offset={4}
          color="yellow"
          processing
        >
          <ActionIcon
            variant="light"
            size="lg"
            aria-label={
              unread ? `Уведомления: ${unread} непрочитанных` : "Уведомления"
            }
            title="Уведомления"
            className="notification-bell"
          >
            <BellIcon />
          </ActionIcon>
        </Indicator>
      </Menu.Target>
      <Menu.Dropdown>
        <Group justify="space-between" px="md" py="sm" wrap="nowrap">
          <Box>
            <Text fw={700}>Уведомления</Text>
            <Text size="xs" c="dimmed">
              {unread ? `Непрочитанных: ${unread}` : "Всё прочитано"}
            </Text>
          </Box>
          {unread > 0 && (
            <Button
              variant="subtle"
              size="compact-xs"
              onClick={() => markAllRead.mutate()}
              loading={markAllRead.isPending}
            >
              Прочитать все
            </Button>
          )}
        </Group>
        <Divider />
        <ScrollArea.Autosize mah={440} type="auto">
          {query.isLoading ? (
            <Group justify="center" p="xl">
              <Loader size="sm" />
            </Group>
          ) : query.isError ? (
            <Stack align="center" gap="xs" p="xl">
              <Text size="sm" ta="center" c="dimmed">
                Не удалось загрузить уведомления
              </Text>
              <Button size="compact-sm" variant="light" onClick={() => query.refetch()}>
                Повторить
              </Button>
            </Stack>
          ) : query.data?.items.length ? (
            <Stack gap={0}>
              {query.data.items.map((item) => (
                <Menu.Item
                  key={item.id}
                  className={`notification-item${item.read_at ? "" : " is-unread"}`}
                  onClick={() => openNotification(item)}
                >
                  <Group gap="sm" align="flex-start" wrap="nowrap">
                    <span className="notification-unread-dot" aria-hidden="true" />
                    <Box className="notification-item-copy">
                      <Text size="sm" fw={item.read_at ? 600 : 750}>
                        {item.title}
                      </Text>
                      <Text size="xs" c="dimmed" lineClamp={3} mt={3}>
                        {item.body}
                      </Text>
                      <Text className="technical-label" mt={7}>
                        {timestamp(item.created_at)}
                      </Text>
                    </Box>
                  </Group>
                </Menu.Item>
              ))}
            </Stack>
          ) : (
            <Stack align="center" gap={4} p="xl">
              <Text fw={650}>Пока тихо</Text>
              <Text size="sm" c="dimmed" ta="center">
                Здесь появятся новые собеседования и важные события.
              </Text>
            </Stack>
          )}
        </ScrollArea.Autosize>
      </Menu.Dropdown>
    </Menu>
  );
}
