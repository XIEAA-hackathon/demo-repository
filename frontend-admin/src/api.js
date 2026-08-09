import { API_URL } from "./config";

const TOKEN_KEY = "bid_to_build_admin_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const hasToken = () => Boolean(getToken());
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(message, status, options) {
    super(message, options);
    this.status = status;
  }
}

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
    throw new ApiError("Cannot reach the event server.", 0, { cause });
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("admin:unauthorized"));
    }
    throw new ApiError(data?.detail || data?.message || `Request failed (${response.status}).`, response.status);
  }
  return data;
}

export async function login(email, password) {
  let token;
  try {
    token = await request("/login", { method: "POST", body: new URLSearchParams({ username: email.trim(), password }) });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      throw new ApiError("Invalid username/email or password.", 401, { cause: error });
    }
    if (error instanceof ApiError && error.status === 502) {
      throw new ApiError("Authentication service temporarily unavailable.", 502, { cause: error });
    }
    throw error;
  }
  localStorage.setItem(TOKEN_KEY, token.access_token);
  try {
    await getAdminState();
  } catch (error) {
    clearToken();
    if (error instanceof ApiError && error.status === 403) {
      throw new ApiError("Admin access required.", 403, { cause: error });
    }
    if (error instanceof ApiError && error.status === 502) {
      throw new ApiError("Authentication service temporarily unavailable.", 502, { cause: error });
    }
    throw error;
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
export const createTeamCredentials = (payload) => request("/admin/teams/credentials", { method: "POST", body: JSON.stringify(payload) });
export const getTeamCredentials = (teamId) => request(`/admin/teams/${teamId}/credentials`);
export const resetParticipantPassword = (userId) => request(`/admin/participant-accounts/${userId}/reset-password`, { method: "POST" });
