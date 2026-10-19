// F5 Thống kê cho quản trị viên. Phụ trách: TV3 (giao diện), TV1 (API).
import { useState } from "react";
import { api } from "../api.js";

export default function AdminPage() {
  const [password, setPassword] = useState("");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try { setStats(await api.stats(password)); } catch (err) { setError(err.message); }
  }

  return (
    <section>
      <form className="card row" onSubmit={submit}>
        <label>Mật khẩu quản trị <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        <button type="submit">Xem thống kê</button>
      </form>
      {error && <div className="banner error">{error}</div>}
      {stats && (
        <>
          <div className="stats">
            <div className="card"><b>{stats.tong.tong}</b><span>lượt hỏi</span></div>
            <div className="card"><b>{stats.tong.huu_ich}</b><span>đánh giá hữu ích</span></div>
            <div className="card"><b>{stats.tong.chua_dung}</b><span>đánh giá chưa đúng</span></div>
          </div>
          <div className="card">
            <h3>Theo ngày (30 ngày gần nhất)</h3>
            <table>
              <thead><tr><th>Ngày</th><th>Số câu hỏi</th><th>Thời gian TB (ms)</th></tr></thead>
              <tbody>{stats.theo_ngay.map((r) => <tr key={r.ngay}><td>{r.ngay}</td><td>{r.so_cau}</td><td>{r.tb_ms}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="card">
            <h3>Câu trả lời bị đánh giá chưa đúng</h3>
            <ul className="units">
              {stats.bi_danh_gia_sai.map((r) => <li key={r.id}><b>{r.cau_hoi}</b><p>{r.tra_loi}</p>{r.ghi_chu && <p className="muted">Ghi chú: {r.ghi_chu}</p>}</li>)}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
