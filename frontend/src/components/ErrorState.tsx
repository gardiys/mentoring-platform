import { Alert, Button, Stack } from "@mantine/core";

export function ErrorState({ retry }: { retry?: () => void }) {
  return (
    <Alert
      color="brandYellow"
      title="Не удалось загрузить данные"
      className="brand-alert"
    >
      <Stack align="flex-start" gap="sm">
        Проверьте соединение и попробуйте ещё раз.
        {retry && (
          <Button variant="light" color="brandNavy" onClick={retry}>
            Повторить
          </Button>
        )}
      </Stack>
    </Alert>
  );
}
