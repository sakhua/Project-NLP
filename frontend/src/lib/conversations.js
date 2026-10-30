// Lưu các cuộc trò chuyện trong trình duyệt (localStorage) để thanh bên hiện lịch sử, tải lại trang không mất.
import { useCallback, useEffect, useState } from "react";
import { storage, uid } from "./format.js";

const KEY = "graphrag.conversations.v1";
const MAX = 40;

export function useConversations() {
  const [list, setList] = useState(() => storage.get(KEY, []).map((c) => ({
    ...c,   // câu đang trả lời dở khi tải lại trang: đánh dấu lỗi để có thể bấm "Thử lại"
    messages: c.messages.map((m) => (m.status === "streaming" ? { ...m, status: "error", error: "Bị gián đoạn khi tải lại trang." } : m)),
  })));
  useEffect(() => {   // ghi trễ 400 ms: khi đang nhận chữ chạy dần không ghi liên tục
    const t = setTimeout(() => storage.set(KEY, list.slice(0, MAX)), 400);
    return () => clearTimeout(t);
  }, [list]);

  const create = useCallback((title, date) => {
    const conv = { id: uid(), title: title.slice(0, 80), date, createdAt: Date.now(), messages: [] };
    setList((l) => [conv, ...l]);
    return conv.id;
  }, []);
  const update = useCallback((id, fn) => setList((l) => l.map((c) => (c.id === id ? fn(c) : c))), []);
  const remove = useCallback((id) => setList((l) => l.filter((c) => c.id !== id)), []);
  const clear = useCallback(() => setList([]), []);
  return { list, create, update, remove, clear };
}
