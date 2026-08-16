import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import {
  useAdminInterviewCard,
  useSaveAdminInterviewCard,
} from "../features/admin/interviewQueries";
import type {
  AdminInterviewCardMutation,
  AdminInterviewCardRead,
} from "../types/api";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function CardForm({
  deckId,
  card,
}: {
  deckId: string;
  card?: AdminInterviewCardRead;
}) {
  const navigate = useNavigate();
  const mutation = useSaveAdminInterviewCard();
  const [form, setForm] = useState<AdminInterviewCardMutation>({
    id: card?.id,
    slug: card?.slug ?? "",
    category: card?.category ?? "Общее",
    subcategory: card?.subcategory ?? null,
    companies: card?.companies ?? null,
    question_markdown: card?.question_markdown ?? "## Вопрос",
    answer_markdown:
      card?.answer_markdown ?? "Краткий, но содержательный ответ.",
    frequency: card?.frequency_override ?? card?.frequency ?? "frequent",
    frequency_mode: card?.frequency_mode ?? "manual",
    position: card?.position ?? 0,
    is_published: card?.is_published ?? false,
  });
  const initial = useRef(form);
  const allowNavigation = useUnsavedChanges(
    JSON.stringify(form) !== JSON.stringify(initial.current),
  );
  const valid =
    SLUG_PATTERN.test(form.slug) &&
    (form.category ?? "").trim().length > 0 &&
    form.question_markdown.trim().length > 0 &&
    form.answer_markdown.trim().length > 0;
  const back = `/admin/interviews/${deckId}/edit`;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || mutation.isPending) return;
    mutation.mutate(
      { deckId, cardId: card?.id, payload: form },
      {
        onSuccess: () => {
          allowNavigation();
          notifications.show({
            color: "green",
            message: card ? "Карточка сохранена" : "Карточка создана",
          });
          navigate(back);
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow="Собеседования · одна карточка"
          title={card ? "Редактирование вопроса" : "Новый вопрос"}
          description="На странице загружена только эта карточка. Остальная колода не перерисовывается."
        />
        {card && (
          <Group>
            <Badge variant="light">Спросили раз: {card.asked_count}</Badge>
            {card.companies && (
              <Text size="sm" c="dimmed">
                Компании: {card.companies}
              </Text>
            )}
          </Group>
        )}
        <Card withBorder>
          <Stack>
            {mutation.error && (
              <Alert color="red">{mutation.error.message}</Alert>
            )}
            <Group grow align="flex-start">
              <TextInput
                label="Slug"
                required
                value={form.slug}
                error={
                  form.slug && !SLUG_PATTERN.test(form.slug)
                    ? "Некорректный slug"
                    : null
                }
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    slug: event.currentTarget.value,
                  }))
                }
              />
              <TextInput
                label="Тема"
                required
                value={form.category ?? ""}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    category: event.currentTarget.value,
                  }))
                }
              />
            </Group>
            <TextInput
              label="Подтема"
              description="Необязательно. Не влияет на группировку карточек по широкой теме."
              value={form.subcategory ?? ""}
              onChange={(event) => {
                const subcategory = event.currentTarget.value || null;
                setForm((current) => ({
                  ...current,
                  subcategory,
                }));
              }}
            />
            <Textarea
              label="Вопрос (Markdown)"
              required
              minRows={5}
              autosize
              value={form.question_markdown}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  question_markdown: event.currentTarget.value,
                }))
              }
            />
            <Textarea
              label="Ответ (Markdown)"
              required
              minRows={12}
              autosize
              value={form.answer_markdown}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  answer_markdown: event.currentTarget.value,
                }))
              }
            />
            <TextInput
              label="Компании"
              value={form.companies ?? ""}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  companies: event.currentTarget.value || null,
                }))
              }
            />
            <Stack gap="xs">
              <Text fw={500} size="sm">
                Как определяется частотность
              </Text>
              <SegmentedControl
                aria-label="Как определяется частотность"
                fullWidth
                value={form.frequency_mode}
                data={[
                  { value: "automatic", label: "Автоматически" },
                  { value: "manual", label: "Вручную" },
                ]}
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    frequency_mode:
                      value === "automatic" ? "automatic" : "manual",
                  }))
                }
              />
              <Text size="sm" c="dimmed">
                {form.frequency_mode === "automatic"
                  ? card
                    ? `Карточка станет частой после ${card.frequency_threshold} разных собеседований. Сейчас: ${card.asked_count}.`
                    : "Счётчик начнёт работать после появления карточки в разборах собеседований."
                  : "Вы сами задаёте приоритет карточки и он не меняется от счётчика."}
              </Text>
            </Stack>
            <Group grow align="flex-start">
              <Select
                label="Частота"
                description={
                  form.frequency_mode === "automatic"
                    ? "Рассчитывается по числу разных собеседований"
                    : "Ручной приоритет показа карточки"
                }
                data={[
                  { value: "frequent", label: "Частый" },
                  { value: "occasional", label: "Обычный" },
                ]}
                value={form.frequency}
                disabled={form.frequency_mode === "automatic"}
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    frequency:
                      value === "occasional" ? "occasional" : "frequent",
                  }))
                }
              />
              <NumberInput
                label="Позиция"
                min={0}
                value={form.position}
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    position: typeof value === "number" ? value : 0,
                  }))
                }
              />
              <Switch
                label="Опубликована"
                checked={form.is_published}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    is_published: event.currentTarget.checked,
                  }))
                }
              />
            </Group>
            <Group justify="flex-end">
              <Button variant="subtle" onClick={() => navigate(back)}>
                Отмена
              </Button>
              <Button
                type="submit"
                loading={mutation.isPending}
                disabled={!valid}
              >
                Сохранить
              </Button>
            </Group>
          </Stack>
        </Card>
      </Stack>
    </form>
  );
}

export function AdminInterviewCardEditPage() {
  const { deckId = "", cardId } = useParams();
  const query = useAdminInterviewCard(deckId, cardId);
  if (cardId && query.isPending)
    return <LoadingState label="Загружаем карточку…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return <CardForm key={cardId ?? "new"} deckId={deckId} card={query.data} />;
}
