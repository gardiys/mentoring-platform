import { Alert, Button, Stack } from "@mantine/core";

import { ApiError } from "../api/client";

interface Props {
  error?: unknown;
  retry?: () => void;
}

function errorCopy(error: unknown): { title: string; message: string } {
  if (!(error instanceof ApiError)) {
    return {
      title: "Не удалось загрузить данные",
      message: "Проверь соединение и попробуй ещё раз.",
    };
  }
  if (error.code === "network_error" || error.status === 0) {
    return { title: "Нет связи с сервером", message: error.message };
  }
  if (error.status === 403) {
    return {
      title: "Недостаточно прав",
      message: "Этот раздел недоступен для твоей роли.",
    };
  }
  if (error.status === 404) {
    return {
      title: "Данные не найдены",
      message: "Возможно, запись была удалена или ссылка устарела.",
    };
  }
  return {
    title: "Не удалось загрузить данные",
    message:
      error.status >= 500
        ? "Сервис временно недоступен. Попробуй ещё раз чуть позже."
        : error.message,
  };
}

export function ErrorState({ error, retry }: Props) {
  const copy = errorCopy(error);
  return (
    <Alert
      color="red"
      icon={<span aria-hidden="true">!</span>}
      title={copy.title}
      className="brand-alert"
    >
      <Stack align="flex-start" gap="sm">
        {copy.message}
        {retry && (
          <Button variant="light" onClick={retry}>
            Повторить
          </Button>
        )}
      </Stack>
    </Alert>
  );
}
