import {
  Badge,
  Button,
  Card,
  Center,
  Group,
  Progress,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { BrandLogo } from "../components/BrandLogo";
import { useCompleteOnboarding, useMe } from "../features/auth/queries";
import { usePlatform } from "../platform/usePlatform";

const steps = [
  {
    eyebrow: "01 · Маршрут",
    title: "Учитесь по понятному плану",
    description:
      "Роадмап разбит на короткие разделы и темы. Продвигайтесь последовательно или возвращайтесь к нужному материалу.",
  },
  {
    eyebrow: "02 · Прогресс",
    title: "Отмечайте реальный результат",
    description:
      "Начинайте тему, изучайте материал и отмечайте завершение. Общий прогресс пересчитается автоматически.",
  },
  {
    eyebrow: "03 · Ментор",
    title: "Ментор видит, где нужна помощь",
    description:
      "Ваш ментор видит статусы и даты прохождения тем — так созвоны становятся предметнее и полезнее.",
  },
] as const;

export function OnboardingPage() {
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const platform = usePlatform();
  const me = useMe();
  const mutation = useCompleteOnboarding();
  const step = steps[active] ?? steps[0];

  const finish = () => {
    mutation.mutate(undefined, {
      onSuccess: () => {
        platform.triggerSuccessFeedback();
        navigate("/roadmaps", { replace: true });
      },
    });
  };

  return (
    <Center className="onboarding-page">
      <Card className="onboarding-card">
        <Stack gap="xl">
          <Group justify="space-between" align="flex-start">
            <BrandLogo />
            <Badge color="brandYellow" c="brandNavy.9">
              Добро пожаловать
              {me.data?.first_name ? `, ${me.data.first_name}` : ""}
            </Badge>
          </Group>
          <Progress
            value={((active + 1) / steps.length) * 100}
            color="brandBlue"
            size={6}
          />
          <div className="onboarding-content">
            <div>
              <Text className="brand-eyebrow" mb="md">
                {step.eyebrow}
              </Text>
              <Title order={1}>{step.title}</Title>
              <Text size="lg" c="dimmed" mt="md" maw={640}>
                {step.description}
              </Text>
            </div>
            <img
              src="/brand/avatar-onboarding.png"
              alt=""
              className="onboarding-mascot"
              decoding="async"
            />
          </div>
          {mutation.isError && (
            <Text c="red" role="alert">
              Не удалось завершить онбординг. Попробуйте ещё раз.
            </Text>
          )}
          <Group justify="space-between">
            <Button
              variant="subtle"
              disabled={active === 0 || mutation.isPending}
              onClick={() => setActive((current) => current - 1)}
            >
              Назад
            </Button>
            {active < steps.length - 1 ? (
              <Button onClick={() => setActive((current) => current + 1)}>
                Продолжить
              </Button>
            ) : (
              <Button loading={mutation.isPending} onClick={finish}>
                Перейти к роадмапам
              </Button>
            )}
          </Group>
        </Stack>
      </Card>
    </Center>
  );
}
