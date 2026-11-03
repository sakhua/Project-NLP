// Lưu các cuộc trò chuyện trong trình duyệt (localStorage) để thanh bên hiện lịch sử, tải lại trang không mất.
// Mở nhiều tab cùng lúc: các tab đồng bộ với nhau qua sự kiện "storage" (gộp theo id, giữ bản cập nhật sau cùng),
// nên tab này không ghi đè mất cuộc trò chuyện của tab kia.
import { useCallback, useEffect, useState } from "react";
import { storage, uid } from "./format.js";

const KEY = "graphrag.conversations.v1";
const MAX = 40;

const stamp = (c) => c.updatedAt || c.createdAt || 0;

function load() {
  return storage.get(KEY, []).map((c) => ({
    ...c,   // câu đang trả lời dở khi tải lại trang: đánh dấu lỗi để có thể bấm "Thử lại"
    messages: c.messages.map((m) => (m.status === "streaming" ? { ...m, status: "error", error: "Bị gián đoạn khi tải lại trang." } : m)),
  }));
}

function merge(mine, theirs) {
  const by = new Map(mine.map((c) => [c.id, c]));
  for (const c of theirs) {
    const m = by.get(c.id);
    if (!m || stamp(c) > stamp(m)) by.set(c.id, c);
  }
  return [...by.values()].sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0)).slice(0, MAX);
}

export function useConversations() {
  const [list, setList] = useState(load);

  useEffect(() => {   // ghi trễ 400 ms: khi đang nhận chữ chạy dần không ghi liên tục
    const t = setTimeout(() => storage.set(KEY, list.slice(0, MAX)), 400);
    return () => clearTimeout(t);
  }, [list]);

  useEffect(() => {   // tab khác vừa ghi: gộp vào danh sách của tab này
    const on = (e) => {
      if (e.key !== KEY) return;
      const theirs = storage.get(KEY, []);
      setList((mine) => {
        const merged = merge(mine, theirs);
        return JSON.stringify(merged) === JSON.stringify(mine) ? mine : merged;
      });
    };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);

  const create = useCallback((title, date) => {
    const now = Date.now();
    const conv = { id: uid(), title: title.slice(0, 80), date, createdAt: now, updatedAt: now, messages: [] };
    setList((l) => [conv, ...l]);
    return conv.id;
  }, []);
  const update = useCallback((id, fn) => setList((l) => l.map((c) => (c.id === id ? { ...fn(c), updatedAt: Date.now() } : c))), []);
  const remove = useCallback((id) => setList((l) => l.filter((c) => c.id !== id)), []);
  const clear = useCallback(() => setList([]), []);
  return { list, create, update, remove, clear };
}
