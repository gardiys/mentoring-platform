import type {
  IntelligenceProcessingStatus,
  IntelligenceQuestion,
} from "../../types/api";

export const intelligenceStatusLabels: Record<
  IntelligenceProcessingStatus,
  string
> = {
  draft: "Ожидает загрузки",
  uploaded: "Ожидает запуска обработки",
  transcription_submitted: "Отправлено в распознавание",
  transcribing: "Распознаём речь",
  transcript_ready: "Расшифровка готова",
  awaiting_candidate_speaker: "Нужно выбрать кандидата",
  analyzing: "Анализируем ответы",
  ready: "Разбор готов",
  failed: "Ошибка обработки",
};

export const intelligenceQuestionKindLabels: Record<
  IntelligenceQuestion["question_kind"],
  string
> = {
  technical: "Технический",
  hr: "HR",
  organizational: "Организационный",
  other: "Иное",
};

export const intelligenceDifficultyLabels: Record<
  IntelligenceQuestion["difficulty"],
  string
> = {
  unknown: "Не определена",
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
};
