// Trang đăng nhập bằng tài khoản có sẵn (không có đăng ký; tài khoản do nhóm tạo bằng scripts/tao_tai_khoan.py).
import { useState } from "react";
import { Eye, EyeOff, LogIn, Scale } from "lucide-react";
import { api } from "../api.js";
import { saveSession } from "../lib/auth.js";

export default function LoginPage() {
  const [ten, setTen] = useState("");
  const [mk, setMk] = useState("");
  const [hien, setHien] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!ten.trim() || !mk) return;
    setBusy(true);
    setErr("");
    try {
      saveSession(await api.login(ten.trim(), mk));
    } catch (e2) {
      setErr(e2.message);
      setMk("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-mark login-mark"><Scale size={22} /></div>
        <h1>Luật Giao thông AI</h1>
        <p className="muted">Hỏi đáp pháp luật giao thông đường bộ Việt Nam dựa trên GraphRAG.</p>
        <label className="field">
          <span>Tên đăng nhập</span>
          <input className="input" autoComplete="username" autoFocus value={ten}
            onChange={(e) => setTen(e.target.value)} disabled={busy} />
        </label>
        <label className="field">
          <span>Mật khẩu</span>
          <div className="pw-wrap">
            <input className="input" type={hien ? "text" : "password"} autoComplete="current-password" value={mk}
              onChange={(e) => setMk(e.target.value)} disabled={busy} />
            <button type="button" className="icon-btn" title={hien ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
              onClick={() => setHien(!hien)}>{hien ? <EyeOff size={16} /> : <Eye size={16} />}</button>
          </div>
        </label>
        {err && <div className="banner error">{err}</div>}
        <button className="btn primary login-submit" type="submit" disabled={busy || !ten.trim() || !mk}>
          <LogIn size={16} /> {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </button>
        <p className="muted small">Chưa có tài khoản? Liên hệ nhóm phát triển để được cấp.</p>
      </form>
    </div>
  );
}
