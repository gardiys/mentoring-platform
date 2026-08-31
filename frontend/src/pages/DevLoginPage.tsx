import {
  Button,
  Center,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  clearDevUserId,
  getDevUserId,
  setDevUserId,
} from "../features/auth/devAuth";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function DevLoginPage() {
  const [value, setValue] = useState(getDevUserId() ?? "");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const valid = UUID_PATTERN.test(value.trim());

  const login = (id: string, destination = "/roadmaps") => {
    queryClient.clear();
    setDevUserId(id);
    navigate(destination);
  };

  return (
    <Center className="login-shell">
      <Paper className="login-card">
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing={0}>
          <div className="login-brand-panel">
            <Stack gap="md" className="login-brand-copy">
              <Text className="brand-eyebrow">Потрачено · Mentoring</Text>
              <Title order={1}>Расти в бэкенде. По понятному плану.</Title>
              <Text size="lg">
                Роадмапы, практика и поддержка ментора — без токсичного
                техношума.
              </Text>
            </Stack>
            <img
              src="/brand/avatar-public.png"
              alt="Геральт"
              className="login-mascot"
              decoding="async"
            />
          </div>
          <div className="login-form-panel">
            <Stack gap="lg">
              <div>
                <Text className="brand-eyebrow" mb="xs">
                  Вход в платформу
                </Text>
                <Title order={2}>Development-вход</Title>
                <Text c="dimmed" size="sm" mt="xs">
                  Временная авторизация MVP. UUID отправляется backend в
                  заголовке X-Dev-User-Id.
                </Text>
              </div>
              <TextInput
                label="UUID пользователя"
                placeholder="00000000-0000-0000-0000-000000000000"
                value={value}
                onChange={(event) => setValue(event.currentTarget.value)}
                error={value && !valid ? "Введите корректный UUID" : undefined}
              />
              <Button disabled={!valid} onClick={() => login(value.trim())}>
                Войти
              </Button>
              <div>
                <Text className="technical-label" mb="sm">
                  Быстрый вход
                </Text>
                <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="xs">
                  {import.meta.env.VITE_DEV_STUDENT_ID && (
                    <Button
                      variant="light"
                      onClick={() =>
                        login(import.meta.env.VITE_DEV_STUDENT_ID!)
                      }
                    >
                      Как ученик
                    </Button>
                  )}
                  {import.meta.env.VITE_DEV_MENTOR_ID && (
                    <Button
                      variant="light"
                      onClick={() => login(import.meta.env.VITE_DEV_MENTOR_ID!)}
                    >
                      Как ментор
                    </Button>
                  )}
                  {import.meta.env.VITE_DEV_ADMIN_ID && (
                    <Button
                      variant="light"
                      onClick={() => login(import.meta.env.VITE_DEV_ADMIN_ID!)}
                    >
                      Как админ
                    </Button>
                  )}
                  {import.meta.env.VITE_DEV_ALUMNI_ID && (
                    <Button
                      color="yellow"
                      variant="light"
                      onClick={() =>
                        login(
                          import.meta.env.VITE_DEV_ALUMNI_ID!,
                          "/opportunities",
                        )
                      }
                    >
                      Как выпускник
                    </Button>
                  )}
                </SimpleGrid>
              </div>
              <Button
                color="brandNavy"
                variant="subtle"
                onClick={() => {
                  clearDevUserId();
                  queryClient.clear();
                  setValue("");
                }}
              >
                Очистить пользователя
              </Button>
            </Stack>
          </div>
        </SimpleGrid>
      </Paper>
    </Center>
  );
}
