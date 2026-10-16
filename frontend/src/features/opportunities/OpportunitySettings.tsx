import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GoTransitionProgramDescription } from "../../components/GoTransitionProgramDescription";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import {
  useSetAdminConsultationMentor,
  useUpdateAdminGoTransitionProgram,
  useUpdateAdminConsultationType,
  opportunityKeys,
} from "./queries";
import { workspaceApi } from "./workspaceApi";
import type { OpportunitiesDashboard } from "../../types/api";
function ConsultationPriceCard({
  item,
}: {
  item: OpportunitiesDashboard["consultation_types"][number];
}) {
  const mutation = useUpdateAdminConsultationType();
  const [price, setPrice] = useState(item.price_kopecks / 100);
  const [comparisonPrice, setComparisonPrice] = useState(
    item.comparison_price_kopecks / 100,
  );
  const [mentorReward, setMentorReward] = useState(
    item.mentor_reward_kopecks / 100,
  );
  const [durationMinutes, setDurationMinutes] = useState(item.duration_minutes);
  useEffect(() => {
    setPrice(item.price_kopecks / 100);
    setComparisonPrice(item.comparison_price_kopecks / 100);
    setMentorReward(item.mentor_reward_kopecks / 100);
    setDurationMinutes(item.duration_minutes);
  }, [
    item.comparison_price_kopecks,
    item.duration_minutes,
    item.mentor_reward_kopecks,
    item.price_kopecks,
  ]);
  const invalid =
    price <= 0 ||
    comparisonPrice < price ||
    mentorReward < 0 ||
    mentorReward > price ||
    durationMinutes < 15 ||
    durationMinutes > 480;
  const dirty =
    Math.round(price * 100) !== item.price_kopecks ||
    Math.round(comparisonPrice * 100) !== item.comparison_price_kopecks ||
    Math.round(mentorReward * 100) !== item.mentor_reward_kopecks ||
    Math.round(durationMinutes) !== item.duration_minutes;
  const numberValue = (value: string | number) =>
    typeof value === "number" ? value : Number(value) || 0;

  return (
    <Card withBorder>
      <Stack h="100%">
        <div>
          <Title order={3}>{item.title}</Title>
          <Text size="sm" c="dimmed">
            {item.description}
          </Text>
        </div>
        <NumberInput
          label="Цена для выпускника"
          suffix=" ₽"
          min={1}
          step={500}
          value={price}
          onChange={(value) => setPrice(numberValue(value))}
        />
        <NumberInput
          label="Публичная цена"
          description="Показывается зачёркнутой для сравнения"
          suffix=" ₽"
          min={price}
          step={500}
          value={comparisonPrice}
          onChange={(value) => setComparisonPrice(numberValue(value))}
        />
        <NumberInput
          label="Вознаграждение ментора"
          suffix=" ₽"
          min={0}
          max={price}
          step={500}
          value={mentorReward}
          onChange={(value) => setMentorReward(numberValue(value))}
        />
        <NumberInput
          label="Длительность консультации"
          description="От 15 минут до 8 часов"
          suffix=" мин"
          min={15}
          max={480}
          step={15}
          value={durationMinutes}
          onChange={(value) => setDurationMinutes(numberValue(value))}
        />
        {invalid && (
          <Text c="red" size="sm">
            Публичная цена должна быть не ниже цены выпускника, а выплата
            ментору — не выше неё. Длительность — от 15 до 480 минут.
          </Text>
        )}
        <Button
          mt="auto"
          disabled={invalid || !dirty}
          loading={mutation.isPending}
          onClick={() =>
            mutation.mutate(
              {
                consultationType: item.code,
                priceKopecks: Math.round(price * 100),
                comparisonPriceKopecks: Math.round(comparisonPrice * 100),
                mentorRewardKopecks: Math.round(mentorReward * 100),
                durationMinutes: Math.round(durationMinutes),
              },
              {
                onSuccess: () =>
                  notifications.show({
                    color: "green",
                    message: `Тариф «${item.title}» обновлён`,
                  }),
                onError: (error) =>
                  notifications.show({ color: "red", message: error.message }),
              },
            )
          }
        >
          Сохранить тариф
        </Button>
      </Stack>
    </Card>
  );
}

function GoTransitionProgramSettings({ description }: { description: string }) {
  const mutation = useUpdateAdminGoTransitionProgram();
  const [value, setValue] = useState(description);
  useEffect(() => setValue(description), [description]);
  const dirty = value.trim() !== description.trim();

  return (
    <Card withBorder>
      <Stack>
        <div>
          <Title order={2}>Описание программы Python → Go</Title>
          <Text c="dimmed">
            Текст видят выпускники и действующие ученики в режиме просмотра.
            Поддерживается Markdown.
          </Text>
        </div>
        <Textarea
          label="Описание программы"
          minRows={10}
          autosize
          maxRows={24}
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
        />
        <Title order={3}>Предпросмотр описания Go</Title>
        <GoTransitionProgramDescription description={value} />
        <Button
          w="fit-content"
          disabled={value.trim().length < 20 || !dirty}
          loading={mutation.isPending}
          onClick={() =>
            mutation.mutate(value.trim(), {
              onSuccess: () =>
                notifications.show({
                  color: "green",
                  message: "Описание программы обновлено",
                }),
              onError: (error) =>
                notifications.show({ color: "red", message: error.message }),
            })
          }
        >
          Сохранить описание
        </Button>
      </Stack>
    </Card>
  );
}

export function OpportunitySettings() {
  const query = useQuery({
    queryKey: [...opportunityKeys.all, "settings"],
    queryFn: workspaceApi.settings,
  });
  const mutation = useSetAdminConsultationMentor();
  const [search, setSearch] = useState("");
  const [enabledOnly, setEnabledOnly] = useState(false);
  if (query.isPending) return <LoadingState />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const mentors = query.data.consultation_mentors.filter(
    (item) =>
      (!enabledOnly || item.is_enabled) &&
      `${item.first_name} ${item.last_name ?? ""} ${item.telegram_username ?? ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <Stack gap="xl">
      <GoTransitionProgramSettings
        description={query.data.go_transition_description_markdown}
      />

      <div>
        <Title order={2}>Тарифы консультаций</Title>
        <Text c="dimmed">Суммы применяются только к новым заявкам</Text>
      </div>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {query.data.consultation_types.map((item) => (
          <ConsultationPriceCard key={item.code} item={item} />
        ))}
      </SimpleGrid>
      <Title order={2}>Менторы-консультанты</Title>
      <TextInput
        label="Поиск ментора"
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
      />
      <Switch
        label="Только включённые"
        checked={enabledOnly}
        onChange={(event) => setEnabledOnly(event.currentTarget.checked)}
      />
      {mentors.map((item) => (
        <Card withBorder key={item.id}>
          <Group justify="space-between">
            <Text>
              {item.first_name} {item.last_name}{" "}
              {item.telegram_username ? `@${item.telegram_username}` : ""}
            </Text>
            <Switch
              label="Принимает консультации"
              checked={item.is_enabled}
              disabled={mutation.isPending}
              onChange={(event) =>
                mutation.mutate(
                  { mentorId: item.id, enabled: event.currentTarget.checked },
                  {
                    onSuccess: () =>
                      notifications.show({
                        color: "green",
                        message: "Настройка ментора сохранена",
                      }),
                    onError: (error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  },
                )
              }
            />
          </Group>
        </Card>
      ))}
      {mentors.length === 0 && <Alert color="gray">Менторы не найдены</Alert>}
    </Stack>
  );
}
