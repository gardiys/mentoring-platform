import {
  Alert,
  Button,
  Card,
  Stack,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useUpdateInterviewProcess } from "./journalQueries";
import type { InterviewProcessDetail } from "../../types/api";

export function InterviewTrackContext({
  process,
}: {
  process: InterviewProcessDetail;
}) {
  const mutation = useUpdateInterviewProcess();
  const [team, setTeam] = useState(process.team_name || "");
  const [position, setPosition] = useState(process.position_name || "");
  const [notes, setNotes] = useState(process.company_notes || "");
  return (
    <Card withBorder>
      <Stack>
        <Title order={3}>Компания, команда и вакансия</Title>
        <TextInput
          label="Команда / подразделение"
          maxLength={240}
          value={team}
          onChange={(e) => setTeam(e.currentTarget.value)}
        />
        <TextInput
          label="Позиция / вакансия"
          maxLength={240}
          value={position}
          onChange={(e) => setPosition(e.currentTarget.value)}
        />
        <Textarea
          label="Что известно о компании и отборе"
          maxLength={10000}
          minRows={3}
          autosize
          value={notes}
          onChange={(e) => setNotes(e.currentTarget.value)}
        />
        <Button
          loading={mutation.isPending}
          onClick={() =>
            mutation.mutate({
              id: process.id,
              payload: {
                company_name: process.company_name,
                company_alias_confirmed: false,
                track_id: process.track_id,
                team_name: team.trim() || null,
                position_name: position.trim() || null,
                company_notes: notes.trim() || null,
              },
            })
          }
        >
          Сохранить контекст трека
        </Button>
        {mutation.isSuccess && (
          <Alert color="green">Контекст сохранён и доступен Copilot.</Alert>
        )}
        {mutation.isError && (
          <Alert color="red">{mutation.error.message}</Alert>
        )}
      </Stack>
    </Card>
  );
}
