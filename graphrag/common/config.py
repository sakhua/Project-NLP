"""Đọc cấu hình theo môi trường chạy.

Hai môi trường (chọn bằng biến APP_ENV, mặc định "local"):
  local  – máy của nhóm, dùng cho môn NLP: PostgreSQL/Neo4j trong Docker
  cloud  – bản triển khai môn Điện toán đám mây: Supabase + Neo4j AuraDB
Cả hai dùng chung mô hình qua OpenRouter (LLM, embedding bge-m3, rerank), khai báo ở base.yaml.

Thứ tự đọc:
  1. configs/base.yaml           (tham số chung)
  2. configs/<APP_ENV>.yaml      (ghi đè theo môi trường)
  3. file .env.<APP_ENV> nếu có, nếu không thì .env   (mật khẩu, API key)
  4. biến môi trường thật (trên Render khai báo ở mục Environment) luôn được ưu tiên
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(os.getenv("GRAPHRAG_ROOT") or Path(__file__).resolve().parents[2])


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _load_env_file(env: str) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for name in (f".env.{env}", ".env"):
        p = ROOT / name
        if p.exists():
            load_dotenv(p, override=False)  # không ghi đè biến môi trường đã có
            return


def load_config(env: str | None = None) -> dict[str, Any]:
    import yaml

    env = env or os.getenv("APP_ENV", "local")
    _load_env_file(env)

    with open(ROOT / "configs" / "base.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    env_file = ROOT / "configs" / f"{env}.yaml"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})

    # PostgreSQL: Supabase cho một chuỗi DATABASE_URL; máy local dùng các biến POSTGRES_*
    cfg["postgres"] = {"dsn": os.getenv("DATABASE_URL") or (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'luat_gt')} user={os.getenv('POSTGRES_USER', 'graphrag')} "
        f"password={os.getenv('POSTGRES_PASSWORD', '')}"
    )}
    cfg["neo4j"] = {
        "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", ""),
    }
    cfg["secrets"] = {
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "admin_password": os.getenv("ADMIN_PASSWORD", ""),
    }
    cfg["env"] = env
    cfg["root"] = ROOT
    return cfg
