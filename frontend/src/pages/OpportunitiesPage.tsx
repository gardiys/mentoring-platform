import {
  Alert,
  Badge,
  Button,
  Card,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { Link, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useCompleteDevelopmentOpportunityPayment,
  useMyOpportunities,
} from "../features/opportunities/queries";

export function OpportunitiesPage() {
  const query = useMyOpportunities();
  const completeDevelopment = useCompleteDevelopmentOpportunityPayment();
  const [searchParams, setSearchParams] = useSearchParams();
  const localPayment = searchParams.get("local_payment");

  if (query.isPending) return <LoadingState label="Загружаем возможности…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Персональные предложения"
        title="Возможности"
        description="Здесь собраны дополнительные программы и сервисы команды. Состав предложений зависит от текущего этапа обучения и уже завершённых направлений."
      />

      {import.meta.env.DEV && localPayment && (
        <Alert color="blue" title="Локальная тестовая оплата">
          <Stack gap="sm">
            <Text size="sm">
              Подтвердите тестовую оплату, чтобы проверить сценарий без
              обращения к банку.
            </Text>
            <Button
              w="fit-content"
              loading={completeDevelopment.isPending}
              onClick={() =>
                completeDevelopment.mutate(localPayment, {
                  onSuccess: () => {
                    const next = new URLSearchParams(searchParams);
                    next.delete("local_payment");
                    setSearchParams(next, { replace: true });
                    notifications.show({
                      color: "green",
                      message: "Тестовая оплата проведена",
                    });
                  },
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                })
              }
            >
              Завершить тестовую оплату
            </Button>
          </Stack>
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
        {query.data.has_active_program && (
          <Card withBorder className="opportunity-card">
            <Stack h="100%" gap="lg">
              <div>
                <Badge color="blue" variant="light" mb="sm">
                  Действующая программа
                </Badge>
                <Title order={2}>Поддержка во время обучения</Title>
              </div>
              <Text>
                Расписание созвонов, контакты ментора, полезные ссылки и
                персональные материалы собраны в одном месте.
              </Text>
              <Button component={Link} to="/my-mentor" mt="auto">
                Перейти к поддержке ментора
              </Button>
            </Stack>
          </Card>
        )}

        {(query.data.has_alumni_access || query.data.has_active_program) && (
          <Card withBorder className="opportunity-card">
            <Stack h="100%" gap="lg">
              <div>
                <Badge
                  color={query.data.has_alumni_access ? "yellow" : "gray"}
                  variant="light"
                  mb="sm"
                >
                  {query.data.has_alumni_access
                    ? "После программы"
                    : "Режим просмотра"}
                </Badge>
                <Title order={2}>Кабинет выпускника</Title>
              </div>
              <Text>
                {query.data.has_alumni_access
                  ? "Консультации с менторами и специальные программы для следующего карьерного шага."
                  : "Посмотрите консультации с менторами и условия перехода Python → Go. Оформление станет доступно после завершения программы."}
              </Text>
              <Button component={Link} to="/opportunities/alumni" mt="auto">
                {query.data.has_alumni_access
                  ? "Открыть кабинет выпускника"
                  : "Посмотреть кабинет выпускника"}
              </Button>
            </Stack>
          </Card>
        )}
      </SimpleGrid>

      {!query.data.has_active_program && !query.data.has_alumni_access && (
        <Alert color="gray">
          Сейчас для вашего профиля нет доступных предложений. Они появятся
          здесь, когда будут соответствовать вашему этапу обучения.
        </Alert>
      )}
    </Stack>
  );
}
