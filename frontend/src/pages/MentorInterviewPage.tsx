import {
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useCreateMentorInterviewFeedback,
  useMentorInterview,
} from "../features/mentor/queries";
import type {
  InterviewCatalogCommentRead,
  InterviewProcessStageRead,
  InterviewStageType,
} from "../types/api";

const stageLabels: Record<InterviewStageType, string> = {
  screening: "Скрининг",
  technical_screening: "Технический скрининг",
  technical_interview: "Техническое интервью",
  system_design: "Системный дизайн",
  final_interview: "Финальное интервью",
  other: "Иное",
};

function MentorStage({
  studentId,
  processId,
  stage,
  comments,
}: {
  studentId: string;
  processId: string;
  stage: InterviewProcessStageRead;
  comments: InterviewCatalogCommentRead[];
}) {
  const [feedback, setFeedback] = useState("");
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [isMediaLoading, setIsMediaLoading] = useState(false);
  const mutation = useCreateMentorInterviewFeedback(studentId, processId);

  const openMedia = async () => {
    if (mediaUrl) {
      setMediaUrl(null);
      return;
    }
    setIsMediaLoading(true);
    try {
      setMediaUrl(await api.interviewCatalogStageMedia(stage.id));
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    } finally {
      setIsMediaLoading(false);
    }
  };

  const handleMediaError = () => {
    setMediaUrl(null);
    notifications.show({
      color: "yellow",
      message:
        "Не удалось воспроизвести запись. Попробуйте открыть её ещё раз.",
    });
  };

  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between">
          <Badge>{stageLabels[stage.stage_type]}</Badge>
          <Text size="sm" c="dimmed">
            {new Date(stage.scheduled_at).toLocaleString("ru-RU")}
          </Text>
        </Group>
        {stage.description && (
          <Text style={{ whiteSpace: "pre-wrap" }}>{stage.description}</Text>
        )}
        {stage.media && (
          <Stack gap="xs">
            <Button
              variant="light"
              loading={isMediaLoading}
              onClick={() => void openMedia()}
            >
              {mediaUrl
                ? "Скрыть запись"
                : stage.media.content_type.startsWith("video/")
                  ? "Посмотреть запись"
                  : "Прослушать запись"}
            </Button>
            {mediaUrl && stage.media.content_type.startsWith("video/") && (
              <video
                controls
                controlsList="nodownload noremoteplayback"
                disablePictureInPicture
                preload="metadata"
                src={mediaUrl}
                onError={handleMediaError}
                onContextMenu={(event) => event.preventDefault()}
                style={{ width: "100%", maxHeight: 600, borderRadius: 12 }}
              />
            )}
            {mediaUrl && stage.media.content_type.startsWith("audio/") && (
              <audio
                controls
                controlsList="nodownload noremoteplayback"
                preload="metadata"
                src={mediaUrl}
                onError={handleMediaError}
                style={{ width: "100%" }}
              />
            )}
          </Stack>
        )}
        {stage.attachments.map((attachment) => (
          <Group key={attachment.id} justify="space-between">
            <Text size="sm">{attachment.filename}</Text>
            <Button
              size="xs"
              variant="subtle"
              onClick={() =>
                void api
                  .openMentorInterviewAttachment(
                    studentId,
                    processId,
                    stage.id,
                    attachment.id,
                  )
                  .then((url) =>
                    window.open(url, "_blank", "noopener,noreferrer"),
                  )
              }
            >
              Открыть
            </Button>
          </Group>
        ))}

        {comments.length > 0 && (
          <Stack gap="xs">
            <Text fw={700}>Обратная связь</Text>
            {comments.map((comment) => (
              <Card
                key={comment.id}
                withBorder
                style={
                  comment.is_mentor_feedback
                    ? {
                        borderColor: "var(--mantine-color-blue-6)",
                        boxShadow: "inset 3px 0 var(--mantine-color-blue-6)",
                      }
                    : undefined
                }
              >
                <Text style={{ whiteSpace: "pre-wrap" }}>{comment.body}</Text>
                <Text size="xs" c="dimmed" mt="xs">
                  {comment.author.name}
                  {comment.is_mentor_feedback ? " · фидбек ментора" : ""}
                </Text>
              </Card>
            ))}
          </Stack>
        )}
        <Textarea
          label="Фидбек по этапу"
          minRows={3}
          value={feedback}
          onChange={(event) => setFeedback(event.currentTarget.value)}
        />
        <Button
          disabled={!feedback.trim()}
          loading={mutation.isPending}
          onClick={() =>
            mutation.mutate(
              { stageId: stage.id, body: feedback.trim() },
              {
                onSuccess: () => {
                  setFeedback("");
                  notifications.show({
                    color: "green",
                    message: "Фидбек добавлен",
                  });
                },
                onError: (error) =>
                  notifications.show({ color: "red", message: error.message }),
              },
            )
          }
        >
          Опубликовать фидбек
        </Button>
      </Stack>
    </Card>
  );
}

export function MentorInterviewPage() {
  const { studentId = "", processId = "" } = useParams();
  const query = useMentorInterview(studentId, processId);
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;
  const { process, feedback } = query.data;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow={`Собеседования · ${process.track_title}`}
        title={process.company_name}
        description={`Этапов: ${process.stage_count}. Здесь можно посмотреть материалы и оставить менторский фидбек.`}
      />
      <Card withBorder>
        <Stack gap="xs">
          <Group>
            <Badge
              color={
                process.status === "offer"
                  ? "green"
                  : process.status === "closed"
                    ? "gray"
                    : "blue"
              }
            >
              {process.status === "offer"
                ? "Получен оффер"
                : process.status === "closed"
                  ? "Трек завершён"
                  : "Активный трек"}
            </Badge>
            <Text size="sm" c="dimmed">
              Создан {new Date(process.created_at).toLocaleDateString("ru-RU")}
            </Text>
          </Group>
          {process.recruiter_telegram_usernames.length > 0 && (
            <Text>
              Рекрутеры:{" "}
              {process.recruiter_telegram_usernames
                .map((username) => `@${username}`)
                .join(", ")}
            </Text>
          )}
          {process.close_reason && (
            <Text style={{ whiteSpace: "pre-wrap" }}>
              Причина завершения: {process.close_reason}
            </Text>
          )}
          {process.offer && (
            <Button
              variant="light"
              w="fit-content"
              onClick={() =>
                void api
                  .openMentorInterviewOffer(studentId, processId)
                  .then((url) =>
                    window.open(url, "_blank", "noopener,noreferrer"),
                  )
                  .catch((error: unknown) =>
                    notifications.show({
                      color: "red",
                      message:
                        error instanceof Error
                          ? error.message
                          : "Не удалось открыть файл оффера",
                    }),
                  )
              }
            >
              Открыть файл оффера · {process.offer.filename}
            </Button>
          )}
        </Stack>
      </Card>
      {process.stages.length === 0 ? (
        <Text c="dimmed">В этом треке пока нет этапов.</Text>
      ) : (
        process.stages.map((stage) => (
          <MentorStage
            key={stage.id}
            studentId={studentId}
            processId={processId}
            stage={stage}
            comments={
              feedback.find((item) => item.stage_id === stage.id)?.comments ??
              []
            }
          />
        ))
      )}
    </Stack>
  );
}
