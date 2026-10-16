import { Anchor, Card, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";

import type { components } from "../../api/generated/schema";
import { questionnaireLabels } from "./legalQuestionnaire";
import { opportunityDate } from "./workspaceLabels";

type Questionnaire = components["schemas"]["AdminQuestionnaireRead"];

export function GoTransitionQuestionnaire({
  questionnaire,
  showApplicationLink = false,
}: {
  questionnaire: Questionnaire | null | undefined;
  showApplicationLink?: boolean;
}) {
  if (!questionnaire) return null;
  return (
    <Card withBorder>
      <Stack gap="md">
        <div>
          <Title order={3}>Анкета перехода Python → Go</Title>
          <Text size="sm" c="dimmed">
            {questionnaire.source === "payment"
              ? "Сведения зафиксированы при оплате"
              : "Сведения заполнены перед оплатой"}
            {" · "}
            {opportunityDate(questionnaire.recorded_at)}
          </Text>
        </div>
        {Object.entries(questionnaireLabels).map(([name, label]) => {
          const value = questionnaire.answers[name];
          const explanation = questionnaire.answers[`${name}_details`];
          return (
            <div key={name}>
              <Text size="sm" c="dimmed">
                {label}
                {["existing_offers", "selection_processes"].includes(name)
                  ? " на Go-позиции"
                  : ""}
              </Text>
              <Text
                style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
              >
                {typeof value === "boolean"
                  ? value
                    ? "Да"
                    : "Нет"
                  : value?.trim() || "Не указано"}
              </Text>
              {value === true &&
                typeof explanation === "string" &&
                explanation.trim() && (
                  <Text
                    size="sm"
                    style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                  >
                    {explanation}
                  </Text>
                )}
            </div>
          );
        })}
        {showApplicationLink && (
          <Anchor
            component={Link}
            to={`/admin/opportunities/go-transition?go=${questionnaire.application_id}`}
          >
            Открыть заявку перехода в Go
          </Anchor>
        )}
      </Stack>
    </Card>
  );
}
