"""Gọi thử mô hình sinh (llm.model) trên từng khóa API trước khi chạy thật: tên mô hình có đúng không, mô hình có nhận
temperature / max_tokens / reasoning_effort không, mỗi lượt tốn bao nhiêu token và tiền.

  python scripts/thu_mo_hinh.py                 # thử mọi khóa trong llm.nha_cung_cap (OpenAI, OpenRouter)
  python scripts/thu_mo_hinh.py --model openai/gpt-6-luna --chi openai

Chi phí: 2 lượt gọi ngắn cho mỗi khóa (dưới 0,001 USD).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graphrag.common.config import load_config  # noqa: E402
from graphrag.openrouter import BASE_URL, OPENAI_URL, OpenRouter, OpenRouterError, _ten_mo_hinh  # noqa: E402

CAU_HOI = "Theo Nghị định 168/2024, người lái ô tô vượt đèn đỏ bị phạt bao nhiêu? Trả lời một câu."


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default="local", choices=["local", "cloud"])
    ap.add_argument("--model", help="mặc định llm.model trong configs/base.yaml")
    ap.add_argument("--chi", choices=["openai", "openrouter"], help="chỉ thử một khóa")
    args = ap.parse_args()
    cfg = load_config(args.env)
    c = cfg["llm"]
    model = args.model or c["model"]
    gia = c.get("gia_usd_trieu_token") or {}
    khoa = {"openai": cfg["secrets"].get("openai_api_key", ""), "openrouter": cfg["secrets"].get("openrouter_api_key", "")}
    url = {"openai": OPENAI_URL, "openrouter": BASE_URL}
    print(f"Mô hình: {model} · temperature {c.get('temperature')} · max_tokens {c.get('max_tokens')} · "
          f"reasoning_effort {c.get('reasoning_effort') or '(mặc định)'}")
    for ten in ([args.chi] if args.chi else c.get("nha_cung_cap", ["openai", "openrouter"])):
        m = _ten_mo_hinh(ten, model)
        print(f"\n== {ten} ({m}) ==")
        if not khoa.get(ten):
            print("  bỏ qua: chưa có khóa trong .env")
            continue
        if m is None:
            print("  bỏ qua: nhà cung cấp này không có mô hình này")
            continue
        cl = OpenRouter(khoa[ten], base_url=url[ten], ten=ten)
        for lan, (t, mt) in enumerate([(c.get("temperature", 0.0), c.get("max_tokens")), (0.0, 60)], 1):
            t0 = time.time()
            try:
                out = cl.chat(m, "Bạn là trợ lý pháp luật giao thông.", CAU_HOI, t, mt, c.get("reasoning_effort"))
            except OpenRouterError as e:
                print(f"  Lượt {lan}: LỖI {e}")
                break
            print(f"  Lượt {lan} ({time.time() - t0:.1f} giây): {out.strip()[:160]!r}")
        u = cl.usage
        if u["calls"]:
            usd = ((u["prompt"] - u["cached"]) * gia.get("vao", 0) + u["cached"] * gia.get("vao_cache", 0)
                   + u["completion"] * gia.get("ra", 0)) / 1e6
            print(f"  Token: vào {u['prompt']} · ra {u['completion']} (trong đó suy luận {u['reasoning']}) · "
                  f"≈ {usd:.5f} USD cho {u['calls']} lượt")
            if u["reasoning"]:
                print("  Mô hình có sinh token suy luận (tính tiền như token ra). Nếu nhiều, đặt llm.reasoning_effort: low "
                      "(hoặc minimal) trong configs/base.yaml.")
        bo = cl.bo_tham_so.get(m)
        if bo:
            print(f"  Mô hình không nhận: {', '.join(sorted(bo))} → client tự bỏ khi gọi, không cần sửa gì.")
        cl.close()


if __name__ == "__main__":
    main()
