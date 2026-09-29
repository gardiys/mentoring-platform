import {
  ActionIcon,
  AppShell,
  Burger,
  Group,
  NavLink,
  Progress,
  ScrollArea,
  Stack,
  Text,
} from "@mantine/core";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { copilotApi } from "../features/copilot/api";
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
import { HeaderIcon } from "./HeaderIcon";
import { NavigationIcon } from "./NavigationIcon";
import { BrandLogo } from "./BrandLogo";
import { NotificationBell } from "./NotificationBell";

const roleLabels = {
  student: "Ученик",
  mentor: "Ментор",
  admin: "Админ",
} as const;

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  const isMobile = useMediaQuery("(max-width: 47.99em)");
  const menuButton = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const navigation = useNavigation();
  const platform = usePlatform();
  const me = useMe();
  const logout = useLogout();
  const student = me.data?.role === "student";
  const mentor = me.data?.role === "mentor" || me.data?.role === "admin";
  const admin = me.data?.role === "admin";
  const copilot = useQuery({
    queryKey: ["copilot-access"],
    queryFn: copilotApi.access,
    enabled: student || admin,
    refetchInterval: 60000,
  });

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
      location.pathname === "/copilot" ||
      [
        "/interviews",
        "/interviews/journal",
        "/interviews/analysis",
        "/interviews/mocks",
        "/interviews/materials",
        "/interviews/catalog",
        "/interviews/recruiters",
      ].includes(location.pathname) ||
      location.pathname === "/interviews/personal-review" ||
      location.pathname === "/my-mentor" ||
      location.pathname === "/payments" ||
      location.pathname.startsWith("/opportunities") ||
      location.pathname === "/admin/opportunities" ||
      location.pathname === "/mentor/profile" ||
      location.pathname === "/mentor/rewards" ||
      location.pathname === "/mentor/card-automation/clusters" ||
      location.pathname === "/mentor/card-automation/decisions" ||
      location.pathname === "/admin/payments" ||
      location.pathname === "/admin/schedule" ||
      location.pathname === "/admin/useful-links" ||
      location.pathname === "/admin/card-automation/clusters" ||
      location.pathname === "/admin/card-automation/decisions" ||
      location.pathname === "/admin/card-automation/metrics" ||
      location.pathname === "/admin/card-automation/settings";
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
        height:
          "calc(var(--header-height) + var(--tg-content-safe-area-inset-top, 0px))",
      }}
      navbar={{ width: 272, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0}
    >
      <a className="skip-link" href="#main-content" onClick={close}>
        Перейти к содержимому
      </a>
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
              ref={menuButton}
              aria-controls="platform-navigation"
              aria-expanded={opened}
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
            {me.data && <NotificationBell />}
            {!platform.isTelegram && (
              <ActionIcon
                variant="light"
                size="lg"
                onClick={() => void handleLogout()}
                loading={logout.isPending}
                aria-label="Выйти"
                title="Выйти"
              >
                <HeaderIcon name="logout" />
              </ActionIcon>
            )}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar
        id="platform-navigation"
        aria-label="Основная навигация"
        p="md"
        className="brand-navbar"
        inert={isMobile && !opened}
        onKeyDown={(event) => {
          if (event.key === "Escape" && isMobile && opened) {
            close();
            menuButton.current?.focus();
          }
        }}
      >
        <AppShell.Section>
          <Text className="brand-eyebrow" px="sm" mb="sm">
            Навигация
          </Text>
        </AppShell.Section>
        <AppShell.Section grow component={ScrollArea} scrollbarSize={6}>
          {[
            {
              label: "Обучение",
              items: [
                {
                  to: "/roadmaps",
                  label: "Роадмапы",
                  description: "Учебные треки",
                },
                {
                  to: "/knowledge",
                  label: "База знаний",
                  description: "Статьи и вопросы",
                },
                {
                  to: admin ? "/admin/opportunities" : "/opportunities",
                  label: "Возможности",
                  description: admin
                    ? "Заявки выпускников"
                    : "Поддержка после программы",
                },
                ...(student
                  ? [{ to: "/career-package", label: "Карьерный пакет" }]
                  : []),
              ],
            },
            {
              label: "Собеседования",
              items: [
                {
                  to: "/interviews",
                  label: "Вопросы с собеседований",
                  description: "Карточки и таблица вопросов",
                  active:
                    location.pathname === "/interviews" ||
                    (/^\/interviews\/[^/]+(?:\/questions)?$/.test(
                      location.pathname,
                    ) &&
                      ![
                        "catalog",
                        "recruiters",
                        "analysis",
                        "journal",
                        "mocks",
                        "materials",
                        "personal-review",
                      ].includes(location.pathname.split("/")[2] ?? "")),
                },
                ...(student
                  ? [
                      {
                        to: "/interviews/analysis",
                        label: "AI-разборы собеседований",
                      },
                    ]
                  : []),
                { to: "/interviews/journal", label: "Дневник собеседований" },
                ...(student
                  ? [
                      { to: "/interviews/mocks", label: "Мок-собеседования" },
                      {
                        to: "/interviews/materials",
                        label: "Резюме и легенда",
                      },
                    ]
                  : []),
                { to: "/interviews/catalog", label: "Каталог записей" },
                { to: "/interviews/recruiters", label: "База рекрутеров" },
                ...(admin || copilot.data?.student_allowed
                  ? [
                      {
                        to: "/copilot",
                        label: "Copilot",
                        description: "AI-помощник на интервью",
                      },
                    ]
                  : []),
                ...(student
                  ? [
                      {
                        to: "/interviews/personal-review",
                        label: "Личные вопросы",
                      },
                    ]
                  : []),
                ...(mentor
                  ? [
                      {
                        to: "/mentor/interview-reviews",
                        label: "Разборы интервью",
                        description: "AI и менторский фидбек",
                      },
                    ]
                  : []),
              ],
            },
            {
              label: "Люди",
              items: [
                ...(student ? [{ to: "/my-mentor", label: "Мой ментор" }] : []),
                ...(mentor
                  ? [
                      { to: "/mentor/profile", label: "Профиль ментора" },
                      {
                        to: "/mentor/students",
                        label: admin ? "Прогресс учеников" : "Ученики",
                      },
                    ]
                  : []),
                ...(admin
                  ? [
                      { to: "/admin/applications", label: "Заявки" },
                      { to: "/admin/students", label: "Управление учениками" },
                      { to: "/admin/mentors", label: "Менторы" },
                    ]
                  : []),
              ],
            },
            {
              label: "Деньги",
              items: [
                ...(student ? [{ to: "/payments", label: "Мои платежи" }] : []),
                ...(mentor
                  ? [{ to: "/mentor/rewards", label: "Вознаграждения" }]
                  : []),
                ...(admin
                  ? [{ to: "/admin/payments", label: "Платежи учеников" }]
                  : []),
              ],
            },
            {
              label: "Модерация",
              collapsible: true,
              items: [
                ...(mentor
                  ? [
                      {
                        to: admin
                          ? "/admin/card-automation/clusters"
                          : "/mentor/card-automation/clusters",
                        label: "Модерация AI-карточек",
                        active: location.pathname.includes("/card-automation"),
                      },
                    ]
                  : []),
                ...(admin
                  ? [
                      {
                        to: "/admin/interview-question-moderation",
                        label: "Вопросы из разборов",
                      },
                      {
                        to: "/admin/company-alias-proposals",
                        label: "Названия компаний",
                      },
                    ]
                  : []),
              ],
            },
            {
              label: "Справочники",
              items: admin
                ? [
                    { to: "/admin/schedule", label: "Расписание" },
                    { to: "/admin/useful-links", label: "Полезные ссылки" },
                    { to: "/admin/tracks", label: "Направления обучения" },
                    { to: "/admin/roadmaps", label: "Роадмапы — редактор" },
                    { to: "/admin/knowledge", label: "Редактор знаний" },
                    { to: "/admin/interviews", label: "Редактор карточек" },
                  ]
                : [],
            },
          ]
            .filter((group) => group.items.length > 0)
            .map((group) => {
              const links = group.items.map((item) => (
                <NavLink
                  key={item.to}
                  component={Link}
                  to={item.to}
                  label={item.label}
                  leftSection={<NavigationIcon to={item.to} />}
                  description={
                    "description" in item ? item.description : undefined
                  }
                  className="brand-nav-link"
                  active={
                    "active" in item
                      ? item.active
                      : location.pathname.startsWith(item.to) ||
                        (item.to === "/roadmaps" &&
                          location.pathname.startsWith("/topics"))
                  }
                  onClick={close}
                />
              ));
              return (
                <AppShell.Section key={group.label} className="nav-group">
                  {group.collapsible ? (
                    <NavLink
                      component="button"
                      type="button"
                      label={group.label}
                      leftSection={
                        <NavigationIcon to="/admin/card-automation/clusters" />
                      }
                      className="brand-nav-link"
                      childrenOffset={12}
                      defaultOpened={group.items.some((item) =>
                        "active" in item
                          ? item.active
                          : location.pathname.startsWith(item.to),
                      )}
                    >
                      {links}
                    </NavLink>
                  ) : (
                    <>
                      <Text className="nav-group-label" px="sm">
                        {group.label}
                      </Text>
                      {links}
                    </>
                  )}
                </AppShell.Section>
              );
            })}
          {import.meta.env.DEV && !platform.isTelegram && (
            <NavLink
              component={Link}
              to="/dev-login"
              label="Сменить роль"
              leftSection={<NavigationIcon to="/dev-login" />}
              className="brand-nav-link change-user-link"
              onClick={close}
            />
          )}
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main inert={isMobile && opened}>
        {navigation.state !== "idle" && (
          <Progress
            value={100}
            size="xs"
            className="route-progress"
            aria-label="Загружаем раздел"
          />
        )}
        <div className="page-container" id="main-content" tabIndex={-1}>
          <Outlet />
        </div>
      </AppShell.Main>
    </AppShell>
  );
}
