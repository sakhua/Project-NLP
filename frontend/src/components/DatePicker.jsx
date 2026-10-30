// Chọn ngày áp dụng: ô nhập ngày + các mốc hay dùng khi demo.
import { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronDown } from "lucide-react";
import { today } from "../api.js";
import { DATE_PRESETS } from "../lib/demo.js";
import { fmtDate } from "../lib/format.js";

export default function DatePicker({ value, onChange, label = "Áp dụng tại" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const pick = (v) => { onChange(v); setOpen(false); };
  return (
    <div className="popover-wrap" ref={ref}>
      <button className="date-chip" onClick={() => setOpen((o) => !o)} title="Ngày áp dụng: hệ thống chỉ dùng điều khoản còn hiệu lực vào ngày này">
        <CalendarDays size={15} /> {label} <b>{fmtDate(value)}</b> <ChevronDown size={14} />
      </button>
      {open && (
        <div className="popover">
          <div className="small muted" style={{ marginBottom: 6 }}>Ngày áp dụng</div>
          <input className="input" type="date" value={value} onChange={(e) => e.target.value && pick(e.target.value)} />
          <div style={{ marginTop: 8 }}>
            <button className="preset" onClick={() => pick(today())}><span>Hôm nay</span><span className="muted">{fmtDate(today())}</span></button>
            {DATE_PRESETS.map((p) => (
              <button key={p.value} className="preset" onClick={() => pick(p.value)}>
                <span>{p.label}</span><span className="muted">{p.hint}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
