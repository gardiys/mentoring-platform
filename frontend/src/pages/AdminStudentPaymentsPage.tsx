import { Button, Group, Modal, Stack, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { AdminPaymentsNavigation } from "../components/AdminPaymentsNavigation";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { PaymentSchedule } from "../components/PaymentSchedule";
import {
  useAdminPaymentStudent,
  useConfirmAdminPayment,
  useRevokeAdminPayment,
  useUpdateStudentPaymentDays,
} from "../features/payments/queries";

export function AdminStudentPaymentsPage() {
  const { studentId = "" } = useParams();
  const query = useAdminPaymentStudent(studentId);
  const updateDays = useUpdateStudentPaymentDays(studentId);
  const confirm = useConfirmAdminPayment();
  const revoke = useRevokeAdminPayment();
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [revokeReason, setRevokeReason] = useState("");

  if (query.isPending)
    return <LoadingState label="Загружаем платежи ученика…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Финансы · ученик"
        title={query.data.student_name}
        description="Полная история трудоустройств и платежей ученика. Просроченные взносы выделены красной обводкой."
      />
      <AdminPaymentsNavigation active="students" />
      <Group>
        <Button component={Link} to="/admin/payments" variant="subtle">
          ← К ученикам с офферами
        </Button>
        <Button
          component={Link}
          to={`/mentor/students/${studentId}`}
          variant="light"
        >
          Открыть карточку ученика
        </Button>
      </Group>
      <PaymentSchedule
        dashboard={query.data}
        onSaveDays={(days) => updateDays.mutateAsync(days)}
        savingDays={updateDays.isPending}
        onConfirm={(installmentId) => {
          if (!window.confirm("Подтвердить получение платежа вручную?")) return;
          confirm.mutate(installmentId, {
            onSuccess: () =>
              notifications.show({
                color: "green",
                message: "Платёж подтверждён",
              }),
            onError: (error) =>
              notifications.show({ color: "red", message: error.message }),
          });
        }}
        confirmingInstallmentId={
          confirm.isPending ? (confirm.variables ?? null) : null
        }
        onRevoke={setRevokeTarget}
        revokingInstallmentId={
          revoke.isPending ? (revoke.variables?.installmentId ?? null) : null
        }
      />
      <Modal
        opened={revokeTarget !== null}
        onClose={() => {
          if (revoke.isPending) return;
          setRevokeTarget(null);
          setRevokeReason("");
        }}
        title="Отменить подтверждение платежа"
        centered
      >
        <Stack>
          <Textarea
            label="Причина отмены"
            description="Причина сохранится в истории платежа. Минимум 3 символа."
            minRows={3}
            maxLength={500}
            value={revokeReason}
            onChange={(event) => setRevokeReason(event.currentTarget.value)}
            required
          />
          <Group justify="flex-end">
            <Button
              variant="subtle"
              disabled={revoke.isPending}
              onClick={() => {
                setRevokeTarget(null);
                setRevokeReason("");
              }}
            >
              Не отменять
            </Button>
            <Button
              color="red"
              loading={revoke.isPending}
              disabled={revokeReason.trim().length < 3}
              onClick={() => {
                if (!revokeTarget) return;
                revoke.mutate(
                  {
                    installmentId: revokeTarget,
                    reason: revokeReason.trim(),
                  },
                  {
                    onSuccess: () => {
                      setRevokeTarget(null);
                      setRevokeReason("");
                      notifications.show({
                        color: "green",
                        message: "Подтверждение платежа отменено",
                      });
                    },
                    onError: (error) =>
                      notifications.show({
                        color: "red",
                        message: error.message,
                      }),
                  },
                );
              }}
            >
              Отменить платёж
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
