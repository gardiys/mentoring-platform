import {
  Badge,
  Button,
  Card,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useKnowledgeSearch,
  useKnowledgeTopics,
} from "../features/knowledge/queries";

const kindLabels = { article: "Статья", question: "Вопрос" } as const;

export function KnowledgeBasePage() {
  const [params, setParams] = useSearchParams();
  const queryText = params.get("q")?.trim() ?? "";
  const [input, setInput] = useState(queryText);
  const topics = useKnowledgeTopics();
  const search = useKnowledgeSearch(queryText);

  useEffect(() => setInput(queryText), [queryText]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = input.trim();
    setParams(normalized.length >= 2 ? { q: normalized } : {});
  };

  if (topics.isPending) return <LoadingState label="Загружаем базу знаний…" />;
  if (topics.isError)
    return (
      <ErrorState error={topics.error} retry={() => void topics.refetch()} />
    );

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Knowledge base · менторская программа"
        title="База знаний"
        description="Статьи, разборы и вопросы, которые мы освещаем в рамках менторства."
      />

      <Paper
        withBorder
        p={{ base: "md", sm: "xl" }}
        className="knowledge-search-panel"
      >
        <form onSubmit={submit}>
          <Group align="flex-end">
            <TextInput
              label="Поиск по содержанию"
              description="Ищем по заголовкам, описаниям и полному тексту материалов"
              placeholder="Например: GIN-индекс или event loop"
              value={input}
              onChange={(event) => setInput(event.currentTarget.value)}
              style={{ flex: 1 }}
            />
            <Button type="submit" disabled={input.trim().length < 2}>
              Найти
            </Button>
            {queryText && (
              <Button
                type="button"
                variant="subtle"
                onClick={() => {
                  setInput("");
                  setParams({});
                }}
              >
                Сбросить
              </Button>
            )}
          </Group>
        </form>
      </Paper>

      {queryText ? (
        <Stack>
          <Group justify="space-between">
            <Title order={2}>Результаты поиска</Title>
            <Text className="technical-label">Запрос / {queryText}</Text>
          </Group>
          {search.isPending && <LoadingState label="Ищем по материалам…" />}
          {search.isError && (
            <ErrorState
              error={search.error}
              retry={() => void search.refetch()}
            />
          )}
          {search.data?.length === 0 && (
            <Text c="dimmed">По этому запросу ничего не найдено.</Text>
          )}
          {search.data?.map((result) => (
            <Card
              key={result.id}
              withBorder
              component={Link}
              to={`/knowledge/entries/${result.slug}`}
              className="knowledge-result-card"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <Stack gap="xs">
                <Group justify="space-between">
                  <Badge
                    color={
                      result.kind === "question" ? "brandYellow" : "brandBlue"
                    }
                  >
                    {kindLabels[result.kind]}
                  </Badge>
                  <Text className="technical-label">{result.topic.title}</Text>
                </Group>
                <Title order={3}>{result.title}</Title>
                {result.summary && <Text fw={500}>{result.summary}</Text>}
                <Text c="dimmed" lineClamp={3}>
                  {result.excerpt}
                </Text>
              </Stack>
            </Card>
          ))}
        </Stack>
      ) : (
        <Stack>
          <Title order={2}>Темы</Title>
          {topics.data.length === 0 ? (
            <Text c="dimmed">Опубликованных тем пока нет.</Text>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              {topics.data.map((topic) => (
                <Card
                  key={topic.id}
                  withBorder
                  component={Link}
                  to={`/knowledge/topics/${topic.slug}`}
                  className="roadmap-card knowledge-topic-card"
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <Stack h="100%">
                    <Text className="roadmap-slug">TOPIC / {topic.slug}</Text>
                    <Title order={2}>{topic.title}</Title>
                    {topic.description && (
                      <Text c="dimmed">{topic.description}</Text>
                    )}
                    <Group mt="auto">
                      <Badge variant="light">
                        {topic.article_count} статей
                      </Badge>
                      <Badge color="brandYellow" c="brandNavy.9">
                        {topic.question_count} вопросов
                      </Badge>
                    </Group>
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      )}
    </Stack>
  );
}
