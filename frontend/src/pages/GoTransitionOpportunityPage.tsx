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
import { type FormEvent, useState } from "react";
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
import { OpportunityFlow } from "../features/opportunities/OpportunityFlow";
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

const statusColors: Record<GoTransitionStatus, string> = {
  submitted: "blue",
  approved: "yellow",
  payment_pending: "yellow",
  paid: "green",
  rejected: "red",
  cancelled: "gray",
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
  const motivationLength = motivation.trim().length;
  const activeApplications = query.data.go_transition_applications.filter(
    (item) => !["paid", "rejected", "cancelled"].includes(item.status),
  );
  const notifyError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });
  const submitApplication = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!offer?.available || motivationLength < 10) return;
    create.mutate(
      { motivation: motivation.trim() },
      {
        onSuccess: () => {
          setMotivation("");
          notifications.show({
            color: "green",
            message: "Заявка отправлена и появилась в разделе ниже",
          });
        },
        onError: notifyError,
      },
    );
  };

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
      {activeApplications.length > 0 && (
        <Alert color="blue" title="Заявка уже в работе">
          <Group justify="space-between" align="center" mt="xs">
            <Text size="sm">
              Текущий статус и следующее действие находятся в разделе «Мои
              заявки».
            </Text>
            <Button
              component="a"
              href="#go-applications"
              variant="light"
              size="sm"
            >
              Перейти к заявке
            </Button>
          </Group>
        </Alert>
      )}
      <OpportunityFlow
        steps={[
          {
            title: "Изучите программу",
            description: "Содержание, стоимость и условия после оффера",
          },
          {
            title: "Подайте заявку",
            description: "Команда оценит цель и текущую ситуацию",
          },
          {
            title: "Примите условия",
            description: "Зафиксированные условия будут показаны отдельно",
          },
          {
            title: "Оплатите и начните",
            description: "После оплаты откроется Go-направление",
          },
        ]}
      />
      <ProgramDescription
        description={query.data.go_transition_description_markdown}
      />
      {offer ? (
        <Card withBorder className="opportunity-card">
          <Stack>
            <Text className="brand-eyebrow">Условия для выпускников</Text>
            <Group align="baseline">
              <Title order={2} c="blue">
                {formatRubles(offer.upfront_price_kopecks ?? 0)}
              </Title>
              <Text>
                + {offer.success_fee_percent ?? 0}% месячной зарплаты после
                Go-оффера
              </Text>
            </Group>
            {offer.comparison_upfront_price_kopecks !== null && (
              <Text c="dimmed">
                Стандартные условия:{" "}
                {formatRubles(offer.comparison_upfront_price_kopecks)} и{" "}
                {offer.comparison_success_fee_percent ?? 0}% после оффера.
              </Text>
            )}
          </Stack>
        </Card>
      ) : (
        <Alert color="gray" title="Программа временно недоступна">
          Команда ещё не опубликовала условия перехода. Вернитесь к этому
          разделу позже.
        </Alert>
      )}

      {offer?.available ? (
        <Card withBorder component="form" onSubmit={submitApplication}>
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
              minLength={10}
              maxLength={5000}
              required
              value={motivation}
              onChange={(event) => setMotivation(event.currentTarget.value)}
              error={
                motivation.length > 0 && motivationLength < 10
                  ? "Расскажите чуть подробнее — минимум 10 символов"
                  : undefined
              }
            />
            <Text size="xs" c="dimmed" ta="right">
              {motivationLength} / 5000
            </Text>
            <Button
              type="submit"
              color="yellow"
              disabled={motivationLength < 10}
              loading={create.isPending}
            >
              Подать заявку
            </Button>
          </Stack>
        </Card>
      ) : (
        <Alert color="gray" title="Подача заявки сейчас недоступна">
          {offer?.unavailable_reason ??
            "Программа временно отключена. Описание сохранено для ознакомления."}
        </Alert>
      )}

      {query.data.go_transition_applications.length > 0 && (
        <Stack id="go-applications" style={{ scrollMarginTop: 24 }}>
          <Title order={2}>Мои заявки</Title>
          {query.data.go_transition_applications.map((item) => {
            const snapshotPrice = Number(
              item.terms_snapshot?.upfront_price_kopecks ??
                item.upfront_price_kopecks,
            );
            const snapshotPercent = Number(
              item.terms_snapshot?.success_fee_percent ??
                item.success_fee_percent,
            );
            const termsExpired = Boolean(
              item.terms_expires_at &&
              new Date(item.terms_expires_at).getTime() <= Date.now(),
            );
            return (
              <Card
                withBorder
                key={item.id}
                className="opportunity-request-card"
                data-complete={item.status === "paid"}
              >
                <Group justify="space-between" align="flex-start" wrap="wrap">
                  <div className="opportunity-request-main">
                    <Title order={3}>Переход Python → Go</Title>
                    <Text
                      c="dimmed"
                      style={{
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                      }}
                    >
                      {item.motivation}
                    </Text>
                    <Text size="sm" c="dimmed" mt="xs">
                      Заявка от{" "}
                      {new Date(item.created_at).toLocaleDateString("ru-RU")}
                    </Text>
                    {item.admin_note && (
                      <Alert
                        color="blue"
                        variant="light"
                        mt="sm"
                        title="Комментарий команды"
                      >
                        <Text
                          style={{
                            whiteSpace: "pre-wrap",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {item.admin_note}
                        </Text>
                      </Alert>
                    )}
                  </div>
                  <Stack
                    align="flex-end"
                    className="opportunity-request-actions"
                  >
                    <Badge color={statusColors[item.status]}>
                      {statusLabels[item.status]}
                    </Badge>
                    {item.status === "approved" && (
                      <Stack align="flex-end">
                        <Alert
                          color={termsExpired ? "red" : "yellow"}
                          title={`Зафиксированные условия · версия ${item.terms_version}`}
                        >
                          <Stack gap={4}>
                            <Text size="sm" fw={700}>
                              {formatRubles(snapshotPrice)} + {snapshotPercent}%
                              после Go-оффера
                            </Text>
                            {item.terms_expires_at && (
                              <Text size="xs">
                                {termsExpired
                                  ? "Срок принятия условий истёк. Свяжитесь с командой."
                                  : `Принять до ${new Date(item.terms_expires_at).toLocaleString("ru-RU")}`}
                              </Text>
                            )}
                          </Stack>
                        </Alert>
                        <Checkbox
                          disabled={termsExpired}
                          checked={acceptedApplicationId === item.id}
                          onChange={(event) =>
                            setAcceptedApplicationId(
                              event.currentTarget.checked ? item.id : null,
                            )
                          }
                          label="Я ознакомился и принимаю условия"
                        />
                        <Button
                          disabled={
                            termsExpired || acceptedApplicationId !== item.id
                          }
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
                      <>
                        {!me.data?.email && (
                          <Alert color="orange" title="Нужен email для чека">
                            <Stack gap="xs">
                              <Text size="sm">
                                Сохраните email, после этого станет доступна
                                оплата.
                              </Text>
                              <Button
                                component={Link}
                                to="/payments"
                                variant="light"
                                size="xs"
                              >
                                Указать email
                              </Button>
                            </Stack>
                          </Alert>
                        )}
                        <Button
                          disabled={!me.data?.email}
                          loading={
                            payment.isPending && payment.variables === item.id
                          }
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
                      </>
                    )}
                  </Stack>
                </Group>
              </Card>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}

function ProgramDescription({ description }: { description: string }) {
  return (
    <Paper withBorder p={{ base: "md", sm: "xl" }} className="markdown-content">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {description}
      </ReactMarkdown>
    </Paper>
  );
}
