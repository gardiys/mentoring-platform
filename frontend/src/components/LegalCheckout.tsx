import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  Group,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { questionnaireLabels } from "../features/opportunities/legalQuestionnaire";
import { useApplicationDraft } from "../features/opportunities/useApplicationDraft";
import { apiRequest, downloadAuthenticated } from "../api/client";
import { formatRubles } from "../utils/money";
import { openExternalResource } from "../utils/openExternalResource";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

type Terms = {
  upfront_amount_minor: number;
  success_fee_percent: number;
  success_fee_installments: number;
  success_fee_due_month_offsets: number[];
};
type Details = {
  title: string;
  offer_version_id: string;
  version_code: string;
  publication_date: string;
  pdf_url: string;
  financial_terms: Terms;
  checkboxes: Record<string, string>;
  email: string | null;
  email_verified: boolean;
};

const boolNames = [
  "existing_offers",
  "selection_processes",
  "previous_obligations",
  "go_in_current_work",
];
const textNames = [
  "employment_status",
  "position",
  "work_format",
  "technologies",
  "previous_contract",
];
const draftLimits = {
  employment_status: 100,
  position: 500,
  work_format: 500,
  technologies: 1000,
  previous_contract: 500,
  ...Object.fromEntries(boolNames.map((name) => [name, 3])),
  ...Object.fromEntries(boolNames.map((name) => [`${name}_details`, 2000])),
};

export function PaymentTerms({
  terms,
  paid = false,
}: {
  terms: Terms;
  paid?: boolean;
}) {
  const upfront = formatRubles(terms.upfront_amount_minor);
  const fee = (250_000_00 * terms.success_fee_percent) / 100;
  return (
    <Stack gap="xs">
      <Title order={3}>
        {paid ? "Условия оплаты договора" : "Стоимость и условия оплаты"}
      </Title>
      <Text fw={700}>
        {paid ? "Первоначально оплачено" : "Сегодня к оплате"}: {upfront} +{" "}
        {terms.success_fee_percent}% при предусмотренном офертой
        трудоустройстве.
      </Text>
      <Text>
        Результативный компонент начисляется дополнительно и не уменьшается на
        первоначальную оплату. Минимальный размер отсутствует. Оплата —{" "}
        {terms.success_fee_installments} равных платежа через{" "}
        {terms.success_fee_due_month_offsets.join(" и ")} календарных месяца с
        даты трудоустройства.
      </Text>
      <Text size="sm">
        Пояснительный пример при расчётном ежемесячном вознаграждении{" "}
        {formatRubles(250_000_00)}: первоначально {upfront}, результативный
        компонент {formatRubles(fee)}, два платежа по{" "}
        {formatRubles(fee / terms.success_fee_installments)}, всего{" "}
        {formatRubles(terms.upfront_amount_minor + fee)}. При расхождении
        применяется формула оферты.
      </Text>
    </Stack>
  );
}

export function LegalCheckout({
  product,
  applicationId,
}: {
  product: string;
  applicationId: string;
}) {
  const query = useQuery({
    queryKey: ["legal-checkout", product],
    queryFn: () =>
      apiRequest<Details>(`/api/v1/legal/products/${product}/checkout`),
    retry: false,
  });
  const draft = useQuery({
    queryKey: ["legal-questionnaire", product],
    queryFn: () =>
      apiRequest<{ answers: Record<string, string | boolean> | null }>(
        `/api/v1/legal/products/${product}/questionnaire`,
      ),
    retry: false,
  });
  if (query.isPending || draft.isPending)
    return <LoadingState label="Загружаем оферту…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  if (draft.isError)
    return (
      <ErrorState error={draft.error} retry={() => void draft.refetch()} />
    );
  return (
    <CheckoutForm
      key={`${applicationId}:${query.data.offer_version_id}`}
      details={query.data}
      initialAnswers={draft.data?.answers ?? {}}
      product={product}
      applicationId={applicationId}
      refresh={() => void query.refetch()}
    />
  );
}

function CheckoutForm({
  details,
  initialAnswers,
  product,
  applicationId,
  refresh,
}: {
  details: Details;
  initialAnswers: Record<string, string | boolean>;
  product: string;
  applicationId: string;
  refresh: () => void;
}) {
  const storedDraft = useApplicationDraft(
    `mentoring.questionnaire-draft.v1:${product}:${applicationId}`,
    Object.fromEntries(
      Object.entries(initialAnswers).map(([key, value]) => [
        key,
        typeof value === "boolean" ? (value ? "yes" : "no") : value,
      ]),
    ),
    draftLimits,
  );
  const answers = storedDraft.values;
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const isGo = product === "python_to_go_transition";
  const boolFields = boolNames.filter(
    (name) => isGo || name !== "go_in_current_work",
  );
  const payloadAnswers = () => ({
    ...Object.fromEntries(textNames.map((name) => [name, answers[name] ?? ""])),
    ...Object.fromEntries(
      boolNames.map((name) => [name, answers[name] === "yes"]),
    ),
    ...Object.fromEntries(
      boolNames.map((name) => [
        `${name}_details`,
        answers[`${name}_details`] ?? "",
      ]),
    ),
  });
  const valid =
    textNames
      .filter((name) => name !== "previous_contract")
      .every((name) => (answers[name]?.trim().length ?? 0) >= 2) &&
    boolFields.every(
      (name) =>
        ["yes", "no"].includes(answers[name] ?? "") &&
        (answers[name] !== "yes" || !!answers[`${name}_details`]?.trim()),
    );
  const mutation = useMutation({
    onError: (error: Error) => {
      setMessage(error.message);
      if (error.message.includes("Оферта изменилась")) refresh();
    },
    mutationFn: async () => {
      await apiRequest(`/api/v1/legal/products/${product}/questionnaire`, {
        method: "PUT",
        body: JSON.stringify(payloadAnswers()),
      });
      return apiRequest<{ payment_url: string }>(
        isGo
          ? `/api/v1/opportunities/go-transition/${applicationId}/payment-link`
          : `/api/v1/opportunities/python-repeat/applications/${applicationId}/checkout`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_offer_version_id: details.offer_version_id,
            questionnaire_schema_version: 1,
            answers: payloadAnswers(),
            confirmations: confirmed,
            page_identifier: window.location.pathname,
          }),
        },
      );
    },
  });
  const emailMutation = useMutation({
    mutationFn: async (confirm: boolean) => {
      await apiRequest(
        `/api/v1/legal/email/${confirm ? "confirm" : "request-code"}`,
        {
          method: "POST",
          ...(confirm ? { body: JSON.stringify({ code }) } : {}),
        },
      );
      setMessage(
        confirm
          ? "Email подтверждён"
          : "Код поставлен в очередь отправки. Проверьте почту.",
      );
      refresh();
    },
  });
  return (
    <Stack component="section" gap="md">
      <PaymentTerms terms={details.financial_terms} />
      <Text>
        Оферта: редакция {details.version_code}, опубликована{" "}
        {new Date(
          `${details.publication_date}T00:00:00+03:00`,
        ).toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" })}
        .
      </Text>
      <Button
        variant="light"
        onClick={() =>
          void downloadAuthenticated(
            details.pdf_url,
            `Offer_${product}_${details.version_code}.pdf`,
          ).catch((error: Error) => setMessage(error.message))
        }
      >
        Открыть точную PDF-оферту
      </Button>
      <Text>
        Документы будут отправлены на:{" "}
        <strong>{details.email ?? "email не указан"}</strong>.{" "}
        <Anchor component={Link} to="/payments">
          Изменить email
        </Anchor>
      </Text>
      {!details.email_verified && (
        <Alert title="Подтвердите email перед оплатой" color="yellow">
          <Stack>
            <Button
              disabled={!details.email}
              loading={emailMutation.isPending}
              onClick={() => emailMutation.mutate(false)}
            >
              Отправить код подтверждения
            </Button>
            <TextInput
              label="Код из письма"
              value={code}
              maxLength={8}
              onChange={(e) => setCode(e.currentTarget.value)}
            />
            <Button
              disabled={!/^\d{8}$/.test(code)}
              onClick={() => emailMutation.mutate(true)}
            >
              Подтвердить email
            </Button>
          </Stack>
        </Alert>
      )}
      <Title order={3}>Предварительные сведения</Title>
      {storedDraft.available ? (
        <Text size="sm" c="dimmed">
          Черновик анкеты сохраняется автоматически на этом устройстве.
        </Text>
      ) : (
        <Alert color="yellow" title="Не удалось сохранить черновик">
          Хранилище браузера недоступно. При закрытии страницы введённые данные
          могут потеряться.
        </Alert>
      )}
      {textNames.map((name) => (
        <TextInput
          key={name}
          required={name !== "previous_contract"}
          label={questionnaireLabels[name]}
          maxLength={
            name === "technologies"
              ? 1000
              : name === "employment_status"
                ? 100
                : 500
          }
          value={answers[name] ?? ""}
          onChange={(event) =>
            storedDraft.setField(name, event.currentTarget.value)
          }
        />
      ))}
      {boolFields.map((name) => (
        <Stack key={name} gap="xs">
          <Select
            required
            label={`${questionnaireLabels[name]}${isGo && ["existing_offers", "selection_processes"].includes(name) ? " на Go-позиции" : ""}`}
            data={[
              { value: "no", label: "Нет" },
              { value: "yes", label: "Да" },
            ]}
            value={answers[name] ?? null}
            onChange={(value) => storedDraft.setField(name, value ?? "")}
          />
          {answers[name] === "yes" && (
            <Textarea
              required
              label="Пояснение"
              maxLength={2000}
              value={answers[`${name}_details`] ?? ""}
              onChange={(event) =>
                storedDraft.setField(
                  `${name}_details`,
                  event.currentTarget.value,
                )
              }
            />
          )}
        </Stack>
      ))}
      {Object.entries(details.checkboxes).map(([name, text]) => (
        <Checkbox
          key={name}
          label={text}
          checked={confirmed[name] ?? false}
          onChange={(event) =>
            setConfirmed({ ...confirmed, [name]: event.currentTarget.checked })
          }
        />
      ))}
      <Text size="sm">
        Подтверждения фиксируют ознакомление. Договор заключается при
        подтверждённой успешной оплате. Письмо подтверждает заключение договора
        и не требует ответа.
      </Text>
      <Group>
        <Button
          loading={mutation.isPending}
          disabled={
            !details.email_verified ||
            !valid ||
            !Object.keys(details.checkboxes).every((name) => confirmed[name])
          }
          onClick={() =>
            void openExternalResource(
              mutation.mutateAsync().then((value) => value.payment_url),
            ).catch((error: Error) => setMessage(error.message))
          }
        >
          Перейти к оплате{" "}
          {formatRubles(details.financial_terms.upfront_amount_minor)}
        </Button>
        <Button component={Link} to="/documents" variant="subtle">
          Мои документы
        </Button>
      </Group>
      {(message || mutation.error || emailMutation.error) && (
        <Alert color="blue">
          {message || mutation.error?.message || emailMutation.error?.message}
        </Alert>
      )}
    </Stack>
  );
}
