import { Button } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/endpoints";

export function ReportDuplicateButton({ cardId }: { cardId: string }) {
  const report = useMutation({
    mutationFn: () => api.reportInterviewCardDuplicate(cardId),
    onSuccess: (result) =>
      notifications.show({
        color: "green",
        message:
          result.status === "pending"
            ? "Сообщение о дубле отправлено администратору."
            : "Администратор уже рассмотрел ваше сообщение об этой карточке.",
      }),
    onError: (error: Error) =>
      notifications.show({ color: "red", message: error.message }),
  });
  return (
    <Button
      size="compact-sm"
      variant="subtle"
      color="gray"
      loading={report.isPending}
      disabled={report.isSuccess}
      onClick={() => report.mutate()}
    >
      {report.isSuccess
        ? report.data.status === "pending"
          ? "Сообщение отправлено"
          : "Уже рассмотрено"
        : "Сообщить о дубле"}
    </Button>
  );
}
