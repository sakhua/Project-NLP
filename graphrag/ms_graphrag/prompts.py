"""Prompt của GraphRAG kiểu Microsoft (Edge và cộng sự, 2024), chuyển sang tiếng Việt và lĩnh vực luật giao thông.

Cấu trúc giữ theo bản gốc: trích thực thể + quan hệ (entity_extraction), tóm tắt mô tả (summarize_descriptions),
báo cáo cộng đồng (community_report), global search (map / reduce). Khác bản gốc: đầu ra JSON thay cho chuỗi phân cách,
và đơn vị văn bản là khoản/điểm thay cho đoạn cắt theo token.
"""
from __future__ import annotations

LOAI_THUC_THE = {
    "HANH_VI": "hành vi vi phạm hoặc hành vi được quy định (vd. không chấp hành hiệu lệnh của đèn tín hiệu giao thông)",
    "PHUONG_TIEN": "loại phương tiện (vd. xe ô tô, xe mô tô, xe đạp, xe máy chuyên dùng)",
    "CHU_THE": "người hoặc tổ chức chịu quy định (vd. người điều khiển xe, chủ xe, hành khách, tổ chức kinh doanh vận tải)",
    "CHE_TAI": "hình thức xử lý cụ thể (vd. phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng, trừ 04 điểm giấy phép lái xe, "
               "tước quyền sử dụng giấy phép lái xe, tịch thu phương tiện, phạt cảnh cáo)",
    "DIEU_KIEN": "ngưỡng, điều kiện, tình tiết (vd. nồng độ cồn vượt quá 80 miligam/100 mililít máu, chạy quá tốc độ trên 35 km/h, "
                 "gây tai nạn giao thông, người từ đủ 16 tuổi đến dưới 18 tuổi)",
    "GIAY_TO": "giấy tờ, thiết bị, thủ tục (vd. giấy phép lái xe, chứng nhận đăng ký xe, thiết bị giám sát hành trình)",
    "CO_QUAN": "cơ quan, người có thẩm quyền (vd. Chủ tịch Ủy ban nhân dân cấp xã, Cảnh sát giao thông)",
    "KHAI_NIEM": "khái niệm, địa điểm, loại đường (vd. đường cao tốc, khu đông dân cư, đường đôi, điểm giấy phép lái xe)",
}

EXTRACT_SYSTEM = """Bạn là chuyên gia xây dựng đồ thị tri thức từ văn bản pháp luật giao thông đường bộ Việt Nam.

MỤC TIÊU: Từ ĐOẠN VĂN BẢN, xác định mọi thực thể thuộc các loại dưới đây và mọi quan hệ rõ ràng giữa các thực thể đó.

LOẠI THỰC THỂ:
{loai}

CÁC BƯỚC:
1. Xác định thực thể. Với mỗi thực thể ghi:
   - ten: tên chuẩn, viết thường, ngắn gọn, giữ đúng thuật ngữ và con số trong văn bản (cùng một khái niệm ở các đoạn khác nhau phải
     cùng một tên, vd. luôn viết "xe ô tô", "giấy phép lái xe", "phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng");
   - loai: một trong các loại ở trên;
   - mo_ta: mô tả đầy đủ thuộc tính và vai trò của thực thể theo đoạn văn bản này.
2. Xác định quan hệ giữa các cặp thực thể ở bước 1 có liên quan rõ ràng với nhau. Với mỗi quan hệ ghi:
   - nguon, dich: tên thực thể (đúng như ở bước 1);
   - mo_ta: vì sao hai thực thể liên quan (vd. "người điều khiển xe ô tô vượt đèn đỏ bị phạt tiền ở mức này");
   - do_manh: số nguyên 1–10, mức độ gắn kết.
3. Chỉ dùng thông tin trong đoạn văn bản, không suy diễn. Hành vi, chủ thể, phương tiện, chế tài phải được nối với nhau khi đoạn văn bản
   quy định chúng cùng nhau.

Chỉ trả về JSON đúng dạng:
{{"thuc_the": [{{"ten": "...", "loai": "...", "mo_ta": "..."}}], "quan_he": [{{"nguon": "...", "dich": "...", "mo_ta": "...", "do_manh": 8}}]}}

VÍ DỤ
ĐOẠN VĂN BẢN: Nghị định 168/2024/NĐ-CP, Điều 6. Xử phạt người điều khiển xe ô tô… – khoản 9: Phạt tiền từ 18.000.000 đồng đến
20.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;
KẾT QUẢ:
{{"thuc_the": [
 {{"ten": "không chấp hành hiệu lệnh của đèn tín hiệu giao thông", "loai": "HANH_VI", "mo_ta": "Hành vi vượt đèn đỏ, không tuân theo đèn tín hiệu giao thông"}},
 {{"ten": "người điều khiển xe ô tô", "loai": "CHU_THE", "mo_ta": "Người lái xe ô tô và các loại xe tương tự xe ô tô, đối tượng bị xử phạt tại Điều 6 Nghị định 168/2024"}},
 {{"ten": "xe ô tô", "loai": "PHUONG_TIEN", "mo_ta": "Phương tiện được quy định tại Điều 6 Nghị định 168/2024"}},
 {{"ten": "phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng", "loai": "CHE_TAI", "mo_ta": "Mức phạt tiền tại khoản 9 Điều 6 Nghị định 168/2024"}}],
 "quan_he": [
 {{"nguon": "người điều khiển xe ô tô", "dich": "không chấp hành hiệu lệnh của đèn tín hiệu giao thông", "mo_ta": "Người lái ô tô thực hiện hành vi không chấp hành đèn tín hiệu thì bị xử phạt", "do_manh": 9}},
 {{"nguon": "không chấp hành hiệu lệnh của đèn tín hiệu giao thông", "dich": "phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng", "mo_ta": "Mức phạt đối với người lái ô tô không chấp hành đèn tín hiệu", "do_manh": 10}},
 {{"nguon": "người điều khiển xe ô tô", "dich": "xe ô tô", "mo_ta": "Người điều khiển loại phương tiện này", "do_manh": 6}}]}}
"""

EXTRACT_USER = """ĐOẠN VĂN BẢN:
{text}

KẾT QUẢ (chỉ JSON):"""

GLEANING_USER = """ĐOẠN VĂN BẢN:
{text}

KẾT QUẢ ĐÃ TRÍCH:
{prev}

Còn NHIỀU thực thể và quan hệ trong đoạn văn bản chưa được trích. Chỉ trả về JSON cùng dạng gồm các thực thể và quan hệ CÒN THIẾU
(trả về {{"thuc_the": [], "quan_he": []}} nếu không còn gì):"""

SUMMARIZE_SYSTEM = """Bạn là trợ lý tổng hợp thông tin pháp luật giao thông. Cho một hoặc hai thực thể và danh sách các mô tả về chúng
(lấy từ nhiều điều khoản khác nhau), hãy viết MỘT đoạn mô tả tổng hợp, đầy đủ, không mâu thuẫn, bằng tiếng Việt, ở ngôi thứ ba,
có nhắc tên thực thể. Nếu các mô tả mâu thuẫn, nêu cả hai và điều kiện áp dụng. Tối đa 120 từ. Chỉ trả về đoạn mô tả."""

SUMMARIZE_USER = """THỰC THỂ: {ten}
CÁC MÔ TẢ:
{mo_ta}

MÔ TẢ TỔNG HỢP:"""

REPORT_SYSTEM = """Bạn là chuyên gia pháp luật giao thông đường bộ Việt Nam, viết báo cáo về một CỘNG ĐỒNG trong đồ thị tri thức
(một nhóm thực thể liên quan chặt chẽ: hành vi, chủ thể, phương tiện, chế tài, điều kiện…).

Báo cáo giúp người đọc nắm nhanh nhóm quy định này: những hành vi nào, ai chịu, mức xử lý ra sao, điều kiện đặc biệt nào.
Chỉ dùng thông tin trong dữ liệu được cung cấp, giữ nguyên các con số (mức tiền, số điểm, tốc độ, nồng độ).

Chỉ trả về JSON đúng dạng:
{"tieu_de": "tên ngắn của cộng đồng, nêu các thực thể chính",
 "tom_tat": "tóm tắt 3–5 câu về cấu trúc và nội dung chính",
 "muc_do": số thực 0–10 (mức độ quan trọng đối với người dân khi tra cứu luật giao thông),
 "ly_do_muc_do": "một câu giải thích",
 "phat_hien": [{"tom_tat": "một phát hiện chính", "giai_thich": "giải thích 2–4 câu, có số liệu cụ thể"}]}
Viết 3–6 phát hiện."""

REPORT_USER = """DỮ LIỆU CỘNG ĐỒNG

Thực thể:
{thuc_the}

Quan hệ:
{quan_he}
{con}
BÁO CÁO (chỉ JSON):"""

MAP_SYSTEM = """Bạn là trợ lý pháp luật giao thông. Từ các BÁO CÁO CỘNG ĐỒNG dưới đây, liệt kê các ý giúp trả lời CÂU HỎI.
Mỗi ý có điểm 0–100 thể hiện mức độ hữu ích để trả lời câu hỏi. Ghi mã báo cáo làm căn cứ, ví dụ [CĐ 12].
Không có ý nào liên quan thì trả về danh sách rỗng. Chỉ dùng thông tin trong báo cáo.
Chỉ trả về JSON: {"y": [{"mo_ta": "nội dung ý, kèm [CĐ mã]", "diem": 80}]}"""

MAP_USER = """BÁO CÁO CỘNG ĐỒNG:
{bao_cao}

CÂU HỎI: {question}
JSON:"""

REDUCE_SYSTEM = """Bạn là trợ lý tra cứu pháp luật giao thông đường bộ Việt Nam. Trả lời CÂU HỎI tổng quan của người dân dựa trên
các Ý do nhiều nhà phân tích tổng hợp từ báo cáo cộng đồng của đồ thị tri thức (ý xếp theo mức độ hữu ích giảm dần).
Trả lời bằng tiếng Việt, có cấu trúc (đề mục, gạch đầu dòng), giữ đúng các con số, giữ mã [CĐ …] làm căn cứ.
Không bịa thông tin ngoài các ý được cung cấp. Nếu các ý không đủ để trả lời, nói rõ là chưa đủ thông tin.
Cuối câu trả lời ghi: "Câu trả lời tổng hợp từ báo cáo cộng đồng của đồ thị, chưa đối chiếu ngày áp dụng của từng điều khoản."."""

REDUCE_USER = """CÁC Ý:
{y}

CÂU HỎI: {question}"""

LOCAL_EXTRA_HEADER = """
THÔNG TIN TỪ ĐỒ THỊ THỰC THỂ (GraphRAG: dùng để hiểu mối liên hệ; căn cứ trả lời và trích dẫn vẫn là các điều khoản trong NGỮ CẢNH):
"""
