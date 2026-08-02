import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminQuestionModerationDetail,
  useIntelligenceQuestionModeration,
} from "../features/interviews/intelligenceQueries";
import type { AdminQuestionModerationDetail } from "../types/api";

function ModerationForm({ item }: { item: AdminQuestionModerationDetail }) {
  const navigate = useNavigate();
  const moderation = useIntelligenceQuestionModeration();
  const [question, setQuestion] = useState(item.question_text);
  const [answer, setAnswer] = useState(
    item.suggested_answer || item.candidate_answer || "",
  );
  const [category, setCategory] = useState(item.category);
  const [frequency, setFrequency] = useState<"frequent" | "occasional">(
    "occasional",
  );

  const submit = (action: "approve" | "reject") =>
    moderation.mutate(
      {
        interviewId: item.interview_id,
        questionId: item.question_id,
        payload:
          action === "approve"
            ? {
                action,
                question_markdown: question.trim(),
                answer_markdown: answer.trim(),
                category: category.trim(),
                frequency,
              }
            : { action },
      },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message:
              action === "approve"
                ? "Вопрос учтён в базе карточек"
                : "Вопрос отклонён",
          });
          navigate("/admin/interview-question-moderation");
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-start">
        <PageHeader
          eyebrow={`${item.track_title} · ${item.company_name}`}
          title="Проверка вопроса"
          description={`${item.student_name} · ${new Date(item.interviewed_at).toLocaleString("ru-RU")}`}
        />
        <Button
          component={Link}
          to="/admin/interview-question-moderation"
          variant="light"
        >
          К списку
        </Button>
      </Group>
      {item.matched_card_id && (
        <Alert color="blue" title="Найдена существующая карточка">
          <Stack gap="xs">
            <Text>{item.matched_card_question}</Text>
            <Text size="sm">
              Уже зафиксировано появлений: {item.matched_card_asked_count}. После
              подтверждения новая карточка не создастся — добавится компания и
              увеличится счётчик.
            </Text>
          </Stack>
        </Alert>
      )}
      <Card withBorder>
        <Stack>
          <Group>
            <Badge>{item.question_kind}</Badge>
            <Badge variant="outline">{item.difficulty}</Badge>
          </Group>
          <Textarea
            label="Вопрос"
            value={question}
            onChange={(event) => setQuestion(event.currentTarget.value)}
            minRows={3}
            required
          />
          <Textarea
            label="Проверенный ответ для обратной стороны карточки"
            value={answer}
            onChange={(event) => setAnswer(event.currentTarget.value)}
            minRows={7}
            required
          />
          {item.candidate_answer && (
            <Alert color="gray" title="Ответ кандидата">
              <Text style={{ whiteSpace: "pre-wrap" }}>
                {item.candidate_answer}
              </Text>
            </Alert>
          )}
          <Group grow align="flex-end">
            <TextInput
              label="Тема"
              value={category}
              onChange={(event) => setCategory(event.currentTarget.value)}
              required
            />
            <Select
              label="Частота"
              value={frequency}
              data={[
                { value: "frequent", label: "Частый вопрос" },
                { value: "occasional", label: "Нечастый вопрос" },
              ]}
              onChange={(value) =>
                setFrequency(value === "frequent" ? "frequent" : "occasional")
              }
            />
          </Group>
          <Group>
            <Button
              loading={moderation.isPending}
              disabled={!question.trim() || !answer.trim() || !category.trim()}
              onClick={() => submit("approve")}
            >
              {item.matched_card_id
                ? "Учесть ещё одно появление"
                : "Создать карточку"}
            </Button>
            <Button
              color="gray"
              variant="light"
              loading={moderation.isPending}
              onClick={() => submit("reject")}
            >
              Отклонить
            </Button>
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}

export function AdminInterviewQuestionModerationEditPage() {
  const { questionId = "" } = useParams();
  const query = useAdminQuestionModerationDetail(questionId);
  if (query.isPending) return <LoadingState label="Загружаем вопрос…" />;
  if (query.isError)
    return <ErrorState retry={() => void query.refetch()} />;
  return <ModerationForm key={query.data.question_id} item={query.data} />;
}
