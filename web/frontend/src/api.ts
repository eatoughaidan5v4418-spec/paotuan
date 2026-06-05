import type {
  BootstrapPayload,
  CampaignSummary,
  LogEntry,
  TurnResult,
  VisibleState
} from "./types";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {})
    }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败：${response.status}`);
  }
  return payload as T;
}

export const api = {
  bootstrap: () => request<BootstrapPayload>("/api/app/bootstrap"),
  campaigns: () => request<{ campaigns: CampaignSummary[] }>("/api/campaigns"),
  state: (campaign: string) =>
    request<VisibleState>(`/api/state?campaign=${encodeURIComponent(campaign)}`),
  logs: () => request<{ logs: LogEntry[] }>("/api/logs"),
  selectCampaign: (campaign: string) =>
    request<VisibleState>("/api/campaigns/select", {
      method: "POST",
      body: JSON.stringify({ campaign })
    }),
  createCampaign: (theme: string) =>
    request<{ campaign: CampaignSummary & { opening_prompt?: string }; state: VisibleState }>(
      "/api/campaigns/new",
      {
        method: "POST",
        body: JSON.stringify({ theme })
      }
    ),
  deleteCampaign: (campaign: string) =>
    request<{ deleted: string; next_campaign: string; campaigns: CampaignSummary[]; state: VisibleState }>(
      "/api/campaigns/delete",
      {
        method: "POST",
        body: JSON.stringify({ campaign })
      }
    ),
  turn: (campaign: string, action: string) =>
    request<TurnResult>("/api/turn", {
      method: "POST",
      body: JSON.stringify({ campaign, action })
    }),
  roll: (expression: string) =>
    request<{ expression: string; rolls: number[]; modifier: number; total: number }>("/api/roll", {
      method: "POST",
      body: JSON.stringify({ expression })
    }),
  exportObsidian: (campaign: string) =>
    request<{ vault?: string; notes?: number }>("/api/obsidian/export", {
      method: "POST",
      body: JSON.stringify({ campaign })
    }),
  validate: (campaign: string) =>
    request<{ ok: boolean; stdout?: string; stderr?: string }>("/api/validate", {
      method: "POST",
      body: JSON.stringify({ campaign })
    })
};
