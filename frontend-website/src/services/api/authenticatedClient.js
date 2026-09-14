export class ApiError extends Error {
  constructor(message, status, detail = null, options) {
    if (options === undefined && detail && Object.keys(detail).length === 1 && "cause" in detail) {
      options = detail;
      detail = null;
    }
    super(message, options);
    this.status = status;
    this.detail = detail;
  }
}

export async function authenticatedRequest(apiUrl, tokenKey, unauthorizedEvent, path, options = {}) {
  const { responseType, ...fetchOptions } = options;
  const headers = new Headers(options.headers || {});
  const token = localStorage.getItem(tokenKey);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let response;
  try {
    response = await fetch(`${apiUrl}${path}`, { ...fetchOptions, headers });
  } catch (cause) {
    throw new ApiError("Cannot reach the event server.", 0, null, { cause });
  }
  const data = response.ok && responseType === "blob" ? await response.blob() : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem(tokenKey);
      window.dispatchEvent(new Event(unauthorizedEvent));
    }
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : detail?.message || data?.message || `Request failed (${response.status}).`;
    throw new ApiError(message, response.status, detail, { cause: data });
  }
  return data;
}
