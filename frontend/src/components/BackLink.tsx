import { Anchor } from "@mantine/core";
import { Link } from "react-router-dom";

export function BackLink({
  to,
  children = "Назад к списку",
}: {
  to: string;
  children?: string;
}) {
  return (
    <Anchor component={Link} to={to} size="sm" className="back-link">
      <span aria-hidden="true">← </span>
      {children}
    </Anchor>
  );
}
