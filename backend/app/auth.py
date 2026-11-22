"""Đăng nhập bằng tên đăng nhập + mật khẩu cho giao diện web. KHÔNG có đăng ký: tài khoản do nhóm tạo sẵn bằng
`python scripts/tao_tai_khoan.py` (thêm, đổi mật khẩu, khóa, liệt kê).

Luồng: POST /api/auth/login {ten_dang_nhap, mat_khau} → so mật khẩu với bản băm PBKDF2-SHA256 trong bảng tai_khoan →
trả phiên đăng nhập (chuỗi ký HMAC-SHA256 dạng JWT, hết hạn sau auth.han_phien_ngay ngày). Các API hỏi đáp, tra cứu,
đồ thị, đánh giá yêu cầu header "Authorization: Bearer <phiên>". Sai mật khẩu nhiều lần thì tạm khóa đăng nhập.

Bật/tắt bằng auth.bat_buoc trong configs/base.yaml. Script đánh giá gọi thẳng pipeline nên không bị ảnh hưởng.
Mật khẩu chỉ lưu dạng băm có muối (salt); khóa ký phiên lấy từ biến môi trường AUTH_SECRET.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

log = logging.getLogger("graphrag")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tai_khoan (
  id               BIGSERIAL PRIMARY KEY,
  ten_dang_nhap    TEXT UNIQUE NOT NULL,     -- chữ thường, không dấu cách
  mat_khau_bam     TEXT NOT NULL,            -- pbkdf2_sha256$số_vòng$muối$băm
  ho_ten           TEXT,
  hoat_dong        BOOLEAN NOT NULL DEFAULT true,
  tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
  dang_nhap_cuoi   TIMESTAMPTZ,
  so_lan_dang_nhap INTEGER NOT NULL DEFAULT 0
);
ALTER TABLE hoi_dap_log ADD COLUMN IF NOT EXISTS tai_khoan_id BIGINT REFERENCES tai_khoan(id);
"""

SO_VONG = 310_000             # PBKDF2-SHA256 (khuyến nghị OWASP)
SAI_TOI_DA, KHOA_GIAY = 5, 300  # sai 5 lần trong 5 phút → tạm khóa tên đăng nhập / địa chỉ IP đó 5 phút


# ---------------------------------------------------------------- mật khẩu

def bam_mat_khau(mat_khau: str, so_vong: int = SO_VONG) -> str:
    muoi = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", mat_khau.encode("utf-8"), muoi.encode(), so_vong).hex()
    return f"pbkdf2_sha256${so_vong}${muoi}${h}"


def kiem_tra_mat_khau(mat_khau: str, ban_bam: str) -> bool:
    try:
        alg, so_vong, muoi, h = ban_bam.split("$")
        if alg != "pbkdf2_sha256":
            return False
        tinh = hashlib.pbkdf2_hmac("sha256", mat_khau.encode("utf-8"), muoi.encode(), int(so_vong)).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(tinh, h)


_BAM_GIA = bam_mat_khau("khong-ton-tai")   # so với bản băm giả khi tên đăng nhập không có, để thời gian trả lời như nhau


def chuan_ten(ten: str) -> str:
    return (ten or "").strip().lower()


# ---------------------------------------------------------------- cấu hình

def cau_hinh(cfg: dict) -> dict:
    a = cfg.get("auth", {})
    return {"bat": bool(a.get("bat_buoc", True)), "han_giay": int(a.get("han_phien_ngay", 7)) * 86400}


def khoa_ky(request: Request) -> bytes:
    """AUTH_SECRET; chưa đặt thì sinh ngẫu nhiên khi khởi động (khởi động lại → mọi người phải đăng nhập lại)."""
    st = request.app.state
    if not getattr(st, "auth_secret", None):
        s = st.res.cfg["secrets"].get("auth_secret", "")
        if not s:
            log.warning("Chưa đặt AUTH_SECRET: dùng khóa ngẫu nhiên, khởi động lại server thì phiên đăng nhập mất hiệu lực")
            s = secrets.token_urlsafe(48)
        st.auth_secret = s.encode()
    return st.auth_secret


# ---------------------------------------------------------------- phiên đăng nhập (HS256)

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def tao_phien(user: dict, khoa: bytes, han_giay: int, now: float | None = None) -> str:
    now = int(now or time.time())
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"uid": user["id"], "ten": user["ten_dang_nhap"], "iat": now,
                            "exp": now + han_giay}).encode())
    sig = _b64(hmac.new(khoa, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def doc_phien(token: str, khoa: bytes, now: float | None = None) -> dict | None:
    try:
        head, body, sig = token.split(".")
        dung = _b64(hmac.new(khoa, f"{head}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, dung):
            return None
        data = json.loads(_unb64(body))
    except Exception:  # noqa: BLE001
        return None
    return data if data.get("exp", 0) > (now or time.time()) else None


# ---------------------------------------------------------------- chống dò mật khẩu

class GioiHanSai:
    """Đếm số lần sai theo khóa (tên đăng nhập, IP) trong cửa sổ KHOA_GIAY giây, lưu trong bộ nhớ tiến trình."""

    def __init__(self, toi_da: int = SAI_TOI_DA, cua_so: int = KHOA_GIAY):
        self.toi_da, self.cua_so = toi_da, cua_so
        self.lan: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def _don(self, k: str, now: float) -> deque:
        q = self.lan[k]
        while q and q[0] < now - self.cua_so:
            q.popleft()
        return q

    def bi_khoa(self, *khoa: str, now: float | None = None) -> int:
        """Số giây còn bị khóa (0 = không khóa)."""
        now = now or time.time()
        with self.lock:
            con = [int(self._don(k, now)[0] + self.cua_so - now) + 1 for k in khoa if len(self._don(k, now)) >= self.toi_da]
        return max(con, default=0)

    def sai(self, *khoa: str, now: float | None = None) -> None:
        now = now or time.time()
        with self.lock:
            for k in khoa:
                self._don(k, now).append(now)

    def dung(self, *khoa: str) -> None:
        with self.lock:
            for k in khoa:
                self.lan.pop(k, None)


gioi_han = GioiHanSai()


# ---------------------------------------------------------------- cơ sở dữ liệu

def dam_bao_bang(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()


def tim_tai_khoan(conn, ten_dang_nhap: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ten_dang_nhap, mat_khau_bam, ho_ten, hoat_dong FROM tai_khoan WHERE ten_dang_nhap = %s",
                    (chuan_ten(ten_dang_nhap),))
        r = cur.fetchone()
    return {"id": r[0], "ten_dang_nhap": r[1], "mat_khau_bam": r[2], "ho_ten": r[3], "hoat_dong": r[4]} if r else None


def ghi_dang_nhap(conn, uid: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE tai_khoan SET dang_nhap_cuoi = now(), so_lan_dang_nhap = so_lan_dang_nhap + 1 WHERE id = %s",
                    (uid,))
    conn.commit()


def lay_tai_khoan(conn, uid: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, ten_dang_nhap, ho_ten, hoat_dong FROM tai_khoan WHERE id = %s", (uid,))
        r = cur.fetchone()
    return {"id": r[0], "ten_dang_nhap": r[1], "ho_ten": r[2], "hoat_dong": r[3]} if r else None


# ---------------------------------------------------------------- phụ thuộc FastAPI

def require_user(request: Request, authorization: str = Header(default="")) -> dict | None:
    """Bắt buộc đăng nhập khi auth.bat_buoc = true; tắt thì trả None và cho qua."""
    if not cau_hinh(request.app.state.res.cfg)["bat"]:
        return None
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    data = doc_phien(token, khoa_ky(request)) if token else None
    if not data:
        raise HTTPException(status_code=401, detail="Cần đăng nhập", headers={"WWW-Authenticate": "Bearer"})
    return {"id": data["uid"], "ten_dang_nhap": data["ten"]}
