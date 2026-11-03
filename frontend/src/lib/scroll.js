// Cuộn một phần tử vào giữa khung cuộn gần nhất của nó.
// Không dùng element.scrollIntoView(): hàm đó cuộn cả các khung cha (kể cả khung có overflow: hidden),
// làm cả giao diện bị "nhảy".
export function scrollIntoContainer(el, container, { block = "center", smooth = true } = {}) {
  if (!el || !container) return;
  const c = container.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  let top = container.scrollTop + (r.top - c.top);
  if (block === "center") top -= (container.clientHeight - r.height) / 2;
  container.scrollTo({ top: Math.max(0, top), behavior: smooth ? "smooth" : "auto" });
}

export const nearBottom = (el, px = 160) => !el || el.scrollHeight - el.scrollTop - el.clientHeight < px;
