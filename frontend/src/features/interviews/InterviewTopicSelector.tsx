import {
  Alert,
  Button,
  Card,
  Checkbox,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";

import type { InterviewTopicOption } from "../../types/api";
import { useUpdateInterviewTopics } from "./queries";

interface Props {
  deckSlug: string;
  topics: InterviewTopicOption[];
}

export function InterviewTopicSelector({ deckSlug, topics }: Props) {
  const serverSelection = useMemo(
    () =>
      topics.filter((topic) => topic.is_selected).map((topic) => topic.name),
    [topics],
  );
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(serverSelection),
  );
  const mutation = useUpdateInterviewTopics();

  useEffect(() => {
    setSelected(new Set(serverSelection));
  }, [serverSelection]);

  const dirty =
    selected.size !== serverSelection.length ||
    serverSelection.some((category) => !selected.has(category));

  const toggle = (category: string, checked: boolean) => {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(category);
      else next.delete(category);
      return next;
    });
  };

  const save = () => {
    mutation.mutate(
      { deckSlug, categories: [...selected] },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message:
              selected.size > 0
                ? "Темы сохранены — сессия обновлена"
                : "Выбор тем очищен",
          });
        },
      },
    );
  };

  return (
    <Card withBorder className="interview-topic-selector">
      <Stack>
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>Выберите темы</Title>
            <Text c="dimmed" size="sm">
              Карточки будут приходить только из тех разделов, которые вы уже
              проходили.
            </Text>
          </div>
          <Text className="technical-label">
            Выбрано {selected.size} из {topics.length}
          </Text>
        </Group>

        {mutation.isError && (
          <Alert color="red">{mutation.error.message}</Alert>
        )}

        <Group>
          <Button
            type="button"
            variant="subtle"
            size="xs"
            onClick={() =>
              setSelected(new Set(topics.map((topic) => topic.name)))
            }
          >
            Выбрать все
          </Button>
          <Button
            type="button"
            variant="subtle"
            color="gray"
            size="xs"
            onClick={() => setSelected(new Set())}
          >
            Сбросить
          </Button>
        </Group>

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
          {topics.map((topic) => (
            <Checkbox
              key={topic.name}
              checked={selected.has(topic.name)}
              onChange={(event) =>
                toggle(topic.name, event.currentTarget.checked)
              }
              label={topic.name}
              description={`${topic.total_cards} вопросов · ${topic.frequent_cards} частых`}
              className="interview-topic-checkbox"
            />
          ))}
        </SimpleGrid>

        <Group justify="flex-end">
          <Button
            type="button"
            onClick={save}
            loading={mutation.isPending}
            disabled={!dirty}
          >
            Сохранить выбор
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
