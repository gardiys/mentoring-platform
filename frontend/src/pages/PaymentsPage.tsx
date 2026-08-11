import {
  Alert,
  Button,
  Card,
  Group,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { PaymentSchedule } from "../components/PaymentSchedule";
import { useMe, useUpdateMyEmail } from "../features/auth/queries";
import {
  useCreatePaymentLink,
  useMyPayments,
  useUpdateMyPaymentDays,
} from "../features/payments/queries";
import { openExternalResource } from "../utils/openExternalResource";

export function PaymentsPage() {
  const query = useMyPayments();
  const updateDays = useUpdateMyPaymentDays();
  const createLink = useCreatePaymentLink();
  const me = useMe();
  const updateEmail = useUpdateMyEmail();
  const [email, setEmail] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    if (!email && me.data?.email) setEmail(me.data.email);
  }, [email, me.data?.email]);

  useEffect(() => {
    const result = searchParams.get("payment_status");
    if (!result) return;
    notifications.show({
      color: result === "success" ? "green" : "red",
      message:
        result === "success"
          ? "Платёж принят. Статус обновится после подтверждения банка."
          : "Платёж не завершён. Можно повторить попытку.",
    });
    setSearchParams({}, { replace: true });
    void query.refetch();
  }, [query, searchParams, setSearchParams]);

  if (query.isPending) return <LoadingState label="Загружаем платежи…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Финансы"
        title="Мои платежи"
        description="График формируется после фиксации трудоустройства. Оплата проходит через защищённую страницу Точка Банка."
      />
      {!me.data?.email && (
        <Alert color="orange" title="Укажите email перед оплатой">
          Точка отправляет электронный чек на почту, поэтому без сохранённого
          email создать платёжную ссылку нельзя.
        </Alert>
      )}
      <Card withBorder>
        <Stack gap="md">
          <div>
            <Title order={3}>Контактный email</Title>
            <Text size="sm" c="dimmed">
              Используется для электронных чеков. Адрес можно изменить в любой
              момент.
            </Text>
          </div>
          <Group align="flex-end">
            <TextInput
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.currentTarget.value)}
              placeholder="name@example.com"
              style={{ flex: "1 1 18rem" }}
            />
            <Button
              loading={updateEmail.isPending}
              disabled={
                !validEmail(email) ||
                email.trim().toLowerCase() === me.data?.email?.toLowerCase()
              }
              onClick={() =>
                updateEmail.mutate(email.trim(), {
                  onSuccess: () =>
                    notifications.show({
                      color: "green",
                      message: "Email сохранён",
                    }),
                  onError: (error) =>
                    notifications.show({
                      color: "red",
                      message: error.message,
                    }),
                })
              }
            >
              {me.data?.email ? "Изменить email" : "Сохранить email"}
            </Button>
          </Group>
        </Stack>
      </Card>
      {!query.data.employment && (
        <Alert color="blue" title="Платежей пока нет">
          После выхода на работу ментор или администратор укажет данные
          трудоустройства, и здесь появится полный график.
        </Alert>
      )}
      <PaymentSchedule
        dashboard={query.data}
        savingDays={updateDays.isPending}
        onSaveDays={(days) => updateDays.mutateAsync(days)}
        payingInstallmentId={createLink.isPending ? createLink.variables : null}
        onPay={
          me.data?.email
            ? (installmentId) => {
                void openExternalResource(
                  createLink
                    .mutateAsync(installmentId)
                    .then((result) => result.payment_url),
                ).catch((error: Error) =>
                  notifications.show({ color: "red", message: error.message }),
                );
              }
            : undefined
        }
      />
    </Stack>
  );
}

function validEmail(value: string) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim());
}
