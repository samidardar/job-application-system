import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000, // 30s — prevents frozen UI if backend is slow/unresponsive
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Auto-refresh on 401 — with loop protection
let _isRefreshing = false;
let _refreshRetryCount = 0;
const _MAX_REFRESH_RETRIES = 1;

api.interceptors.response.use(
  (r) => {
    _refreshRetryCount = 0; // Reset on any successful response
    return r;
  },
  async (error) => {
    const status = error.response?.status;

    // Only attempt refresh once per 401, never for the refresh endpoint itself
    if (
      status === 401 &&
      typeof window !== "undefined" &&
      !_isRefreshing &&
      _refreshRetryCount < _MAX_REFRESH_RETRIES &&
      !error.config?.url?.includes("/auth/refresh")
    ) {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        _isRefreshing = true;
        _refreshRetryCount++;
        try {
          const res = await axios.post(
            `${API_BASE}/api/v1/auth/refresh`,
            { refresh_token: refresh },
            { timeout: 10_000 },
          );
          localStorage.setItem("access_token", res.data.access_token);
          localStorage.setItem("refresh_token", res.data.refresh_token);
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          _isRefreshing = false;
          return api.request(error.config);
        } catch {
          // Refresh failed — clear session and redirect to login
          _isRefreshing = false;
          _refreshRetryCount = 0;
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
          return Promise.reject(error);
        }
      }
    }

    // Not a 401, or refresh already failed — propagate error
    if (status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }

    return Promise.reject(error);
  }
);

// Auth
export const authApi = {
  register: (data: { email: string; password: string; first_name: string; last_name: string }) =>
    api.post("/auth/register", data),
  login: (data: { email: string; password: string }) => api.post("/auth/login", data),
  refresh: (refresh_token: string) => api.post("/auth/refresh", { refresh_token }),
};

// Users
export const usersApi = {
  getMe: () => api.get("/users/me"),
  getProfile: () => api.get("/users/me/profile"),
  updateProfile: (data: Record<string, unknown>) => api.put("/users/me/profile", data),
  getPreferences: () => api.get("/users/me/preferences"),
  updatePreferences: (data: Record<string, unknown>) => api.put("/users/me/preferences", data),
};

// CV
export const cvApi = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/cv/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 60_000, // CV parsing can take longer
    });
  },
  getParsed: () => api.get("/cv/parsed"),
};

// Jobs
export const jobsApi = {
  list: (params?: Record<string, unknown>) => api.get("/jobs", { params }),
  get: (id: string) => api.get(`/jobs/${id}`),
  updateStatus: (id: string, status: string) =>
    api.patch(`/jobs/${id}/status`, { status }),
};

// Applications
export const applicationsApi = {
  list: (params?: Record<string, unknown>) => api.get("/applications", { params }),
  get: (id: string) => api.get(`/applications/${id}`),
  update: (id: string, data: Record<string, unknown>) =>
    api.patch(`/applications/${id}`, data),
  getStats: () => api.get("/applications/stats"),
};

// Pipeline
export const pipelineApi = {
  trigger: () => api.post("/pipeline/trigger"),
  getStatus: () => api.get("/pipeline/status"),
  getRuns: () => api.get("/pipeline/runs"),
  getRun: (id: string) => api.get(`/pipeline/runs/${id}`),
  getStreamUrl: () => `${API_BASE}/api/v1/pipeline/stream`,
};

// Dashboard
export const dashboardApi = {
  getMetrics: () => api.get("/dashboard/metrics"),
};

// Documents
export const documentsApi = {
  get: (id: string) => api.get(`/documents/${id}`),
  getDownloadUrl: (id: string) => `${API_BASE}/api/v1/documents/${id}/download`,
  getPreview: (id: string) => api.get(`/documents/${id}/preview`),
};

// Consultant (Dr. Rousseau career chatbot)
export const consultantApi = {
  listConversations: (limit = 50) =>
    api.get(`/consultant/conversations?limit=${limit}`),
  createConversation: () => api.post("/consultant/conversations"),
  getMessages: (convId: string) =>
    api.get(`/consultant/conversations/${convId}/messages`),
  deleteConversation: (convId: string) =>
    api.delete(`/consultant/conversations/${convId}`),
  // Returns the SSE stream URL (use with fetch + ReadableStream, not axios)
  getChatStreamUrl: (convId: string) =>
    `${API_BASE}/api/v1/consultant/conversations/${convId}/chat`,
};
