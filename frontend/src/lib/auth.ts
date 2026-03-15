export const setTokens = (access: string, refresh: string) => {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
};

export const clearTokens = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
};

export const getAccessToken = () =>
  typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

export const isAuthenticated = () => !!getAccessToken();
