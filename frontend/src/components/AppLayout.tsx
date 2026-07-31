import {
  ActionIcon,
  AppShell,
  Badge,
  Burger,
  Group,
  NavLink,
  Stack,
  Text,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useEffect } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useMe } from "../features/auth/queries";
import { usePlatform } from "../platform/usePlatform";
import { BrandLogo } from "./BrandLogo";

const roleLabels = {
  student: "Ученик",
  mentor: "Ментор",
  admin: "Админ",
} as const;

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { toggleColorScheme } = useMantineColorScheme();
  const colorScheme = useComputedColorScheme("light");
  const location = useLocation();
  const navigate = useNavigate();
  const platform = usePlatform();
  const me = useMe();
  const mentor = me.data?.role === "mentor" || me.data?.role === "admin";
  const admin = me.data?.role === "admin";

  useEffect(() => {
    if (!platform.isTelegram) return;
    const rootRoute =
      location.pathname === "/roadmaps" ||
      location.pathname === "/knowledge" ||
      location.pathname === "/interviews";
    if (rootRoute) {
      platform.hideBackButton();
      return;
    }
    platform.showBackButton();
    const unsubscribe = platform.onBackButton(() => navigate(-1));
    return () => {
      unsubscribe();
      platform.hideBackButton();
    };
  }, [location.pathname, navigate, platform]);

  return (
    <AppShell
      header={{ height: 76 }}
      navbar={{ width: 272, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0}
    >
      <AppShell.Header className="brand-header">
        <Group h="100%" px={{ base: "md", sm: "xl" }} justify="space-between">
          <Group wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
            />
            <BrandLogo compact />
          </Group>
          <Group gap="sm" wrap="nowrap">
            {me.data && (
              <Stack gap={0} align="flex-end" visibleFrom="sm">
                <Text size="sm" fw={600}>
                  {me.data.first_name}
                </Text>
                <Text className="technical-label">
                  {roleLabels[me.data.role]}
                </Text>
              </Stack>
            )}
            <ActionIcon
              variant="light"
              size="lg"
              onClick={toggleColorScheme}
              aria-label="Переключить тему"
              className="theme-toggle"
            >
              {colorScheme === "dark" ? "☀" : "◐"}
            </ActionIcon>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md" className="brand-navbar">
        <AppShell.Section>
          <Text className="brand-eyebrow" px="sm" mb="sm">
            Навигация
          </Text>
        </AppShell.Section>
        <AppShell.Section grow>
          <NavLink
            component={Link}
            to="/roadmaps"
            label="Роадмапы"
            description="Учебные треки"
            leftSection={<span className="nav-index">01</span>}
            className="brand-nav-link"
            active={
              location.pathname.startsWith("/roadmaps") ||
              location.pathname.startsWith("/topics")
            }
            onClick={close}
          />
          <NavLink
            component={Link}
            to="/knowledge"
            label="База знаний"
            description="Статьи и вопросы"
            leftSection={<span className="nav-index">02</span>}
            className="brand-nav-link"
            active={location.pathname.startsWith("/knowledge")}
            onClick={close}
          />
          <NavLink
            component={Link}
            to="/interviews"
            label="Собеседования"
            description="Карточки и повторения"
            leftSection={<span className="nav-index">03</span>}
            className="brand-nav-link"
            active={location.pathname.startsWith("/interviews")}
            onClick={close}
          />
          {mentor && (
            <NavLink
              component={Link}
              to="/mentor/students"
              label="Ученики"
              description="Прогресс потока"
              leftSection={<span className="nav-index">04</span>}
              className="brand-nav-link"
              active={location.pathname.startsWith("/mentor")}
              onClick={close}
            />
          )}
          {admin && (
            <>
              <NavLink
                component={Link}
                to="/admin/tracks"
                label="Треки"
                description="Направления и доступы"
                leftSection={<span className="nav-index">05</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/tracks")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/roadmaps"
                label="Роадмапы"
                description="Материалы курса"
                leftSection={<span className="nav-index">06</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/roadmaps")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/knowledge"
                label="Редактор знаний"
                description="Темы и материалы"
                leftSection={<span className="nav-index">07</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/knowledge")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/interviews"
                label="Карточки интервью"
                description="Колоды Python и Go"
                leftSection={<span className="nav-index">08</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/interviews")}
                onClick={close}
              />
            </>
          )}
          {import.meta.env.DEV && !platform.isTelegram && (
            <NavLink
              component={Link}
              to="/dev-login"
              label="Сменить роль"
              leftSection={<span className="nav-index">→</span>}
              className="brand-nav-link change-user-link"
              onClick={close}
            />
          )}
        </AppShell.Section>
        <AppShell.Section>
          <div className="mentor-note">
            <Group wrap="nowrap" align="center">
              <img
                src="/brand/geralt-avatar.png"
                alt=""
                className="mentor-note-avatar"
              />
              <div>
                <Badge color="brandYellow" c="brandNavy.9" mb={4}>
                  Геральт рядом
                </Badge>
                <Text size="xs" c="dimmed">
                  Сегодня деплоим без паники.
                </Text>
              </div>
            </Group>
          </div>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        <main className="page-container">
          <Outlet />
        </main>
      </AppShell.Main>
    </AppShell>
  );
}
