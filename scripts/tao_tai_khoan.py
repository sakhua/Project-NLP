"""Quản lý tài khoản đăng nhập giao diện web (hệ thống không có trang đăng ký).

  python scripts/tao_tai_khoan.py them khua --ho-ten "Sùng A Khua"     # hỏi mật khẩu (gõ không hiện chữ)
  python scripts/tao_tai_khoan.py them taikhoan1 --mat-khau "Matkhau123@"   # đặt mật khẩu ngay trong lệnh
  python scripts/tao_tai_khoan.py doi-mat-khau khua
  python scripts/tao_tai_khoan.py khoa khua            # không cho đăng nhập nữa (giữ lịch sử)
  python scripts/tao_tai_khoan.py mo-khoa khua
  python scripts/tao_tai_khoan.py ds                   # liệt kê tài khoản
  python scripts/tao_tai_khoan.py ds --env cloud       # trên Supabase (bản triển khai Render)

Mật khẩu chỉ lưu dạng băm PBKDF2-SHA256 có muối; không ai (kể cả nhóm) đọc lại được mật khẩu gốc.
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.app import auth  # noqa: E402
from graphrag.common.config import load_config  # noqa: E402
from graphrag.storage import postgres  # noqa: E402


def nhap_mat_khau() -> str:
    while True:
        a = getpass.getpass("Mật khẩu (ít nhất 8 ký tự): ")
        if len(a) < 8:
            print("  Quá ngắn.")
            continue
        if getpass.getpass("Nhập lại: ") != a:
            print("  Hai lần nhập không khớp.")
            continue
        return a


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lenh", choices=["them", "doi-mat-khau", "khoa", "mo-khoa", "ds"])
    ap.add_argument("ten", nargs="?", help="tên đăng nhập (chữ thường, số, dấu . _ -)")
    ap.add_argument("--ho-ten", help="tên hiển thị trên giao diện")
    ap.add_argument("--mat-khau", help="đặt mật khẩu trong lệnh (bỏ trống thì hỏi, gõ không hiện chữ)")
    ap.add_argument("--env", default="local", choices=["local", "cloud"])
    args = ap.parse_args()
    conn = postgres.connect(load_config(args.env))
    auth.dam_bao_bang(conn)
    ten = auth.chuan_ten(args.ten or "")
    if args.lenh != "ds":
        if not re.fullmatch(r"[a-z0-9._-]{3,64}", ten):
            sys.exit("Tên đăng nhập 3–64 ký tự, chỉ gồm chữ thường không dấu, số và . _ -")
    with conn.cursor() as cur:
        if args.lenh == "ds":
            cur.execute("SELECT ten_dang_nhap, ho_ten, hoat_dong, tao_luc, dang_nhap_cuoi, so_lan_dang_nhap "
                        "FROM tai_khoan ORDER BY id")
            rows = cur.fetchall()
            print(f"{len(rows)} tài khoản")
            for t, h, hd, tao, cuoi, n in rows:
                print(f"  {t:<20} {h or '':<25} {'hoạt động' if hd else 'ĐÃ KHÓA':<10} "
                      f"tạo {tao:%d/%m/%Y} · đăng nhập {n} lần" + (f", gần nhất {cuoi:%d/%m/%Y %H:%M}" if cuoi else ""))
        elif args.lenh == "them":
            if auth.tim_tai_khoan(conn, ten):
                sys.exit(f"Đã có tài khoản {ten}. Dùng lệnh doi-mat-khau để đổi mật khẩu.")
            cur.execute("INSERT INTO tai_khoan (ten_dang_nhap, mat_khau_bam, ho_ten) VALUES (%s, %s, %s)",
                        (ten, auth.bam_mat_khau(args.mat_khau or nhap_mat_khau()), args.ho_ten or ten))
            print(f"Đã tạo tài khoản {ten}.")
        else:
            if not auth.tim_tai_khoan(conn, ten):
                sys.exit(f"Không có tài khoản {ten}.")
            if args.lenh == "doi-mat-khau":
                cur.execute("UPDATE tai_khoan SET mat_khau_bam = %s WHERE ten_dang_nhap = %s",
                            (auth.bam_mat_khau(args.mat_khau or nhap_mat_khau()), ten))
            else:
                cur.execute("UPDATE tai_khoan SET hoat_dong = %s WHERE ten_dang_nhap = %s", (args.lenh == "mo-khoa", ten))
            if args.ho_ten:
                cur.execute("UPDATE tai_khoan SET ho_ten = %s WHERE ten_dang_nhap = %s", (args.ho_ten, ten))
            print(f"Đã cập nhật tài khoản {ten}.")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
