import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Select,
  Stack,
  Tabs,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { api } from "../api/endpoints";
import { CareerPackageContent } from "../components/CareerPackageContent";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMyCareerPackages } from "../features/careerPackages/queries";
import type {
  CareerActiveSearchParameters,
  CareerObjection,
  CareerSelfPresentationCard,
  CareerVersion,
} from "../types/api";
import { openExternalResource } from "../utils/openExternalResource";

const components: { value: CareerObjection["component"]; label: string }[] = [
  { value: "resume", label: "Финальная версия резюме" },
  { value: "self_presentation_card", label: "Карта самопрезентации" },
  { value: "active_search_parameters", label: "Параметры поиска" },
  { value: "completeness", label: "Комплектность пакета" },
  { value: "other", label: "Другое" },
];

function packageContent(version: CareerVersion) {
  const snapshot = version.snapshot as {
    self_presentation_card?: CareerSelfPresentationCard;
    active_search_parameters?: CareerActiveSearchParameters;
  };
  return snapshot.self_presentation_card &&
    snapshot.active_search_parameters ? (
    <CareerPackageContent
      selfPresentation={snapshot.self_presentation_card}
      activeSearch={snapshot.active_search_parameters}
    />
  ) : (
    <Alert color="red">
      Содержимое этой версии повреждено. Обратитесь к администратору.
    </Alert>
  );
}

export function CareerPackagePage() {
  const query = useMyCareerPackages();
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [component, setComponent] =
    useState<CareerObjection["component"]>("other");
  const [reason, setReason] = useState("");
  const [expected, setExpected] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (query.isPending)
    return <LoadingState label="Загружаем Карьерный пакет…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  if (!query.data.length) {
    return (
      <Stack gap="xl">
        <PageHeader
          eyebrow="Карьера"
          title="Карьерный пакет"
          description="Здесь появятся финальное резюме, карта самопрезентации и стратегия поиска."
        />
        <Card withBorder>
          <Title order={3}>Пакет ещё готовится</Title>
          <Text c="dimmed" mt="xs">
            Когда ментор проверит и предоставит пакет, вы получите уведомление.
          </Text>
        </Card>
      </Stack>
    );
  }
  const packageItem =
    query.data.find((item) => item.id === selectedPackage) ?? query.data[0]!;
  const currentVersion =
    packageItem.versions.find((item) => item.id === versionId) ??
    packageItem.current_version;
  const deadlineOpen = Boolean(
    currentVersion.objection_deadline_at &&
    new Date(currentVersion.objection_deadline_at) >= new Date(),
  );

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-start">
        <PageHeader
          eyebrow="Карьера · персональный документ"
          title="Карьерный пакет"
          description="Финальная версия резюме, подготовка к самопрезентации и план активного поиска."
        />
        {query.data.length > 1 && (
          <Select
            label="Направление"
            value={packageItem.id}
            onChange={(next) => {
              setSelectedPackage(next);
              setVersionId(null);
            }}
            data={query.data.map((item) => ({
              value: item.id,
              label: item.direction,
            }))}
          />
        )}
      </Group>

      <Card withBorder>
        <Stack>
          <Group justify="space-between">
            <div>
              <Title order={3}>{packageItem.direction}</Title>
              <Text c="dimmed">
                Версия {currentVersion.version_number} предоставлена{" "}
                {currentVersion.provided_at
                  ? new Date(currentVersion.provided_at).toLocaleString("ru-RU")
                  : "—"}
              </Text>
            </div>
            <Badge color="green">Предоставлен</Badge>
          </Group>
          <Group>
            <Select
              label="Редакция"
              value={currentVersion.id}
              onChange={setVersionId}
              data={packageItem.versions.map((item) => ({
                value: item.id,
                label: `Версия ${item.version_number} · ${new Date(item.published_at).toLocaleDateString("ru-RU")}`,
              }))}
            />
            <Button
              mt={24}
              onClick={() =>
                void openExternalResource(
                  api.careerPackagePdfUrl(currentVersion.id),
                )
              }
            >
              Скачать весь пакет PDF
            </Button>
            <Button
              mt={24}
              variant="light"
              onClick={() =>
                void openExternalResource(
                  api.careerPackageResumeUrl(currentVersion.id),
                )
              }
            >
              Скачать резюме
            </Button>
            <Button
              mt={24}
              variant="subtle"
              onClick={() =>
                void api
                  .acknowledgeCareerVersion(currentVersion.id)
                  .then(() =>
                    notifications.show({
                      color: "green",
                      message: "Ознакомление зафиксировано",
                    }),
                  )
                  .catch((error: Error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                  )
              }
            >
              Подтвердить ознакомление
            </Button>
          </Group>
          <Text size="xs" c="dimmed">
            Идентификатор содержания: {currentVersion.snapshot_sha256}
          </Text>
        </Stack>
      </Card>

      {packageContent(currentVersion)}

      {packageItem.reviews.length > 0 && (
        <Card withBorder>
          <Stack>
            <Title order={3}>Итоги созвонов по самопрезентации</Title>
            {packageItem.reviews.map((review) => (
              <Card key={review.id} withBorder padding="sm">
                <Text fw={700}>
                  {new Date(review.held_at).toLocaleDateString("ru-RU")}
                </Text>
                <Text mt="sm">
                  <b>Что получилось:</b> {review.strengths}
                </Text>
                <Text>
                  <b>Что улучшить:</b> {review.improvements}
                </Text>
                <Text>
                  <b>К следующей попытке:</b>{" "}
                  {review.preparation_for_next_attempt}
                </Text>
                {review.additional_notes && (
                  <Text>{review.additional_notes}</Text>
                )}
              </Card>
            ))}
          </Stack>
        </Card>
      )}

      <Tabs defaultValue="objection">
        <Tabs.List>
          <Tabs.Tab value="objection">Направить возражение</Tabs.Tab>
          <Tabs.Tab value="history">
            История ({packageItem.objections.length})
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="objection" pt="lg">
          <Card withBorder>
            <Stack>
              <Title order={3}>Мотивированное возражение</Title>
              <Text c="dimmed">
                Срок:{" "}
                {currentVersion.objection_deadline_at
                  ? new Date(
                      currentVersion.objection_deadline_at,
                    ).toLocaleString("ru-RU")
                  : "не указан"}
                . Позднее обращение будет сохранено с соответствующей отметкой.
              </Text>
              {!currentVersion.objection_deadline_at ? (
                <Alert color="blue">
                  Юридический срок возражений ещё не начался. Вы уже можете
                  отправить обращение — оно будет зарегистрировано как поданное
                  до начала срока.
                </Alert>
              ) : !deadlineOpen ? (
                <Alert color="yellow">
                  Срок возражений истёк, но обращение всё равно можно отправить
                  на рассмотрение.
                </Alert>
              ) : null}
              <Select
                label="К какой части относится"
                data={components}
                value={component}
                onChange={(next) =>
                  next && setComponent(next as CareerObjection["component"])
                }
              />
              <Textarea
                label="Что именно неверно или требует исправления"
                minRows={4}
                value={reason}
                onChange={(event) => setReason(event.currentTarget.value)}
                required
              />
              <Textarea
                label="Какого результата вы ожидаете"
                minRows={3}
                value={expected}
                onChange={(event) => setExpected(event.currentTarget.value)}
                required
              />
              <Button
                disabled={
                  reason.trim().length < 10 || expected.trim().length < 3
                }
                loading={submitting}
                onClick={() => {
                  setSubmitting(true);
                  void api
                    .createCareerObjection({
                      package_version_id: currentVersion.id,
                      component,
                      reason: reason.trim(),
                      expected_result: expected.trim(),
                    })
                    .then(() => {
                      setReason("");
                      setExpected("");
                      notifications.show({
                        color: "green",
                        message: "Возражение зарегистрировано",
                      });
                      return query.refetch();
                    })
                    .catch((error: Error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                    )
                    .finally(() => setSubmitting(false));
                }}
              >
                Отправить возражение
              </Button>
            </Stack>
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="history" pt="lg">
          <Stack>
            {packageItem.objections.length ? (
              packageItem.objections.map((item) => (
                <Alert
                  key={item.id}
                  color={item.status === "submitted" ? "yellow" : "gray"}
                  title={`${components.find((entry) => entry.value === item.component)?.label ?? item.component} · ${item.status}`}
                >
                  <Text>{item.reason}</Text>
                  {item.resolution_comment && (
                    <Text mt="xs">
                      <b>Ответ:</b> {item.resolution_comment}
                    </Text>
                  )}
                </Alert>
              ))
            ) : (
              <Text c="dimmed">Возражений нет.</Text>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>

      {packageItem.obligation && packageItem.obligation.due_at && (
        <Alert
          color={packageItem.obligation.status === "active" ? "blue" : "gray"}
          title="Фиксированный компонент стоимости"
        >
          <Text>
            30 000 ₽ · срок оплаты{" "}
            {new Date(packageItem.obligation.due_at).toLocaleDateString(
              "ru-RU",
            )}{" "}
            · статус {packageItem.obligation.status}
          </Text>
        </Alert>
      )}
    </Stack>
  );
}
