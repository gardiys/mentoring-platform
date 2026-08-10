import { Button, Group } from "@mantine/core";
import { Link } from "react-router-dom";

type Section = "students" | "overdue" | "mentors";

const items: Array<{ section: Section; label: string; to: string }> = [
  { section: "students", label: "Ученики с офферами", to: "/admin/payments" },
  {
    section: "overdue",
    label: "Просроченные платежи",
    to: "/admin/payments/overdue",
  },
  {
    section: "mentors",
    label: "Выплаты менторам",
    to: "/admin/payments/mentors",
  },
];

export function AdminPaymentsNavigation({ active }: { active: Section }) {
  return (
    <Group gap="sm">
      {items.map((item) => (
        <Button
          key={item.section}
          component={Link}
          to={item.to}
          variant={active === item.section ? "filled" : "light"}
        >
          {item.label}
        </Button>
      ))}
    </Group>
  );
}
