// F5 Thống kê: số liệu kho dữ liệu, đồ thị (công khai) và hoạt động hỏi đáp (cần mật khẩu quản trị). Phụ trách: TV1.
import { useEffect, useState } from "react";
import { Lock, LogOut, RefreshCw } from "lucide-react";
import { api } from "../api.js";
import { CAP_LABEL, EDGE_LABEL, fmtDate, fmtMs, fmtNum, shortLabel } from "../lib/format.js";
import { navigate } from "../lib/router.js";
import { EDGE_COLORS } from "../components/ContextGraph.jsx";

const MA_HT = { GRAPH: "Hybrid GraphRAG (đề xuất)", B1: "Hybrid RAG (B1)", B2: "GraphRAG kiểu Microsoft (B2)" };

const PW_KEY = "graphrag.admin";

function Bars({ data, colors, unit }) {
  const max = Math.max(1, ...data.map((d) => d.n));
  return (
    <div className="bars">
      {data.map((d) => (
        <div key={d.k} className="bar-row">
          <span>{d.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(100 * d.n) / max}%`, background: colors?.[d.k] }} /></div>
          <span className="n">{fmtNum(d.n)}{unit || ""}</span>
        </div>
      ))}
    </div>
  );
}

function Activity({ password, onLogout }) {
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const load = () => { setErr(""); api.stats(password).then(setS).catch((e) => { setErr(e.message); if (/mật khẩu/i.test(e.message)) onLogout(); }); };
  useEffect(load, [password]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <div className="banner error">{err}</div>;
  if (!s) return <div className="skeleton" style={{ height: 160 }} />;
  const t = s.tong;
  const rated = (t.huu_ich || 0) + (t.chua_dung || 0);
  const days = s.theo_ngay.slice(-14);
  const maxDay = Math.max(1, ...days.map((d) => d.so_cau));
  return (
    <>
      <div className="row" style={{ margin: "26px 0 12px" }}>
        <h2 style={{ margin: 0, fontSize: 18 }} className="grow">Hoạt động hỏi đáp</h2>
        <button className="btn sm" onClick={load}><RefreshCw size={14} /> Làm mới</button>
        <button className="btn sm ghost" onClick={onLogout}><LogOut size={14} /> Thoát</button>
      </div>
      <div className="kpis">
        <div className="kpi"><div className="v">{fmtNum(t.tong)}</div><div className="l">Câu hỏi đã trả lời</div></div>
        <div className="kpi"><div className="v">{rated ? `${Math.round((100 * t.huu_ich) / rated)}%` : "–"}</div><div className="l">Đánh giá hữu ích</div><div className="s">{t.huu_ich} hữu ích · {t.chua_dung} chưa đúng</div></div>
        <div className="kpi"><div className="v">{fmtMs(t.trung_vi_ms)}</div><div className="l">Thời gian trả lời (trung vị)</div><div className="s">trung bình {fmtMs(t.tb_ms)}</div></div>
        <div className="kpi"><div className="v">{t.tb_trich_dan ?? "–"}</div><div className="l">Trích dẫn mỗi câu trả lời</div></div>
      </div>
      <div className="grid-2">
        <div className="box">
          <h3>Số câu hỏi theo ngày</h3>
          {days.length === 0 ? <div className="muted small">Chưa có dữ liệu</div> : (
            <div className="cols">
              {days.map((d) => (
                <div key={d.ngay} className="col" title={`${d.so_cau} câu · TB ${fmtMs(d.tb_ms)}`}>
                  <small>{d.so_cau}</small>
                  <div className="col-bar" style={{ height: `${(110 * d.so_cau) / maxDay}px` }} />
                  <small>{fmtDate(d.ngay).slice(0, 5)}</small>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="box">
          <h3>Điều khoản được trích dẫn nhiều nhất</h3>
          <Bars data={(s.hay_trich_dan || []).map((r) => ({ k: r.ma, label: shortLabel(r.ma), n: r.n }))} />
        </div>
      </div>
      {(s.theo_he_thong || []).length > 0 && (
        <div className="box" style={{ marginBottom: 14 }}>
          <h3>Theo hệ thống</h3>
          <table className="tbl">
            <thead><tr><th>Hệ thống</th><th>Số câu</th><th>Thời gian TB</th><th>Trích dẫn TB</th><th>Hữu ích</th><th>Chưa đúng</th></tr></thead>
            <tbody>
              {s.theo_he_thong.map((r) => (
                <tr key={r.he_thong}><td>{MA_HT[r.he_thong] || r.he_thong}</td><td>{fmtNum(r.so_cau)}</td><td>{fmtMs(r.tb_ms)}</td>
                  <td>{r.tb_trich_dan ?? "–"}</td><td>{r.huu_ich}</td><td>{r.chua_dung}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="box" style={{ marginBottom: 14 }}>
        <h3>Câu hỏi gần đây</h3>
        <table className="tbl">
          <thead><tr><th>Thời gian</th><th>Câu hỏi</th><th>Hệ thống</th><th>Ngày áp dụng</th><th>Thời gian trả lời</th><th>Trích dẫn</th><th>Đánh giá</th></tr></thead>
          <tbody>
            {s.gan_day.map((r) => (
              <tr key={r.id}>
                <td className="muted">{new Date(r.thoi_gian).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}</td>
                <td>{r.cau_hoi}</td>
                <td className="muted nowrap">{r.he_thong || "GRAPH"}</td>
                <td>{fmtDate(r.ngay_ap_dung)}</td>
                <td>{fmtMs(r.latency_ms)}</td>
                <td>{r.so_trich_dan ?? 0}</td>
                <td>{r.danh_gia === 1 ? <span className="badge ok">Hữu ích</span> : r.danh_gia === -1 ? <span className="badge danger">Chưa đúng</span> : <span className="muted">–</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {s.bi_danh_gia_sai.length > 0 && (
        <div className="box">
          <h3>Câu trả lời bị đánh giá chưa đúng</h3>
          <table className="tbl"><tbody>
            {s.bi_danh_gia_sai.map((r) => (
              <tr key={r.id}><td style={{ width: "35%" }}><b>{r.cau_hoi}</b></td><td className="muted">{r.tra_loi?.slice(0, 260)}…</td></tr>
            ))}
          </tbody></table>
        </div>
      )}
    </>
  );
}

export default function AdminPage() {
  const [ov, setOv] = useState(null);
  const [err, setErr] = useState("");
  const [pw, setPw] = useState(() => { try { return sessionStorage.getItem(PW_KEY) || ""; } catch { return ""; } });
  const [input, setInput] = useState("");
  useEffect(() => { api.overview().then(setOv).catch((e) => setErr(e.message)); }, []);
  const login = (e) => { e.preventDefault(); setPw(input); try { sessionStorage.setItem(PW_KEY, input); } catch { /* */ } };
  const logout = () => { setPw(""); try { sessionStorage.removeItem(PW_KEY); } catch { /* */ } };
  const pg = ov?.postgres, g = ov?.neo4j;
  return (
    <div className="page">
      <div className="page-inner">
        <h1 className="page-title">Thống kê hệ thống</h1>
        <p className="page-sub">Kho văn bản, đồ thị tri thức và hoạt động hỏi đáp.</p>
        {err && <div className="banner error">{err}</div>}
        {!ov && !err && <div className="skeleton" style={{ height: 120 }} />}
        {ov && (
          <>
            <div className="kpis">
              <div className="kpi"><div className="v">{fmtNum(pg.van_ban)}</div><div className="l">Văn bản</div><div className="s">5 gốc · 6 sửa đổi · 1 hợp nhất</div></div>
              <div className="kpi"><div className="v">{fmtNum(pg.don_vi)}</div><div className="l">Điều khoản (Chương → Điểm)</div></div>
              <div className="kpi"><div className="v">{fmtNum(pg.phien_ban)}</div><div className="l">Phiên bản theo thời gian</div><div className="s">{fmtNum(pg.phien_ban_sua_doi)} do văn bản sửa đổi tạo ra</div></div>
              <div className="kpi"><div className="v">{fmtNum(pg.co_embedding)}</div><div className="l">Phiên bản có embedding</div><div className="s">{ov.mo_hinh.embedding}</div></div>
              <div className="kpi"><div className="v">{fmtNum(g?.tong_node)}</div><div className="l">Node đồ thị (Neo4j)</div></div>
              <div className="kpi"><div className="v">{fmtNum(g?.tong_canh)}</div><div className="l">Cạnh đồ thị</div></div>
              <div className="kpi"><div className="v">{fmtNum(ov.so_cau_hoi)}</div><div className="l">Câu hỏi đã trả lời</div></div>
              <div className="kpi"><div className="v">{ov.ms_graphrag?.ms_thuc_the ? fmtNum(ov.ms_graphrag.ms_thuc_the) : "–"}</div><div className="l">Thực thể (GraphRAG kiểu Microsoft)</div>
                <div className="s">{ov.ms_graphrag?.ms_thuc_the ? `${fmtNum(ov.ms_graphrag.ms_quan_he)} quan hệ · ${fmtNum(ov.ms_graphrag.ms_cong_dong)} cộng đồng` : "chưa dựng chỉ mục (scripts/05)"}</div></div>
              <div className="kpi"><div className="v" style={{ fontSize: 15, paddingTop: 8 }}>{ov.mo_hinh.llm}</div><div className="l">Mô hình sinh câu trả lời</div><div className="s">rerank: {ov.mo_hinh.reranker || "tắt"}</div></div>
            </div>
            <div className="grid-2">
              <div className="box">
                <h3>Cạnh theo loại quan hệ</h3>
                {g?.canh ? <Bars colors={EDGE_COLORS} data={Object.entries(g.canh).sort((a, b) => b[1] - a[1]).map(([k, n]) => ({ k, label: EDGE_LABEL[k] || k, n }))} />
                  : <div className="muted small">Neo4j chưa kết nối</div>}
              </div>
              <div className="box">
                <h3>Điều khoản theo cấp</h3>
                <Bars data={["Chuong", "Dieu", "Khoan", "Diem"].map((k) => ({ k, label: CAP_LABEL[k], n: pg.theo_cap[k] || 0 }))} />
                <div className="muted small" style={{ marginTop: 12 }}>Xem các điều khoản đã thay đổi ở trang <a href="#/history" onClick={(e) => { e.preventDefault(); navigate("history"); }}>Lịch sử sửa đổi</a>.</div>
              </div>
            </div>
          </>
        )}
        {pw ? <Activity password={pw} onLogout={logout} /> : (
          <form className="box login" style={{ marginTop: 26 }} onSubmit={login}>
            <h3 className="row"><Lock size={15} /> Hoạt động hỏi đáp (quản trị viên)</h3>
            <p className="muted small" style={{ marginTop: 0 }}>Nhập mật khẩu quản trị (ADMIN_PASSWORD trong .env).</p>
            <div className="row">
              <input className="input" type="password" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Mật khẩu" />
              <button className="btn primary" type="submit">Xem</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
