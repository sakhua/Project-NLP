// Câu trả lời dạng markdown; mã [ND168_2024.D6.K9.b] được đổi thành chip bấm được, rê chuột xem nội dung.
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { shortLabel } from "../lib/format.js";

const BRACKET = /\[([^[\]]{3,300})\](?!\()/g;
const ID_G = /[A-Z]+\d+_\d{4}(?:\.[A-Za-z]?\d+[a-z]?|\.[a-zđ]\d?)*/g;

function withCiteLinks(text) {
  return (text || "").replace(BRACKET, (m, inner) => {
    const ids = inner.match(ID_G);
    if (!ids) return m;
    return ids.map((id) => `[${id}](#cite-${encodeURIComponent(id)})`).join("");
  });
}

function CiteChip({ id, unit, onCite }) {
  const [hover, setHover] = useState(false);
  return (
    <button className={`cite ${unit ? "" : "bad"}`} onClick={() => onCite?.(id)}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      {shortLabel(id)}
      {hover && (
        <span className="cite-tip">
          <b>{unit ? unit.ten : id}</b>
          {unit ? unit.noi_dung.slice(0, 260) + (unit.noi_dung.length > 260 ? "…" : "")
            : "Mã này không có trong ngữ cảnh được cung cấp cho mô hình."}
        </span>
      )}
    </button>
  );
}

export default function AnswerText({ text, units, onCite, streaming }) {
  const byId = useMemo(() => Object.fromEntries((units || []).map((u) => [u.id, u])), [units]);
  const md = useMemo(() => withCiteLinks(text), [text]);
  const components = useMemo(() => ({
    a({ href, children }) {
      if (href?.startsWith("#cite-")) {
        const id = decodeURIComponent(href.slice(6));
        return <CiteChip id={id} unit={byId[id]} onCite={onCite} />;
      }
      return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
    },
  }), [byId, onCite]);
  return (
    <div className={`answer ${streaming ? "cursor" : ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{md}</ReactMarkdown>
    </div>
  );
}
