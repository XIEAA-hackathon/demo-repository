import { API_URL } from "../../services/api/config";

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
  const { responseType, ...fetchOptions } = options;
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...fetchOptions, headers });
  } catch (cause) {
    throw new ApiError("Cannot reach the event server.", 0, { cause });
  }
  const data = response.ok && responseType === "blob" ? await response.blob() : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      window.dispatchEvent(new Event("admin:unauthorized"));
    }
    if (response.status === 409 || response.status === 503) window.dispatchEvent(new Event("admin:resync"));
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
export const setEventState = (state) => request("/admin/event/transition", { method: "POST", body: JSON.stringify({ state }) });
export const getAdminConfig = () => request("/admin/config");
export const updateAdminConfig = (config) => request("/admin/config", { method: "PUT", body: JSON.stringify(config) });
export const pauseTimer = () => request("/admin/event/timer/pause", { method: "POST" });
export const resumeTimer = () => request("/admin/event/timer/resume", { method: "POST" });
export const addTime = (seconds) => request("/admin/event/timer/adjust", { method: "POST", body: JSON.stringify({ seconds }) });
export const removeTime = (seconds) => request("/admin/event/timer/adjust", { method: "POST", body: JSON.stringify({ seconds: -seconds }) });
export const finalizeProblem = (id) => request(`/admin/auction/${id}/finalize`, { method: "POST" });
export const finalizeWildcard = () => request("/admin/wildcard/finalize", { method: "POST" });
export const previewRegistrationImport = (file) => {
  const body = new FormData(); body.append("file", file);
  return request("/admin/registration/import/preview", { method: "POST", body });
};
export const confirmRegistrationImport = (importId) => request("/admin/registration/import/confirm", { method: "POST", body: JSON.stringify({ import_id: importId }) });
export const importRegistrations = (file) => {
  const body = new FormData(); body.append("file", file);
  return request("/admin/registration/import", { method: "POST", body });
};
export const downloadRegistrationCredentials = (token) => request(`/admin/registration/import/download/${encodeURIComponent(token)}`, { responseType: "blob" });
export const downloadRegistrationSample = () => request("/admin/registration/sample.csv", { responseType: "blob" });
export const downloadRegistrationDemo = () => request("/admin/registration/demo.csv", { responseType: "blob" });
export const createTeamCredentials = (payload) => request("/admin/teams/credentials", { method: "POST", body: JSON.stringify(payload) });
export const getTeamCredentials = (teamId) => request(`/admin/teams/${teamId}/credentials`);
export const resetParticipantPassword = (userId) => request(`/admin/participant-accounts/${userId}/reset-password`, { method: "POST" });
export const getRoundControl = (round) => request(`/admin/rounds/${round}`);
export const importRoundProblems = (round, file) => {
  const body = new FormData(); body.append("file", file);
  return request(`/admin/rounds/${round}/problems/import`, { method: "POST", body });
};
export const downloadRoundProblemSample = (round) => request(`/admin/rounds/${round}/problems/sample.csv`, { responseType: "blob" });
export const selectRoundProblem = (round, problemId) => request(`/admin/rounds/${round}/problems/${problemId}/select`, { method: "POST" });
export const startRoundPreview = (round) => request(`/admin/rounds/${round}/preview/start`, { method: "POST" });
export const startRoundBidding = (round) => request(`/admin/rounds/${round}/bidding/start`, { method: "POST" });
export const closeRoundBidding = (round) => request(`/admin/rounds/${round}/bidding/close`, { method: "POST" });
export const assignRoundWinners = (round) => request(`/admin/rounds/${round}/assign-winners`, { method: "POST" });
export const endRoundOne = () => request("/admin/rounds/round-1/end", { method: "POST" });
export const openWildcardApplications = () => request("/admin/rounds/wildcard/applications/open", { method: "POST" });
export const closeWildcardApplications = () => request("/admin/rounds/wildcard/applications/close", { method: "POST" });
export const confirmWildcardSlots = (slots) => request("/admin/rounds/wildcard/slots", { method: "POST", body: JSON.stringify({ slots }) });
export const startWildcardSlotBidding = () => request("/admin/rounds/wildcard/bidding/start", { method: "POST" });
export const closeWildcardSlotBidding = () => request("/admin/rounds/wildcard/bidding/close", { method: "POST" });
export const getAdminSubmissions = () => request("/admin/submissions");
export const openSubmissions = () => request("/admin/submissions/open", { method: "POST" });
export const closeSubmissions = () => request("/admin/submissions/close", { method: "POST" });
export const getAdminHealth = () => request("/health");
export const runPreflight = () => request("/admin/preflight");
export const getRecoveryState = () => request("/admin/recovery");
export const resumeRecoveryTimer = () => request("/admin/recovery/resume-timer", { method: "POST" });
export const reloadRecoveryState = () => request("/admin/recovery/reload-state", { method: "POST" });
export const resyncClients = () => request("/admin/recovery/resync-clients", { method: "POST" });
export const retryCurrentTransition = () => request("/admin/recovery/retry-transition", { method: "POST" });
export const getActivityLog = (limit = 200) => request(`/admin/activity-log?limit=${encodeURIComponent(limit)}`);
export const developmentReset = (confirmation) => request("/admin/development/reset", { method: "POST", body: JSON.stringify({ confirmation }) });
export const resetEventData = (confirmation) => request("/admin/event-data/reset", { method: "POST", body: JSON.stringify({ confirmation }) });
