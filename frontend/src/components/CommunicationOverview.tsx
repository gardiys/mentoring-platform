import {
  Badge,
  Button,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import type {
  CommunicationSkill,
  IntelligenceCommunicationDimension,
} from "../types/api";

function assessment(score: number | null | undefined) {
  if (score == null) return { color: "gray", label: "Недостаточно данных" };
  if (score >= 0.8) return { color: "green", label: "Сильная сторона" };
  if (score >= 0.6) return { color: "yellow", label: "Можно усилить" };
  return { color: "orange", label: "Нужна проработка" };
}

export function CommunicationOverview({
  dimensions,
  labels,
  onExample,
}: {
  dimensions: IntelligenceCommunicationDimension[];
  labels: Partial<Record<CommunicationSkill, string>>;
  onExample: (skill: CommunicationSkill) => void;
}) {
  // Independent of the mixed top-six list: technical gaps must not crowd out
  // communication priorities in the dedicated Soft Skills report.
  const priorities = dimensions
    .filter(
      (item) =>
        item.skill &&
        (item.example_score ?? item.score) != null &&
        (item.example_score ?? item.score)! < 0.6 &&
        item.exercise,
    )
    .sort(
      (a, b) => (a.example_score ?? a.score)! - (b.example_score ?? b.score)!,
    )
    .slice(0, 3);
  const hasScores = dimensions.some((item) => item.score != null);
  return (
    <>
      <section aria-labelledby="communication-priorities-title">
        <Title order={3} id="communication-priorities-title" mb="sm">
          Приоритетные улучшения Soft Skills
        </Title>
        {priorities.length ? (
          <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="sm">
            {priorities.map((item, index) => (
              <Stack
                key={item.skill}
                className="analysis-priority-action"
                gap="sm"
              >
                <Group align="flex-start" wrap="nowrap">
                  <span className="analysis-priority-number">{index + 1}</span>
                  <Text fw={800}>{item.name}</Text>
                </Group>
                <Text size="sm">{item.summary}</Text>
                <Text size="sm">
                  <b>Что сделать:</b> {item.exercise!.task}
                </Text>
                <Text size="sm" c="dimmed">
                  <b>Готово, когда:</b> {item.exercise!.success_criterion}
                </Text>
                <Button
                  variant="light"
                  size="xs"
                  aria-label={`Разобрать пример: ${item.name}`}
                  onClick={() => onExample(item.skill!)}
                >
                  Разобрать пример
                </Button>
              </Stack>
            ))}
          </SimpleGrid>
        ) : (
          <Text size="sm" c="dimmed">
            {hasScores
              ? "В оценённых категориях нет выраженных пробелов с упражнениями. Закрепляй сильные стороны и смотри примеры ниже."
              : "Для приоритетных рекомендаций пока недостаточно подтверждённых данных."}
          </Text>
        )}
      </section>

      <section aria-labelledby="communication-categories-title">
        <Title order={3} id="communication-categories-title" mb="sm">
          Оценка по категориям Soft Skills
        </Title>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
          {(Object.entries(labels) as [CommunicationSkill, string][]).map(
            ([skill, label]) => {
              const item = dimensions.find(
                (dimension) => dimension.skill === skill,
              );
              const presentation = assessment(item?.score);
              return (
                <Stack
                  key={skill}
                  className="analysis-communication-dimension"
                  gap="xs"
                >
                  <Group justify="space-between" align="flex-start">
                    <Title order={4}>{label}</Title>
                    {item?.score != null && (
                      <Badge color={presentation.color} variant="light">
                        {Math.round(item.score * 100)}%
                      </Badge>
                    )}
                  </Group>
                  <Text
                    size="sm"
                    c={item?.score != null ? presentation.color : "dimmed"}
                  >
                    {presentation.label}
                  </Text>
                  {item && (
                    <Text size="xs" c="dimmed">
                      Подтверждённых ответов: {item.observation_count ?? 1}.
                      Оценено:{" "}
                      {item.scored_observation_count ??
                        (item.score != null ? 1 : 0)}
                      .
                    </Text>
                  )}
                  <Text size="sm">
                    {item && <b>Отдельный пример: </b>}
                    {item?.summary ??
                      "В записи нет подтверждённого примера для оценки этой категории."}
                  </Text>
                  {item && (
                    <Button
                      variant="subtle"
                      size="xs"
                      aria-label={`К примеру: ${label}`}
                      onClick={() => onExample(skill)}
                    >
                      К примеру
                    </Button>
                  )}
                </Stack>
              );
            },
          )}
        </SimpleGrid>
      </section>
    </>
  );
}
