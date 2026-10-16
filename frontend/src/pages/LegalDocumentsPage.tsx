import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiRequest, downloadAuthenticated } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { PaymentTerms } from "../components/LegalCheckout";
import { LoadingState } from "../components/LoadingState";
import { questionnaireLabels } from "../features/opportunities/legalQuestionnaire";
import { useMe } from "../features/auth/queries";

interface Contract {
  id: string;
  public_number: string;
  product_code: string;
  status: string;
  accepted_at: string;
  acceptance_snapshot_sha256: string;
  snapshot: {
    title: string;
    customer_email: string;
    offer_version_code: string;
    offer_publication_date: string;
    offer_pdf_sha256: string;
    questionnaire_answers: Record<string, string | boolean>;
    financial_terms: {
      upfront_amount_minor: number;
      success_fee_percent: number;
      success_fee_installments: number;
      success_fee_due_month_offsets: number[];
    };
  };
  email_deliveries?: {
    id: string;
    status: string;
    attempt_number: number;
    recipient_email: string;
    error_code?: string;
    safe_error_message?: string;
    provider_message_id?: string;
  }[];
  current_email?: string;
  webhooks?: unknown[];
  audit?: unknown[];
}
interface Offer {
  id: string;
  title: string;
  version_code: string;
  status: string;
  pdf_sha256: string;
}
const statuses: Record<string, string> = {
  active: "Действует",
  terminated: "Прекращён",
  refunded: "Возврат",
  disputed: "Оспаривается",
  pending: "В очереди",
  processing: "Отправляется",
  sent: "Принято почтовым провайдером; доставка не подтверждена",
  delivered: "Доставлено",
  bounced: "Не доставлено",
  failed: "Ошибка отправки",
};

export function LegalDocumentsPage() {
  const me = useMe();
  const admin = me.data?.role === "admin";
  const [q, setQ] = useState("");
  const [params, setParams] = useSearchParams();
  const selected = params.get("contract");
  const [message, setMessage] = useState("");
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["legal-contracts", admin, q],
    queryFn: () =>
      apiRequest<Contract[]>(
        admin
          ? `/api/v1/admin/legal/contracts?q=${encodeURIComponent(q)}`
          : "/api/v1/legal/contracts",
      ),
    enabled: !!me.data,
    refetchInterval: params.get("payment_status") === "success" ? 5000 : false,
  });
  const details = useQuery({
    queryKey: ["legal-contract", selected],
    queryFn: () => apiRequest<Contract>(`/api/v1/legal/contracts/${selected}`),
    enabled: !!selected,
  });
  const offers = useQuery({
    queryKey: ["legal-offers"],
    queryFn: () => apiRequest<Offer[]>("/api/v1/admin/legal/offers"),
    enabled: admin,
  });
  const metrics = useQuery({
    queryKey: ["legal-metrics"],
    queryFn: () =>
      apiRequest<Record<string, unknown>>("/api/v1/admin/legal/metrics"),
    enabled: admin,
  });
  const resend = useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/v1/legal/contracts/${id}/resend-email`, {
        method: "POST",
      }),
    onSuccess: () => {
      setMessage(
        "Письмо поставлено в очередь на первоначальный email договора",
      );
      void client.invalidateQueries({ queryKey: ["legal-contract"] });
    },
    onError: (error: Error) => setMessage(error.message),
  });
  const activate = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiRequest(`/api/v1/admin/legal/offers/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["legal-offers"] }),
    onError: (error: Error) => setMessage(error.message),
  });
  const contract = details.data;
  return (
    <Stack gap="lg">
      <Title order={1}>{admin ? "Договоры и оферты" : "Мои документы"}</Title>
      {message && <Alert>{message}</Alert>}
      {admin && (
        <TextInput
          label="Поиск по пользователю, email, номеру договора, платежу или продукту"
          value={q}
          onChange={(event) => setQ(event.currentTarget.value)}
        />
      )}
      {list.isPending && <LoadingState />}
      {list.isError && (
        <ErrorState error={list.error} retry={() => void list.refetch()} />
      )}
      {list.data?.length === 0 && (
        <Text>Договоры появятся после подтверждения успешной оплаты.</Text>
      )}
      {list.data?.map((row) => (
        <Card withBorder key={row.id}>
          <Group justify="space-between">
            <div>
              <Title order={3}>{row.snapshot.title}</Title>
              <Text>{row.public_number}</Text>
              <Text>
                {new Date(row.accepted_at).toLocaleString("ru-RU", {
                  timeZone: "Europe/Moscow",
                })}{" "}
                МСК
              </Text>
              <Badge>{statuses[row.status] ?? row.status}</Badge>
            </div>
            <Button
              variant="light"
              onClick={() => setParams({ contract: row.id })}
            >
              Открыть договор
            </Button>
          </Group>
        </Card>
      ))}
      {details.isError && (
        <ErrorState
          error={details.error}
          retry={() => void details.refetch()}
        />
      )}
      {contract && (
        <Card withBorder>
          <Stack>
            <Title order={2}>{contract.public_number}</Title>
            <Text>{contract.snapshot.title}</Text>
            <Text>
              Акцепт оплатой:{" "}
              {new Date(contract.accepted_at).toLocaleString("ru-RU", {
                timeZone: "Europe/Moscow",
              })}{" "}
              МСК. Статус: {statuses[contract.status]}.
            </Text>
            <Text>
              Редакция {contract.snapshot.offer_version_code}, публикация{" "}
              {contract.snapshot.offer_publication_date}.
            </Text>
            <PaymentTerms terms={contract.snapshot.financial_terms} paid />
            <Text>
              Первоначальный email: {contract.snapshot.customer_email}
            </Text>
            {admin && <Text>Текущий email: {contract.current_email}</Text>}
            <Group>
              <Button
                onClick={() =>
                  void downloadAuthenticated(
                    `/api/v1/legal/contracts/${contract.id}/offer.pdf`,
                    `Offer_${contract.product_code}_${contract.snapshot.offer_version_code}.pdf`,
                  ).catch((error: Error) => setMessage(error.message))
                }
              >
                Скачать точную PDF-копию
              </Button>
              <Button
                variant="light"
                loading={resend.isPending}
                onClick={() => resend.mutate(contract.id)}
              >
                Повторно отправить письмо
              </Button>
            </Group>
            <Title order={3}>Отправка письма</Title>
            {contract.email_deliveries?.map((row) => (
              <Text key={row.id}>
                Попытка {row.attempt_number}:{" "}
                {statuses[row.status] ?? row.status}; {row.recipient_email}
                {row.error_code
                  ? ` — ${row.safe_error_message ?? row.error_code}`
                  : ""}
                {admin && row.provider_message_id
                  ? ` · Message-ID: ${row.provider_message_id}`
                  : ""}
              </Text>
            ))}
            <Title order={3}>Предварительные сведения на момент оплаты</Title>
            {Object.entries(contract.snapshot.questionnaire_answers).map(
              ([key, value]) => (
                <Text key={key}>
                  <strong>
                    {questionnaireLabels[key] ??
                      (key.endsWith("_details")
                        ? `Пояснение: ${questionnaireLabels[key.replace("_details", "")]}`
                        : key)}
                    :
                  </strong>{" "}
                  {typeof value === "boolean"
                    ? value
                      ? "Да"
                      : "Нет"
                    : value || "—"}
                </Text>
              ),
            )}
            {admin && (
              <>
                <Text>SHA-256 PDF: {contract.snapshot.offer_pdf_sha256}</Text>
                <Text>
                  SHA-256 акцепта: {contract.acceptance_snapshot_sha256}
                </Text>
                <Title order={3}>
                  Снимок подтверждений, платежа и технических сведений
                </Title>
                <Code block>{JSON.stringify(contract.snapshot, null, 2)}</Code>
                <Title order={3}>Webhook и аудит</Title>
                <Code block>
                  {JSON.stringify(
                    { webhooks: contract.webhooks, audit: contract.audit },
                    null,
                    2,
                  )}
                </Code>
              </>
            )}
          </Stack>
        </Card>
      )}
      {admin && (
        <>
          <Title order={2}>Редакции оферт</Title>
          {offers.data?.map((offer) => (
            <Card withBorder key={offer.id}>
              <Stack>
                <Text>
                  {offer.title} · {offer.version_code} · {offer.status}
                </Text>
                <Text size="xs">SHA-256: {offer.pdf_sha256}</Text>
                <Group>
                  {["active", "retired", "revoked"]
                    .filter(
                      (status) =>
                        status !== offer.status && offer.status !== "revoked",
                    )
                    .map((status) => (
                      <Button
                        key={status}
                        loading={activate.isPending}
                        onClick={() =>
                          activate.mutate({ id: offer.id, status })
                        }
                      >
                        {status === "active"
                          ? "Активировать"
                          : status === "retired"
                            ? "Завершить новые продажи"
                            : "Отозвать редакцию"}
                      </Button>
                    ))}
                </Group>
              </Stack>
            </Card>
          ))}
          <Title order={2}>Очередь писем и сигналы мониторинга</Title>
          <Code block>{JSON.stringify(metrics.data, null, 2)}</Code>
        </>
      )}
    </Stack>
  );
}
