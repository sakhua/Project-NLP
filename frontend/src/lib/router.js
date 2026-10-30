// Điều hướng bằng hash (#/chat/abc, #/docs/ND168_2024?unit=…): không cần thư viện, tải lại trang vẫn giữ vị trí.
import { useEffect, useState } from "react";

function parse() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  const [page = "chat", ...rest] = path.split("/").filter(Boolean);
  return { page, param: rest.length ? decodeURIComponent(rest.join("/")) : null, query: new URLSearchParams(qs || "") };
}

export function useRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function navigate(page, param, query) {
  let h = `#/${page}`;
  if (param) h += `/${encodeURIComponent(param)}`;
  if (query) {
    const qs = new URLSearchParams(Object.entries(query).filter(([, v]) => v != null && v !== "")).toString();
    if (qs) h += `?${qs}`;
  }
  window.location.hash = h;
}
