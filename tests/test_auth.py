"""Kiểm thử đăng nhập bằng tài khoản có sẵn, không cần DB (PostgreSQL giả)."""
import json

from fastapi.testclient import TestClient

from backend.app import auth
from backend.app.main import app


def test_bam_mat_khau():
    h = auth.bam_mat_khau("matkhau123", so_vong=1000)
    assert h.startswith("pbkdf2_sha256$1000$") and "matkhau123" not in h
    assert auth.kiem_tra_mat_khau("matkhau123", h)
    assert not auth.kiem_tra_mat_khau("matkhau124", h)
    assert auth.bam_mat_khau("matkhau123", so_vong=1000) != h          # muối khác nhau
    assert not auth.kiem_tra_mat_khau("x", "hong")


def test_phien_ky_va_het_han():
    k = b"khoa-bi-mat"
    t = auth.tao_phien({"id": 7, "ten_dang_nhap": "khua"}, k, 3600, now=1000)
    assert auth.doc_phien(t, k, now=2000)["uid"] == 7
    assert auth.doc_phien(t, k, now=1000 + 3601) is None          # hết hạn
    assert auth.doc_phien(t, b"khoa-khac", now=2000) is None      # sai chữ ký
    head, body, sig = t.split(".")
    gia = auth._b64(json.dumps({"uid": 1, "ten": "x", "exp": 9e9}).encode())
    assert auth.doc_phien(f"{head}.{gia}.{sig}", k, now=2000) is None   # sửa nội dung thì chữ ký không khớp


def test_gioi_han_sai():
    g = auth.GioiHanSai(toi_da=3, cua_so=60)
    for _ in range(3):
        assert g.bi_khoa("u:a", now=100) == 0
        g.sai("u:a", now=100)
    assert g.bi_khoa("u:a", now=110) > 0 and g.bi_khoa("u:b", now=110) == 0
    assert g.bi_khoa("u:a", now=161) == 0                           # hết cửa sổ thì mở lại


class FakeDB:
    """Bảng tai_khoan giả: tài khoản 'khua' (mật khẩu 'dungroi123') và tài khoản 'cu' đã bị khóa."""

    def __init__(self):
        self.rows = {"khua": (5, "khua", auth.bam_mat_khau("dungroi123", 1000), "Sùng A Khua", True),
                     "cu": (6, "cu", auth.bam_mat_khau("dungroi123", 1000), "Cũ", False)}
        self.sql = []

    def cursor(self):
        db = self

        class C:
            r = None

            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def execute(s, q, p=None):
                db.sql.append(q)
                if "WHERE ten_dang_nhap" in q:
                    s.r = db.rows.get(p[0])
                elif "FROM tai_khoan WHERE id" in q:
                    s.r = next(((r[0], r[1], r[3], r[4]) for r in db.rows.values() if r[0] == p[0]), None)

            def fetchone(s):
                return s.r
        return C()

    def commit(self):
        pass


def test_dang_nhap(monkeypatch):
    db = FakeDB()

    class Pool:
        def connection(self):
            class Cm:
                def __enter__(s):
                    return db

                def __exit__(s, *a):
                    return False
            return Cm()

    monkeypatch.setattr(auth, "gioi_han", auth.GioiHanSai())
    with TestClient(app) as client:
        res = client.app.state.res
        res.cfg["auth"]["bat_buoc"] = True
        res.cfg["secrets"]["auth_secret"] = "s" * 40
        client.app.state.auth_secret = None
        monkeypatch.setattr(type(res), "pg_pool", property(lambda self: Pool()), raising=False)

        assert client.get("/api/auth/config").json() == {"bat_buoc": True}
        assert client.post("/api/ask", json={"question": "Ô tô vượt đèn đỏ?"}).status_code == 401
        assert client.get("/api/documents").status_code == 401
        assert client.get("/health").status_code == 200                     # health vẫn công khai
        assert client.post("/api/auth/register", json={}).status_code in (404, 405)   # không có đăng ký

        r = client.post("/api/auth/login", json={"ten_dang_nhap": "khua", "mat_khau": "sai"})
        assert r.status_code == 401 and "Sai tên đăng nhập" in r.json()["detail"]
        assert client.post("/api/auth/login", json={"ten_dang_nhap": "khong-co", "mat_khau": "x"}).status_code == 401
        assert client.post("/api/auth/login", json={"ten_dang_nhap": "cu", "mat_khau": "dungroi123"}).json()["detail"] \
            == "Tài khoản đã bị khóa"

        r = client.post("/api/auth/login", json={"ten_dang_nhap": " KHUA ", "mat_khau": "dungroi123"})
        assert r.status_code == 200
        body = r.json()
        assert body["nguoi_dung"] == {"id": 5, "ten_dang_nhap": "khua", "ho_ten": "Sùng A Khua"}
        assert any("CREATE TABLE IF NOT EXISTS tai_khoan" in q for q in db.sql)
        h = {"Authorization": "Bearer " + body["token"]}
        assert client.get("/api/auth/me", headers=h).json()["nguoi_dung"]["ten_dang_nhap"] == "khua"
        assert client.post("/api/ask", json={"question": "?"}, headers=h).status_code == 422   # qua được bước đăng nhập
        assert client.post("/api/ask", json={"question": "?"}, headers={"Authorization": "Bearer sai"}).status_code == 401

        for _ in range(5):
            client.post("/api/auth/login", json={"ten_dang_nhap": "khua", "mat_khau": "sai"})
        r = client.post("/api/auth/login", json={"ten_dang_nhap": "khua", "mat_khau": "dungroi123"})
        assert r.status_code == 429                                          # sai 5 lần → tạm khóa
        res.cfg["auth"]["bat_buoc"] = False
