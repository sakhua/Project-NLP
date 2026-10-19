// F1 Hỏi đáp + F4 Đánh giá câu trả lời. Phụ trách: TV3.
import { useState } from "react";
import { api, today } from "../api.js";

export default function AskPage({ onOpenGraph }) {
  const [question, setQuestion] = useState("");
  const [date, setDate] = useState(today());
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [rated, setRated] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setLoading(true); setError(""); setResult(null); setRated(false);
    try { setResult(await api.ask(question, date)); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  async function rate(v) {
    if (!result?.log_id) return;
    await api.feedback(result.log_id, v).catch(() => {});
    setRated(true);
  }

  return (
    <section>
      <form onSubmit={submit} className="card">
        <label>Câu hỏi
          <textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ví dụ: Ô tô vượt đèn đỏ bị phạt bao nhiêu tiền, trừ mấy điểm?" required minLength={5} />
        </label>
        <div className="row">
          <label>Ngày áp dụng <input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <button type="submit" disabled={loading}>{loading ? "Đang trả lời…" : "Hỏi"}</button>
        </div>
      </form>

      {error && <div className="banner error">{error}</div>}

      {result && (
        <div className="card">
          <h2>Trả lời</h2>
          <p className="answer">{result.answer}</p>
          <p className="muted">Áp dụng tại ngày {result.date} · {result.latency_ms} ms</p>
          <h3>Căn cứ</h3>
          <ul className="units">
            {result.units.map((u) => (
              <li key={u.id}>
                <button className="link" onClick={() => onOpenGraph(u.id)}>{u.id}</button>
                <span className="muted"> hiệu lực từ {u.hieu_luc_tu}{u.hieu_luc_den ? ` đến ${u.hieu_luc_den}` : ""}</span>
                <p>{u.noi_dung}</p>
              </li>
            ))}
          </ul>
          {result.log_id && (rated ? <p className="muted">Cảm ơn bạn đã đánh giá.</p> : (
            <div className="row">
              <span>Câu trả lời có hữu ích?</span>
              <button onClick={() => rate(1)}>Hữu ích</button>
              <button className="secondary" onClick={() => rate(-1)}>Chưa đúng</button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
