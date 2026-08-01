import {
  Alert,
  Button,
  Center,
  Paper,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { ApiError } from "../api/client";
import { getDevUserId } from "../features/auth/devAuth";
import { useMe } from "../features/auth/queries";
import { usePlatform } from "../platform/usePlatform";
import { LoadingState } from "./LoadingState";

export function ProtectedLayout() {
  const platform = usePlatform();
  const location = useLocation();
  const hasTelegramAuth = Boolean(platform.getTelegramInitData());
  const hasDevAuth = import.meta.env.DEV && Boolean(getDevUserId());
  const shouldCheckSession =
    !platform.isTelegram || hasTelegramAuth || hasDevAuth;
  const query = useMe(shouldCheckSession);

  if (platform.isTelegram && !hasTelegramAuth && !hasDevAuth) {
    return (
      <Center mih="100vh" p="md">
        <Paper withBorder p="xl" maw={520}>
          <Stack>
            <Title order={2}>Не удалось войти через Telegram</Title>
            <Text c="dimmed">
              Откройте приложение заново из меню бота. Telegram не передал
              данные для входа.
            </Text>
            <Button onClick={() => platform.close()}>Закрыть Mini App</Button>
          </Stack>
        </Paper>
      </Center>
    );
  }

  if (query.isPending) {
    return <LoadingState label="Проверяем вход…" />;
  }

  if (query.isError) {
    const apiError = query.error instanceof ApiError ? query.error : null;
    const expired = apiError?.status === 401;
    const accessNotGranted = apiError?.code === "platform_access_not_granted";
    if (!platform.isTelegram && expired) {
      const next = encodeURIComponent(`${location.pathname}${location.search}`);
      return (
        <Navigate
          to={import.meta.env.DEV ? "/dev-login" : `/login?next=${next}`}
          replace
        />
      );
    }
    return (
      <Center mih="100vh" p="md">
        <Alert
          color="brandYellow"
          title={accessNotGranted ? "Доступ ещё не открыт" : "Вход не выполнен"}
          maw={520}
        >
          <Stack align="flex-start">
            <Text>
              {accessNotGranted
                ? "Вернитесь в бота и завершите оплату. После подтверждения откройте платформу ещё раз."
                : expired
                  ? "Сессия Telegram истекла. Закройте Mini App и откройте его заново."
                  : "Не удалось проверить данные пользователя. Попробуйте ещё раз."}
            </Text>
            {accessNotGranted ? (
              <Button variant="light" onClick={() => platform.close()}>
                Вернуться в бота
              </Button>
            ) : (
              <Button variant="light" onClick={() => void query.refetch()}>
                Повторить
              </Button>
            )}
          </Stack>
        </Alert>
      </Center>
    );
  }

  const onboardingRoute = location.pathname === "/onboarding";
  if (!query.data.onboarding_completed_at && !onboardingRoute) {
    return <Navigate to="/onboarding" replace />;
  }
  if (query.data.onboarding_completed_at && onboardingRoute) {
    return <Navigate to="/roadmaps" replace />;
  }
  return <Outlet />;
}
