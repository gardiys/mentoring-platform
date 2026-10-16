import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Radio,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type { ConsultationDetail, GoDetail } from "./workspaceApi";
import {
  useConsultationCommands,
  useGoCommands,
  useConfirmOpportunityPayment,
} from "./workspaceQueries";
import {
  isoToLocalDateTimeInput,
  localDateTimeInputToIso,
} from "../../utils/dateTimeInput";
import { formatRubles } from "../../utils/money";
import {
  stageLabels,
  opportunityDate,
  consultationTypeLabels,
} from "./workspaceLabels";

const stageColors: Record<string, string> = {
  new: "blue",
  review: "blue",
  awaiting_payment: "yellow",
  awaiting_student: "yellow",
  payment_review: "red",
  needs_schedule: "orange",
  scheduled: "cyan",
  needs_completion: "red",
  expired: "red",
  needs_mentor: "orange",
  offer_review: "orange",
  completed: "green",
  enrolled: "green",
  active: "green",
  cancelled: "gray",
  closed: "gray",
};

export function OpportunityStage({ stage }: { stage: string }) {
  return (
    <Badge color={stageColors[stage] ?? "gray"}>
      {stageLabels[stage] ?? "Заявка"}
    </Badge>
  );
}

export function OpportunityContacts({
  student,
}: {
  student: ConsultationDetail["student"];
}) {
  return (
    <Stack gap="xs">
      <Title order={3}>
        {student.first_name} {student.last_name}
      </Title>
      <Group gap="xs">
        {student.telegram_username && (
          <Button
            component="a"
            size="xs"
            variant="light"
            target="_blank"
            rel="noreferrer"
            href={`https://t.me/${encodeURIComponent(student.telegram_username.replace(/^@/, ""))}`}
          >
            Написать в Telegram
          </Button>
        )}
        <Button
          size="xs"
          variant="subtle"
          component={Link}
          to={`/admin/students/${student.id}/edit`}
        >
          Профиль ученика
        </Button>
      </Group>
      {student.email && (
        <Group gap="xs">
          <Text size="sm" style={{ overflowWrap: "anywhere" }}>
            {student.email}
          </Text>
          <Button
            size="compact-xs"
            variant="subtle"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(student.email!);
                notifications.show({ message: "Email скопирован" });
              } catch {
                notifications.show({
                  color: "red",
                  message: "Не удалось скопировать email",
                });
              }
            }}
          >
            Скопировать email
          </Button>
        </Group>
      )}
    </Stack>
  );
}

function InternalNote({
  value,
  save,
  pending,
}: {
  value: string | null;
  save: (value: string) => void;
  pending: boolean;
}) {
  const [note, setNote] = useState(value ?? "");
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Textarea
          label="Внутренняя заметка"
          description="Видят только администраторы"
          maxLength={5000}
          value={note}
          onChange={(event) => setNote(event.currentTarget.value)}
        />
        <Button
          variant="light"
          loading={pending}
          disabled={note === (value ?? "")}
          onClick={() => save(note)}
        >
          Сохранить заметку
        </Button>
      </Stack>
    </Card>
  );
}

function History({ items }: { items: ConsultationDetail["history"] }) {
  const labels: Record<string, string> = {
    approve: "Заявка одобрена",
    reject: "Заявка отклонена",
    mentor: "Ментор изменён",
    schedule: "Время встречи сохранено",
    complete: "Консультация завершена",
    summary: "Итог исправлен",
    cancel: "Заявка отменена",
    "internal-note": "Внутренняя заметка изменена",
    payment: "Оплата подтверждена",
    extend: "Условия продлены",
  };
  return (
    <Stack gap="xs">
      <Title order={4}>История</Title>
      {items.map((event, index) => (
        <Card withBorder key={event.id ?? `${event.created_at}-${index}`}>
          <Text size="sm">
            {opportunityDate(event.created_at)} ·{" "}
            {event.actor_name ?? "Система"}
          </Text>
          <Text>
            {event.comment ||
              labels[String(event.snapshot?.action)] ||
              "Заявка создана"}
          </Text>
        </Card>
      ))}
    </Stack>
  );
}

function StudentMessages({
  note,
  history,
}: {
  note: string | null;
  history: ConsultationDetail["history"];
}) {
  const messages = history.filter(
    (event) =>
      event.comment &&
      ["approve", "reject", "cancel", "extend"].includes(
        String(event.snapshot?.action),
      ),
  );
  if (!note && !messages.length) return null;
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Title order={4}>Сообщения выпускнику</Title>
        <Text size="xs" c="dimmed">
          Видит выпускник
        </Text>
        {messages.length ? (
          messages.map((event, index) => (
            <div key={event.id ?? index}>
              <Text c="dimmed" size="xs">
                {opportunityDate(event.created_at)}
              </Text>
              <Text style={{ whiteSpace: "pre-wrap" }}>{event.comment}</Text>
            </div>
          ))
        ) : (
          <Text style={{ whiteSpace: "pre-wrap" }}>{note}</Text>
        )}
      </Stack>
    </Card>
  );
}

function ReasonDialog({
  opened,
  title,
  paid,
  reason,
  setReason,
  refund,
  setRefund,
  loading,
  close,
  submit,
}: {
  opened: boolean;
  title: string;
  paid: boolean;
  reason: string;
  setReason: (value: string) => void;
  refund: string | null;
  setRefund: (value: string) => void;
  loading: boolean;
  close: () => void;
  submit: () => void;
}) {
  return (
    <Modal opened={opened} onClose={close} title={title} centered>
      <Stack>
        <Textarea
          label="Причина для выпускника"
          description="Причину увидит выпускник. Не менее 10 символов"
          minRows={3}
          maxLength={2000}
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
        {paid && (
          <Radio.Group
            label="Возврат оплаты"
            description="Возврат оформляется вручную вне платформы"
            value={refund ?? ""}
            onChange={setRefund}
            required
          >
            <Stack gap="xs" mt="xs">
              <Radio value="yes" label="Нужен возврат денег" />
              <Radio value="no" label="Без возврата" />
            </Stack>
          </Radio.Group>
        )}
        <Button
          color="red"
          loading={loading}
          disabled={reason.trim().length < 10 || (paid && !refund)}
          onClick={submit}
        >
          Подтвердить решение
        </Button>
      </Stack>
    </Modal>
  );
}

export function ConsultationPanel({ item }: { item: ConsultationDetail }) {
  const actions = useConsultationCommands(item.id);
  const confirm = useConfirmOpportunityPayment();
  const [mentor, setMentor] = useState(item.mentor?.id ?? null);
  const [scheduled, setScheduled] = useState(
    isoToLocalDateTimeInput(item.scheduled_at),
  );
  const [heldAt, setHeldAt] = useState(
    isoToLocalDateTimeInput(item.scheduled_at ?? new Date().toISOString()),
  );
  const [summary, setSummary] = useState(item.written_summary ?? "");
  const [message, setMessage] = useState(item.admin_note ?? "");
  const [showComplete, setShowComplete] = useState(
    item.stage === "needs_completion",
  );
  const [editSummary, setEditSummary] = useState(false);
  const [mode, setMode] = useState<"reject" | "cancel" | null>(null);
  const [reason, setReason] = useState("");
  const [refund, setRefund] = useState<string | null>(null);
  const length = summary.trim().length;
  const completing =
    ["needs_schedule", "scheduled", "needs_completion"].includes(item.stage) &&
    (showComplete || item.stage === "needs_completion");
  const showSummaryForm =
    completing || (item.stage === "completed" && editSummary);
  const scheduledIso = localDateTimeInputToIso(scheduled);
  const heldIso = localDateTimeInputToIso(heldAt);
  const openDecision = (value: "reject" | "cancel") => {
    setReason("");
    setRefund(null);
    setMode(value);
  };
  const canChangeMentor = [
    "new",
    "awaiting_payment",
    "payment_review",
    "needs_schedule",
    "scheduled",
    "needs_completion",
  ].includes(item.stage);
  const paymentLabels: Record<string, string> = {
    pending: "Ожидает оплаты",
    approved: "Подтверждена",
    manual_review: "Требует ручной проверки",
    revoked: "Ссылка отозвана",
    failed: "Ошибка оплаты",
    cancelled: "Отменена",
  };
  const primaryAction =
    item.stage === "new" ? (
      <Button
        loading={actions.approve.isPending}
        disabled={
          !mentor ||
          !(item.available_mentors ?? []).some((value) => value.id === mentor)
        }
        onClick={() =>
          mentor &&
          actions.approve.mutate({
            mentor_id: mentor,
            message_to_student: message || null,
          })
        }
      >
        Одобрить и выставить счёт
      </Button>
    ) : item.stage === "payment_review" ? (
      <Button
        loading={confirm.isPending}
        onClick={() => {
          if (
            window.confirm(
              "Подтвердить поступление оплаты за эту консультацию?",
            )
          )
            confirm.mutate(item.last_payment!.attempt_id);
        }}
      >
        Подтвердить оплату
      </Button>
    ) : showSummaryForm ? (
      <Button
        loading={
          editSummary ? actions.summary.isPending : actions.complete.isPending
        }
        disabled={length < 10 || (!editSummary && !heldIso)}
        onClick={() => {
          if (editSummary)
            actions.summary.mutate(
              { written_summary: summary.trim() },
              { onSuccess: () => setEditSummary(false) },
            );
          else if (heldIso)
            actions.complete.mutate(
              {
                written_summary: summary.trim(),
                held_at: heldIso,
              },
              { onSuccess: () => setShowComplete(false) },
            );
        }}
      >
        {editSummary ? "Сохранить исправленный итог" : "Завершить консультацию"}
      </Button>
    ) : ["needs_schedule", "scheduled"].includes(item.stage) ? (
      <Button
        disabled={!scheduledIso}
        loading={actions.schedule.isPending}
        onClick={() =>
          scheduledIso &&
          actions.schedule.mutate({ scheduled_at: scheduledIso })
        }
      >
        {item.stage === "scheduled" ? "Перенести" : "Назначить время"}
      </Button>
    ) : null;
  return (
    <Stack gap="lg">
      <OpportunityContacts student={item.student} />
      <Group>
        <OpportunityStage stage={item.stage} />
        <Text fw={700}>{item.next_action}</Text>
      </Group>
      <Text size="sm" c="dimmed">
        Создана {opportunityDate(item.created_at)} · оплачена{" "}
        {opportunityDate(item.paid_at)}
      </Text>
      {item.scheduled_at && (
        <Text fw={600}>Встреча: {opportunityDate(item.scheduled_at)}</Text>
      )}
      <Text fw={600}>{consultationTypeLabels[item.consultation_type]}</Text>
      <Text style={{ whiteSpace: "pre-wrap" }}>{item.brief}</Text>
      {item.requested_mentor_known && (
        <Text size="sm" c="dimmed">
          Ментор из запроса:{" "}
          {item.requested_mentor
            ? `${item.requested_mentor.first_name} ${item.requested_mentor.last_name ?? ""}`
            : "любой доступный"}
        </Text>
      )}
      <Text>
        {formatRubles(item.price_kopecks)} · ментору{" "}
        {formatRubles(item.mentor_reward_kopecks)} · {item.duration_minutes} мин
      </Text>
      <Text>
        Ментор:{" "}
        {item.mentor
          ? `${item.mentor.first_name} ${item.mentor.last_name ?? ""} ${item.mentor.telegram_username ? `@${item.mentor.telegram_username}` : ""}`
          : "не назначен"}
      </Text>
      {canChangeMentor && (
        <Group align="flex-end" wrap="wrap">
          <Select
            style={{ flex: "1 1 220px" }}
            label="Ментор консультации"
            description="Перед выставлением счёта выберите доступного ментора"
            data={(item.available_mentors ?? []).map((value) => ({
              value: value.id,
              label: `${value.first_name} ${value.last_name ?? ""}`,
            }))}
            value={mentor}
            onChange={setMentor}
          />
          {item.stage !== "new" && (
            <Button
              variant="light"
              loading={actions.mentor.isPending}
              disabled={!mentor || mentor === item.mentor?.id}
              onClick={() =>
                mentor && actions.mentor.mutate({ mentor_id: mentor })
              }
            >
              Сменить ментора
            </Button>
          )}
        </Group>
      )}
      {item.stage === "new" && (
        <Stack>
          {(item.available_mentors ?? []).length === 0 && (
            <Alert color="yellow">
              Нет доступных менторов. Включите менторов-консультантов в{" "}
              <Link to="/admin/opportunities/settings">настройках</Link>.
            </Alert>
          )}
          <Textarea
            label="Сообщение выпускнику"
            description="Выпускник увидит сообщение после одобрения"
            maxLength={5000}
            value={message}
            onChange={(event) => setMessage(event.currentTarget.value)}
          />

          <Button
            color="red"
            variant="light"
            onClick={() => openDecision("reject")}
          >
            Отклонить
          </Button>
        </Stack>
      )}
      <Card withBorder>
        <Stack gap="xs">
          <Title order={4}>Оплата</Title>
          <Text>
            {item.last_payment
              ? (paymentLabels[item.last_payment.status] ?? "Проверяется")
              : "Выпускник ещё не открывал оплату"}
          </Text>
          {item.last_payment && (
            <Text size="sm" c="dimmed">
              Попытка от {opportunityDate(item.last_payment.created_at)}
            </Text>
          )}
          {item.last_payment?.status === "manual_review" && (
            <Alert color="red">
              Проверьте поступление денег перед подтверждением
            </Alert>
          )}
        </Stack>
      </Card>
      {["needs_schedule", "scheduled"].includes(item.stage) &&
        !showComplete && (
          <Stack>
            <TextInput
              type="datetime-local"
              label="Дата и время встречи"
              description={`Часовой пояс: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`}
              value={scheduled}
              onChange={(event) => setScheduled(event.currentTarget.value)}
            />

            <Button variant="light" onClick={() => setShowComplete(true)}>
              {item.stage === "scheduled"
                ? "Завершить"
                : "Отметить проведённой"}
            </Button>
          </Stack>
        )}
      {showSummaryForm && (
        <Card withBorder>
          <Stack>
            <Textarea
              label="Итог для выпускника"
              description="Видит выпускник после завершения. Рекомендации и план дальнейших действий"
              minRows={4}
              maxLength={10000}
              value={summary}
              onChange={(event) => setSummary(event.currentTarget.value)}
            />
            <Text size="xs" c="dimmed">
              {summary.length} / 10 000
            </Text>
            {length < 10 && (
              <Text size="xs" c="dimmed">
                Ещё {10 - length} символов, чтобы завершить
              </Text>
            )}
            {!editSummary && (
              <TextInput
                type="datetime-local"
                label="Когда прошла встреча"
                description={`Часовой пояс: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`}
                value={heldAt}
                onChange={(event) => setHeldAt(event.currentTarget.value)}
              />
            )}

            {!editSummary && item.stage !== "needs_completion" && (
              <Button variant="subtle" onClick={() => setShowComplete(false)}>
                К назначению времени
              </Button>
            )}
          </Stack>
        </Card>
      )}
      {item.stage === "completed" && !editSummary && (
        <Card withBorder>
          <Stack>
            <Title order={4}>Итог для выпускника</Title>
            <Text style={{ whiteSpace: "pre-wrap" }}>
              {item.written_summary}
            </Text>
            <Button
              variant="light"
              onClick={() => {
                setSummary(item.written_summary ?? "");
                setEditSummary(true);
              }}
            >
              Исправить итог
            </Button>
          </Stack>
        </Card>
      )}
      {[
        "awaiting_payment",
        "payment_review",
        "needs_schedule",
        "scheduled",
        "needs_completion",
      ].includes(item.stage) && (
        <Button
          color="red"
          variant="light"
          disabled={confirm.isPending}
          onClick={() => openDecision("cancel")}
        >
          {item.stage === "needs_completion"
            ? "Не состоялась"
            : "Отменить заявку"}
        </Button>
      )}
      {item.stage === "cancelled" && item.paid_at && (
        <Alert color="gray">
          {item.refund_required
            ? "Нужен ручной возврат оплаты"
            : "Отменена без возврата оплаты"}
        </Alert>
      )}
      <StudentMessages note={item.admin_note} history={item.history} />
      <InternalNote
        value={item.internal_note}
        save={(value) => actions.note.mutate({ internal_note: value || null })}
        pending={actions.note.isPending}
      />
      <History items={item.history} />
      {primaryAction && <PrimaryAction>{primaryAction}</PrimaryAction>}
      <ReasonDialog
        opened={mode !== null}
        title={
          mode === "reject" ? "Отклонить консультацию" : "Отменить консультацию"
        }
        paid={mode === "cancel" && !!item.paid_at}
        reason={reason}
        setReason={setReason}
        refund={refund}
        setRefund={setRefund}
        loading={actions.reject.isPending || actions.cancel.isPending}
        close={() => setMode(null)}
        submit={() => {
          if (mode === "reject")
            actions.reject.mutate(
              { reason: reason.trim() },
              { onSuccess: () => setMode(null) },
            );
          else
            actions.cancel.mutate(
              {
                reason: reason.trim(),
                refund_required: item.paid_at ? refund === "yes" : false,
              },
              { onSuccess: () => setMode(null) },
            );
        }}
      />
    </Stack>
  );
}

export function GoPanel({ item }: { item: GoDetail }) {
  const actions = useGoCommands(item.id);
  const [message, setMessage] = useState(item.admin_note ?? "");
  const [mode, setMode] = useState<"reject" | "cancel" | null>(null);
  const [reason, setReason] = useState("");
  const primaryAction =
    item.stage === "new" ? (
      <Button
        loading={actions.approve.isPending}
        onClick={() =>
          actions.approve.mutate({ message_to_student: message || null })
        }
      >
        Одобрить
      </Button>
    ) : item.stage === "expired" ? (
      <Button
        loading={actions.extend.isPending}
        disabled={!!item.payment_block_reason}
        onClick={() => actions.extend.mutate()}
      >
        Продлить на 14 дней
      </Button>
    ) : null;
  return (
    <Stack gap="lg">
      <OpportunityContacts student={item.student} />
      <Group>
        <OpportunityStage stage={item.stage} />
        <Text fw={700}>{item.next_action}</Text>
      </Group>
      <Text size="sm" c="dimmed">
        Создана {opportunityDate(item.created_at)}
      </Text>
      <Text style={{ whiteSpace: "pre-wrap" }}>{item.motivation}</Text>
      <Text>
        {formatRubles(item.upfront_price_kopecks)} + {item.success_fee_percent}%
        после оффера
      </Text>
      {item.terms_expires_at && (
        <Text fw={600}>
          Условия действуют до {opportunityDate(item.terms_expires_at)}
        </Text>
      )}
      {item.stage === "new" && (
        <Stack>
          <Textarea
            label="Сообщение выпускнику"
            maxLength={5000}
            value={message}
            onChange={(event) => setMessage(event.currentTarget.value)}
          />

          <Button
            color="red"
            variant="light"
            onClick={() => {
              setReason("");
              setMode("reject");
            }}
          >
            Отклонить
          </Button>
        </Stack>
      )}
      {item.payment_block_reason &&
        ["expired", "awaiting_student"].includes(item.stage) && (
          <Alert color="yellow">{item.payment_block_reason}</Alert>
        )}

      {["expired", "awaiting_student"].includes(item.stage) && (
        <Button
          color="red"
          variant="light"
          disabled={!!item.payment_block_reason}
          onClick={() => {
            setReason("");
            setMode("cancel");
          }}
        >
          Отменить заявку
        </Button>
      )}
      {item.stage === "enrolled" && (
        <Alert color="green">
          Назначьте Go-ментора в{" "}
          <Link to={`/admin/students/${item.student.id}/edit`}>
            профиле ученика
          </Link>
        </Alert>
      )}
      <StudentMessages note={item.admin_note} history={item.history} />
      <InternalNote
        value={item.internal_note}
        save={(value) => actions.note.mutate({ internal_note: value || null })}
        pending={actions.note.isPending}
      />
      <History items={item.history} />
      {primaryAction && <PrimaryAction>{primaryAction}</PrimaryAction>}
      <ReasonDialog
        opened={mode !== null}
        title={
          mode === "reject" ? "Отклонить заявку на Go" : "Отменить заявку на Go"
        }
        paid={false}
        reason={reason}
        setReason={setReason}
        refund={null}
        setRefund={() => undefined}
        loading={actions.reject.isPending || actions.cancel.isPending}
        close={() => setMode(null)}
        submit={() => {
          if (mode === "reject")
            actions.reject.mutate(
              { reason: reason.trim() },
              { onSuccess: () => setMode(null) },
            );
          else
            actions.cancel.mutate(
              { reason: reason.trim() },
              { onSuccess: () => setMode(null) },
            );
        }}
      />
    </Stack>
  );
}

export function PrimaryAction({ children }: { children: ReactNode }) {
  return (
    <Stack
      role="group"
      aria-label="Основное действие"
      gap={0}
      style={{
        position: "sticky",
        bottom: 0,
        zIndex: 5,
        background: "var(--mantine-color-body)",
        borderTop: "1px solid var(--mantine-color-default-border)",
        padding:
          "var(--mantine-spacing-xs) 0 calc(var(--mantine-spacing-xs) + env(safe-area-inset-bottom, 0px))",
      }}
    >
      {children}
    </Stack>
  );
}
