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
  releases: () =>
    apiRequest<{ releases: CopilotRelease[] }>("/api/v1/copilot/releases"),
  download: (
    id: CopilotRelease["id"],
    signal: AbortSignal,
    progress: (percent: number) => void,
  ) => apiDownload(`/api/v1/copilot/releases/${id}/download`, signal, progress),
};
