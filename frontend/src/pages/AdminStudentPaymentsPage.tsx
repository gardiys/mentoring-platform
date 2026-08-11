import {
  Button,
  Group,
  Modal,
  Stack,
  Textarea,
  TextInput,
} from "@mantine/core";
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
  useRescheduleAdminPayment,
  useRevokeAdminPayment,
  useUpdateStudentPaymentDays,
} from "../features/payments/queries";

export function AdminStudentPaymentsPage() {
  const { studentId = "" } = useParams();
  const query = useAdminPaymentStudent(studentId);
  const updateDays = useUpdateStudentPaymentDays(studentId);
  const confirm = useConfirmAdminPayment();
  const revoke = useRevokeAdminPayment();
  const reschedule = useRescheduleAdminPayment(studentId);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [rescheduleTarget, setRescheduleTarget] = useState<{
    id: string;
    currentDueDate: string;
  } | null>(null);
  const [rescheduleDueDate, setRescheduleDueDate] = useState("");
  const [rescheduleReason, setRescheduleReason] = useState("");

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
        onReschedule={(installmentId, currentDueDate) => {
          setRescheduleTarget({ id: installmentId, currentDueDate });
          setRescheduleDueDate(nextAvailableDate(currentDueDate));
          setRescheduleReason("");
        }}
        reschedulingInstallmentId={
          reschedule.isPending
            ? (reschedule.variables?.installmentId ?? null)
            : null
        }
      />
      <Modal
        opened={rescheduleTarget !== null}
        onClose={() => {
          if (reschedule.isPending) return;
          setRescheduleTarget(null);
          setRescheduleDueDate("");
          setRescheduleReason("");
        }}
        title="Перенести дату платежа"
        centered
      >
        <Stack>
          <TextInput
            label="Новая дата платежа"
            type="date"
            min={
              rescheduleTarget
                ? nextAvailableDate(rescheduleTarget.currentDueDate)
                : undefined
            }
            value={rescheduleDueDate}
            onChange={(event) =>
              setRescheduleDueDate(event.currentTarget.value)
            }
            required
          />
          <Textarea
            label="Причина переноса"
            description="Причина и предыдущая дата сохранятся в истории платежа."
            minRows={3}
            maxLength={500}
            value={rescheduleReason}
            onChange={(event) => setRescheduleReason(event.currentTarget.value)}
            required
          />
          <Group justify="flex-end">
            <Button
              variant="subtle"
              disabled={reschedule.isPending}
              onClick={() => setRescheduleTarget(null)}
            >
              Не переносить
            </Button>
            <Button
              color="orange"
              loading={reschedule.isPending}
              disabled={
                !rescheduleTarget ||
                !rescheduleDueDate ||
                rescheduleReason.trim().length < 3
              }
              onClick={() => {
                if (!rescheduleTarget) return;
                reschedule.mutate(
                  {
                    installmentId: rescheduleTarget.id,
                    dueDate: rescheduleDueDate,
                    reason: rescheduleReason.trim(),
                  },
                  {
                    onSuccess: () => {
                      setRescheduleTarget(null);
                      setRescheduleDueDate("");
                      setRescheduleReason("");
                      notifications.show({
                        color: "green",
                        message: "Дата платежа перенесена",
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
              Перенести платёж
            </Button>
          </Group>
        </Stack>
      </Modal>
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

function nextAvailableDate(currentDueDate: string) {
  const current = new Date(`${currentDueDate}T00:00:00`);
  current.setDate(current.getDate() + 1);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const next = current > today ? current : today;
  return [
    next.getFullYear(),
    String(next.getMonth() + 1).padStart(2, "0"),
    String(next.getDate()).padStart(2, "0"),
  ].join("-");
}
