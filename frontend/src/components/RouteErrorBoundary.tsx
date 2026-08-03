import { Alert, Button, Center, Stack, Text, Title } from "@mantine/core";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteErrorBoundary() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? error.status === 404
      ? "Страница не найдена или уже была удалена."
      : `Не удалось открыть страницу (${error.status}).`
    : error instanceof Error &&
        /chunk|dynamically imported module/i.test(error.message)
      ? "После обновления платформы браузер не смог загрузить новую версию раздела."
      : "При открытии раздела произошла непредвиденная ошибка.";

  return (
    <Center mih="100vh" p="md">
      <Alert color="brandYellow" maw={560} className="brand-alert">
        <Stack align="flex-start">
          <Title order={2}>Раздел не загрузился</Title>
          <Text>{message}</Text>
          <Button onClick={() => window.location.reload()}>
            Перезагрузить страницу
          </Button>
        </Stack>
      </Alert>
    </Center>
  );
}
