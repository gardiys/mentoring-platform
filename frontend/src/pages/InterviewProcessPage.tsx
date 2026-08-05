import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  Select,
  SimpleGrid,
  Stack,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, type UploadStatus } from "../api/client";
import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { UploadProgressPanel } from "../components/UploadProgressPanel";
import {
  useCancelInterviewOffer,
  useCreateInterviewStage,
  useDeleteInterviewStageAttachment,
  useInterviewProcess,
  useMarkInterviewOffer,
  useSetInterviewProcessOutcome,
  useSetInterviewProcessRecruiters,
  useStartInterviewStageAnalysis,
  useUploadInterviewStageMedia,
  useUploadInterviewStageAttachments,
} from "../features/interviews/journalQueries";
import type {
  InterviewProcessStageRead,
  InterviewStageType,
} from "../types/api";
import { AUDIO_MAX_BYTES, VIDEO_MAX_BYTES, mediaKind } from "../utils/media";
import { openExternalResource } from "../utils/openExternalResource";

const stageOptions = [
  { value: "screening", label: "Скрининг" },
  { value: "technical_screening", label: "Технический скрининг" },
  { value: "technical_interview", label: "Техническое интервью" },
  { value: "system_design", label: "Системный дизайн" },
  { value: "final_interview", label: "Финальное интервью" },
  { value: "other", label: "Иное" },
] satisfies { value: InterviewStageType; label: string }[];

const stageLabels = Object.fromEntries(
  stageOptions.map((option) => [option.value, option.label]),
) as Record<InterviewStageType, string>;

const OFFER_MAX_BYTES = 20 * 1024 * 1024;
const ATTACHMENT_MAX_BYTES = 50 * 1024 * 1024;

function dateTimeInputValue() {
  const date = new Date(Date.now() + 24 * 60 * 60 * 1000);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSize(value: number) {
  if (value <= 0) return "размер не указан";
  return value >= 1024 * 1024
    ? `${(value / 1024 / 1024).toFixed(1)} МБ`
    : `${Math.ceil(value / 1024)} КБ`;
}

async function downloadFile(request: Promise<string>, filename: string) {
  try {
    const url = await request;
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.click();
  } catch (error) {
    notifications.show({
      color: "red",
      message:
        error instanceof Error ? error.message : "Не удалось скачать файл",
    });
  }
}

async function openFile(request: Promise<string>) {
  try {
    await openExternalResource(request);
  } catch (error) {
    notifications.show({
      color: "red",
      message:
        error instanceof Error ? error.message : "Не удалось открыть файл",
    });
  }
}

function StageMedia({
  processId,
  stage,
}: {
  processId: string;
  stage: InterviewProcessStageRead;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [playerUrl, setPlayerUrl] = useState<string | null>(null);
  const [isPlayerLoading, setIsPlayerLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const uploadController = useRef<AbortController | null>(null);
  const mutation = useUploadInterviewStageMedia();
  const analysisMutation = useStartInterviewStageAnalysis();
  const storedMediaKind = stage.media
    ? mediaKind(stage.media.content_type, stage.media.filename)
    : null;

  useEffect(() => {
    setPlayerUrl(null);
  }, [stage.media?.filename, stage.media?.size]);

  useEffect(
    () => () => {
      uploadController.current?.abort();
    },
    [],
  );

  const togglePlayer = async () => {
    if (playerUrl) {
      setPlayerUrl(null);
      return;
    }
    setIsPlayerLoading(true);
    try {
      setPlayerUrl(await api.viewInterviewStageMedia(processId, stage.id));
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    } finally {
      setIsPlayerLoading(false);
    }
  };

  const upload = () => {
    const selectedMediaKind = file ? mediaKind(file.type, file.name) : null;
    if (!file || !selectedMediaKind) {
      notifications.show({
        color: "red",
        message: "Выберите аудио- или видеофайл",
      });
      return;
    }
    const maxBytes =
      selectedMediaKind === "video" ? VIDEO_MAX_BYTES : AUDIO_MAX_BYTES;
    if (file.size > maxBytes) {
      notifications.show({
        color: "red",
        message:
          selectedMediaKind === "video"
            ? "Видео должно быть не больше 2 ГБ"
            : "Аудио должно быть не больше 500 МБ",
      });
      return;
    }
    const controller = new AbortController();
    uploadController.current = controller;
    mutation.mutate(
      {
        processId,
        stageId: stage.id,
        file,
        signal: controller.signal,
        onProgress: (percent) =>
          setUploadStatus((current) =>
            current?.phase === "uploading" ? { ...current, percent } : current,
          ),
        onStatus: setUploadStatus,
      },
      {
        onSuccess: () => {
          setFile(null);
          notifications.show({ color: "green", message: "Запись сохранена" });
        },
        onError: (error) =>
          notifications.show({
            color:
              error instanceof ApiError && error.code === "request_aborted"
                ? "yellow"
                : "red",
            message: error.message,
          }),
        onSettled: () => {
          uploadController.current = null;
          setUploadStatus(null);
        },
      },
    );
  };

  return (
    <Stack gap="xs">
      {stage.media && (
        <>
          <Group justify="space-between" className="file-action-row">
            <Text size="sm" className="file-name">
              {stage.media.filename} · {formatSize(stage.media.size)}
            </Text>
            <Group gap="xs" className="file-actions">
              <Button
                size="xs"
                variant="light"
                loading={isPlayerLoading}
                onClick={() => void togglePlayer()}
              >
                {playerUrl
                  ? "Скрыть запись"
                  : storedMediaKind === "video"
                    ? "Посмотреть запись"
                    : "Прослушать запись"}
              </Button>
              <Button
                size="xs"
                variant="subtle"
                onClick={() =>
                  void downloadFile(
                    api.downloadInterviewStageMedia(processId, stage.id),
                    stage.media!.filename,
                  )
                }
              >
                Скачать
              </Button>
            </Group>
          </Group>
          {playerUrl && storedMediaKind === "video" && (
            <video
              controls
              preload="metadata"
              src={playerUrl}
              onError={() => {
                setPlayerUrl(null);
                notifications.show({
                  color: "yellow",
                  message:
                    "Не удалось воспроизвести видео. Нажмите «Посмотреть запись», чтобы повторить.",
                });
              }}
              style={{ width: "100%", maxHeight: 520, borderRadius: 12 }}
            >
              Ваш браузер не поддерживает воспроизведение видео.
            </video>
          )}
          {playerUrl && storedMediaKind === "audio" && (
            <audio
              controls
              preload="metadata"
              src={playerUrl}
              onError={() => {
                setPlayerUrl(null);
                notifications.show({
                  color: "yellow",
                  message:
                    "Не удалось воспроизвести аудио. Нажмите «Прослушать запись», чтобы повторить.",
                });
              }}
              style={{ width: "100%" }}
            >
              Ваш браузер не поддерживает воспроизведение аудио.
            </audio>
          )}
          <Group justify="flex-end">
            {stage.ai_analysis_id ? (
              <Button
                component={Link}
                to={`/interviews/analysis/${stage.ai_analysis_id}`}
                variant="light"
              >
                {stage.ai_analysis_status === "ready"
                  ? "Открыть AI-разбор"
                  : stage.ai_analysis_status === "failed"
                    ? "Открыть ошибку AI-разбора"
                    : stage.ai_analysis_status === "uploaded"
                      ? "AI-разбор ожидает запуска"
                      : "AI-разбор выполняется"}
              </Button>
            ) : stage.ai_analysis_requested_at ? (
              <Button disabled variant="light">
                AI-разбор уже запрашивался
              </Button>
            ) : (
              <Button
                loading={analysisMutation.isPending}
                onClick={() => {
                  if (
                    !window.confirm(
                      "Запустить AI-разбор? Для одного собеседования это можно сделать только один раз.",
                    )
                  )
                    return;
                  analysisMutation.mutate(
                    { processId, stageId: stage.id },
                    {
                      onSuccess: () =>
                        notifications.show({
                          color: "green",
                          message: "AI-разбор запущен",
                        }),
                      onError: (error) =>
                        notifications.show({
                          color: "red",
                          message: error.message,
                        }),
                    },
                  );
                }}
              >
                Разобрать с AI
              </Button>
            )}
          </Group>
        </>
      )}
      {!stage.ai_analysis_requested_at && (
        <Stack gap="xs">
          <Group align="flex-end" className="upload-control-row">
            <FileInput
              flex={1}
              label={stage.media ? "Заменить запись" : "Добавить запись"}
              placeholder="Аудио или видео"
              description="Видео до 2 ГБ, аудио до 500 МБ"
              accept="audio/*,video/*"
              value={file}
              onChange={setFile}
              disabled={mutation.isPending}
              clearable
            />
            <Button
              variant="light"
              disabled={!file}
              loading={mutation.isPending}
              onClick={upload}
            >
              Загрузить
            </Button>
          </Group>
          {mutation.isPending && uploadStatus && (
            <UploadProgressPanel
              status={uploadStatus}
              onCancel={() => uploadController.current?.abort()}
            />
          )}
        </Stack>
      )}
    </Stack>
  );
}

function StageAttachments({
  processId,
  stage,
}: {
  processId: string;
  stage: InterviewProcessStageRead;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const [uploadDetail, setUploadDetail] = useState<string | null>(null);
  const uploadController = useRef<AbortController | null>(null);
  const uploadMutation = useUploadInterviewStageAttachments();
  const deleteMutation = useDeleteInterviewStageAttachment();

  useEffect(
    () => () => {
      uploadController.current?.abort();
    },
    [],
  );

  const upload = () => {
    if (files.length === 0) return;
    const oversized = files.find((file) => file.size > ATTACHMENT_MAX_BYTES);
    if (oversized) {
      notifications.show({
        color: "red",
        message: `Файл «${oversized.name}» должен быть не больше 50 МБ`,
      });
      return;
    }
    if (stage.attachments.length + files.length > 20) {
      notifications.show({
        color: "red",
        message: "К одному собеседованию можно добавить не больше 20 файлов",
      });
      return;
    }
    const controller = new AbortController();
    uploadController.current = controller;
    uploadMutation.mutate(
      {
        processId,
        stageId: stage.id,
        files,
        onFileStart: (currentFile, index, total) =>
          setUploadDetail(`Файл ${index + 1} из ${total}: ${currentFile.name}`),
        onFileComplete: (completedFile) =>
          setFiles((current) =>
            current.filter((candidate) => candidate !== completedFile),
          ),
        options: {
          signal: controller.signal,
          onStatus: setUploadStatus,
          onProgress: (percent) =>
            setUploadStatus((current) =>
              current?.phase === "uploading"
                ? { ...current, percent }
                : current,
            ),
        },
      },
      {
        onSuccess: () => {
          setFiles([]);
          notifications.show({ color: "green", message: "Файлы добавлены" });
        },
        onError: (error) =>
          notifications.show({
            color:
              error instanceof ApiError && error.code === "request_aborted"
                ? "yellow"
                : "red",
            message: error.message,
          }),
        onSettled: () => {
          uploadController.current = null;
          setUploadStatus(null);
          setUploadDetail(null);
        },
      },
    );
  };

  return (
    <Stack gap="xs">
      <Text fw={600} size="sm">
        Дополнительные материалы
      </Text>
      {stage.attachments.map((attachment) => {
        const canOpen =
          attachment.content_type.startsWith("image/") ||
          attachment.content_type === "application/pdf";
        return (
          <Group
            key={attachment.id}
            justify="space-between"
            className="file-action-row"
          >
            <Text size="sm" className="file-name">
              {attachment.filename} · {formatSize(attachment.size)}
            </Text>
            <Group gap="xs" className="file-actions">
              {canOpen && (
                <Button
                  size="xs"
                  variant="light"
                  onClick={() =>
                    void openFile(
                      api.viewInterviewStageAttachment(
                        processId,
                        stage.id,
                        attachment.id,
                      ),
                    )
                  }
                >
                  Открыть
                </Button>
              )}
              <Button
                size="xs"
                variant="subtle"
                onClick={() =>
                  void downloadFile(
                    api.downloadInterviewStageAttachment(
                      processId,
                      stage.id,
                      attachment.id,
                    ),
                    attachment.filename,
                  )
                }
              >
                Скачать
              </Button>
              <Button
                size="xs"
                color="red"
                variant="subtle"
                loading={
                  deleteMutation.isPending &&
                  deleteMutation.variables?.attachmentId === attachment.id
                }
                onClick={() => {
                  if (!window.confirm(`Удалить файл «${attachment.filename}»?`))
                    return;
                  deleteMutation.mutate(
                    {
                      processId,
                      stageId: stage.id,
                      attachmentId: attachment.id,
                    },
                    {
                      onError: (error) =>
                        notifications.show({
                          color: "red",
                          message: error.message,
                        }),
                    },
                  );
                }}
              >
                Удалить
              </Button>
            </Group>
          </Group>
        );
      })}
      <Group align="flex-end" className="upload-control-row">
        <FileInput
          flex={1}
          multiple
          label="Добавить файлы или изображения"
          placeholder="Выберите один или несколько файлов"
          description="До 50 МБ на файл, максимум 20 файлов"
          value={files}
          onChange={setFiles}
          disabled={uploadMutation.isPending}
          clearable
        />
        <Button
          variant="light"
          disabled={files.length === 0}
          loading={uploadMutation.isPending}
          onClick={upload}
        >
          Загрузить файлы
        </Button>
      </Group>
      {uploadMutation.isPending && uploadStatus && (
        <UploadProgressPanel
          status={uploadStatus}
          detail={uploadDetail ?? undefined}
          onCancel={() => uploadController.current?.abort()}
        />
      )}
    </Stack>
  );
}

export function InterviewProcessPage() {
  const { processId = "" } = useParams();
  const query = useInterviewProcess(processId);
  const stageMutation = useCreateInterviewStage();
  const outcomeMutation = useSetInterviewProcessOutcome();
  const recruiterMutation = useSetInterviewProcessRecruiters();
  const offerMutation = useMarkInterviewOffer();
  const cancelOfferMutation = useCancelInterviewOffer();
  const [stageType, setStageType] = useState<InterviewStageType>("screening");
  const [scheduledAt, setScheduledAt] = useState(dateTimeInputValue);
  const [description, setDescription] = useState("");
  const [closeReason, setCloseReason] = useState("");
  const [offerFile, setOfferFile] = useState<File | null>(null);
  const [offerUploadStatus, setOfferUploadStatus] =
    useState<UploadStatus | null>(null);
  const offerUploadController = useRef<AbortController | null>(null);
  const [recruiterUsernames, setRecruiterUsernames] = useState<string[]>([]);
  const recruitersInitializedFor = useRef<string | null>(null);

  useEffect(() => {
    if (!query.data || recruitersInitializedFor.current === query.data.id)
      return;
    recruitersInitializedFor.current = query.data.id;
    setRecruiterUsernames(
      query.data.recruiter_telegram_usernames.map((username) => `@${username}`),
    );
  }, [query.data]);

  useEffect(
    () => () => {
      offerUploadController.current?.abort();
    },
    [],
  );

  if (query.isPending) return <LoadingState label="Загружаем трек…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const process = query.data;

  const addStage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!scheduledAt || stageMutation.isPending) return;
    stageMutation.mutate(
      {
        processId,
        payload: {
          stage_type: stageType,
          scheduled_at: new Date(scheduledAt).toISOString(),
          description: description.trim() || null,
        },
      },
      {
        onSuccess: () => {
          setDescription("");
          setScheduledAt(dateTimeInputValue());
          notifications.show({ color: "green", message: "Этап добавлен" });
        },
        onError: (error) =>
          notifications.show({
            color:
              error instanceof ApiError && error.code === "request_aborted"
                ? "yellow"
                : "red",
            message: error.message,
          }),
      },
    );
  };

  const closeProcess = () => {
    if (!closeReason.trim()) return;
    outcomeMutation.mutate(
      {
        id: processId,
        payload: { status: "closed", close_reason: closeReason.trim() },
      },
      {
        onSuccess: () =>
          notifications.show({ color: "green", message: "Трек закрыт" }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const restoreProcess = () => {
    outcomeMutation.mutate(
      {
        id: processId,
        payload: { status: "active", close_reason: null },
      },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message: "Трек восстановлен и снова активен",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const markOffer = () => {
    if (
      offerFile &&
      offerFile.type !== "application/pdf" &&
      !offerFile.type.startsWith("image/")
    ) {
      notifications.show({
        color: "red",
        message: "Выберите PDF или изображение",
      });
      return;
    }
    if (offerFile && offerFile.size > OFFER_MAX_BYTES) {
      notifications.show({
        color: "red",
        message: "Файл оффера должен быть не больше 20 МБ",
      });
      return;
    }
    const controller = offerFile ? new AbortController() : null;
    offerUploadController.current = controller;
    offerMutation.mutate(
      {
        processId,
        file: offerFile,
        options: controller
          ? {
              signal: controller.signal,
              onStatus: setOfferUploadStatus,
              onProgress: (percent) =>
                setOfferUploadStatus((current) =>
                  current?.phase === "uploading"
                    ? { ...current, percent }
                    : current,
                ),
            }
          : undefined,
      },
      {
        onSuccess: () =>
          notifications.show({ color: "green", message: "Оффер сохранён" }),
        onError: (error) =>
          notifications.show({
            color:
              error instanceof ApiError && error.code === "request_aborted"
                ? "yellow"
                : "red",
            message: error.message,
          }),
        onSettled: () => {
          offerUploadController.current = null;
          setOfferUploadStatus(null);
        },
      },
    );
  };

  const cancelOffer = () => {
    if (
      !window.confirm(
        "Отменить отметку о полученном оффере? Трек снова станет активным, а загруженный файл оффера будет удалён.",
      )
    ) {
      return;
    }
    cancelOfferMutation.mutate(
      { processId },
      {
        onSuccess: () => {
          setOfferFile(null);
          notifications.show({
            color: "green",
            message: "Оффер отменён, трек снова активен",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const saveRecruiters = () => {
    recruiterMutation.mutate(
      {
        id: processId,
        payload: { recruiter_telegram_usernames: recruiterUsernames },
      },
      {
        onSuccess: (updatedProcess) => {
          setRecruiterUsernames(
            updatedProcess.recruiter_telegram_usernames.map(
              (username) => `@${username}`,
            ),
          );
          notifications.show({
            color: "green",
            message: "Контакты рекрутеров сохранены",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Собеседования · дневник"
          title={process.company_name}
          description={`${process.track_title} · ${process.stage_count} этапов в процессе`}
        />
        <Button component={Link} to="/interviews" variant="subtle">
          ← Все собеседования
        </Button>
      </Group>

      <Card withBorder>
        <Group justify="space-between">
          <div>
            <Text className="technical-label">Статус</Text>
            <Badge
              mt="xs"
              size="lg"
              color={
                process.status === "active"
                  ? "green"
                  : process.status === "offer"
                    ? "brandYellow"
                    : "gray"
              }
              c={process.status === "offer" ? "brandNavy.9" : undefined}
            >
              {process.status === "active"
                ? "Активный"
                : process.status === "offer"
                  ? "Получен оффер"
                  : "Закрыт"}
            </Badge>
          </div>
          <Stack gap="xs" align="flex-end">
            {process.closed_at && (
              <Text size="sm" c="dimmed">
                {process.status === "closed" ? "Закрыт" : "Ранее закрыт"}{" "}
                {formatDate(process.closed_at)}
              </Text>
            )}
            {process.status === "closed" && (
              <Button
                variant="light"
                loading={outcomeMutation.isPending}
                onClick={restoreProcess}
              >
                Восстановить трек
              </Button>
            )}
            {process.status === "offer" && (
              <Button
                color="red"
                variant="light"
                loading={cancelOfferMutation.isPending}
                onClick={cancelOffer}
              >
                Отменить оффер
              </Button>
            )}
          </Stack>
        </Group>
        {process.close_reason && (
          <Alert
            mt="md"
            color="gray"
            title={
              process.status === "closed"
                ? "Причина закрытия"
                : "Предыдущая причина отказа"
            }
          >
            {process.close_reason}
          </Alert>
        )}
        {process.offer && (
          <Group justify="space-between" mt="md">
            <Text>
              {process.offer.filename} · {formatSize(process.offer.size)}
            </Text>
            <Button
              size="xs"
              variant="light"
              onClick={() =>
                void downloadFile(
                  api.downloadInterviewOffer(processId),
                  process.offer!.filename,
                )
              }
            >
              Скачать оффер
            </Button>
          </Group>
        )}
      </Card>

      <Card withBorder>
        <Stack>
          <Title order={2}>Рекрутеры</Title>
          <TagsInput
            label="Telegram никнеймы"
            placeholder="@recruiter_name"
            description="Можно добавить до 20 рекрутеров. Нажимайте Enter после каждого никнейма."
            value={recruiterUsernames}
            onChange={setRecruiterUsernames}
            maxTags={20}
            clearable
          />
          <Group justify="flex-end">
            <Button
              variant="light"
              loading={recruiterMutation.isPending}
              onClick={saveRecruiters}
            >
              Сохранить рекрутеров
            </Button>
          </Group>
        </Stack>
      </Card>

      <Stack gap="md">
        <Title order={2}>Этапы</Title>
        {process.stages.length === 0 ? (
          <Card withBorder>
            <Text c="dimmed">Собеседований в этом треке пока нет.</Text>
          </Card>
        ) : (
          process.stages.map((stage, index) => (
            <Card key={stage.id} withBorder>
              <Stack>
                <Group justify="space-between">
                  <Group>
                    <Badge variant="light">{index + 1}</Badge>
                    <Title order={3}>{stageLabels[stage.stage_type]}</Title>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {formatDate(stage.scheduled_at)}
                  </Text>
                </Group>
                {stage.description && <Text>{stage.description}</Text>}
                <StageMedia processId={processId} stage={stage} />
                <StageAttachments processId={processId} stage={stage} />
                {(stage.comments ?? []).length > 0 && (
                  <Stack gap="xs">
                    <Text fw={700}>Обратная связь</Text>
                    {(stage.comments ?? []).map((comment) => (
                      <Card
                        key={comment.id}
                        withBorder
                        style={
                          comment.is_ai_feedback
                            ? {
                                borderColor: "var(--mantine-color-violet-6)",
                                boxShadow:
                                  "inset 3px 0 var(--mantine-color-violet-6)",
                              }
                            : comment.is_mentor_feedback
                              ? {
                                  borderColor: "var(--mantine-color-blue-6)",
                                  boxShadow:
                                    "inset 3px 0 var(--mantine-color-blue-6)",
                                }
                              : undefined
                        }
                      >
                        <Text style={{ whiteSpace: "pre-wrap" }}>
                          {comment.body}
                        </Text>
                        <Text size="xs" c="dimmed" mt="xs">
                          {comment.is_ai_feedback
                            ? "AI · автоматический разбор"
                            : comment.author
                              ? `${comment.author.name}${comment.author.telegram_username ? ` · @${comment.author.telegram_username}` : ""}`
                              : "Пользователь удалён"}
                        </Text>
                      </Card>
                    ))}
                  </Stack>
                )}
              </Stack>
            </Card>
          ))
        )}
      </Stack>

      {process.status === "active" && (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <form onSubmit={addStage}>
            <Card withBorder h="100%">
              <Stack>
                <Title order={2}>Добавить этап</Title>
                <Select
                  label="Тип собеседования"
                  required
                  data={stageOptions}
                  value={stageType}
                  onChange={(value) =>
                    setStageType(
                      (value as InterviewStageType | null) ?? "other",
                    )
                  }
                />
                <TextInput
                  label="Дата и время"
                  type="datetime-local"
                  required
                  value={scheduledAt}
                  onChange={(event) =>
                    setScheduledAt(event.currentTarget.value)
                  }
                />
                <Textarea
                  label="Описание"
                  placeholder="Что будут проверять, кто проводит, что подготовить"
                  minRows={4}
                  value={description}
                  onChange={(event) =>
                    setDescription(event.currentTarget.value)
                  }
                />
                <Button type="submit" loading={stageMutation.isPending}>
                  Добавить собеседование
                </Button>
              </Stack>
            </Card>
          </form>

          <Stack>
            <Card withBorder>
              <Stack>
                <Title order={2}>Получен оффер</Title>
                <Text size="sm" c="dimmed">
                  Можно дополнительно сохранить PDF или изображение оффера.
                </Text>
                <FileInput
                  label="Файл оффера"
                  placeholder="PDF или изображение"
                  description="Не больше 20 МБ"
                  accept="application/pdf,image/*"
                  value={offerFile}
                  onChange={setOfferFile}
                  disabled={offerMutation.isPending}
                  clearable
                />
                {offerMutation.isPending && offerUploadStatus && (
                  <UploadProgressPanel
                    status={offerUploadStatus}
                    onCancel={() => offerUploadController.current?.abort()}
                  />
                )}
                <Button
                  color="brandYellow"
                  c="brandNavy.9"
                  loading={offerMutation.isPending}
                  onClick={markOffer}
                >
                  Отметить оффер
                </Button>
              </Stack>
            </Card>
            <Card withBorder>
              <Stack>
                <Title order={2}>Закрыть трек</Title>
                <Textarea
                  label="Причина отказа"
                  placeholder="Компания отказала, позиция заморожена, остановил процесс…"
                  required
                  value={closeReason}
                  onChange={(event) =>
                    setCloseReason(event.currentTarget.value)
                  }
                />
                <Button
                  color="red"
                  variant="light"
                  disabled={!closeReason.trim()}
                  loading={outcomeMutation.isPending}
                  onClick={closeProcess}
                >
                  Закрыть процесс
                </Button>
              </Stack>
            </Card>
          </Stack>
        </SimpleGrid>
      )}

      {process.status === "offer" && !process.offer && (
        <Card withBorder>
          <Stack>
            <Title order={2}>Добавить файл оффера</Title>
            <FileInput
              accept="application/pdf,image/*"
              description="Не больше 20 МБ"
              value={offerFile}
              onChange={setOfferFile}
              disabled={offerMutation.isPending}
            />
            {offerMutation.isPending && offerUploadStatus && (
              <UploadProgressPanel
                status={offerUploadStatus}
                onCancel={() => offerUploadController.current?.abort()}
              />
            )}
            <Button
              disabled={!offerFile}
              loading={offerMutation.isPending}
              onClick={markOffer}
            >
              Загрузить файл
            </Button>
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
