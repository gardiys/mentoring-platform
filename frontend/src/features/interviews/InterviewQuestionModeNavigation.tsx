import { Button, Group } from "@mantine/core";
import { Link } from "react-router-dom";

export function InterviewQuestionModeNavigation({
  deckSlug,
  mode,
}: {
  deckSlug: string;
  mode: "table" | "study";
}) {
  return (
    <Group gap="sm" className="interview-question-mode-navigation">
      <Button
        component={Link}
        to={`/interviews/${deckSlug}/questions`}
        variant={mode === "table" ? "filled" : "light"}
      >
        Таблица вопросов
      </Button>
      <Button
        component={Link}
        to={`/interviews/${deckSlug}`}
        variant={mode === "study" ? "filled" : "light"}
      >
        Учить карточки
      </Button>
    </Group>
  );
}
