import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
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

// Auto-refresh on 401
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const res = await axios.post(`${API_BASE}/api/v1/auth/refresh`, {
            refresh_token: refresh,
          });
          localStorage.setItem("access_token", res.data.access_token);
          localStorage.setItem("refresh_token", res.data.refresh_token);
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api.request(error.config);
        } catch {
          localStorage.clear();
          window.location.href = "/login";
        }
      }
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
  generateDocuments: (id: string) => api.post(`/jobs/${id}/generate`),
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
  trigger: (data: { job_title: string; location: string; min_match_score?: number }) =>
    api.post("/pipeline/trigger", data),
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
