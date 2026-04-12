/**
 * Postulio API client.
 * All endpoints use VITE_API_URL from the environment (falls back to localhost).
 * Auth tokens are stored in localStorage under "postulio_access_token".
 */

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const API_BASE = `${BASE_URL}/api/v1`;

// ─── Token helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null {
  return localStorage.getItem("postulio_access_token");
}

function setTokens(access: string, refresh: string): void {
  localStorage.setItem("postulio_access_token", access);
  localStorage.setItem("postulio_refresh_token", refresh);
}

function clearTokens(): void {
  localStorage.removeItem("postulio_access_token");
  localStorage.removeItem("postulio_refresh_token");
}

// ─── Core fetch wrapper ────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (authenticated) {
    const token = getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, errorBody.detail ?? "Unknown error");
  }

  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface ProfileOut {
  id: string;
  user_id: string;
  phone: string | null;
  ville: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  skills_technical: unknown[] | null;
  skills_soft: unknown[] | null;
  education: unknown[] | null;
  experience: unknown[] | null;
  languages: unknown[] | null;
  certifications: unknown[] | null;
  projects: unknown[] | null;
  updated_at: string;
}

export interface JobListItem {
  id: string;
  platform: string;
  title: string;
  company: string;
  location: string | null;
  job_type: string | null;
  match_score: number | null;
  status: string;
  posted_at: string | null;
  scraped_at: string;
  application_url: string | null;
  description_clean: string | null;
}

export interface JobListResponse {
  items: JobListItem[];
  total: number;
  page: number;
  size: number;
}

export interface DashboardMetrics {
  total_applications: number;
  applications_this_month: number;
  response_rate: number;
  interviews_count: number;
  avg_match_score: number | null;
  pipeline_today: Record<string, unknown> | null;
  daily_stats_7d: Array<{ date: string; scraped: number; matched: number; applied: number }>;
  platform_breakdown: Array<{ platform: string; count: number }>;
  match_score_distribution: Array<{ range: string; count: number }>;
  last_pipeline_run: Record<string, unknown> | null;
  top_opportunities: Array<Record<string, unknown>>;
  recent_activity: Array<Record<string, unknown>>;
}

export interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface PipelineTriggerResponse {
  run_id: string;
  status: string;
  message: string;
  pipeline_run_id: string | null;
  celery_task_id: string | null;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const auth = {
  async register(
    email: string,
    password: string,
    first_name: string,
    last_name: string,
  ): Promise<TokenResponse> {
    const tokens = await apiFetch<TokenResponse>(
      "/auth/register",
      { method: "POST", body: JSON.stringify({ email, password, first_name, last_name }) },
      false,
    );
    setTokens(tokens.access_token, tokens.refresh_token);
    return tokens;
  },

  async login(email: string, password: string): Promise<TokenResponse> {
    const tokens = await apiFetch<TokenResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    );
    setTokens(tokens.access_token, tokens.refresh_token);
    return tokens;
  },

  async refresh(): Promise<TokenResponse> {
    const refresh_token = localStorage.getItem("postulio_refresh_token");
    if (!refresh_token) throw new ApiError(401, "No refresh token");
    const tokens = await apiFetch<TokenResponse>(
      "/auth/refresh",
      { method: "POST", body: JSON.stringify({ refresh_token }) },
      false,
    );
    setTokens(tokens.access_token, tokens.refresh_token);
    return tokens;
  },

  logout(): void {
    clearTokens();
  },

  isLoggedIn(): boolean {
    return !!getToken();
  },
};

// ─── Users ────────────────────────────────────────────────────────────────────

export const users = {
  me: (): Promise<UserOut> => apiFetch<UserOut>("/users/me"),
  profile: (): Promise<ProfileOut> => apiFetch<ProfileOut>("/users/me/profile"),
  updateProfile: (data: Partial<ProfileOut>): Promise<ProfileOut> =>
    apiFetch<ProfileOut>("/users/me/profile", { method: "PUT", body: JSON.stringify(data) }),
};

// ─── CV ───────────────────────────────────────────────────────────────────────

export const cv = {
  async upload(file: File): Promise<{ message: string; profile: Partial<ProfileOut> }> {
    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/cv/upload`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, err.detail ?? "Upload failed");
    }
    return res.json();
  },

  parsed: (): Promise<Record<string, unknown>> => apiFetch("/cv/parsed"),
};

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export const jobs = {
  list: (params?: { status?: string; platform?: string; score_min?: number; page?: number; size?: number }): Promise<JobListResponse> => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.platform) q.set("platform", params.platform);
    if (params?.score_min !== undefined) q.set("score_min", String(params.score_min));
    if (params?.page !== undefined) q.set("page", String(params.page));
    if (params?.size !== undefined) q.set("size", String(params.size));
    const qs = q.toString();
    return apiFetch<JobListResponse>(`/jobs${qs ? `?${qs}` : ""}`);
  },

  get: (id: string): Promise<Record<string, unknown>> => apiFetch(`/jobs/${id}`),

  updateStatus: (id: string, status: string): Promise<Record<string, unknown>> =>
    apiFetch(`/jobs/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboard = {
  metrics: (): Promise<DashboardMetrics> => apiFetch<DashboardMetrics>("/dashboard/metrics"),
  warRoom: (): Promise<Record<string, unknown>> => apiFetch("/dashboard/war-room"),
};

// ─── Pipeline ─────────────────────────────────────────────────────────────────

export const pipeline = {
  trigger: (): Promise<PipelineTriggerResponse> =>
    apiFetch<PipelineTriggerResponse>("/pipeline/trigger", { method: "POST" }),

  status: (): Promise<Record<string, unknown>> => apiFetch("/pipeline/status"),

  runs: (limit = 20): Promise<unknown[]> => apiFetch(`/pipeline/runs?limit=${limit}`),

  /**
   * Open an SSE stream for live pipeline updates.
   * Returns an EventSource connected to /pipeline/stream.
   * The caller must call .close() when done.
   */
  stream(): EventSource {
    const token = getToken();
    // EventSource doesn't support headers natively — token is passed via query param
    // Backend should be updated to accept ?token= query param, or use a cookie.
    // For now we pass the token in the URL (acceptable for SSE in controlled environments).
    return new EventSource(`${API_BASE}/pipeline/stream?token=${token ?? ""}`);
  },
};

// ─── Consultant (Dr. Rousseau) ────────────────────────────────────────────────

export const consultant = {
  createConversation: (): Promise<ConversationOut> =>
    apiFetch<ConversationOut>("/consultant/conversations", { method: "POST" }),

  listConversations: (): Promise<ConversationOut[]> =>
    apiFetch<ConversationOut[]>("/consultant/conversations"),

  getMessages: (conversationId: string): Promise<{ messages: MessageOut[] }> =>
    apiFetch<{ messages: MessageOut[] }>(`/consultant/conversations/${conversationId}/messages`),

  deleteConversation: (conversationId: string): Promise<void> =>
    apiFetch<void>(`/consultant/conversations/${conversationId}`, { method: "DELETE" }),

  /**
   * Send a message and get a streaming SSE response.
   * Returns a ReadableStreamDefaultReader over the SSE byte stream.
   * Events:
   *   data: {"chunk": "..."} — text token
   *   data: {"event": "tool_start", "tool": "...", "input": {...}}
   *   data: {"event": "tool_end", "tool": "...", "result": "..."}
   *   data: {"event": "done", "message_id": "..."}
   *   data: {"event": "error", "message": "..."}
   */
  async chatStream(
    conversationId: string,
    message: string,
  ): Promise<ReadableStreamDefaultReader<Uint8Array>> {
    const token = getToken();
    const res = await fetch(`${API_BASE}/consultant/conversations/${conversationId}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, err.detail ?? "Chat error");
    }
    if (!res.body) throw new ApiError(500, "No response body");
    return res.body.getReader();
  },
};

// ─── Documents ────────────────────────────────────────────────────────────────

export const documents = {
  get: (id: string): Promise<Record<string, unknown>> => apiFetch(`/documents/${id}`),

  downloadUrl: (id: string): string => `${API_BASE}/documents/${id}/download?token=${getToken() ?? ""}`,

  preview: (id: string): Promise<{ content_html: string; content_text: string }> =>
    apiFetch(`/documents/${id}/preview`),
};
