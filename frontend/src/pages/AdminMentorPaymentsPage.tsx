import { Stack } from "@mantine/core";

import { AdminMentorPayoutsPanel } from "../components/AdminMentorPayoutsPanel";
import { AdminPaymentsNavigation } from "../components/AdminPaymentsNavigation";
import { PageHeader } from "../components/PageHeader";

export function AdminMentorPaymentsPage() {
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование · финансы"
        title="Выплаты менторам"
        description="Доступный баланс складывается из долей от уже оплаченных ученических платежей и разовых вознаграждений. Откройте ментора, чтобы увидеть детализацию."
      />
      <AdminPaymentsNavigation active="mentors" />
      <AdminMentorPayoutsPanel />
    </Stack>
  );
}
