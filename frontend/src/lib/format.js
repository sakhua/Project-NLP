// Định dạng ngày, nhãn, mã điều khoản dùng chung cho mọi trang.

export const fmtDate = (d) => {
  if (!d) return "";
  const [y, m, day] = String(d).slice(0, 10).split("-");
  return `${day}/${m}/${y}`;
};

export const fmtMs = (ms) => (ms == null ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace(".", ",")} giây`);

export const fmtNum = (n) => (n == null ? "–" : Number(n).toLocaleString("vi-VN"));

const LOAI = { L: "Luật", ND: "NĐ", TT: "TT", VBHN: "VBHN" };
const LOAI_DAI = { L: "Luật", ND: "Nghị định", TT: "Thông tư", VBHN: "Văn bản hợp nhất" };

export function docShort(docId) {
  const m = /^([A-Z]+)(\d+)_(\d{4})$/.exec(docId || "");
  return m ? `${LOAI[m[1]] || m[1]} ${m[2]}/${m[3]}` : docId;
}

export function docLong(docId) {
  const m = /^([A-Z]+)(\d+)_(\d{4})$/.exec(docId || "");
  return m ? `${LOAI_DAI[m[1]] || m[1]} ${m[2]}/${m[3]}` : docId;
}

const ID_RE = /^([A-Z]+\d+_\d{4})(?:\.C(\d+)|(?:\.D(\d+[a-z]?))?(?:\.K(\d+[a-z]?))?(?:\.([a-zđ]\d?))?)$/;

export function parseId(uid) {
  const m = ID_RE.exec((uid || "").split("@")[0]);
  if (!m) return null;
  return { doc: m[1], chuong: m[2], dieu: m[3], khoan: m[4], diem: m[5] };
}

/** 'ND168_2024.D6.K9.b' -> 'Đ6.K9.b · NĐ 168/2024' */
export function shortLabel(uid) {
  const p = parseId(uid);
  if (!p) return uid;
  if (p.chuong) return `Chương ${p.chuong} · ${docShort(p.doc)}`;
  const parts = [p.dieu && `Đ${p.dieu}`, p.khoan && `K${p.khoan}`, p.diem].filter(Boolean);
  return parts.length ? `${parts.join(".")} · ${docShort(p.doc)}` : docShort(p.doc);
}

/** 'ND168_2024.D6.K9.b' -> 'điểm b khoản 9 Điều 6 NĐ 168/2024' */
export function longLabel(uid) {
  const p = parseId(uid);
  if (!p) return uid;
  const parts = [p.diem && `điểm ${p.diem}`, p.khoan && `khoản ${p.khoan}`, p.dieu && `Điều ${p.dieu}`,
    p.chuong && `Chương ${p.chuong}`].filter(Boolean);
  return `${parts.join(" ")} ${docLong(p.doc)}`.trim();
}

export const CAP_LABEL = { VanBan: "Văn bản", Chuong: "Chương", Dieu: "Điều", Khoan: "Khoản", Diem: "Điểm" };

export const EDGE_LABEL = {
  THAM_CHIEU: "Dẫn chiếu",
  THUOC: "Thuộc",
  HUONG_DAN: "Hướng dẫn",
  SUA_DOI: "Sửa đổi",
  BO_SUNG: "Bổ sung",
  THAY_THE: "Thay thế",
  BAI_BO: "Bãi bỏ",
};

export const VERSION_LABEL = { goc: "Bản gốc", sua_doi: "Sửa đổi", bo_sung: "Bổ sung", thay_the: "Thay thế" };

export const ROLE_LABEL = { seed: "Tìm trực tiếp", graph: "Từ đồ thị", path: "Trung gian" };

/** Mã điều khoản trong ngoặc vuông của câu trả lời: [ND168_2024.D6.K9.b] */
export const CITE_RE = /\[([A-Z]+\d+_\d{4}(?:\.[A-Za-z]?\d+[a-z]?|\.[a-zđ]\d?)*)\]/g;

export const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

export const storage = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(key);
      return v ? JSON.parse(v) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* đầy bộ nhớ hoặc chế độ riêng tư: bỏ qua */
    }
  },
};

/** So sánh hai đoạn văn theo từ (LCS), trả về [{type: 'same'|'add'|'del', text}] để tô màu thay đổi. */
export function diffWords(a, b) {
  const A = (a || "").split(/(\s+)/), B = (b || "").split(/(\s+)/);
  const n = A.length, m = B.length;
  if (n * m > 400000) return [{ type: "del", text: a }, { type: "add", text: b }];
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  const push = (type, text) => {
    const last = out[out.length - 1];
    if (last && last.type === type) last.text += text;
    else out.push({ type, text });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { push("same", A[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { push("del", A[i]); i++; }
    else { push("add", B[j]); j++; }
  }
  while (i < n) push("del", A[i++]);
  while (j < m) push("add", B[j++]);
  return out;
}
