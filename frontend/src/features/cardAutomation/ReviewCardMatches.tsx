import {
  Alert,
  Badge,
  Card,
  Group,
  Radio,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import ReactMarkdown from "react-markdown";

import type { QuestionClusterDetail } from "../../types/api";
import { judgeDecisionLabels, percent } from "./presentation";

export function ReviewCardMatches({
  matches,
  selectedId,
  linkedId,
  onSelect,
}: {
  matches: QuestionClusterDetail["top_card_matches"];
  selectedId: string | null;
  linkedId: string | null;
  onSelect: (id: string) => void;
}) {
  const selected = matches.find(
    (candidate) => candidate.card_id === selectedId,
  );
  return (
    <Card withBorder style={{ minWidth: 0 }}>
      <Stack>
        <div>
          <Title order={3}>4. Проверьте возможный дубль</Title>
          <Text size="sm" c="dimmed" mt={4}>
            Сравните вопрос и ответ. Если карточка проверяет те же знания,
            нажмите «Связать с выбранной карточкой».
          </Text>
        </div>
        {matches.length === 0 ? (
          <Alert color="green" title="Похожих карточек не найдено">
            Можно проверять и создавать новую карточку.
          </Alert>
        ) : (
          <>
            <Radio.Group
              label="Похожие карточки"
              value={selectedId ?? ""}
              onChange={onSelect}
            >
              <Stack mt="sm" gap="xs">
                {matches.map((candidate) => (
                  <Radio.Card
                    key={candidate.card_id}
                    value={candidate.card_id}
                    withBorder
                    p="sm"
                    radius="md"
                  >
                    <Group wrap="nowrap" align="flex-start">
                      <Radio.Indicator />
                      <Stack gap={4} style={{ minWidth: 0, flex: 1 }}>
                        <Text fw={600}>{candidate.question_markdown}</Text>
                        <Group gap="xs">
                          <Badge variant="light">
                            {percent(candidate.semantic_score)} похоже
                          </Badge>
                          {candidate.card_id === linkedId && (
                            <Badge color="green">Уже связано системой</Badge>
                          )}
                        </Group>
                      </Stack>
                    </Group>
                  </Radio.Card>
                ))}
              </Stack>
            </Radio.Group>
            {selected ? (
              <Stack
                component="section"
                aria-label="Выбранный возможный дубль"
                gap="sm"
              >
                <Group gap="xs">
                  <Badge variant="outline">{selected.category}</Badge>
                  {selected.judge_decision && (
                    <Badge variant="light" color="blue">
                      AI: {judgeDecisionLabels[selected.judge_decision]}
                    </Badge>
                  )}
                </Group>
                <Text fw={600}>Вопрос существующей карточки</Text>
                <div className="markdown-content card-review-markdown">
                  <ReactMarkdown>{selected.question_markdown}</ReactMarkdown>
                </div>
                <Text fw={600}>Ответ существующей карточки</Text>
                <div className="markdown-content card-review-markdown">
                  <ReactMarkdown>{selected.answer_markdown}</ReactMarkdown>
                </div>
                {selected.judge_reason && (
                  <Text size="sm" c="dimmed">
                    {selected.judge_reason}
                  </Text>
                )}
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Выберите карточку, чтобы сравнить её ответ с предложением AI.
              </Text>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}
