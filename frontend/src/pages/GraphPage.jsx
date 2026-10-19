// F3 Đồ thị liên kết quanh một điều khoản (vẽ SVG hình tròn, không cần thư viện). Phụ trách: TV3.
import { useEffect, useState } from "react";
import { api } from "../api.js";

const W = 640, H = 440, R = 160;

export default function GraphPage({ initialId }) {
  const [uid, setUid] = useState(initialId || "");
  const [g, setG] = useState(null);
  const [error, setError] = useState("");

  const load = (id) => {
    if (!id) return;
    setError(""); setG(null);
    api.graph(id).then(setG).catch((e) => setError(e.message));
  };
  useEffect(() => { load(initialId); }, [initialId]);

  const n = g?.neighbors.length || 0;
  const pos = (i) => [W / 2 + R * Math.cos((2 * Math.PI * i) / n), H / 2 + R * Math.sin((2 * Math.PI * i) / n)];

  return (
    <section>
      <form className="card row" onSubmit={(e) => { e.preventDefault(); load(uid.trim()); }}>
        <label>Mã điều khoản <input value={uid} onChange={(e) => setUid(e.target.value)} placeholder="ND168_2024.D6.K5" /></label>
        <button type="submit">Xem đồ thị</button>
      </form>
      {error && <div className="banner error">{error}</div>}
      {g && (
        <div className="card">
          <svg viewBox={`0 0 ${W} ${H}`} className="graph" role="img" aria-label={`Đồ thị quanh ${g.center.id}`}>
            {g.neighbors.map((m, i) => {
              const [x, y] = pos(i);
              return (
                <g key={m.id + m.rel}>
                  <line x1={W / 2} y1={H / 2} x2={x} y2={y} className="edge" />
                  <text x={(W / 2 + x) / 2} y={(H / 2 + y) / 2 - 4} className="rel">{m.rel}</text>
                  <circle cx={x} cy={y} r={8} className="node" onClick={() => { setUid(m.id); load(m.id); }} />
                  <text x={x} y={y + 22} className="lbl">{m.id}</text>
                </g>
              );
            })}
            <circle cx={W / 2} cy={H / 2} r={12} className="node center" />
            <text x={W / 2} y={H / 2 + 28} className="lbl center">{g.center.id}</text>
          </svg>
          <p className="muted">Bấm vào một nút để xem đồ thị quanh nút đó.</p>
        </div>
      )}
    </section>
  );
}
