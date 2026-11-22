// Phiên đăng nhập: token của hệ thống lưu trong trình duyệt, gửi kèm mọi lời gọi API (xem api.js).
import { useEffect, useState } from "react";

const KEY = "graphrag.auth.v1";
const EVENT = "graphrag:auth";

function read() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    return s && s.token && s.het_han > Date.now() ? s : null;
  } catch {
    return null;
  }
}

export const getToken = () => read()?.token || null;

export function saveSession({ token, han_giay, nguoi_dung }) {
  const s = { token, nguoi_dung, het_han: Date.now() + (han_giay || 0) * 1000 };
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* chế độ riêng tư: chỉ giữ trong phiên */ }
  window.dispatchEvent(new Event(EVENT));
}

export function clearSession() {
  try { localStorage.removeItem(KEY); } catch { /* bỏ qua */ }
  window.dispatchEvent(new Event(EVENT));
}

/** Người dùng đang đăng nhập (null nếu chưa); tự cập nhật khi đăng nhập/đăng xuất ở tab này hoặc tab khác. */
export function useSession() {
  const [s, setS] = useState(read);
  useEffect(() => {
    const on = () => setS(read());
    window.addEventListener(EVENT, on);
    window.addEventListener("storage", on);
    return () => { window.removeEventListener(EVENT, on); window.removeEventListener("storage", on); };
  }, []);
  return s;
}
