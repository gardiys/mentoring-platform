import { apiDownload, apiRequest } from "../../api/client";

export type CopilotRelease = {
  id: "mac-arm64" | "mac-x64" | "win-x64";
  os: "macos" | "windows";
  arch: "arm64" | "x64";
  version: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  signed: boolean;
};

export const copilotApi = {
  access: () =>
    apiRequest<{
      allowed: boolean;
      student_allowed: boolean;
      students_enabled: boolean;
      learning_status: string;
      reason: string;
    }>("/api/v1/copilot/access"),
  usage: (offset = 0) =>
    apiRequest<{
      total: number;
      students: {
        student_id: string;
        name: string;
        is_active: boolean;
        learning_status: string;
        student_allowed: boolean;
        interviews_completed: number;
        real_completed: number;
        mock_completed: number;
        sessions_started: number;
        active_ms: number;
        last_interview_at: string | null;
      }[];
    }>(`/api/v1/copilot/usage?offset=${offset}&limit=50`),
  releases: () =>
    apiRequest<{ releases: CopilotRelease[] }>("/api/v1/copilot/releases"),
  download: (
    id: CopilotRelease["id"],
    signal: AbortSignal,
    progress: (percent: number) => void,
  ) => apiDownload(`/api/v1/copilot/releases/${id}/download`, signal, progress),
};
