import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  Pagination,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import {
  useAdminInterviewCards,
  useAdminInterviewDeck,
  useUpdateAdminInterviewDeckSettings,
} from "../features/admin/interviewQueries";
import { useAdminTracks } from "../features/admin/queries";
import type { AdminInterviewDeckSummary } from "../types/api";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function DeckEditor({ deck }: { deck: AdminInterviewDeckSummary }) {
  const [form, setForm] = useState({
    track_id: deck.track_id,
    slug: deck.slug,
    title: deck.title,
    description: deck.description,
    position: deck.position,
    is_published: deck.is_published,
  });
  const initial = useRef(form);
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 250);
  const [page, setPage] = useState(1);
  const tracks = useAdminTracks();
  const cards = useAdminInterviewCards(deck.id, debouncedSearch, page);
  const mutation = useUpdateAdminInterviewDeckSettings();
  const valid = form.title.trim().length > 0 && SLUG_PATTERN.test(form.slug);
  useUnsavedChanges(JSON.stringify(form) !== JSON.stringify(initial.current));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || mutation.isPending) return;
    mutation.mutate(
      { id: deck.id, payload: form },
      {
        onSuccess: () => {
          initial.current = form;
          notifications.show({
            color: "green",
            message: "Настройки колоды сохранены",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Собеседования · редактор"
        title={deck.title}
        description="Настройки колоды и вопросы сохраняются независимо друг от друга."
      />
      <form onSubmit={submit}>
        <Card withBorder>
          <Stack>
            <Title order={2}>Настройки колоды</Title>
            {mutation.error && (
              <Alert color="red">{mutation.error.message}</Alert>
            )}
            <Select
              label="Учебный трек"
              required
              searchable
              data={(tracks.data ?? []).map((track) => ({
                value: track.id,
                label: `${track.title} / ${track.slug}`,
              }))}
              value={form.track_id}
              onChange={(value) =>
                setForm((current) => ({ ...current, track_id: value ?? "" }))
              }
            />
            <Group grow align="flex-start">
              <TextInput
                label="Название"
                required
                value={form.title}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    title: event.currentTarget.value,
                  }))
                }
              />
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
            </Group>
            <Textarea
              label="Описание"
              value={form.description ?? ""}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.currentTarget.value || null,
                }))
              }
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
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    is_published: event.currentTarget.checked,
                  }))
                }
              />
            </Group>
            <Button
              type="submit"
              loading={mutation.isPending}
              disabled={!valid}
            >
              Сохранить настройки
            </Button>
          </Stack>
        </Card>
      </form>

      <Card withBorder>
        <Stack>
          <Group justify="space-between">
            <div>
              <Title order={2}>Вопросы</Title>
              <Text c="dimmed" size="sm">
                В таблице загружается не более 50 строк без текста ответов.
              </Text>
            </div>
            <Button
              component={Link}
              to={`/admin/interviews/${deck.id}/cards/new`}
            >
              + Добавить вопрос
            </Button>
          </Group>
          <TextInput
            label="Поиск по вопросу, теме или slug"
            value={search}
            onChange={(event) => {
              setSearch(event.currentTarget.value);
              setPage(1);
            }}
          />
          {cards.isPending ? (
            <LoadingState label="Загружаем вопросы…" />
          ) : cards.isError ? (
            <ErrorState
              error={cards.error}
              retry={() => void cards.refetch()}
            />
          ) : (
            <>
              <Table.ScrollContainer minWidth={760}>
                <Table striped highlightOnHover verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Вопрос</Table.Th>
                      <Table.Th>Тема</Table.Th>
                      <Table.Th>Частота</Table.Th>
                      <Table.Th>Спросили раз</Table.Th>
                      <Table.Th>Статус</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {cards.data.items.map((card) => (
                      <Table.Tr key={card.id}>
                        <Table.Td maw={420}>{card.question_preview}</Table.Td>
                        <Table.Td>{card.category}</Table.Td>
                        <Table.Td>
                          <Badge
                            color={
                              card.frequency === "frequent"
                                ? "brandYellow"
                                : "gray"
                            }
                          >
                            {card.frequency === "frequent"
                              ? "Частый"
                              : "Обычный"}
                          </Badge>
                        </Table.Td>
                        <Table.Td>{card.asked_count}</Table.Td>
                        <Table.Td>
                          {card.is_published ? "Опубликован" : "Черновик"}
                        </Table.Td>
                        <Table.Td>
                          <Button
                            component={Link}
                            to={`/admin/interviews/${deck.id}/cards/${card.id}/edit`}
                            variant="subtle"
                            size="xs"
                          >
                            Редактировать
                          </Button>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {cards.data.total === 0 && (
                <Text c="dimmed">Вопросы не найдены.</Text>
              )}
              {cards.data.total > 50 && (
                <Pagination
                  value={page}
                  onChange={setPage}
                  total={Math.ceil(cards.data.total / 50)}
                />
              )}
            </>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}

export function AdminInterviewDeckEditPage() {
  const { deckId = "" } = useParams();
  const query = useAdminInterviewDeck(deckId);
  if (query.isPending) return <LoadingState label="Загружаем колоду…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return <DeckEditor key={query.data.id} deck={query.data} />;
}
