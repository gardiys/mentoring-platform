import { Alert, Stack } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { PaymentSchedule } from "../components/PaymentSchedule";
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
  const [searchParams, setSearchParams] = useSearchParams();

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
        onPay={(installmentId) => {
          void openExternalResource(
            createLink
              .mutateAsync(installmentId)
              .then((result) => result.payment_url),
          ).catch((error: Error) =>
            notifications.show({ color: "red", message: error.message }),
          );
        }}
      />
    </Stack>
  );
}
