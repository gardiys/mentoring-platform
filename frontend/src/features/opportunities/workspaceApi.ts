import { apiRequest } from "../../api/client";
import type { components } from "../../api/generated/schema";

type Schemas = components["schemas"];
export type ConsultationDetail = Schemas["AdminConsultationDetail"];
export type GoDetail = Schemas["AdminGoTransitionDetail"];
export type RepeatDetail = Schemas["AdminPythonRepeatDetail"];
export type WorkspaceItem = Schemas["WorkspaceItem"];
export type WorkspacePage = Schemas["WorkspacePage"];
export type WorkspaceTab =
  "inbox" | "consultations" | "go-transition" | "python-repeat" | "settings";
const base = "/api/v1/admin/opportunities";
function command<T>(path: string, body: unknown = {}, method = "POST") {
  return apiRequest<T>(`${base}/${path}`, {
    method,
    body: JSON.stringify(body),
  });
}

export const workspaceApi = {
  summary: () =>
    apiRequest<Schemas["OpportunitySummary"]>(
      "/api/v1/admin/opportunities/summary",
    ),
  page: (tab: Exclude<WorkspaceTab, "settings">, params: URLSearchParams) =>
    apiRequest<WorkspacePage>(`${base}/${tab}?${params}`),
  settings: () => apiRequest<Schemas["WorkspaceSettings"]>(`${base}/settings`),
  consultation: (id: string) =>
    apiRequest<ConsultationDetail>(`${base}/consultations/${id}`),
  go: (id: string) => apiRequest<GoDetail>(`${base}/go-transition/${id}`),
  repeat: (id: string) =>
    apiRequest<RepeatDetail>(`${base}/python-repeat/${id}`),
  approveConsultation: (
    id: string,
    body: Schemas["ConsultationApproveCommand"],
  ) => command<ConsultationDetail>(`consultations/${id}/approve`, body),
  rejectConsultation: (id: string, body: Schemas["ReasonCommand"]) =>
    command<ConsultationDetail>(`consultations/${id}/reject`, body),
  mentorConsultation: (id: string, body: Schemas["MentorCommand"]) =>
    command<ConsultationDetail>(`consultations/${id}/mentor`, body),
  scheduleConsultation: (
    id: string,
    body: Schemas["ConsultationScheduleCommand"],
  ) => command<ConsultationDetail>(`consultations/${id}/schedule`, body),
  completeConsultation: (
    id: string,
    body: Schemas["ConsultationCompleteCommand"],
  ) => command<ConsultationDetail>(`consultations/${id}/complete`, body),
  summaryConsultation: (
    id: string,
    body: Schemas["ConsultationSummaryCommand"],
  ) =>
    command<ConsultationDetail>(`consultations/${id}/summary`, body, "PATCH"),
  cancelConsultation: (
    id: string,
    body: Schemas["ConsultationCancelCommand"],
  ) => command<ConsultationDetail>(`consultations/${id}/cancel`, body),
  noteConsultation: (id: string, body: Schemas["InternalNoteCommand"]) =>
    command<ConsultationDetail>(
      `consultations/${id}/internal-note`,
      body,
      "PATCH",
    ),
  approveGo: (id: string, body: Schemas["GoApproveCommand"]) =>
    command<GoDetail>(`go-transition/${id}/approve`, body),
  rejectGo: (id: string, body: Schemas["ReasonCommand"]) =>
    command<GoDetail>(`go-transition/${id}/reject`, body),
  cancelGo: (id: string, body: Schemas["ReasonCommand"]) =>
    command<GoDetail>(`go-transition/${id}/cancel`, body),
  extendGo: (id: string) => command<GoDetail>(`go-transition/${id}/extend`),
  noteGo: (id: string, body: Schemas["InternalNoteCommand"]) =>
    command<GoDetail>(`go-transition/${id}/internal-note`, body, "PATCH"),
  confirmPayment: (id: string) =>
    command<ConsultationDetail | GoDetail | RepeatDetail>(
      `payments/${id}/confirm`,
    ),
};
