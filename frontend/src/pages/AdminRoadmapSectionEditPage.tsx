import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  Stack,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminRoadmapSection,
  useSaveAdminRoadmapSection,
} from "../features/admin/queries";
import type { AdminSectionMutation, AdminSectionOutline } from "../types/api";

function SectionForm({
  roadmapId,
  section,
}: {
  roadmapId: string;
  section?: AdminSectionOutline;
}) {
  const navigate = useNavigate();
  const mutation = useSaveAdminRoadmapSection();
  const [form, setForm] = useState<AdminSectionMutation>({
    title: section?.title ?? "",
    description: section?.description ?? null,
    position: section?.position ?? 0,
    duration_days: section?.duration_days ?? null,
  });
  const back = `/admin/roadmaps/${roadmapId}/edit`;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.title.trim() || mutation.isPending) return;
    mutation.mutate(
      { roadmapId, sectionId: section?.id, payload: form },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: section ? "Раздел сохранён" : "Раздел создан",
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
          eyebrow="Роадмап · один раздел"
          title={section ? "Настройки раздела" : "Новый раздел"}
          description="Темы раздела редактируются отдельно на странице роадмапа."
        />
        <Card withBorder>
          <Stack>
            {mutation.error && (
              <Alert color="red">{mutation.error.message}</Alert>
            )}
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
              <NumberInput
                label="Длительность, дней"
                min={1}
                value={form.duration_days ?? ""}
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    duration_days: typeof value === "number" ? value : null,
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
                disabled={!form.title.trim()}
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

export function AdminRoadmapSectionEditPage() {
  const { roadmapId = "", sectionId } = useParams();
  const query = useAdminRoadmapSection(roadmapId, sectionId);
  if (sectionId && query.isPending)
    return <LoadingState label="Загружаем раздел…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  return (
    <SectionForm
      key={sectionId ?? "new"}
      roadmapId={roadmapId}
      section={query.data}
    />
  );
}
