import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminCompanyAliasProposals,
  useModerateCompanyAliasProposal,
} from "../features/interviews/companyAliasQueries";
import type {
  AdminCompanyAliasProposalRead,
  CompanyAliasProposalStatus,
} from "../types/api";

type QueueStatus = CompanyAliasProposalStatus | "all";

const statusLabels: Record<CompanyAliasProposalStatus, string> = {
  pending: "Ожидает проверки",
  approved: "Одобрено",
  rejected: "Отклонено",
};

export function AdminCompanyAliasProposalsPage() {
  const [status, setStatus] = useState<QueueStatus>("pending");
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [page, setPage] = useState(1);
  const [rejectedProposal, setRejectedProposal] =
    useState<AdminCompanyAliasProposalRead | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const offset = (page - 1) * 20;
  const query = useAdminCompanyAliasProposals(status, debouncedSearch, offset);
  const moderation = useModerateCompanyAliasProposal();

  const decide = (
    proposal: AdminCompanyAliasProposalRead,
    action: "approve" | "reject",
  ) => {
    const hasConflict = proposal.conflicting_company_name !== null;
    if (
      action === "approve" &&
      hasConflict &&
      !window.confirm(
        `Название «${proposal.alias_name}» уже относится к компании «${proposal.conflicting_company_name}». Объединить её с «${proposal.company_name}»? Это изменит существующие треки.`,
      )
    ) {
      return;
    }
    moderation.mutate(
      {
        proposalId: proposal.id,
        payload: {
          action,
          merge_conflicting_company: action === "approve" && hasConflict,
          rejection_reason: action === "reject" ? rejectionReason.trim() : null,
        },
      },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message:
              action === "approve"
                ? "Альтернативное название одобрено"
                : "Предложение отклонено",
          });
          setRejectedProposal(null);
          setRejectionReason("");
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  if (query.isPending) return <LoadingState label="Загружаем предложения…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  const pages = Math.max(1, Math.ceil(query.data.total / query.data.limit));
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование · Собеседования"
        title="Названия компаний"
        description="Проверяйте предложенные альтернативные названия до того, как они начнут влиять на глобальный поиск."
      />
      <Group align="flex-end" grow>
        <TextInput
          label="Поиск"
          placeholder="Название или алиас"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            setPage(1);
          }}
        />
        <Select
          label="Статус"
          value={status}
          data={[
            { value: "pending", label: "Ожидают проверки" },
            { value: "approved", label: "Одобренные" },
            { value: "rejected", label: "Отклонённые" },
            { value: "all", label: "Все" },
          ]}
          onChange={(value) => {
            setStatus((value as QueueStatus | null) ?? "pending");
            setPage(1);
          }}
        />
      </Group>
      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">В этой очереди пока нет предложений.</Text>
        </Card>
      ) : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={900}>
            <Table verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Предложение</Table.Th>
                  <Table.Th>Автор</Table.Th>
                  <Table.Th>Статус</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {query.data.items.map((proposal) => (
                  <Table.Tr key={proposal.id}>
                    <Table.Td miw={360}>
                      <Text fw={650}>
                        «{proposal.alias_name}» → «{proposal.company_name}»
                      </Text>
                      <Text size="xs" c="dimmed">
                        {new Date(proposal.created_at).toLocaleString("ru-RU")}
                      </Text>
                      {proposal.conflicting_company_name && (
                        <Alert color="yellow" mt="xs" py="xs">
                          Сейчас это название относится к «
                          {proposal.conflicting_company_name}». Одобрение
                          объединит компании и их треки.
                        </Alert>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text>
                        {proposal.suggested_by_name ?? "Удалённый пользователь"}
                      </Text>
                      {proposal.suggested_by_telegram_username && (
                        <Text size="xs" c="dimmed">
                          @{proposal.suggested_by_telegram_username}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={
                          proposal.status === "approved"
                            ? "green"
                            : proposal.status === "rejected"
                              ? "gray"
                              : "yellow"
                        }
                      >
                        {statusLabels[proposal.status]}
                      </Badge>
                      {proposal.rejection_reason && (
                        <Text size="xs" c="dimmed" mt={4}>
                          {proposal.rejection_reason}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {proposal.status === "pending" && (
                        <Group gap="xs" justify="flex-end" wrap="nowrap">
                          <Button
                            size="xs"
                            loading={moderation.isPending}
                            onClick={() => decide(proposal, "approve")}
                          >
                            {proposal.conflicting_company_name
                              ? "Объединить и одобрить"
                              : "Одобрить"}
                          </Button>
                          <Button
                            size="xs"
                            variant="light"
                            color="red"
                            disabled={moderation.isPending}
                            onClick={() => {
                              setRejectedProposal(proposal);
                              setRejectionReason("");
                            }}
                          >
                            Отклонить
                          </Button>
                        </Group>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}
      {pages > 1 && (
        <Group justify="center">
          <Pagination value={page} total={pages} onChange={setPage} />
        </Group>
      )}
      <Modal
        opened={rejectedProposal !== null}
        onClose={() => setRejectedProposal(null)}
        title="Отклонить альтернативное название"
        centered
      >
        <Stack>
          <Text>
            {rejectedProposal
              ? `Почему «${rejectedProposal.alias_name}» не относится к «${rejectedProposal.company_name}»?`
              : null}
          </Text>
          <Textarea
            label="Причина"
            required
            minRows={3}
            maxLength={500}
            value={rejectionReason}
            onChange={(event) => setRejectionReason(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setRejectedProposal(null)}>
              Отмена
            </Button>
            <Button
              color="red"
              disabled={!rejectionReason.trim() || !rejectedProposal}
              loading={moderation.isPending}
              onClick={() => {
                if (rejectedProposal) decide(rejectedProposal, "reject");
              }}
            >
              Отклонить
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
