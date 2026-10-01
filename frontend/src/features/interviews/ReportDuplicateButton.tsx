import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Menu,
  Modal,
  Stack,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../../api/endpoints";

export function ReportDuplicateButton({
  cardId,
  question,
}: {
  cardId: string;
  question: string;
}) {
  const [opened, setOpened] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const report = useMutation({
    mutationFn: () => api.reportInterviewCardDuplicate(cardId),
    onSuccess: (result) => {
      setOpened(false);
      notifications.show({
        color: "green",
        message:
          result.status === "pending"
            ? "Сообщение о дубле отправлено администратору."
            : "Администратор уже рассмотрел ваше сообщение об этой карточке.",
      });
    },
  });
  return (
    <>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon
            ref={trigger}
            size={44}
            variant="subtle"
            color="gray"
            aria-label={`Действия с вопросом: ${question}`}
            title="Действия с вопросом"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <circle cx="5" cy="12" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="19" cy="12" r="2" />
            </svg>
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            disabled={report.isSuccess}
            onClick={() => {
              report.reset();
              setOpened(true);
            }}
          >
            {report.isSuccess
              ? report.data.status === "pending"
                ? "Сообщение отправлено"
                : "Уже рассмотрено"
              : "Сообщить о дубле"}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      <Modal
        opened={opened}
        onClose={() => {
          if (!report.isPending) setOpened(false);
        }}
        title="Сообщить о дубликате?"
        centered
        closeOnClickOutside={!report.isPending}
        closeOnEscape={!report.isPending}
        withCloseButton={!report.isPending}
        closeButtonProps={{ "aria-label": "Закрыть подтверждение" }}
        onExitTransitionEnd={() => trigger.current?.focus()}
      >
        <Stack>
          <Text fw={600} lineClamp={4}>
            {question}
          </Text>
          <Text size="sm">
            Администратор проверит, повторяет ли этот вопрос другую карточку, и
            при необходимости объединит их. Отправить сообщение о возможном
            дубле?
          </Text>
          {report.isError && (
            <Alert color="red" role="alert">
              {report.error.message}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button
              variant="default"
              data-autofocus
              disabled={report.isPending}
              onClick={() => setOpened(false)}
            >
              Отмена
            </Button>
            <Button
              loading={report.isPending}
              disabled={report.isPending}
              onClick={() => report.mutate()}
            >
              Отправить сообщение
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
