import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent } from "react";
import { useMe } from "../features/auth/queries";
import { useApplicationDraft } from "../features/opportunities/useApplicationDraft";
import { GoTransitionProgramDescription as ProgramDescription } from "../components/GoTransitionProgramDescription";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { LegalCheckout } from "../components/LegalCheckout";
import {
  useCreateGoTransition,
  useMyOpportunities,
} from "../features/opportunities/queries";
import { OpportunityFlow } from "../features/opportunities/OpportunityFlow";
import type { GoTransitionStatus } from "../types/api";
import { formatRubles } from "../utils/money";

const statusLabels: Record<GoTransitionStatus, string> = {
  submitted: "На рассмотрении",
  approved: "Одобрена — прими условия",
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

function GoTransitionApplicationForm({ userId }: { userId: string }) {
  const create = useCreateGoTransition();
  const draft = useApplicationDraft(
    `mentoring.go-motivation-draft.v1:${userId}`,
    { motivation: "" },
    { motivation: 5000 },
  );
  const motivation = draft.values.motivation ?? "";
  const motivationLength = motivation.trim().length;
  const notifyError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });
  const submitApplication = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (motivationLength < 10) return;
    void create
      .mutateAsync({ motivation: motivation.trim() })
      .then(() => {
        draft.reset();
        notifications.show({
          color: "green",
          message: "Заявка отправлена и появилась в разделе ниже",
        });
      })
      .catch(notifyError);
  };

  return (
    <Card withBorder component="form" onSubmit={submitApplication}>
      <Stack>
        <Title order={2}>Подать заявку</Title>
        <Text>
          Сначала команда рассмотрит вашу цель и текущую ситуацию. Оплата станет
          доступна только после одобрения и принятия зафиксированных условий.
        </Text>
        {draft.available ? (
          <Text size="sm" c="dimmed">
            Черновик сохраняется автоматически на этом устройстве.
          </Text>
        ) : (
          <Alert color="yellow" title="Не удалось сохранить черновик">
            Хранилище браузера недоступно. При закрытии страницы введённые
            данные могут потеряться.
          </Alert>
        )}
        <Textarea
          label="Зачем тебе Go-направление"
          description="Расскажи о цели перехода и ожидаемом результате"
          minRows={5}
          minLength={10}
          maxLength={5000}
          required
          value={motivation}
          onChange={(event) =>
            draft.setField("motivation", event.currentTarget.value)
          }
          error={
            motivation.length > 0 && motivationLength < 10
              ? "Расскажи чуть подробнее — минимум 10 символов"
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
  );
}

export function GoTransitionOpportunityPage() {
  const query = useMyOpportunities();
  const me = useMe();

  if (query.isPending || me.isPending)
    return <LoadingState label="Загружаем программу перехода…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  if (me.isError)
    return <ErrorState error={me.error} retry={() => void me.refetch()} />;

  const offer = query.data.opportunities.find(
    (item) => item.code === "PYTHON_TO_GO_ALUMNI",
  );
  const activeApplications = query.data.go_transition_applications.filter(
    (item) => !["paid", "rejected", "cancelled"].includes(item.status),
  );

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
            title: "Изучи программу",
            description: "Содержание, стоимость и условия после оффера",
          },
          {
            title: "Подай заявку",
            description: "Команда оценит цель и текущую ситуацию",
          },
          {
            title: "Прими условия",
            description: "Зафиксированные условия будут показаны отдельно",
          },
          {
            title: "Оплати и начни",
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
          Команда ещё не опубликовала условия перехода. Вернись к этому разделу
          позже.
        </Alert>
      )}

      {offer?.available ? (
        <GoTransitionApplicationForm key={me.data.id} userId={me.data.id} />
      ) : (
        <Alert color="gray" title="Подача заявки сейчас недоступна">
          {offer?.unavailable_reason ??
            "Программа временно отключена. Описание сохранено для ознакомления."}
        </Alert>
      )}

      {query.data.go_transition_applications.length > 0 && (
        <Stack id="go-applications" className="anchor-target">
          <Title order={2}>Мои заявки</Title>
          {query.data.go_transition_applications.map((item) => {
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
                    <Text c="dimmed" className="wrap-copy">
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
                        <Text className="wrap-copy">{item.admin_note}</Text>
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
                    {["approved", "payment_pending"].includes(item.status) && (
                      <LegalCheckout
                        product="python_to_go_transition"
                        applicationId={item.id}
                      />
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
