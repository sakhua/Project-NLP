// Các điều khoản vừa xem ở trang Khám phá đồ thị (gợi ý "Xem gần đây" trong ô tìm kiếm).
// Tách khỏi GraphPage.jsx để khi sửa code, Vite chỉ cập nhật nóng trang đó thay vì tải lại cả trang.
const RECENT_KEY = "graphrag.graph.recent";

export function rememberRecent(id) {
  try {
    const old = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]").filter((x) => x !== id);
    localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...old].slice(0, 6)));
  } catch { /* không lưu được thì bỏ qua */ }
}

export function readRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
}
