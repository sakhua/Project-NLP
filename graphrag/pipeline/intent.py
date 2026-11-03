"""Phân loại câu hỏi trước khi tra cứu: chào hỏi, cảm ơn, hỏi về trợ lý, ngoài phạm vi, hay câu hỏi pháp luật giao thông.

Hai tầng để nhanh và rẻ:
  1. Luật (regex), không gọi LLM:
     - câu chào / cảm ơn / tạm biệt / hỏi "bạn là ai" ngắn → trả lời mẫu;
     - câu có từ khóa giao thông (xe, phạt, giấy phép lái xe, tốc độ, nồng độ cồn…) → tra cứu như bình thường.
  2. Không khớp luật nào: hỏi LLM một nhãn (LUAT / NGOAI). LLM lỗi thì coi là câu hỏi pháp luật (không chặn nhầm).
Chỉ câu hỏi pháp luật mới chạy tìm kiếm + đồ thị; các loại còn lại trả lời mẫu, không tốn embedding/rerank.
"""
from __future__ import annotations

import re
import unicodedata

LUAT, CHAO, CAM_ON, TAM_BIET, GIOI_THIEU, NGOAI = "luat", "chao", "cam_on", "tam_biet", "gioi_thieu", "ngoai_pham_vi"

EXAMPLES = ("Ví dụ:\n"
            "- Ô tô vượt đèn đỏ bị phạt bao nhiêu tiền?\n"
            "- Lái xe máy mà nồng độ cồn vượt mức thì bị xử phạt thế nào?\n"
            "- Giấy phép lái xe bị trừ hết điểm thì làm sao để phục hồi?")

REPLIES = {
    CHAO: ("Xin chào! Mình là trợ lý tra cứu **pháp luật giao thông đường bộ Việt Nam**. "
           "Bạn có thể hỏi về mức phạt, trừ điểm giấy phép lái xe, tốc độ, nồng độ cồn, quy tắc giao thông… "
           "và chọn ngày áp dụng để nhận câu trả lời đúng với quy định có hiệu lực vào ngày đó.\n\n" + EXAMPLES),
    CAM_ON: "Rất vui được hỗ trợ bạn! Nếu còn thắc mắc về luật giao thông đường bộ, cứ hỏi tiếp nhé.",
    TAM_BIET: "Tạm biệt bạn! Chúc bạn tham gia giao thông an toàn.",
    GIOI_THIEU: ("Mình là trợ lý hỏi đáp **pháp luật giao thông đường bộ Việt Nam**, trả lời dựa trên Luật Trật tự, "
                 "an toàn giao thông đường bộ 2024, Nghị định 168/2024 về xử phạt, trừ điểm giấy phép lái xe và các "
                 "văn bản sửa đổi, hướng dẫn. Mỗi câu trả lời có trích dẫn điều khoản, đúng với ngày áp dụng bạn chọn.\n\n"
                 + EXAMPLES),
    NGOAI: ("Câu hỏi này **không thuộc phạm vi hỗ trợ** của hệ thống. Mình chỉ trả lời các câu hỏi về "
            "pháp luật giao thông đường bộ Việt Nam: mức phạt, trừ điểm và tước giấy phép lái xe, tốc độ, nồng độ cồn, "
            "quy tắc tham gia giao thông, phục hồi điểm giấy phép lái xe…\n\n" + EXAMPLES),
}


def _norm(s: str) -> str:
    """Chữ thường, bỏ dấu (để khớp cả khi người dùng gõ không dấu), gộp khoảng trắng, bỏ dấu câu."""
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _words(*phrases: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(_norm(p).replace(" ", r"\s+") for p in phrases) + r")\b")


# Câu xã giao (cả câu chỉ gồm các cụm này, cộng vài từ đệm)
_FILLER = r"(?:\s+(?:ban|ad|admin|bot|tro ly|nhe|nha|a|ah|nhieu|lam|ban nhe|shop|minh|em|anh|chi|ạ))*"
_SOCIAL = [
    (CHAO, re.compile(r"^(?:xin chao|chao|hello|hi|hey|alo|a lo|chao buoi (?:sang|trua|chieu|toi))" + _FILLER + r"$")),
    (CAM_ON, re.compile(r"^(?:cam on|cam ơn|thanks|thank you|thank|tks|ok cam on|cảm ơn)" + _FILLER + r"$")),
    (TAM_BIET, re.compile(r"^(?:tam biet|bye|goodbye|hen gap lai)" + _FILLER + r"$")),
    (GIOI_THIEU, re.compile(r"^(?:ban la ai|ban la gi|ban lam duoc gi|ban giup duoc gi|ban co the lam gi|"
                            r"gioi thieu ve ban|ban ho tro (?:gi|nhung gi)|he thong (?:nay )?(?:la gi|lam duoc gi))" + _FILLER + r"$")),
]

# Từ khóa chắc chắn thuộc lĩnh vực giao thông đường bộ (đã bỏ dấu)
_DOMAIN = _words(
    "xe", "o to", "oto", "xe may", "mo to", "xe dap", "xe tai", "xe khach", "container", "phuong tien",
    "lai xe", "nguoi lai", "dieu khien", "cho nguoi", "cho tre em", "cho hang",
    "giao thong", "duong bo", "cao toc", "nga tu", "lan duong", "phan duong", "vach ke", "bien bao", "den do",
    "den tin hieu", "vuot den", "toc do", "km h", "nong do con", "uong ruou", "ruou bia", "ma tuy",
    "giay phep lai xe", "gplx", "bang lai", "tru diem", "phuc hoi diem", "tuoc", "tam giu",
    "phat", "muc phat", "xu phat", "vi pham", "csgt", "canh sat giao thong", "phat nguoi",
    "mu bao hiem", "day an toan", "dang kiem", "dang ky xe", "bien so", "do xe", "dung xe", "quay dau", "vuot xe",
    "luat 36", "nghi dinh 168", "nghi dinh 151", "thong tu 38", "thong tu 65", "trat tu an toan",
)

CLASSIFY_SYSTEM = """Bạn phân loại câu hỏi gửi tới một trợ lý chỉ trả lời về PHÁP LUẬT GIAO THÔNG ĐƯỜNG BỘ VIỆT NAM \
(mức phạt, trừ điểm/tước giấy phép lái xe, tốc độ, nồng độ cồn, quy tắc giao thông, đăng ký, giấy tờ xe, \
phục hồi điểm, trách nhiệm của người tham gia giao thông…).
Trả lời đúng MỘT từ:
LUAT  nếu câu hỏi liên quan tới giao thông đường bộ hoặc luật giao thông (kể cả câu hỏi tiếp nối, hỏi chung chung về luật này);
NGOAI nếu câu hỏi về chủ đề khác (tài chính, cổ phiếu, giá vàng, thời tiết, thể thao, lập trình, y tế, luật lĩnh vực khác…)."""


def classify(question: str, llm=None) -> tuple[str, str]:
    """Trả về (nhãn, cách xác định: 'luật' | 'LLM' | 'mặc định')."""
    n = _norm(question)
    if not n:
        return CHAO, "luật"
    for label, pat in _SOCIAL:
        if pat.match(n):
            return label, "luật"
    if _DOMAIN.search(n):
        return LUAT, "luật"
    if llm is None:
        return LUAT, "mặc định"
    try:
        out = llm.generate(CLASSIFY_SYSTEM, f"CÂU HỎI: {question.strip()}\nNHÃN:").strip().upper()
    except Exception:  # noqa: BLE001 – lỗi gọi mô hình: không chặn câu hỏi
        return LUAT, "mặc định"
    return (NGOAI if out.startswith("NGOAI") or out.startswith("NGOÀI") else LUAT), "LLM"


LABELS = {LUAT: "Câu hỏi pháp luật giao thông", CHAO: "Lời chào", CAM_ON: "Lời cảm ơn", TAM_BIET: "Lời tạm biệt",
          GIOI_THIEU: "Hỏi về trợ lý", NGOAI: "Ngoài phạm vi hỗ trợ"}
