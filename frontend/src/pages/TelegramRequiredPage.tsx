import {
  Alert,
  Button,
  Center,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Navigate, useSearchParams } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { API_URL } from "../api/client";
import { useMe } from "../features/auth/queries";
import { telegramMiniAppLink } from "../platform/telegramLinks";

const errorMessages: Record<string, string> = {
  platform_access_not_granted:
    "Твой Telegram-аккаунт пока не получил доступ. Заверши оплату в боте и попробуй снова.",
  student_access_suspended:
    "Доступ к платформе приостановлен. Свяжись с ментором или администратором.",
  invalid_login_state:
    "Запрос на вход устарел или уже был использован. Начни вход заново.",
  telegram_login_failed:
    "Telegram не подтвердил вход. Попробуй ещё раз или открой Mini App.",
};

function safeNextPath(value: string | null): string {
  return value?.startsWith("/") && !value.startsWith("//")
    ? value
    : "/roadmaps";
}

export function TelegramRequiredPage() {
  const me = useMe();
  const [searchParams] = useSearchParams();
  const botUrl =
    import.meta.env.VITE_TELEGRAM_BOT_URL ?? "https://telegram.org";
  const nextPath = safeNextPath(searchParams.get("next"));
  const loginUrl = `${API_URL}/api/v1/auth/web/telegram/start?next=${encodeURIComponent(nextPath)}`;
  const error = searchParams.get("error");

  if (me.data) return <Navigate to={nextPath} replace />;

  return (
    <Center className="login-shell">
      <Paper className="login-card">
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing={0}>
          <div className="login-brand-panel">
            <Stack gap="md" className="login-brand-copy">
              <BrandLogo />
              <Title order={1}>Время, потраченное не зря.</Title>
              <Text size="lg">
                Роадмапы, практика и поддержка ментора — в браузере и Telegram.
              </Text>
            </Stack>
          </div>
          <div className="login-form-panel">
            <Stack gap="lg">
              <div>
                <Text className="brand-eyebrow" mb="xs">
                  Вход в платформу
                </Text>
                <Title order={2}>Продолжить через Telegram</Title>
                <Text c="dimmed" size="sm" mt="xs">
                  Telegram подтвердит аккаунт, а платформа проверит твой доступ.
                  После входа сайт будет работать как обычное веб-приложение.
                </Text>
              </div>
              {error && (
                <Alert color="red" title="Не удалось войти">
                  {errorMessages[error] ?? errorMessages.telegram_login_failed}
                </Alert>
              )}
              <Button
                component="a"
                href={loginUrl}
                size="md"
                color="brandYellow"
              >
                Войти через Telegram
              </Button>
              <Button
                component="a"
                href={telegramMiniAppLink(botUrl)}
                variant="light"
              >
                Открыть Mini App
              </Button>
              <Text c="dimmed" size="xs">
                Новая регистрация на сайте не создаётся: доступ выдаёт бот после
                оплаты.
              </Text>
            </Stack>
          </div>
        </SimpleGrid>
      </Paper>
    </Center>
  );
}
