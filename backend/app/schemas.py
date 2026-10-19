"""Định dạng dữ liệu vào/ra của API (cũng là đặc tả API cho báo cáo, xem /docs)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000, examples=["Ô tô vượt đèn đỏ bị phạt bao nhiêu?"])
    date: dt.date | None = Field(default=None, description="Ngày áp dụng; bỏ trống = hôm nay")


class Unit(BaseModel):
    id: str
    noi_dung: str
    tieu_de: str | None = None
    hieu_luc_tu: dt.date | None = None
    hieu_luc_den: dt.date | None = None


class AskResponse(BaseModel):
    log_id: int | None
    answer: str
    citations: list[str]
    units: list[Unit]
    date: dt.date
    latency_ms: int


class FeedbackRequest(BaseModel):
    log_id: int
    rating: int = Field(description="1 = hữu ích, -1 = chưa đúng")
    note: str | None = Field(default=None, max_length=1000)
