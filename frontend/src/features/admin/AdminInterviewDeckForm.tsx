import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  NumberInput,
  Select,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../components/PageHeader";
import type {
  AdminInterviewCardMutation,
  AdminInterviewDeckMutation,
  AdminInterviewDeckRead,
  InterviewCardFrequency,
} from "../../types/api";
import { useAdminTracks } from "./queries";
import {
  useCreateAdminInterviewDeck,
  useUpdateAdminInterviewDeck,
} from "./interviewQueries";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const emptyDeck: AdminInterviewDeckMutation = {
  track_id: "",
  slug: "",
  title: "",
  description: null,
  position: 0,
  is_published: false,
  cards: [],
};

function emptyCard(position: number): AdminInterviewCardMutation {
  return {
    slug: "",
    category: "Общее",
    question_markdown: "## Вопрос",
    answer_markdown: "Краткий, но содержательный ответ.",
    frequency: "frequent",
    position,
    is_published: false,
  };
}

function toMutation(deck: AdminInterviewDeckRead): AdminInterviewDeckMutation {
  return {
    track_id: deck.track_id,
    slug: deck.slug,
    title: deck.title,
    description: deck.description,
    position: deck.position,
    is_published: deck.is_published,
    cards: deck.cards.map((card) => ({
      id: card.id,
      slug: card.slug,
      category: card.category,
      companies: card.companies,
      question_markdown: card.question_markdown,
      answer_markdown: card.answer_markdown,
      frequency: card.frequency,
      position: card.position,
      is_published: card.is_published,
    })),
  };
}

interface Props {
  deck?: AdminInterviewDeckRead;
}

export function AdminInterviewDeckForm({ deck }: Props) {
  const [form, setForm] = useState<AdminInterviewDeckMutation>(
    deck ? toMutation(deck) : emptyDeck,
  );
  const tracks = useAdminTracks();
  const createMutation = useCreateAdminInterviewDeck();
  const updateMutation = useUpdateAdminInterviewDeck();
  const navigate = useNavigate();
  const editing = deck !== undefined;
  const cards = form.cards ?? [];
  const pending = createMutation.isPending || updateMutation.isPending;
  const error = createMutation.error ?? updateMutation.error;
  const valid =
    form.track_id.length > 0 &&
    form.title.trim().length > 0 &&
    SLUG_PATTERN.test(form.slug) &&
    cards.every(
      (card) =>
        SLUG_PATTERN.test(card.slug) &&
        (card.category ?? "").trim().length > 0 &&
        card.question_markdown.trim().length > 0 &&
        card.answer_markdown.trim().length > 0,
    );

  const updateCard = (
    index: number,
    patch: Partial<AdminInterviewCardMutation>,
  ) => {
    setForm((current) => ({
      ...current,
      cards: (current.cards ?? []).map((card, cardIndex) =>
        cardIndex === index ? { ...card, ...patch } : card,
      ),
    }));
  };

  const addCard = () => {
    setForm((current) => ({
      ...current,
      cards: [...(current.cards ?? []), emptyCard(current.cards?.length ?? 0)],
    }));
  };

  const removeCard = (index: number) => {
    setForm((current) => ({
      ...current,
      cards: (current.cards ?? [])
        .filter((_, cardIndex) => cardIndex !== index)
        .map((card, position) => ({ ...card, position })),
    }));
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || pending) return;
    const handlers = {
      onSuccess: () => {
        notifications.show({
          color: "green",
          message: editing ? "Колода обновлена" : "Колода создана",
        });
        navigate("/admin/interviews");
      },
      onError: (mutationError: Error) => {
        notifications.show({ color: "red", message: mutationError.message });
      },
    };
    if (deck) {
      updateMutation.mutate({ id: deck.id, payload: form }, handlers);
    } else {
      createMutation.mutate(form, handlers);
    }
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow="Собеседования · редактор"
          title={editing ? deck.title : "Новая колода карточек"}
          description="Колода — самостоятельный набор вопросов одного учебного направления."
        />
        {error && (
          <Alert color="red" title="Не удалось сохранить">
            {error.message}
          </Alert>
        )}

        <Card withBorder>
          <Stack>
            <Title order={2}>Настройки колоды</Title>
            <Select
              label="Учебный трек"
              description="Колоду увидят только ученики с доступом к этому треку"
              required
              searchable
              disabled={tracks.isPending}
              data={(tracks.data ?? []).map((track) => ({
                value: track.id,
                label: `${track.title} / ${track.slug}`,
              }))}
              value={form.track_id || null}
              onChange={(value) =>
                setForm((current) => ({ ...current, track_id: value ?? "" }))
              }
            />
            <TextInput
              label="Название"
              required
              value={form.title}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({ ...current, title: value }));
              }}
            />
            <TextInput
              label="Slug"
              description="Латинские строчные буквы, цифры и дефисы"
              required
              value={form.slug}
              error={
                form.slug && !SLUG_PATTERN.test(form.slug)
                  ? "Некорректный slug"
                  : null
              }
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({ ...current, slug: value }));
              }}
            />
            <Textarea
              label="Описание"
              value={form.description ?? ""}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setForm((current) => ({
                  ...current,
                  description: value || null,
                }));
              }}
            />
            <Group grow>
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
                label="Колода опубликована"
                checked={form.is_published}
                onChange={(event) => {
                  const checked = event.currentTarget.checked;
                  setForm((current) => ({
                    ...current,
                    is_published: checked,
                  }));
                }}
              />
            </Group>
          </Stack>
        </Card>

        <Group justify="space-between">
          <div>
            <Title order={2}>Карточки</Title>
            <Text c="dimmed" size="sm">
              Частые вопросы всегда выдаются ученику раньше редких.
            </Text>
          </div>
          <Button type="button" onClick={addCard}>
            + Добавить карточку
          </Button>
        </Group>

        {cards.length === 0 && (
          <Card withBorder>
            <Text c="dimmed">Добавьте первый вопрос и ответ.</Text>
          </Card>
        )}
        {cards.map((card, index) => (
          <Card
            key={card.id ?? `new-${index}`}
            withBorder
            className="builder-topic-card"
          >
            <Stack>
              <Group justify="space-between">
                <Group>
                  <Badge
                    color={
                      card.frequency === "frequent"
                        ? "brandYellow"
                        : "brandSand"
                    }
                    c="brandNavy.9"
                  >
                    {card.frequency === "frequent" ? "Частый" : "Редкий"}
                  </Badge>
                  <Text className="technical-label">Карточка {index + 1}</Text>
                  {card.id &&
                    deck?.cards.find((source) => source.id === card.id)
                      ?.source_number && (
                      <Text className="technical-label">
                        CSV №
                        {
                          deck.cards.find((source) => source.id === card.id)
                            ?.source_number
                        }
                      </Text>
                    )}
                </Group>
                <Button
                  type="button"
                  variant="subtle"
                  color="red"
                  onClick={() => removeCard(index)}
                >
                  Удалить
                </Button>
              </Group>
              <Divider />
              <TextInput
                label="Slug карточки"
                required
                value={card.slug}
                error={
                  card.slug && !SLUG_PATTERN.test(card.slug)
                    ? "Некорректный slug"
                    : null
                }
                onChange={(event) =>
                  updateCard(index, { slug: event.currentTarget.value })
                }
              />
              <TextInput
                label="Тема вопроса"
                placeholder="Например: Конкурентность в Python"
                value={card.category ?? ""}
                onChange={(event) =>
                  updateCard(index, {
                    category: event.currentTarget.value || undefined,
                  })
                }
              />
              <TextInput
                label="Компании"
                description="Где встречался вопрос; можно перечислить через запятую"
                value={card.companies ?? ""}
                onChange={(event) =>
                  updateCard(index, {
                    companies: event.currentTarget.value || null,
                  })
                }
              />
              <Textarea
                label="Лицевая сторона · вопрос"
                description="Поддерживается Markdown"
                required
                minRows={4}
                autosize
                value={card.question_markdown}
                onChange={(event) =>
                  updateCard(index, {
                    question_markdown: event.currentTarget.value,
                  })
                }
              />
              <Textarea
                label="Обратная сторона · ответ"
                description="Короткий ответ, пояснение и примеры в Markdown"
                required
                minRows={8}
                autosize
                value={card.answer_markdown}
                onChange={(event) =>
                  updateCard(index, {
                    answer_markdown: event.currentTarget.value,
                  })
                }
              />
              <Group grow align="flex-end">
                <Select
                  label="Частота на собеседованиях"
                  data={[
                    { value: "frequent", label: "Часто задают" },
                    { value: "occasional", label: "Задают реже" },
                  ]}
                  value={card.frequency}
                  allowDeselect={false}
                  onChange={(value) =>
                    updateCard(index, {
                      frequency: (value ??
                        "occasional") as InterviewCardFrequency,
                    })
                  }
                />
                <NumberInput
                  label="Позиция"
                  min={0}
                  value={card.position}
                  onChange={(value) =>
                    updateCard(index, {
                      position: typeof value === "number" ? value : 0,
                    })
                  }
                />
                <Switch
                  label="Карточка опубликована"
                  checked={card.is_published}
                  onChange={(event) =>
                    updateCard(index, {
                      is_published: event.currentTarget.checked,
                    })
                  }
                />
              </Group>
            </Stack>
          </Card>
        ))}

        <Group justify="flex-end">
          <Button
            type="button"
            variant="subtle"
            onClick={() => navigate("/admin/interviews")}
          >
            Отмена
          </Button>
          <Button type="submit" loading={pending} disabled={!valid}>
            {editing ? "Сохранить колоду" : "Создать колоду"}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
