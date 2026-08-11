import {
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  TextInput,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState, type FormEvent } from "react";

import {
  useCancelAdminMentorPayout,
  useEditAdminMentorPayout,
} from "../features/payments/queries";
import type { MentorPayoutRead } from "../types/api";
import { formatRubles } from "../utils/money";

interface AdminMentorPayoutActionsProps {
  payout: MentorPayoutRead;
}

export function AdminMentorPayoutActions({
  payout,
}: AdminMentorPayoutActionsProps) {
  const editPayout = useEditAdminMentorPayout();
  const cancelPayout = useCancelAdminMentorPayout();
  const [editOpened, setEditOpened] = useState(false);
  const [cancelOpened, setCancelOpened] = useState(false);
  const [amount, setAmount] = useState<number | string>(
    payout.amount_kopecks / 100,
  );
  const [reference, setReference] = useState(payout.payment_reference ?? "");
  const [paidAt, setPaidAt] = useState(toDateTimeLocal(payout.paid_at));
  const [editReason, setEditReason] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  if (payout.status === "cancelled") return null;

  const openEdit = () => {
    setAmount(payout.amount_kopecks / 100);
    setReference(payout.payment_reference ?? "");
    setPaidAt(toDateTimeLocal(payout.paid_at));
    setEditReason("");
    setEditOpened(true);
  };

  const submitEdit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const amountRubles = Number(amount);
    if (!Number.isFinite(amountRubles) || amountRubles <= 0) {
      notifications.show({ color: "red", message: "Укажите сумму выплаты" });
      return;
    }
    if (editReason.trim().length < 3) return;
    editPayout.mutate(
      {
        payoutId: payout.id,
        amountRubles,
        paymentReference: reference.trim() || null,
        paidAt:
          payout.status === "paid" && paidAt
            ? new Date(paidAt).toISOString()
            : null,
        reason: editReason.trim(),
      },
      {
        onSuccess: () => {
          setEditOpened(false);
          notifications.show({
            color: "green",
            message: "Выплата исправлена, баланс пересчитан",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const submitCancel = () => {
    if (cancelReason.trim().length < 3) return;
    cancelPayout.mutate(
      { payoutId: payout.id, reason: cancelReason.trim() },
      {
        onSuccess: () => {
          setCancelOpened(false);
          setCancelReason("");
          notifications.show({
            color: "green",
            message:
              payout.status === "paid"
                ? "Ошибочная выплата отменена, сумма возвращена в баланс"
                : "Заявка на выплату отменена",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <>
      <Group gap="xs" wrap="nowrap">
        <Button size="compact-sm" variant="light" onClick={openEdit}>
          Редактировать
        </Button>
        <Button
          size="compact-sm"
          color="red"
          variant="subtle"
          onClick={() => {
            setCancelReason("");
            setCancelOpened(true);
          }}
        >
          {payout.status === "paid" ? "Удалить ошибочную" : "Отменить"}
        </Button>
      </Group>

      <Modal
        opened={editOpened}
        onClose={() => !editPayout.isPending && setEditOpened(false)}
        title="Редактировать выплату"
        centered
      >
        <form onSubmit={submitEdit}>
          <Stack>
            <NumberInput
              label="Сумма выплаты, ₽"
              min={0.01}
              decimalScale={2}
              value={amount}
              onChange={setAmount}
              required
            />
            {payout.status === "paid" && (
              <TextInput
                label="Дата и время выплаты"
                type="datetime-local"
                value={paidAt}
                onChange={(event) => setPaidAt(event.currentTarget.value)}
              />
            )}
            <TextInput
              label="Акт или комментарий"
              value={reference}
              maxLength={500}
              onChange={(event) => setReference(event.currentTarget.value)}
            />
            <Textarea
              label="Причина изменения"
              description="Сохранится в истории изменений. Минимум 3 символа."
              minRows={3}
              maxLength={500}
              value={editReason}
              onChange={(event) => setEditReason(event.currentTarget.value)}
              required
            />
            <Group justify="flex-end">
              <Button
                variant="subtle"
                disabled={editPayout.isPending}
                onClick={() => setEditOpened(false)}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                loading={editPayout.isPending}
                disabled={editReason.trim().length < 3}
              >
                Сохранить изменения
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal
        opened={cancelOpened}
        onClose={() => !cancelPayout.isPending && setCancelOpened(false)}
        title={
          payout.status === "paid"
            ? "Удалить ошибочную выплату"
            : "Отменить заявку"
        }
        centered
      >
        <Stack>
          <Alert color="red" variant="light">
            {payout.status === "paid"
              ? `${formatRubles(payout.amount_kopecks)} вернутся в доступный баланс ментора. Запись останется в аудите со статусом «Отменена».`
              : "Зарезервированная сумма снова станет доступна для выплаты."}
          </Alert>
          <Textarea
            label="Причина отмены"
            description="Причина сохранится в истории. Минимум 3 символа."
            minRows={3}
            maxLength={500}
            value={cancelReason}
            onChange={(event) => setCancelReason(event.currentTarget.value)}
            required
          />
          <Group justify="flex-end">
            <Button
              variant="subtle"
              disabled={cancelPayout.isPending}
              onClick={() => setCancelOpened(false)}
            >
              Не отменять
            </Button>
            <Button
              color="red"
              loading={cancelPayout.isPending}
              disabled={cancelReason.trim().length < 3}
              onClick={submitCancel}
            >
              {payout.status === "paid"
                ? "Удалить ошибочную"
                : "Отменить заявку"}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

function toDateTimeLocal(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const localDate = new Date(
    date.getTime() - date.getTimezoneOffset() * 60_000,
  );
  return localDate.toISOString().slice(0, 16);
}
