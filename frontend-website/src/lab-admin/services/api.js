import { API_URL } from "../../services/api/config";
import { ApiError, authenticatedRequest } from "../../services/api/authenticatedClient";

const TOKEN_KEY = "bid_to_build_lab_admin_token";
const request = (path, options = {}) => authenticatedRequest(API_URL, TOKEN_KEY, "lab-admin:unauthorized", path, options);

export { ApiError };
export const getLabAdminToken = () => localStorage.getItem(TOKEN_KEY);
export const hasLabAdminToken = () => Boolean(getLabAdminToken());
export const clearLabAdminToken = () => localStorage.removeItem(TOKEN_KEY);

export async function labAdminLogin(email, password) {
  const token = await request("/lab-admin/login", {
    method: "POST",
    body: new URLSearchParams({ username: email.trim(), password }),
  });
  localStorage.setItem(TOKEN_KEY, token.access_token);
  try {
    await getLabAdminSession();
  } catch (error) {
    clearLabAdminToken();
    throw error;
  }
  return token;
}

export async function labAdminLogout() {
  try {
    if (getLabAdminToken()) await request("/logout", { method: "POST" });
  } finally {
    clearLabAdminToken();
  }
}

export const getLabAdminSession = () => request("/lab-admin/session");
export const getLabAllocation = () => request("/lab-allocation");
export const getProblemResults = (signal) => request("/lab-admin/problem-results", { signal });
export const moveLabAssignment = (id, payload) => request(`/lab-admin/teams/${id}/lab`, {
  method: "PUT",
  body: JSON.stringify(payload),
});
