import {
  ActionIcon,
  AppShell,
  Badge,
  Burger,
  Group,
  NavLink,
  Progress,
  ScrollArea,
  Stack,
  Text,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect } from "react";
import {
  Link,
  Outlet,
  useLocation,
  useNavigate,
  useNavigation,
} from "react-router-dom";

import { clearDevUserId } from "../features/auth/devAuth";
import { useLogout, useMe } from "../features/auth/queries";
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
  const navigation = useNavigation();
  const platform = usePlatform();
  const me = useMe();
  const logout = useLogout();
  const mentor = me.data?.role === "mentor" || me.data?.role === "admin";
  const admin = me.data?.role === "admin";

  const handleLogout = async () => {
    try {
      await logout.mutateAsync();
      clearDevUserId();
      navigate("/login", { replace: true });
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось завершить сессию на сервере",
      });
    }
  };

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
      header={{
        height: "calc(76px + var(--tg-content-safe-area-inset-top, 0px))",
      }}
      navbar={{ width: 272, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0}
    >
      <AppShell.Header className="brand-header">
        <Group
          h="100%"
          px={{ base: "md", sm: "xl" }}
          pt="var(--tg-content-safe-area-inset-top, 0px)"
          justify="space-between"
          className="brand-header-inner"
        >
          <Group wrap="nowrap">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label={opened ? "Закрыть меню" : "Открыть меню"}
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
            {!platform.isTelegram && (
              <ActionIcon
                variant="light"
                size="lg"
                onClick={() => void handleLogout()}
                loading={logout.isPending}
                aria-label="Выйти"
                title="Выйти"
              >
                ↪
              </ActionIcon>
            )}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md" className="brand-navbar">
        <AppShell.Section>
          <Text className="brand-eyebrow" px="sm" mb="sm">
            Навигация
          </Text>
        </AppShell.Section>
        <AppShell.Section grow component={ScrollArea} scrollbarSize={6}>
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
            description="Дневник, каталог и карточки"
            leftSection={<span className="nav-index">03</span>}
            className="brand-nav-link"
            active={location.pathname.startsWith("/interviews")}
            onClick={close}
          />
          {mentor && (
            <>
              <NavLink
                component={Link}
                to="/mentor/students"
                label={admin ? "Прогресс" : "Ученики"}
                description={admin ? "Учебная активность" : "Прогресс потока"}
                leftSection={<span className="nav-index">04</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/mentor/students")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/mentor/interview-reviews"
                label="Разборы интервью"
                description="AI и менторский фидбек"
                leftSection={<span className="nav-index">AI</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith(
                  "/mentor/interview-reviews",
                )}
                onClick={close}
              />
            </>
          )}
          {admin && (
            <>
              <NavLink
                component={Link}
                to="/admin/students"
                label="Ученики"
                description="Данные и доступы"
                leftSection={<span className="nav-index">05</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/students")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/mentors"
                label="Менторы"
                description="Команда и назначения"
                leftSection={<span className="nav-index">06</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/mentors")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/tracks"
                label="Треки"
                description="Направления и доступы"
                leftSection={<span className="nav-index">07</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/tracks")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/roadmaps"
                label="Роадмапы"
                description="Материалы курса"
                leftSection={<span className="nav-index">08</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/roadmaps")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/knowledge"
                label="Редактор знаний"
                description="Темы и материалы"
                leftSection={<span className="nav-index">09</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/knowledge")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/interviews"
                label="Карточки интервью"
                description="Колоды Python и Go"
                leftSection={<span className="nav-index">10</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith("/admin/interviews")}
                onClick={close}
              />
              <NavLink
                component={Link}
                to="/admin/interview-question-moderation"
                label="Вопросы из разборов"
                description="Очередь добавления карточек"
                leftSection={<span className="nav-index">AI</span>}
                className="brand-nav-link"
                active={location.pathname.startsWith(
                  "/admin/interview-question-moderation",
                )}
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
                src="/brand/avatar-memes-small.png"
                alt=""
                className="mentor-note-avatar"
                loading="lazy"
                decoding="async"
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
        {navigation.state !== "idle" && (
          <Progress
            value={100}
            animated
            size="xs"
            className="route-progress"
            aria-label="Загружаем раздел"
          />
        )}
        <main className="page-container">
          <Outlet />
        </main>
      </AppShell.Main>
    </AppShell>
  );
}
