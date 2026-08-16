import { Tabs } from "@mantine/core";
import { Link, useLocation } from "react-router-dom";

import type { CardAutomationScope } from "./queries";

function currentTab(pathname: string) {
  if (pathname.includes("/card-automation/decisions")) return "decisions";
  if (pathname.includes("/card-automation/metrics")) return "metrics";
  if (pathname.includes("/card-automation/settings")) return "settings";
  if (pathname.startsWith("/admin/interview-question-moderation"))
    return "legacy";
  return "clusters";
}

export function CardAutomationNavigation({
  scope = "admin",
}: {
  scope?: CardAutomationScope;
}) {
  const location = useLocation();
  const base = `/${scope}/card-automation`;
  return (
    <Tabs value={currentTab(location.pathname)}>
      <Tabs.List className="responsive-tabs">
        <Tabs.Tab
          value="clusters"
          renderRoot={(props) => <Link {...props} to={`${base}/clusters`} />}
        >
          Карточки на проверку
        </Tabs.Tab>
        <Tabs.Tab
          value="decisions"
          renderRoot={(props) => <Link {...props} to={`${base}/decisions`} />}
        >
          Технический журнал
        </Tabs.Tab>
        {scope === "admin" && (
          <>
            <Tabs.Tab
              value="metrics"
              renderRoot={(props) => <Link {...props} to={`${base}/metrics`} />}
            >
              Метрики
            </Tabs.Tab>
            <Tabs.Tab
              value="settings"
              renderRoot={(props) => (
                <Link {...props} to={`${base}/settings`} />
              )}
            >
              Настройки
            </Tabs.Tab>
            <Tabs.Tab
              value="legacy"
              renderRoot={(props) => (
                <Link {...props} to="/admin/interview-question-moderation" />
              )}
            >
              Старая очередь
            </Tabs.Tab>
          </>
        )}
      </Tabs.List>
    </Tabs>
  );
}
