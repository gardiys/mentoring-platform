import { Card, Divider, SimpleGrid, Stack, Text, Title } from "@mantine/core";

import type {
  CareerActiveSearchParameters,
  CareerSelfPresentationCard,
} from "../types/api";

const cardLabels: Record<keyof CareerSelfPresentationCard, string> = {
  target_position: "Целевая позиция",
  target_seniority: "Уровень",
  short_positioning: "Краткое позиционирование",
  self_presentation_structure: "Структура рассказа",
  key_experience_points: "Ключевой опыт",
  key_projects: "Проекты",
  achievements_to_highlight: "Достижения",
  technologies_to_highlight: "Технологии",
  personal_contribution_points: "Личный вклад",
  difficult_or_risky_topics: "Рискованные темы",
  questions_to_prepare: "Вопросы для подготовки",
  inconsistencies_or_missing_facts: "Что нужно уточнить",
  preparation_checklist: "Чек-лист подготовки",
  additional_notes: "Дополнительные рекомендации",
};

const searchLabels: Record<keyof CareerActiveSearchParameters, string> = {
  target_positions: "Целевые позиции",
  target_seniority: "Уровень",
  primary_technology_stack: "Основной стек",
  secondary_technology_stack: "Дополнительный стек",
  employment_formats: "Форматы занятости",
  work_schedule_preferences: "Пожелания по графику",
  geography: "География",
  remote_preferences: "Удалённая работа",
  relocation_preferences: "Релокация",
  salary_min: "Минимальная зарплата",
  salary_target: "Целевая зарплата",
  salary_currency: "Валюта",
  search_channels: "Каналы поиска",
  applications_per_workday: "Откликов в рабочий день",
  applications_per_week: "Откликов в неделю",
  resume_refresh_schedule: "Обновление резюме",
  inbound_processing_rules: "Обработка входящих",
  interview_logging_rules: "Фиксация собеседований",
  interview_preparation_priorities: "Приоритеты подготовки",
  funnel_control_points: "Контрольные точки воронки",
  resume_revision_threshold: "Когда менять резюме",
  strategy_revision_threshold: "Когда менять стратегию",
  start_date: "Начало активного поиска",
  additional_notes: "Дополнительные рекомендации",
};

function display(value: unknown) {
  if (Array.isArray(value)) {
    return value.length
      ? value.map((item) => `• ${String(item)}`).join("\n")
      : "—";
  }
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function ContentGrid({
  data,
  labels,
}: {
  data: Record<string, unknown>;
  labels: Record<string, string>;
}) {
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
      {Object.entries(labels).map(([key, label]) => (
        <div key={key}>
          <Text className="technical-label">{label}</Text>
          <Text style={{ whiteSpace: "pre-line" }}>{display(data[key])}</Text>
        </div>
      ))}
    </SimpleGrid>
  );
}

export function CareerPackageContent({
  selfPresentation,
  activeSearch,
}: {
  selfPresentation: CareerSelfPresentationCard;
  activeSearch: CareerActiveSearchParameters;
}) {
  return (
    <Stack gap="xl">
      <Card withBorder>
        <Stack>
          <Title order={3}>Карта подготовки к самопрезентации</Title>
          <Divider />
          <ContentGrid
            data={selfPresentation as unknown as Record<string, unknown>}
            labels={cardLabels}
          />
        </Stack>
      </Card>
      <Card withBorder>
        <Stack>
          <Title order={3}>Параметры активного поиска</Title>
          <Divider />
          <ContentGrid
            data={activeSearch as unknown as Record<string, unknown>}
            labels={searchLabels}
          />
        </Stack>
      </Card>
    </Stack>
  );
}
