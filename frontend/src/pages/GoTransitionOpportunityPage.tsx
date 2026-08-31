import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Paper,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import {
  useAcceptGoTransition,
  useCreateGoTransition,
  useCreateGoTransitionPaymentLink,
  useMyOpportunities,
} from "../features/opportunities/queries";
import type { GoTransitionStatus } from "../types/api";
import { formatRubles } from "../utils/money";
import { openExternalResource } from "../utils/openExternalResource";

const statusLabels: Record<GoTransitionStatus, string> = {
  submitted: "На рассмотрении",
  approved: "Одобрена — примите условия",
  payment_pending: "Ожидает оплаты",
  paid: "Оплачена, Go доступен",
  rejected: "Отклонена",
  cancelled: "Отменена",
};

export function GoTransitionOpportunityPage() {
  const query = useMyOpportunities();
  const me = useMe();
  const create = useCreateGoTransition();
  const accept = useAcceptGoTransition();
  const payment = useCreateGoTransitionPaymentLink();
  const [motivation, setMotivation] = useState("");
  const [acceptedApplicationId, setAcceptedApplicationId] = useState<
    string | null
  >(null);

  if (query.isPending)
    return <LoadingState label="Загружаем программу перехода…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const offer = query.data.opportunities.find(
    (item) => item.code === "PYTHON_TO_GO_ALUMNI",
  );
  const notifyError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });

  return (
    <Stack gap="xl">
      <Button
        component={Link}
        to="/opportunities/alumni"
        variant="subtle"
        w="fit-content"
      >
        ← В кабинет выпускника
      </Button>
      <PageHeader
        eyebrow="Кабинет выпускника"
        title="Программа перехода в Go"
        description="Специальный путь для выпускников Python-направления, которые хотят освоить Go и выйти на следующий оффер вместе с командой менторства."
      />
      <ProgramDescription
        description={query.data.go_transition_description_markdown}
      />
      <Card withBorder>
        <Stack>
          <Text className="brand-eyebrow">Условия для выпускников</Text>
          <Group align="baseline">
            <Title order={2} c="blue">
              {formatRubles(offer?.upfront_price_kopecks ?? 0)}
            </Title>
            <Text>
              + {offer?.success_fee_percent ?? 0}% месячной зарплаты после
              Go-оффера
            </Text>
          </Group>
          <Text c="dimmed">
            Стандартные условия:{" "}
            {formatRubles(offer?.comparison_upfront_price_kopecks ?? 0)} и{" "}
            {offer?.comparison_success_fee_percent ?? 0}% после оффера.
          </Text>
        </Stack>
      </Card>

      {offer?.available ? (
        <Card withBorder>
          <Stack>
            <Title order={2}>Подать заявку</Title>
            <Text>
              Сначала команда рассмотрит вашу цель и текущую ситуацию. Оплата
              станет доступна только после одобрения и принятия зафиксированных
              условий.
            </Text>
            <Textarea
              label="Зачем вам Go-направление"
              description="Расскажите о цели перехода и ожидаемом результате"
              minRows={5}
              value={motivation}
              onChange={(event) => setMotivation(event.currentTarget.value)}
            />
            <Button
              color="yellow"
              disabled={motivation.trim().length < 10}
              loading={create.isPending}
              onClick={() =>
                create.mutate(
                  { motivation: motivation.trim() },
                  {
                    onSuccess: () => {
                      setMotivation("");
                      notifications.show({
                        color: "green",
                        message: "Заявка отправлена",
                      });
                    },
                    onError: notifyError,
                  },
                )
              }
            >
              Подать заявку
            </Button>
          </Stack>
        </Card>
      ) : (
        <Alert color="gray">{offer?.unavailable_reason}</Alert>
      )}

      {query.data.go_transition_applications.length > 0 && (
        <Stack>
          <Title order={2}>Мои заявки</Title>
          {query.data.go_transition_applications.map((item) => (
            <Card withBorder key={item.id}>
              <Group justify="space-between" align="flex-start">
                <div>
                  <Title order={3}>Переход Python → Go</Title>
                  <Text c="dimmed">{item.motivation}</Text>
                  {item.admin_note && (
                    <Text mt="xs">Комментарий: {item.admin_note}</Text>
                  )}
                </div>
                <Stack align="flex-end">
                  <Badge>{statusLabels[item.status]}</Badge>
                  {item.status === "approved" && (
                    <Stack align="flex-end">
                      <Checkbox
                        checked={acceptedApplicationId === item.id}
                        onChange={(event) =>
                          setAcceptedApplicationId(
                            event.currentTarget.checked ? item.id : null,
                          )
                        }
                        label="Я ознакомился и принимаю условия"
                      />
                      <Button
                        disabled={acceptedApplicationId !== item.id}
                        loading={accept.isPending}
                        onClick={() =>
                          accept.mutate(item.id, { onError: notifyError })
                        }
                      >
                        Принять условия
                      </Button>
                    </Stack>
                  )}
                  {item.status === "payment_pending" && (
                    <Button
                      disabled={!me.data?.email}
                      loading={payment.isPending}
                      onClick={() =>
                        void openExternalResource(
                          payment
                            .mutateAsync(item.id)
                            .then((result) => result.payment_url),
                        ).catch(notifyError)
                      }
                    >
                      Оплатить {formatRubles(item.upfront_price_kopecks)}
                    </Button>
                  )}
                </Stack>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function ProgramDescription({ description }: { description: string }) {
  return (
    <Paper withBorder p={{ base: "md", sm: "xl" }} className="markdown-content">
      <ReactMarkdown>{description}</ReactMarkdown>
    </Paper>
  );
}
