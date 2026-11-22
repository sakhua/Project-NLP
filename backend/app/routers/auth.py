"""Đăng nhập bằng tài khoản có sẵn (không có đăng ký). Xem backend/app/auth.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth
from ..deps import get_res

router = APIRouter(tags=["đăng nhập"])


class DangNhap(BaseModel):
    ten_dang_nhap: str = Field(min_length=1, max_length=64)
    mat_khau: str = Field(min_length=1, max_length=200)


@router.get("/auth/config")
def auth_config(request: Request):
    """Giao diện đọc để biết có phải đăng nhập không."""
    return {"bat_buoc": auth.cau_hinh(request.app.state.res.cfg)["bat"]}


@router.post("/auth/login")
def login(body: DangNhap, request: Request, res=Depends(get_res)):
    ch = auth.cau_hinh(res.cfg)
    if not ch["bat"]:
        raise HTTPException(status_code=400, detail="Hệ thống không yêu cầu đăng nhập")
    ten = auth.chuan_ten(body.ten_dang_nhap)
    ip = request.client.host if request.client else "?"
    khoa = ("u:" + ten, "ip:" + ip)
    con = auth.gioi_han.bi_khoa(*khoa)
    if con:
        raise HTTPException(status_code=429, detail=f"Sai quá nhiều lần. Thử lại sau {con} giây.")
    with res.pg_pool.connection() as conn:
        auth.dam_bao_bang(conn)
        tk = auth.tim_tai_khoan(conn, ten)
        ok = auth.kiem_tra_mat_khau(body.mat_khau, tk["mat_khau_bam"] if tk else auth._BAM_GIA) and bool(tk)
        if not ok or not tk["hoat_dong"]:
            auth.gioi_han.sai(*khoa)
            raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu"
                                if not ok else "Tài khoản đã bị khóa")
        auth.ghi_dang_nhap(conn, tk["id"])
    auth.gioi_han.dung(*khoa)
    user = {"id": tk["id"], "ten_dang_nhap": tk["ten_dang_nhap"], "ho_ten": tk["ho_ten"]}
    return {"token": auth.tao_phien(user, auth.khoa_ky(request), ch["han_giay"]), "han_giay": ch["han_giay"],
            "nguoi_dung": user}


@router.get("/auth/me")
def me(res=Depends(get_res), user=Depends(auth.require_user)):
    if user is None:
        return {"nguoi_dung": None, "bat_buoc": False}
    with res.pg_pool.connection() as conn:
        tk = auth.lay_tai_khoan(conn, user["id"])
    if not tk or not tk["hoat_dong"]:
        raise HTTPException(status_code=401, detail="Tài khoản không còn hiệu lực")
    return {"nguoi_dung": {k: tk[k] for k in ("id", "ten_dang_nhap", "ho_ten")}, "bat_buoc": True}
