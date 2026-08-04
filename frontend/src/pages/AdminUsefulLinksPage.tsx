import {
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminUsefulLinks,
  useDeleteAdminUsefulLink,
  useSaveAdminUsefulLink,
} from "../features/schedule/queries";
import type {
  PinnedResourceLinkMutation,
  PinnedResourceLinkRead,
} from "../types/api";

interface UsefulLinkFormState {
  title: string;
  description: string;
  url: string;
  position: number | string;
}

const emptyForm: UsefulLinkFormState = {
  title: "",
  description: "",
  url: "",
  position: 0,
};

function linkForm(link: PinnedResourceLinkRead): UsefulLinkFormState {
  return {
    title: link.title,
    description: link.description ?? "",
    url: link.url,
    position: link.position,
  };
}

function validHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function AdminUsefulLinksPage() {
  const query = useAdminUsefulLinks();
  const saveLink = useSaveAdminUsefulLink();
  const deleteLink = useDeleteAdminUsefulLink();
  const [opened, setOpened] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<UsefulLinkFormState>(emptyForm);
  const [submitted, setSubmitted] = useState(false);

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setSubmitted(false);
    setOpened(true);
  };

  const openEdit = (link: PinnedResourceLinkRead) => {
    setEditingId(link.id);
    setForm(linkForm(link));
    setSubmitted(false);
    setOpened(true);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitted(true);
    const title = form.title.trim();
    const url = form.url.trim();
    if (
      !title ||
      !validHttpUrl(url) ||
      typeof form.position !== "number" ||
      !Number.isInteger(form.position) ||
      form.position < 0
    ) {
      return;
    }

    const payload: PinnedResourceLinkMutation = {
      title,
      description: form.description.trim() || null,
      url,
      position: form.position,
    };
    saveLink.mutate(
      { linkId: editingId ?? undefined, payload },
      {
        onSuccess: () => {
          setOpened(false);
          notifications.show({
            color: "green",
            message: editingId ? "Ссылка обновлена" : "Ссылка добавлена",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const remove = (link: PinnedResourceLinkRead) => {
    if (!window.confirm(`Удалить ссылку «${link.title}»?`)) return;
    deleteLink.mutate(link.id, {
      onSuccess: () =>
        notifications.show({ color: "green", message: "Ссылка удалена" }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Полезные ссылки"
          title="Полезные ссылки"
          description="Закрепляйте общие материалы и сервисы, которые ученики увидят в разделе своего ментора."
        />
        <Button onClick={openCreate}>+ Добавить ссылку</Button>
      </Group>

      {query.isPending ? (
        <LoadingState label="Загружаем полезные ссылки…" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data.length === 0 ? (
        <Text c="dimmed">
          Полезных ссылок пока нет. Добавьте первую — она появится у учеников.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={100}>Позиция</Table.Th>
                <Table.Th>Материал</Table.Th>
                <Table.Th>Ссылка</Table.Th>
                <Table.Th aria-label="Действия" />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {query.data.map((link) => (
                <Table.Tr key={link.id}>
                  <Table.Td>
                    <Text fw={600}>{link.position}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text fw={600}>{link.title}</Text>
                    {link.description && (
                      <Text size="sm" c="dimmed" lineClamp={2}>
                        {link.description}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text
                      component="a"
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      c="blue"
                    >
                      Открыть ссылку
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" justify="flex-end" wrap="nowrap">
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() => openEdit(link)}
                      >
                        Изменить
                      </Button>
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        loading={
                          deleteLink.isPending &&
                          deleteLink.variables === link.id
                        }
                        onClick={() => remove(link)}
                      >
                        Удалить
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}

      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title={editingId ? "Изменить полезную ссылку" : "Новая полезная ссылка"}
        centered
      >
        <form onSubmit={submit} noValidate>
          <Stack>
            <TextInput
              label="Название"
              required
              maxLength={240}
              value={form.title}
              error={
                submitted && !form.title.trim() ? "Укажите название" : undefined
              }
              onChange={(event) => {
                const title = event.currentTarget.value;
                setForm((current) => ({ ...current, title }));
              }}
            />
            <Textarea
              label="Описание"
              description="Необязательно"
              minRows={3}
              maxLength={5000}
              value={form.description}
              onChange={(event) => {
                const description = event.currentTarget.value;
                setForm((current) => ({ ...current, description }));
              }}
            />
            <TextInput
              label="URL"
              required
              type="url"
              maxLength={2048}
              placeholder="https://example.com/material"
              value={form.url}
              error={
                submitted && !validHttpUrl(form.url.trim())
                  ? "Укажите полную ссылку с http:// или https://"
                  : undefined
              }
              onChange={(event) => {
                const url = event.currentTarget.value;
                setForm((current) => ({ ...current, url }));
              }}
            />
            <NumberInput
              label="Позиция"
              description="Ссылки с меньшим номером показываются первыми"
              required
              min={0}
              allowDecimal={false}
              value={form.position}
              error={
                submitted &&
                (typeof form.position !== "number" ||
                  !Number.isInteger(form.position) ||
                  form.position < 0)
                  ? "Укажите целое число от 0"
                  : undefined
              }
              onChange={(value) =>
                setForm((current) => ({ ...current, position: value }))
              }
            />
            <Group justify="flex-end">
              <Button
                type="button"
                variant="subtle"
                onClick={() => setOpened(false)}
              >
                Отмена
              </Button>
              <Button type="submit" loading={saveLink.isPending}>
                {editingId ? "Сохранить" : "Добавить ссылку"}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
