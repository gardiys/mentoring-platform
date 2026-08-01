import {
  Alert,
  Autocomplete,
  Button,
  Card,
  Group,
  Modal,
  Select,
  Stack,
  TagsInput,
  Text,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/endpoints";
import { PageHeader } from "../components/PageHeader";
import {
  useCreateInterviewProcess,
  useInterviewCompanySuggestions,
  useInterviewDirections,
} from "../features/interviews/journalQueries";
import type { CompanyOption, InterviewProcessMutation } from "../types/api";

interface AliasConfirmation {
  enteredName: string;
  selectedName: string;
}

interface CompanyMatchConfirmation {
  enteredName: string;
  companies: CompanyOption[];
}

export function InterviewProcessCreatePage() {
  const [trackId, setTrackId] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    null,
  );
  const [selectedCompanyName, setSelectedCompanyName] = useState<string | null>(
    null,
  );
  const [companyAlias, setCompanyAlias] = useState<string | null>(null);
  const [recruiterUsernames, setRecruiterUsernames] = useState<string[]>([]);
  const [aliasConfirmation, setAliasConfirmation] =
    useState<AliasConfirmation | null>(null);
  const [companyMatchConfirmation, setCompanyMatchConfirmation] =
    useState<CompanyMatchConfirmation | null>(null);
  const [isCheckingCompanies, setIsCheckingCompanies] = useState(false);
  const [debouncedCompanyName] = useDebouncedValue(companyName, 250);
  const suggestions = useInterviewCompanySuggestions(debouncedCompanyName);
  const mutation = useCreateInterviewProcess();
  const directions = useInterviewDirections();
  const navigate = useNavigate();

  const createTrack = (payload: Omit<InterviewProcessMutation, "track_id">) => {
    if (!trackId) return;
    mutation.mutate(
      {
        ...payload,
        track_id: trackId,
        recruiter_telegram_usernames: recruiterUsernames,
      },
      {
        onSuccess: (process) => {
          notifications.show({ color: "green", message: "Трек создан" });
          navigate(`/interviews/journal/${process.id}`);
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !companyName.trim() ||
      !trackId ||
      mutation.isPending ||
      isCheckingCompanies ||
      aliasConfirmation
    ) {
      return;
    }
    const selectedCompanyIsCurrent = companyName === selectedCompanyName;
    if (selectedCompanyIsCurrent) {
      createTrack({
        company_name: companyName.trim(),
        company_id: selectedCompanyId,
        company_alias: companyAlias,
      });
      return;
    }

    const enteredName = companyName.trim();
    setIsCheckingCompanies(true);
    try {
      const companies = await api.interviewCompanySuggestions(enteredName);
      if (companies.length > 0) {
        setCompanyMatchConfirmation({ enteredName, companies });
      } else {
        createTrack({
          company_name: enteredName,
          company_id: null,
          company_alias: null,
        });
      }
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error
            ? error.message
            : "Не удалось проверить компании",
      });
    } finally {
      setIsCheckingCompanies(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <Stack gap="xl">
        <PageHeader
          eyebrow="Собеседования · дневник"
          title="Новый трек"
          description="Создайте отдельный процесс для компании, в которую проходите собеседования."
        />
        <Card withBorder>
          <Stack>
            {mutation.error && (
              <Alert color="red">{mutation.error.message}</Alert>
            )}
            <Select
              label="Направление"
              placeholder="Выберите Python или Go"
              required
              searchable
              disabled={directions.isPending || directions.isError}
              data={(directions.data ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              value={trackId}
              onChange={setTrackId}
              error={
                directions.isError
                  ? "Не удалось загрузить доступные направления"
                  : undefined
              }
            />
            <Autocomplete
              label="Компания"
              placeholder="Яндекс"
              required
              value={companyName}
              onChange={setCompanyName}
              onOptionSubmit={(value) => {
                const selected = suggestions.data?.find(
                  (company) => company.name === value,
                );
                if (!selected) return;
                const enteredName = companyName.trim();
                setSelectedCompanyId(selected.id);
                setSelectedCompanyName(selected.name);
                setCompanyAlias(null);
                if (
                  enteredName.localeCompare(selected.name, "ru", {
                    sensitivity: "base",
                  }) !== 0
                ) {
                  setAliasConfirmation({
                    enteredName,
                    selectedName: selected.name,
                  });
                }
                setCompanyName(selected.name);
              }}
              data={(suggestions.data ?? []).map((company) => company.name)}
              filter={({ options }) => options}
              limit={8}
            />
            <Text size="xs" c="dimmed">
              ООО, ИП, АО и другие юридические формы будут удалены. Если вы
              выберете существующую компанию после другого ввода, платформа
              уточнит, нужно ли запомнить его как альтернативное название. Если
              ничего не выбрать, перед созданием будут ещё раз показаны
              возможные совпадения.
            </Text>
            <TagsInput
              label="Telegram рекрутеров"
              placeholder="@recruiter_name"
              description="Можно указать до 20 никнеймов. Нажимайте Enter после каждого."
              value={recruiterUsernames}
              onChange={setRecruiterUsernames}
              maxTags={20}
              clearable
            />
          </Stack>
        </Card>
        <Group justify="flex-end">
          <Button
            type="button"
            variant="subtle"
            onClick={() => navigate("/interviews")}
          >
            Отмена
          </Button>
          <Button
            type="submit"
            loading={mutation.isPending || isCheckingCompanies}
            disabled={
              !companyName.trim() || !trackId || aliasConfirmation !== null
            }
          >
            Создать трек
          </Button>
        </Group>
      </Stack>
      <Modal
        opened={aliasConfirmation !== null}
        onClose={() => {
          setCompanyAlias(null);
          setAliasConfirmation(null);
        }}
        title="Уточним название компании"
        centered
      >
        <Stack>
          <Text>
            {`Вы ввели «${aliasConfirmation?.enteredName}», а выбрали «${aliasConfirmation?.selectedName}».`}
          </Text>
          <Text fw={600}>
            То, что вы ввели, — альтернативное название компании?
          </Text>
          <Group justify="flex-end">
            <Button
              type="button"
              variant="subtle"
              onClick={() => {
                setCompanyAlias(null);
                setAliasConfirmation(null);
              }}
            >
              Нет
            </Button>
            <Button
              type="button"
              onClick={() => {
                setCompanyAlias(aliasConfirmation?.enteredName ?? null);
                setAliasConfirmation(null);
              }}
            >
              Да, это альтернативное название
            </Button>
          </Group>
        </Stack>
      </Modal>
      <Modal
        opened={companyMatchConfirmation !== null}
        onClose={() => setCompanyMatchConfirmation(null)}
        title="Возможно, компания уже есть"
        centered
      >
        <Stack>
          <Text>
            {`Вы ввели «${companyMatchConfirmation?.enteredName}». Есть ли ваша компания среди найденных?`}
          </Text>
          <Stack gap="xs">
            {companyMatchConfirmation?.companies.map((company) => (
              <Button
                key={company.id}
                type="button"
                variant="light"
                fullWidth
                onClick={() => {
                  const enteredName = companyMatchConfirmation.enteredName;
                  setCompanyMatchConfirmation(null);
                  createTrack({
                    company_name: company.name,
                    company_id: company.id,
                    company_alias: enteredName,
                  });
                }}
              >
                Связать с «{company.name}»
              </Button>
            ))}
          </Stack>
          <Button
            type="button"
            variant="subtle"
            onClick={() => {
              if (!companyMatchConfirmation) return;
              const enteredName = companyMatchConfirmation.enteredName;
              setCompanyMatchConfirmation(null);
              createTrack({
                company_name: enteredName,
                company_id: null,
                company_alias: null,
              });
            }}
          >
            Моей компании нет — создать новую
          </Button>
        </Stack>
      </Modal>
    </form>
  );
}
