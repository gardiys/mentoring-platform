import type { ConsultationDetail } from "./workspaceApi";

export const consultationTypeLabels: Record<
  ConsultationDetail["consultation_type"],
  string
> = {
  free_topic: "Свободная тема",
  technical_mock: "Техническое мок-собеседование",
  legend_mock: "Мок-собеседование по легенде",
  resume_legend: "Составление резюме и легенды",
  system_design_mock: "Мок-собеседование по системному дизайну",
  work_task: "Помощь с рабочей задачей",
};

export const stageLabels: Record<string, string> = {
  new: "Новая заявка",
  review: "На рассмотрении",
  awaiting_payment: "Ждём оплату",
  awaiting_student: "Ждём выпускника",
  payment_review: "Проверить оплату",
  needs_schedule: "Назначить время",
  scheduled: "Запланирована",
  needs_completion: "Нужно закрыть",
  expired: "Условия истекли",
  needs_mentor: "Назначить ментора",
  offer_review: "Проверить оффер",
  completed: "Завершена",
  enrolled: "Зачислен",
  active: "Идёт программа",
  cancelled: "Отменена",
  closed: "Закрыта",
};
export function opportunityDate(value: string | null | undefined) {
  return value
    ? new Date(value).toLocaleString("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
}
