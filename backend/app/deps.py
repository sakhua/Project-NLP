"""Phụ thuộc dùng chung cho các router."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request

from graphrag.resources import Resources


def get_res(request: Request) -> Resources:
    return request.app.state.res


def require_admin(request: Request, x_admin_password: str = Header(default="")) -> None:
    """Quản trị viên gửi mật khẩu qua header X-Admin-Password (ADMIN_PASSWORD trên Render)."""
    expected = request.app.state.res.cfg["secrets"]["admin_password"]
    if not expected or not secrets.compare_digest(x_admin_password, expected):
        raise HTTPException(status_code=401, detail="Sai mật khẩu quản trị")
