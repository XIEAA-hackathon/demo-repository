import { API_URL } from "./config";

const TOKEN_KEY = "bid_to_build_admin_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const hasToken = () => Boolean(getToken());
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch (cause) {
    throw new Error("Cannot reach the event server.", { cause });
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("admin:unauthorized"));
    }
    throw new Error(data?.detail || data?.message || `Request failed (${response.status}).`);
  }
  return data;
}

export async function login(email, password) {
  const token = await request("/login", { method: "POST", body: new URLSearchParams({ username: email.trim(), password }) });
  localStorage.setItem(TOKEN_KEY, token.access_token);
  try {
    await getAdminState();
  } catch (error) {
    clearToken();
    throw new Error(error.message === "Administrator access required" ? "This account is not an administrator." : error.message, { cause: error });
  }
  return token;
}

export async function logout() {
  try { if (getToken()) await request("/logout", { method: "POST" }); } finally { clearToken(); }
}

export const getTeams = () => request("/teams");
export const approveTeam = (id) => request(`/team/${id}/approve`, { method: "PUT" });
export const deleteTeam = (id) => request(`/team/${id}`, { method: "DELETE" });
export const getProblemStatements = () => request("/problem-statements");
export const setProblemVisibility = (id, status) => request(`/problem-statement/${id}/visibility?status=${encodeURIComponent(status)}`, { method: "PUT" });
export const getBidHistory = () => request("/bid-history");
export const getLeaderboard = () => request("/leaderboard");
export const getAdminState = () => request("/admin/state");
export const setEventState = (state) => request("/admin/event/state", { method: "PUT", body: JSON.stringify({ state }) });
export const getAdminConfig = () => request("/admin/config");
export const updateAdminConfig = (config) => request("/admin/config", { method: "PUT", body: JSON.stringify(config) });
export const pauseTimer = () => request("/admin/round/pause", { method: "POST" });
export const resumeTimer = () => request("/admin/round/resume", { method: "POST" });
export const addTime = (seconds) => request(`/admin/round/add-time?seconds=${seconds}`, { method: "POST" });
export const removeTime = (seconds) => request(`/admin/round/remove-time?seconds=${seconds}`, { method: "POST" });
export const finalizeProblem = (id) => request(`/admin/auction/${id}/finalize`, { method: "POST" });
export const finalizeWildcard = () => request("/admin/wildcard/finalize", { method: "POST" });
export const previewRegistrationImport = (file) => {
  const body = new FormData(); body.append("file", file);
  return request("/admin/registration/import/preview", { method: "POST", body });
};
export const confirmRegistrationImport = (importId) => request("/admin/registration/import/confirm", { method: "POST", body: JSON.stringify({ import_id: importId }) });
