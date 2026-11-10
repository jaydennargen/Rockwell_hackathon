// The ONLY module that calls fetch(). One function per endpoint in ARCHITECTURE.md §4.

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(path, { method = "GET", body, form } = {}) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`/api${path}`, opts);
  } catch {
    throw new ApiError(0, "network", "Can't reach the server. Check that the backend is running.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data.error || {};
    throw new ApiError(res.status, e.code || "error", e.message || `Request failed (${res.status}).`);
  }
  return data;
}

// auth
export const demoLogin = (role) => request("/auth/demo-login", { method: "POST", body: { role } });
export const logout = () => request("/auth/logout", { method: "POST" });
export const getMe = () => request("/me");
export const getHealth = () => request("/health");

// orders
export const listOrders = ({ filter = "all", limit = 50, offset = 0 } = {}) =>
  request(`/orders?filter=${filter}&limit=${limit}&offset=${offset}`);
export const createOrder = (order) => request("/orders", { method: "POST", body: order });
export const bulkUpload = (file) => {
  const form = new FormData();
  form.append("file", file);
  return request("/orders/bulk", { method: "POST", form });
};
export const getOrder = (id) => request(`/orders/${encodeURIComponent(id)}`);
export const reviewOrder = (id, review) =>
  request(`/orders/${encodeURIComponent(id)}/review`, { method: "POST", body: review });
// PDF repair report (reference SAP layout). Returns a Blob; same role filtering as getOrder.
export async function downloadReportPdf(id) {
  let res;
  try {
    res = await fetch(`/api/orders/${encodeURIComponent(id)}/report.pdf`, { credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network", "Can't reach the server. Check that the backend is running.");
  }
  if (!res.ok) {
    const e = (await res.json().catch(() => ({}))).error || {};
    throw new ApiError(res.status, e.code || "error", e.message || `Download failed (${res.status}).`);
  }
  return res.blob();
}
export const retryOrder = (id) => request(`/orders/${encodeURIComponent(id)}/retry`, { method: "POST" });

// chat
export const getChat = (id) => request(`/orders/${encodeURIComponent(id)}/chat`);
export const sendChat = (id, message) =>
  request(`/orders/${encodeURIComponent(id)}/chat`, { method: "POST", body: { message } });
