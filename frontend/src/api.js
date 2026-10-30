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
  } catch (e) {
    if (e.name === "AbortError") throw new Error("Máy chủ phản hồi quá lâu. Thử lại sau.");
    if (e instanceof TypeError) throw new Error("Không kết nối được backend. Kiểm tra uvicorn đã chạy chưa.");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** Hỏi đáp dạng luồng: gọi onEvent(ev) cho từng dòng NDJSON (step, context, token, done, error). */
export async function askStream({ question, date, history }, onEvent, signal) {
  const res = await fetch(API_URL + "/api/ask/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, date: date || null, history: history || [] }),
    signal,
  }).catch((e) => {
    if (e.name === "AbortError") throw e;
    throw new Error("Không kết nối được backend. Kiểm tra uvicorn đã chạy chưa.");
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `Lỗi ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}

export const api = {
  health: () => request("/health", { timeoutMs: 10000 }),
  healthDb: () => request("/health/db", { timeoutMs: 15000 }),
  overview: () => request("/api/overview"),
  feedback: (log_id, rating, note) => request("/api/feedback", { method: "POST", body: { log_id, rating, note } }),
  documents: () => request("/api/documents"),
  units: (docId, date) => request(`/api/documents/${encodeURIComponent(docId)}/units?date=${date}`),
  unit: (uid) => request(`/api/units/${encodeURIComponent(uid)}`),
  search: (q, limit = 20) => request(`/api/units/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  amended: () => request("/api/amended"),
  graph: (uid, limit = 60) => request(`/api/graph/${encodeURIComponent(uid)}?limit=${limit}`),
  stats: (password) => request("/api/admin/stats", { headers: { "X-Admin-Password": password } }),
};

export const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
