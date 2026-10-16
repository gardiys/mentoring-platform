import { useMutation, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";

import { opportunityKeys } from "./queries";
import { workspaceApi } from "./workspaceApi";

function useWorkspaceAction<T>(
  mutationFn: (body: T) => Promise<unknown>,
  message: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: T) => mutationFn(body),
    onSuccess: async () => {
      notifications.show({ color: "green", message });
      await queryClient.invalidateQueries({ queryKey: opportunityKeys.all });
    },
    onError: (error: Error) =>
      notifications.show({ color: "red", message: error.message }),
  });
}

export function useConsultationCommands(id: string) {
  const approve = useWorkspaceAction(
    workspaceApi.approveConsultation.bind(null, id),
    "Консультация одобрена — можно оплатить",
  );
  const reject = useWorkspaceAction(
    workspaceApi.rejectConsultation.bind(null, id),
    "Заявка отклонена",
  );
  const mentor = useWorkspaceAction(
    workspaceApi.mentorConsultation.bind(null, id),
    "Ментор назначен",
  );
  const schedule = useWorkspaceAction(
    workspaceApi.scheduleConsultation.bind(null, id),
    "Время встречи сохранено",
  );
  const complete = useWorkspaceAction(
    workspaceApi.completeConsultation.bind(null, id),
    "Консультация завершена, итог сохранён",
  );
  const summary = useWorkspaceAction(
    workspaceApi.summaryConsultation.bind(null, id),
    "Итог исправлен",
  );
  const cancel = useWorkspaceAction(
    workspaceApi.cancelConsultation.bind(null, id),
    "Консультация отменена",
  );
  const note = useWorkspaceAction(
    workspaceApi.noteConsultation.bind(null, id),
    "Внутренняя заметка сохранена",
  );
  return { approve, reject, mentor, schedule, complete, summary, cancel, note };
}

export function useGoCommands(id: string) {
  const approve = useWorkspaceAction(
    workspaceApi.approveGo.bind(null, id),
    "Заявка на Go одобрена",
  );
  const reject = useWorkspaceAction(
    workspaceApi.rejectGo.bind(null, id),
    "Заявка отклонена",
  );
  const cancel = useWorkspaceAction(
    workspaceApi.cancelGo.bind(null, id),
    "Заявка отменена",
  );
  const extend = useWorkspaceAction<void>(
    () => workspaceApi.extendGo(id),
    "Условия продлены на 14 дней",
  );
  const note = useWorkspaceAction(
    workspaceApi.noteGo.bind(null, id),
    "Внутренняя заметка сохранена",
  );
  return { approve, reject, cancel, extend, note };
}

export function useConfirmOpportunityPayment() {
  return useWorkspaceAction(workspaceApi.confirmPayment, "Оплата проверена");
}
