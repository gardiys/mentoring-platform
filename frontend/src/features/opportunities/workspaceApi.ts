import { apiRequest } from "../../api/client";
import type { components } from "../../api/generated/schema";

type Schemas = components["schemas"];

export const workspaceApi = {
  summary: () =>
    apiRequest<Schemas["OpportunitySummary"]>(
      "/api/v1/admin/opportunities/summary",
    ),
};
