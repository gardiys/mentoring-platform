import { Button, Center, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <Center mih="100vh" className="not-found-page">
      <Stack align="center" ta="center">
        <img
          src="/brand/avatar-memes.png"
          alt="Геральт"
          className="not-found-mascot"
          decoding="async"
        />
        <Text className="brand-eyebrow">Ошибка навигации</Text>
        <Title>404 — тут ничего нет</Title>
        <Text c="dimmed">Страница не найдена</Text>
        <Button component={Link} to="/roadmaps">
          К роадмапам
        </Button>
      </Stack>
    </Center>
  );
}
