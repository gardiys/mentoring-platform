import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ScheduleEventList } from "../components/ScheduleEventList";
import { useMyMentor } from "../features/schedule/queries";
import { normalizeTelegramUsername } from "../utils/telegram";

function mentorName(firstName: string, lastName: string | null) {
  return [firstName, lastName].filter(Boolean).join(" ");
}

export function MyMentorPage() {
  const query = useMyMentor();

  if (query.isPending)
    return <LoadingState label="Загружаем данные ментора…" />;
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  const { mentor, schedule, useful_links: usefulLinks } = query.data;
  const telegramUsername = normalizeTelegramUsername(mentor?.telegram_username);

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Поддержка · Мой ментор"
        title="Мой ментор"
        description="Контакты, запись на личную консультацию и ближайшие встречи вашего направления."
      />

      {mentor ? (
        <Card withBorder>
          <Stack gap="md">
            <Group justify="space-between" align="flex-start">
              <div>
                <Badge color="brandYellow" c="brandNavy.9" mb="sm">
                  Ваш ментор
                </Badge>
                <Title order={2}>
                  {mentorName(mentor.first_name, mentor.last_name)}
                </Title>
                {telegramUsername && (
                  <Text
                    component="a"
                    href={`https://t.me/${telegramUsername}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    c="blue"
                    td="none"
                  >
                    @{telegramUsername}
                  </Text>
                )}
              </div>
              <Group justify="flex-end">
                {telegramUsername && (
                  <Button
                    component="a"
                    href={`https://t.me/${telegramUsername}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    variant="light"
                  >
                    Написать в Telegram
                  </Button>
                )}
                {mentor.group_calendar_url && (
                  <Button
                    component="a"
                    href={mentor.group_calendar_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    variant="light"
                  >
                    Календарь группы
                  </Button>
                )}
                {mentor.consultation_url && (
                  <Button
                    component="a"
                    href={mentor.consultation_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Записаться на консультацию
                  </Button>
                )}
              </Group>
            </Group>
            {!mentor.consultation_url && (
              <Text size="sm" c="dimmed">
                Ментор пока не добавил ссылку для записи. Для личной встречи
                напишите ему в Telegram.
              </Text>
            )}
          </Stack>
        </Card>
      ) : (
        <Alert color="blue" title="Ментор ещё не назначен">
          Когда администратор назначит вам ментора, здесь появятся его контакты
          и личное расписание. Общие встречи направлений уже доступны ниже.
        </Alert>
      )}

      {usefulLinks.length > 0 && (
        <section>
          <Title order={2} mb="md">
            Полезные ссылки
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            {usefulLinks.map((link) => (
              <Card key={link.id} withBorder>
                <Stack gap="sm" h="100%">
                  <Title order={3}>{link.title}</Title>
                  {link.description && (
                    <Text size="sm" c="dimmed">
                      {link.description}
                    </Text>
                  )}
                  <Button
                    component="a"
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    variant="light"
                    mt="auto"
                  >
                    Открыть ссылку
                  </Button>
                </Stack>
              </Card>
            ))}
          </SimpleGrid>
        </section>
      )}

      <section>
        <Title order={2} mb="md">
          Расписание
        </Title>
        <ScheduleEventList
          events={schedule}
          emptyText="Для ваших направлений пока нет запланированных созвонов и встреч."
        />
      </section>
    </Stack>
  );
}
