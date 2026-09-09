import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Table,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { copilotApi, type CopilotRelease } from "../features/copilot/api";
import { useMe } from "../features/auth/queries";

const labels = {
  "mac-arm64": {
    title: "macOS · Apple Silicon",
    detail: "Для Mac с процессором Apple M1, M2, M3, M4 и новее",
    button: "Скачать для Mac · Apple Silicon",
    format: "DMG",
  },
  "mac-x64": {
    title: "macOS · Intel",
    detail: "Для Mac с процессором Intel",
    button: "Скачать для Mac · Intel",
    format: "DMG",
  },
  "win-x64": {
    title: "Windows",
    detail: "Для компьютеров с 64-битной Windows (x64)",
    button: "Скачать для Windows",
    format: "EXE",
  },
};

function ReleaseCard({ release }: { release: CopilotRelease }) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const label = labels[release.id];
  const download = async () => {
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setProgress(0);
    setError("");
    try {
      const blob = await copilotApi.download(
        release.id,
        request.signal,
        setProgress,
      );
      if (request.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = release.filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) {
      if (!request.signal.aborted)
        setError(
          reason instanceof Error
            ? reason.message
            : "Не удалось скачать файл. Повторите попытку.",
        );
    } finally {
      if (controller.current === request) {
        controller.current = null;
        setBusy(false);
      }
    }
  };
  return (
    <Card withBorder p="xl" radius="lg" component="article">
      <Stack h="100%" gap="md">
        <Group justify="space-between">
          <Badge variant="light">{label.format}</Badge>
          <Text size="sm" c="dimmed">
            v{release.version}
          </Text>
        </Group>
        <Title order={3}>{label.title}</Title>
        <Text c="dimmed" size="sm">
          {label.detail}
        </Text>
        <Text size="sm">
          {(release.size_bytes / 1024 / 1024).toFixed(1)} МБ
        </Text>
        {!release.signed && (
          <Text size="xs" c="dimmed">
            Тестовая сборка без подписи разработчика. ОС может запросить
            дополнительное подтверждение установки.
          </Text>
        )}
        <Stack mt="auto" gap="xs">
          <Button
            fullWidth
            aria-label={label.button}
            onClick={() => void download()}
            loading={busy}
          >
            Скачать {label.format}
          </Button>
          {busy && (
            <>
              <Progress value={progress} aria-label="Прогресс скачивания" />
              <Group justify="space-between">
                <Text size="xs" role="status">
                  Скачиваем: {progress}%
                </Text>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  onClick={() => controller.current?.abort()}
                >
                  Отменить
                </Button>
              </Group>
            </>
          )}
          {error && (
            <Text c="red" size="sm" role="alert">
              {error}
            </Text>
          )}
        </Stack>
      </Stack>
    </Card>
  );
}

export function CopilotPage() {
  const me = useMe();
  const access = useQuery({
    queryKey: ["copilot-access"],
    queryFn: copilotApi.access,
    refetchInterval: 60000,
  });
  const [offset, setOffset] = useState(0);
  const usage = useQuery({
    queryKey: ["copilot-usage", offset],
    queryFn: () => copilotApi.usage(offset),
    enabled: me.data?.role === "admin",
    refetchInterval: 30000,
  });
  const query = useQuery({
    queryKey: ["copilot-releases"],
    queryFn: copilotApi.releases,
    enabled: access.data?.allowed === true,
  });
  if (access.isPending)
    return <LoadingState label="Проверяем доступ к Copilot…" />;
  if (access.isError)
    return (
      <ErrorState error={access.error} retry={() => void access.refetch()} />
    );
  if (!access.data.allowed)
    return (
      <Alert title="Copilot пока недоступен" color="brandYellow">
        {access.data.reason}
      </Alert>
    );
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Copilot · Python & Go"
        title="Помощник на собеседовании"
        description="Interview Copilot — приложение для компьютера, которое помогает разбирать вопросы и формулировать ответы во время тренировочного интервью."
      />
      <Alert
        color="brandYellow"
        title={
          access.data.students_enabled
            ? "Доступ для проходящих собеседования"
            : "Закрытый доступ"
        }
      >
        {access.data.students_enabled
          ? "Copilot доступен активным ученикам со статусом «Ходит на собеседования»."
          : "Доступ учеников пока выключен. После открытия он будет доступен только активным ученикам со статусом «Ходит на собеседования»."}
      </Alert>
      {me.data?.role === "admin" && (
        <Card withBorder>
          <Stack>
            <Group justify="space-between">
              <Title order={2}>Использование Copilot учениками</Title>
              <Button variant="light" onClick={() => void usage.refetch()}>
                Обновить статистику
              </Button>
            </Group>
            <Text size="sm" c="dimmed">
              Серверное активное время без пауз и отключений. Учитываются все
              сессии, даже если ученик не загрузил запись. Обновление — примерно
              раз в минуту.
            </Text>
            {usage.isPending && <LoadingState label="Загружаем статистику…" />}
            {usage.isError && (
              <ErrorState
                error={usage.error}
                retry={() => void usage.refetch()}
              />
            )}
            {usage.data && (
              <>
                <Table.ScrollContainer minWidth={750}>
                  <Table
                    striped
                    highlightOnHover
                    aria-label="Статистика Copilot"
                  >
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Ученик</Table.Th>
                        <Table.Th>Доступ</Table.Th>
                        <Table.Th>Завершено</Table.Th>
                        <Table.Th>Реальных / тренировок</Table.Th>
                        <Table.Th>Время</Table.Th>
                        <Table.Th>Последнее интервью</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {usage.data.students.map((student) => (
                        <Table.Tr key={student.student_id}>
                          <Table.Td>{student.name}</Table.Td>
                          <Table.Td>
                            {student.student_allowed ? "Открыт" : "Закрыт"}
                          </Table.Td>
                          <Table.Td>{student.interviews_completed}</Table.Td>
                          <Table.Td>
                            {student.real_completed} / {student.mock_completed}
                          </Table.Td>
                          <Table.Td>
                            {Math.floor(student.active_ms / 3600000)} ч{" "}
                            {Math.floor(student.active_ms / 60000) % 60} мин
                          </Table.Td>
                          <Table.Td>
                            {student.last_interview_at
                              ? new Date(
                                  student.last_interview_at,
                                ).toLocaleString("ru-RU")
                              : "—"}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
                <Group justify="center">
                  <Button
                    variant="light"
                    disabled={!offset}
                    onClick={() => setOffset(Math.max(0, offset - 50))}
                  >
                    Назад
                  </Button>
                  <Text>
                    {Math.min(offset + 1, usage.data.total)}–
                    {Math.min(offset + 50, usage.data.total)} из{" "}
                    {usage.data.total}
                  </Text>
                  <Button
                    variant="light"
                    disabled={offset + 50 >= usage.data.total}
                    onClick={() => setOffset(offset + 50)}
                  >
                    Далее
                  </Button>
                </Group>
              </>
            )}
          </Stack>
        </Card>
      )}
      <SimpleGrid
        style={{
          gridTemplateColumns:
            "repeat(auto-fit, minmax(min(100%, 260px), 1fr))",
        }}
        spacing="lg"
      >
        {[
          [
            "01 / Слушает",
            "Расшифровывает разговор",
            "Показывает вашу речь и вопросы собеседника в отдельных дорожках.",
          ],
          [
            "02 / Подсказывает",
            "Помогает по запросу",
            "По кнопке или Ctrl+Space даёт короткую подсказку и развёрнутый ответ. Может разобрать задачу со скриншота.",
          ],
          [
            "03 / Учитывает контекст",
            "Опирается на ваши материалы",
            "Использует базу знаний, вопросы Python/Go и опубликованное резюме, если вы разрешили его обработку.",
          ],
        ].map(([step, title, text]) => (
          <Paper key={step} withBorder p="lg">
            <Stack gap="sm">
              <Text className="technical-label">{step}</Text>
              <Title order={3}>{title}</Title>
              <Text c="dimmed" size="sm">
                {text}
              </Text>
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>
      <Stack gap="md">
        <Title order={2}>Скачать Copilot</Title>
        <Text c="dimmed">
          Выберите сборку для своего компьютера. На Mac тип процессора указан в
          меню Apple → «Об этом Mac».
        </Text>
        {query.isPending && <LoadingState label="Загружаем список сборок…" />}
        {query.isError && (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        )}
        {query.data &&
          (query.data.releases.length ? (
            <SimpleGrid
              style={{
                gridTemplateColumns:
                  "repeat(auto-fit, minmax(min(100%, 260px), 1fr))",
              }}
              spacing="lg"
            >
              {query.data.releases.map((release) => (
                <ReleaseCard key={release.id} release={release} />
              ))}
            </SimpleGrid>
          ) : (
            <Alert title="Сборки скоро появятся" color="brandYellow">
              Файлы приложения ещё не загружены. Зайдите в раздел позже.
            </Alert>
          ))}
      </Stack>
      <Paper withBorder p={{ base: "lg", sm: "xl" }}>
        <Stack gap="md">
          <Title order={2}>Как начать</Title>
          <List type="ordered" spacing="sm">
            <List.Item>
              Скачайте и установите приложение для своей ОС.
            </List.Item>
            <List.Item>
              Войдите через менторскую платформу, когда доступ к сервису будет
              открыт.
            </List.Item>
            <List.Item>
              Выберите Python или Go, обновите материалы и разрешите доступ к
              микрофону и системному звуку.
            </List.Item>
            <List.Item>
              Начните тренировочное интервью. Запрашивайте подсказку, когда она
              нужна.
            </List.Item>
          </List>
          <Text size="sm" c="dimmed">
            Запись начинается только после вашего согласия. Для реального
            интервью нужно разрешение на использование AI. Copilot сохраняет
            расшифровку и ответы; фидбек остаётся в менторской платформе.
          </Text>
        </Stack>
      </Paper>
    </Stack>
  );
}
