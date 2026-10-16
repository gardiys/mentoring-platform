import {
  Alert,
  Badge,
  Button,
  Card,
  Drawer,
  Group,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  opportunityKeys,
  useOpportunitySummary,
} from "../features/opportunities/queries";
import {
  workspaceApi,
  type WorkspaceItem,
  type WorkspaceTab,
} from "../features/opportunities/workspaceApi";
import {
  ConsultationPanel,
  GoPanel,
  OpportunityStage,
} from "../features/opportunities/OpportunityDetail";
import { OpportunitySettings } from "../features/opportunities/OpportunitySettings";
import { PythonRepeatApplicationCard } from "../features/opportunities/PythonRepeatApplicationCard";
import { formatRubles } from "../utils/money";
import {
  stageLabels,
  opportunityDate,
} from "../features/opportunities/workspaceLabels";

const paths: Record<WorkspaceTab, string> = {
  inbox: "/admin/opportunities",
  consultations: "/admin/opportunities/consultations",
  "go-transition": "/admin/opportunities/go-transition",
  "python-repeat": "/admin/opportunities/python-repeat",
  settings: "/admin/opportunities/settings",
};

function waitingLabel(value: string | null | undefined) {
  if (!value) return "";
  const hours = Math.max(
    0,
    (Date.now() - new Date(value).getTime()) / 3_600_000,
  );
  return hours >= 24
    ? `${Math.floor(hours / 24)} дн`
    : hours >= 1
      ? `${Math.floor(hours)} ч`
      : "меньше часа";
}

function WorkspaceDrawer() {
  const [params, setParams] = useSearchParams();
  const mobile = useMediaQuery("(max-width: 47.99em)");
  const consultationId = params.get("consultation");
  const goId = consultationId ? null : params.get("go");
  const repeatId = consultationId || goId ? null : params.get("application");
  const consultation = useQuery({
    queryKey: [...opportunityKeys.all, "consultation", consultationId],
    queryFn: () => workspaceApi.consultation(consultationId!),
    enabled: !!consultationId,
  });
  const go = useQuery({
    queryKey: [...opportunityKeys.all, "go", goId],
    queryFn: () => workspaceApi.go(goId!),
    enabled: !!goId,
  });
  const repeat = useQuery({
    queryKey: [...opportunityKeys.all, "repeat", repeatId],
    queryFn: () => workspaceApi.repeat(repeatId!),
    enabled: !!repeatId,
  });
  const active = consultationId ? consultation : goId ? go : repeat;
  const close = () => {
    const next = new URLSearchParams(params);
    ["consultation", "go", "application"].forEach((key) => next.delete(key));
    setParams(next, { replace: true });
  };
  return (
    <Drawer
      opened={!!(consultationId || goId || repeatId)}
      onClose={close}
      title={
        consultationId
          ? "Консультация"
          : goId
            ? "Заявка Python → Go"
            : "Повторное менторство по Python"
      }
      position="right"
      size={mobile ? "100%" : "lg"}
      padding={mobile ? "sm" : "lg"}
      closeButtonProps={{ "aria-label": "Закрыть заявку" }}
      styles={{ body: { minWidth: 0, overflowWrap: "anywhere" } }}
    >
      {active.isPending && <LoadingState label="Загружаем заявку…" />}
      {active.isError && (
        <ErrorState error={active.error} retry={() => void active.refetch()} />
      )}
      {consultationId && consultation.data && (
        <ConsultationPanel
          key={consultation.data.id}
          item={consultation.data}
        />
      )}
      {goId && go.data && <GoPanel key={go.data.id} item={go.data} />}
      {repeatId && repeat.data && (
        <PythonRepeatApplicationCard key={repeat.data.id} item={repeat.data} />
      )}
    </Drawer>
  );
}

export function AdminOpportunitiesPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const summary = useOpportunitySummary();
  const desktop = useMediaQuery("(min-width: 48em)");
  const tab = (Object.entries(paths).find(
    ([, value]) => value === location.pathname,
  )?.[0] ?? "inbox") as WorkspaceTab;
  const listTab = tab === "settings" ? "inbox" : tab;
  const query = useQuery({
    queryKey: [...opportunityKeys.all, "list", listTab, params.toString()],
    queryFn: () => workspaceApi.page(listTab, params),
    enabled: tab !== "settings",
  });
  const settings = useQuery({
    queryKey: [...opportunityKeys.all, "settings"],
    queryFn: workspaceApi.settings,
    enabled: tab === "consultations",
  });
  const filter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
  };
  const open = (item: WorkspaceItem) => {
    const next = new URLSearchParams(params);
    ["consultation", "go", "application"].forEach((key) => next.delete(key));
    next.set(
      item.product === "consultations"
        ? "consultation"
        : item.product === "go_transition"
          ? "go"
          : "application",
      item.id,
    );
    setParams(next);
  };
  const rows = query.data?.items ?? [];
  const wait = (item: WorkspaceItem) => (
    <Text
      size="sm"
      c={
        item.overdue
          ? "red"
          : item.waiting_since &&
              Date.now() - new Date(item.waiting_since).getTime() >= 86_400_000
            ? "yellow"
            : "dimmed"
      }
    >
      {item.waiting_since
        ? `Ждёт ${waitingLabel(item.waiting_since)}`
        : opportunityDate(item.key_date)}
    </Text>
  );
  return (
    <Stack gap="lg" style={{ minWidth: 0 }}>
      <PageHeader
        eyebrow="Администрирование"
        title="Возможности"
        description="Очередь заявок выпускников и следующие действия"
      />
      <Tabs
        value={tab}
        onChange={(value) => value && navigate(paths[value as WorkspaceTab])}
      >
        <Tabs.List>
          <Tabs.Tab value="inbox">
            Нужно сделать{" "}
            {summary.data?.needs_action_total
              ? `(${summary.data.needs_action_total})`
              : ""}
          </Tabs.Tab>
          <Tabs.Tab value="consultations">Консультации</Tabs.Tab>
          <Tabs.Tab value="go-transition">Python → Go</Tabs.Tab>
          <Tabs.Tab value="python-repeat">Повтор Python</Tabs.Tab>
          <Tabs.Tab value="settings">Настройки</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {tab === "settings" ? (
        <OpportunitySettings />
      ) : (
        <>
          {tab === "inbox" && (
            <SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }}>
              {Object.entries(query.data?.counts ?? {}).map(
                ([stage, count]) => (
                  <Button
                    key={stage}
                    variant={params.get("stage") === stage ? "filled" : "light"}
                    onClick={() =>
                      filter(
                        "stage",
                        params.get("stage") === stage ? null : stage,
                      )
                    }
                  >
                    {stageLabels[stage] ?? "Требуют действия"} · {count}
                  </Button>
                ),
              )}
            </SimpleGrid>
          )}
          <Group align="flex-end" grow>
            <TextInput
              label="Поиск заявок"
              placeholder="Имя, @telegram, email или ID"
              value={params.get("q") ?? ""}
              onChange={(event) => filter("q", event.currentTarget.value)}
            />
            {tab === "inbox" ? (
              <Select
                label="Продукт"
                placeholder="Все продукты"
                clearable
                value={params.get("product")}
                onChange={(value) => filter("product", value)}
                data={[
                  { value: "consultations", label: "Консультации" },
                  { value: "go_transition", label: "Python → Go" },
                  { value: "python_repeat", label: "Повтор Python" },
                ]}
              />
            ) : (
              <Select
                label="Группа заявок"
                value={params.get("group") ?? "active"}
                onChange={(value) => filter("group", value)}
                data={[
                  { value: "active", label: "Активные" },
                  { value: "needs_action", label: "Требуют действия" },
                  { value: "waiting", label: "Ожидание" },
                  { value: "completed", label: "Завершённые" },
                  { value: "cancelled", label: "Закрытые и отменённые" },
                  { value: "all", label: "Все" },
                ]}
              />
            )}
          </Group>
          {tab === "consultations" && (
            <Group grow>
              <Select
                label="Ментор"
                clearable
                placeholder="Все менторы"
                value={params.get("mentor_id")}
                onChange={(value) => filter("mentor_id", value)}
                data={(settings.data?.consultation_mentors ?? []).map(
                  (value) => ({
                    value: value.id,
                    label: `${value.first_name} ${value.last_name ?? ""}`,
                  }),
                )}
              />
              <Select
                label="Формат"
                clearable
                placeholder="Все форматы"
                value={params.get("consultation_type")}
                onChange={(value) => filter("consultation_type", value)}
                data={(settings.data?.consultation_types ?? []).map(
                  (value) => ({ value: value.code, label: value.title }),
                )}
              />
            </Group>
          )}
          {params.get("stage") && (
            <Group>
              <Badge>{stageLabels[params.get("stage")!] ?? "Этап"}</Badge>
              <Button
                size="compact-xs"
                variant="subtle"
                onClick={() => filter("stage", null)}
              >
                Сбросить этап
              </Button>
            </Group>
          )}
          {query.isPending && <LoadingState label="Загружаем заявки…" />}
          {query.isError && (
            <ErrorState
              error={query.error}
              retry={() => void query.refetch()}
            />
          )}
          {query.isSuccess && rows.length === 0 && (
            <Alert
              color="gray"
              title={tab === "inbox" ? "Всё разобрано" : "Заявки не найдены"}
            >
              {tab === "inbox" ? (
                <Group>
                  <Button
                    variant="subtle"
                    component={Link}
                    to={paths.consultations}
                  >
                    Все консультации
                  </Button>
                  <Button
                    variant="subtle"
                    component={Link}
                    to={paths["go-transition"]}
                  >
                    Все заявки на Go
                  </Button>
                  <Button
                    variant="subtle"
                    component={Link}
                    to={paths["python-repeat"]}
                  >
                    Все заявки на повтор Python
                  </Button>
                </Group>
              ) : (
                "Измените поиск или фильтры"
              )}
            </Alert>
          )}
          {rows.length > 0 &&
            (desktop ? (
              <Table verticalSpacing="md">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Выпускник и запрос</Table.Th>
                    <Table.Th>Следующий шаг</Table.Th>
                    <Table.Th>Дата / ожидание</Table.Th>
                    <Table.Th>Сумма</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((item) => (
                    <Table.Tr key={`${item.product}:${item.id}`}>
                      <Table.Td>
                        <Button
                          variant="subtle"
                          px={0}
                          onClick={() => open(item)}
                        >
                          {item.student.first_name} {item.student.last_name}
                        </Button>
                        <Text size="sm">{item.title}</Text>
                        <Text size="xs" c="dimmed">
                          {item.student.telegram_username
                            ? `@${item.student.telegram_username}`
                            : item.student.email}
                          {item.mentor
                            ? ` · ${item.mentor.first_name} ${item.mentor.last_name ?? ""}`
                            : ""}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <OpportunityStage stage={item.stage} />
                        <Text size="sm" mt={4}>
                          {item.next_action}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        {wait(item)}
                        <Text size="xs" c="dimmed">
                          {opportunityDate(item.key_date)}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        {item.amount_kopecks
                          ? formatRubles(item.amount_kopecks)
                          : "—"}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            ) : (
              <Stack>
                {rows.map((item) => (
                  <Card withBorder key={`${item.product}:${item.id}`}>
                    <Stack gap="xs">
                      <Group justify="space-between">
                        <Title order={3}>
                          {item.student.first_name} {item.student.last_name}
                        </Title>
                        <OpportunityStage stage={item.stage} />
                      </Group>
                      <Text size="sm">{item.title}</Text>
                      <Text c="dimmed" size="sm">
                        {item.student.telegram_username
                          ? `@${item.student.telegram_username}`
                          : item.student.email}
                      </Text>
                      <Text fw={600}>{item.next_action}</Text>
                      {wait(item)}
                      <Text size="sm">
                        {opportunityDate(item.key_date)}
                        {item.amount_kopecks
                          ? ` · ${formatRubles(item.amount_kopecks)}`
                          : ""}
                      </Text>
                      <Button variant="light" onClick={() => open(item)}>
                        Открыть заявку {item.student.first_name}
                      </Button>
                    </Stack>
                  </Card>
                ))}
              </Stack>
            ))}
          {query.data && query.data.total > query.data.page_size && (
            <Pagination
              value={query.data.page}
              total={Math.ceil(query.data.total / query.data.page_size)}
              onChange={(value) => {
                const next = new URLSearchParams(params);
                next.set("page", String(value));
                setParams(next, { replace: true });
              }}
            />
          )}
        </>
      )}
      <WorkspaceDrawer />
    </Stack>
  );
}
