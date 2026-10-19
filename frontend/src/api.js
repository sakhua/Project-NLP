// Mọi lời gọi tới backend nằm ở đây. Địa chỉ backend lấy từ biến VITE_API_URL lúc build.
export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function request(path, { method = "GET", body, headers = {}, timeoutMs = 90000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs); // gói Free có thể mất ~1 phút để "thức dậy"
  try {
    const res = await fetch(API_URL + path, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = data.detail;
      throw new Error(typeof d === "string" ? d : d ? JSON.stringify(d) : `Lỗi ${res.status}`);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: () => request("/health"),
  ask: (question, date) => request("/api/ask", { method: "POST", body: { question, date: date || null } }),
  feedback: (log_id, rating, note) => request("/api/feedback", { method: "POST", body: { log_id, rating, note } }),
  documents: () => request("/api/documents"),
  units: (docId, date) => request(`/api/documents/${encodeURIComponent(docId)}/units?date=${date}`),
  unit: (uid) => request(`/api/units/${encodeURIComponent(uid)}`),
  graph: (uid) => request(`/api/graph/${encodeURIComponent(uid)}`),
  stats: (password) => request("/api/admin/stats", { headers: { "X-Admin-Password": password } }),
};

export const today = () => new Date().toISOString().slice(0, 10);
