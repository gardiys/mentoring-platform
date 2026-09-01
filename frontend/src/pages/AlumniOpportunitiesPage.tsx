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
  const pythonRepeat = query.data.opportunities.find(
    (item) => item.code === "PYTHON_REPEAT_MENTORSHIP",
  );
  const activeConsultation = query.data.consultations.find(
    (item) => !["completed", "cancelled"].includes(item.status),
  );
  const activeTransition = query.data.go_transition_applications.find(
    (item) => !["paid", "rejected", "cancelled"].includes(item.status),
  );
  const hasOffers = Boolean(consultation || transition || pythonRepeat);

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
      {(activeConsultation || activeTransition) && (
        <Alert color="blue" title="У вас есть активные заявки">
          <Group mt="sm" gap="sm">
            {activeConsultation && (
              <Button
                component={Link}
                to="/opportunities/alumni/consultations"
                variant="light"
                size="sm"
              >
                Открыть консультацию
              </Button>
            )}
            {activeTransition && (
              <Button
                component={Link}
                to="/opportunities/alumni/go-transition"
                variant="light"
                size="sm"
              >
                Открыть заявку Python → Go
              </Button>
            )}
          </Group>
        </Alert>
      )}
      {!hasOffers && (
        <Alert color="gray" title="Предложения временно недоступны">
          Новые программы и консультации появятся здесь после их публикации
          командой.
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="xl">
        {consultation && (
          <Card withBorder className="opportunity-card">
            <Stack h="100%" gap="lg">
              <div>
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Text className="brand-eyebrow">Поддержка команды</Text>
                    <Title order={2}>Консультации</Title>
                  </div>
                  {activeConsultation && (
                    <Badge color="blue" variant="light">
                      Заявка в работе
                    </Badge>
                  )}
                </Group>
              </div>
              <Text>
                Выберите подходящий формат: рабочая задача, техническое
                мок-интервью, системный дизайн, резюме или свободная тема.
              </Text>
              {consultation.price && (
                <Stack gap={2}>
                  <Group gap="xs" align="baseline">
                    <Text c="dimmed" size="sm">
                      Для выпускника от
                    </Text>
                    <Title order={3} c="blue">
                      {formatRubles(consultation.price.amount_kopecks)}
                    </Title>
                  </Group>
                  {consultation.comparison_price &&
                    consultation.comparison_price.amount_kopecks >
                      consultation.price.amount_kopecks && (
                      <Text size="sm" c="dimmed">
                        Обычная цена:{" "}
                        <Text span td="line-through">
                          {formatRubles(
                            consultation.comparison_price.amount_kopecks,
                          )}
                        </Text>
                      </Text>
                    )}
                </Stack>
              )}
              {!consultation.available && (
                <Alert color="gray">
                  {consultation.unavailable_reason ??
                    "Оформление консультаций временно недоступно"}
                </Alert>
              )}
              <Button
                component={Link}
                to="/opportunities/alumni/consultations"
                mt="auto"
              >
                {activeConsultation
                  ? "Продолжить работу с заявкой"
                  : "Посмотреть форматы консультаций"}
              </Button>
            </Stack>
          </Card>
        )}
        {pythonRepeat && (
          <Card withBorder className="opportunity-card">
            <Stack h="100%" gap="lg">
              <div>
                <Text className="brand-eyebrow">Новый карьерный цикл</Text>
                <Title order={2}>Повторное менторство по Python</Title>
              </div>
              <Text>
                Диагностика, персональный план и сопровождение до нового Python
                Backend оффера без сброса старого прогресса.
              </Text>
              <Group align="baseline">
                <Title order={3} c="blue">
                  {formatRubles(pythonRepeat?.upfront_price_kopecks ?? 0)}
                </Title>
                <Text>
                  + {pythonRepeat?.success_fee_percent ?? 0}% от оффера
                </Text>
              </Group>
              {!pythonRepeat?.available && (
                <Alert color="gray">{pythonRepeat?.unavailable_reason}</Alert>
              )}
              <Button
                component={Link}
                to="/opportunities/alumni/python-repeat"
                mt="auto"
              >
                Подробнее и подать заявку
              </Button>
            </Stack>
          </Card>
        )}
        {transition && (
          <Card withBorder className="opportunity-card">
            <Stack h="100%" gap="lg">
              <Group justify="space-between" align="flex-start">
                <div>
                  <Text className="brand-eyebrow">Новое направление</Text>
                  <Title order={2}>Переход Python → Go</Title>
                </div>
                {activeTransition && (
                  <Badge color="blue" variant="light">
                    Заявка в работе
                  </Badge>
                )}
              </Group>
              <Text>
                Программа для выпускников Python, которые хотят освоить Go с
                поддержкой команды и подготовиться к выходу на новое
                направление.
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
                {activeTransition
                  ? "Продолжить работу с заявкой"
                  : "Подробнее о программе"}
              </Button>
            </Stack>
          </Card>
        )}
      </SimpleGrid>
    </Stack>
  );
}
