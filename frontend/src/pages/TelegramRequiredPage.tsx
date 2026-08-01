import { Button, Center, Paper, Stack, Text, Title } from "@mantine/core";

export function TelegramRequiredPage() {
  return (
    <Center className="login-shell">
      <Paper className="login-card" maw={560} p="xl">
        <Stack gap="lg">
          <Text className="brand-eyebrow">Потрачено · Mentoring</Text>
          <Title order={1}>Откройте платформу в Telegram</Title>
          <Text c="dimmed">
            Авторизация выполняется через Mini App. Вернитесь в бот и нажмите
            кнопку входа в платформу — Telegram безопасно передаст данные вашей
            сессии.
          </Text>
          <Button
            component="a"
            href={
              import.meta.env.VITE_TELEGRAM_BOT_URL ?? "https://telegram.org"
            }
            variant="light"
          >
            Открыть Telegram
          </Button>
        </Stack>
      </Paper>
    </Center>
  );
}
