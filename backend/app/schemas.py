"""Định dạng dữ liệu vào/ra của API (cũng là đặc tả API cho báo cáo, xem /docs)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, examples=["Ô tô vượt đèn đỏ bị phạt bao nhiêu?"])
    date: dt.date | None = Field(default=None, description="Ngày áp dụng; bỏ trống = hôm nay")
    history: list[ChatTurn] = Field(default_factory=list, max_length=12,
                                    description="Các lượt trước trong cuộc trò chuyện (để hiểu câu hỏi tiếp nối)")
    he_thong: Literal["hybrid_graphrag", "hybrid_rag", "ms_graphrag"] = Field(
        default="hybrid_graphrag", description="hybrid_graphrag: hệ thống đề xuất · hybrid_rag: B1 · ms_graphrag: B2")
    che_do: Literal["local", "global"] = Field(default="local", description="Chỉ dùng cho ms_graphrag")


class AskResponse(BaseModel):
    log_id: int | None
    question: str
    question_rewritten: str | None = None
    date: dt.date
    answer: str
    citations: list[str]
    unknown_citations: list[str] = []
    units: list[dict[str, Any]]
    graph: dict[str, Any]
    notes: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    he_thong: str = "hybrid_graphrag"
    che_do: str | None = None
    graph_context: dict[str, Any] | None = None
    latency_ms: int


class FeedbackRequest(BaseModel):
    log_id: int
    rating: int = Field(description="1 = hữu ích, -1 = chưa đúng")
    note: str | None = Field(default=None, max_length=1000)
