import { Alert, Button, Stack, Text } from "@mantine/core";
import { Link, Outlet } from "react-router-dom";

import { useMe } from "../features/auth/queries";
import type { User } from "../types/api";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { PageHeader } from "./PageHeader";

interface Props {
  roles: User["role"][];
}

export function RoleGuard({ roles }: Props) {
  const me = useMe();
  if (me.isPending) return <LoadingState label="Проверяем права доступа…" />;
  if (me.isError)
    return <ErrorState error={me.error} retry={() => void me.refetch()} />;
  if (roles.includes(me.data.role)) return <Outlet />;

  return (
    <Stack gap="lg">
      <PageHeader
        eyebrow="Доступ · роли"
        title="Раздел недоступен"
        description="У вашей роли нет доступа к этой части платформы."
      />
      <Alert color="brandYellow" title="Недостаточно прав">
        <Stack align="flex-start">
          <Text>
            Если вам нужен доступ, обратитесь к администратору платформы.
          </Text>
          <Button component={Link} to="/roadmaps" variant="light">
            Вернуться к роадмапам
          </Button>
        </Stack>
      </Alert>
    </Stack>
  );
}
