import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMyOpportunities } from "../features/opportunities/queries";
import { formatRubles } from "../utils/money";

export function AlumniOpportunitiesPage() {
  const query = useMyOpportunities();

  if (query.isPending)
    return <LoadingState label="Загружаем кабинет выпускника…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  const consultation = query.data.opportunities.find(
    (item) => item.code === "ALUMNI_CONSULTATION",
  );
  const transition = query.data.opportunities.find(
    (item) => item.code === "PYTHON_TO_GO_ALUMNI",
  );

  return (
    <Stack gap="xl">
      <Button
        component={Link}
        to="/opportunities"
        variant="subtle"
        w="fit-content"
      >
        ← К возможностям
      </Button>
      <PageHeader
        eyebrow="После программы"
        title="Кабинет выпускника"
        description="Продолжайте пользоваться поддержкой команды после завершения программы: разбирайте рабочие и карьерные задачи с менторами или переходите в новое направление на специальных условиях."
      />
      {!query.data.has_alumni_access && (
        <Alert color="blue" title="Режим просмотра">
          Вы можете заранее изучить форматы, цены и условия. Отправка заявок и
          оплата станут доступны после завершения программы.
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
        <Card withBorder>
          <Stack h="100%" gap="lg">
            <div>
              <Text className="brand-eyebrow">Поддержка команды</Text>
              <Title order={2}>Консультации</Title>
            </div>
            <Text>
              Выберите подходящий формат: рабочая задача, техническое
              мок-интервью, системный дизайн, резюме или свободная тема.
            </Text>
            <Group align="baseline">
              <Text c="dimmed">от</Text>
              <Title order={3} c="blue">
                {formatRubles(consultation?.price?.amount_kopecks ?? 0)}
              </Title>
              <Text td="line-through" c="dimmed">
                {formatRubles(
                  consultation?.comparison_price?.amount_kopecks ?? 0,
                )}
              </Text>
              <Badge color="yellow">Для выпускников</Badge>
            </Group>
            {!consultation?.available && (
              <Alert color="gray">{consultation?.unavailable_reason}</Alert>
            )}
            <Button
              component={Link}
              to="/opportunities/alumni/consultations"
              mt="auto"
            >
              Посмотреть форматы консультаций
            </Button>
          </Stack>
        </Card>
        <Card withBorder>
          <Stack h="100%" gap="lg">
            <div>
              <Text className="brand-eyebrow">Новое направление</Text>
              <Title order={2}>Переход Python → Go</Title>
            </div>
            <Text>
              Программа для выпускников Python, которые хотят освоить Go с
              поддержкой команды и подготовиться к выходу на новое направление.
            </Text>
            <Group align="baseline">
              <Title order={3} c="blue">
                {formatRubles(transition?.upfront_price_kopecks ?? 0)}
              </Title>
              <Text>
                + {transition?.success_fee_percent ?? 0}% после Go-оффера
              </Text>
            </Group>
            {!transition?.available && (
              <Alert color="gray">{transition?.unavailable_reason}</Alert>
            )}
            <Button
              component={Link}
              to="/opportunities/alumni/go-transition"
              color="yellow"
              mt="auto"
            >
              Подробнее о программе
            </Button>
          </Stack>
        </Card>
      </SimpleGrid>
    </Stack>
  );
}
