// Câu hỏi gợi ý trên màn hình trò chuyện mới. Trùng với kịch bản trong docs/kich_ban_demo.md.
export const SUGGESTIONS = [
  {
    tag: "Mức phạt",
    question: "Ô tô vượt đèn đỏ bị phạt bao nhiêu tiền?",
  },
  {
    tag: "Trừ điểm (đồ thị)",
    question: "Lái ô tô vượt đèn đỏ có bị trừ điểm giấy phép lái xe không?",
  },
  {
    tag: "Hiệu lực theo ngày",
    question: "Chở trẻ em dưới 10 tuổi ngồi ghế trước ô tô bị xử phạt thế nào?",
    date: "2026-09-01",
  },
  {
    tag: "Nồng độ cồn",
    question: "Lái ô tô mà nồng độ cồn vượt quá 0,4 miligam/1 lít khí thở bị xử phạt thế nào?",
  },
  {
    tag: "Nhiều bước",
    question: "Ô tô con chạy 75 km/h trên đường đôi trong khu đông dân cư thì bị phạt thế nào?",
  },
  {
    tag: "Phục hồi điểm",
    question: "Giấy phép lái xe bị trừ hết điểm thì làm thế nào để được phục hồi?",
  },
];

// Ngày áp dụng hay dùng khi demo (đổi nhanh trong ô chọn ngày)
export const DATE_PRESETS = [
  { label: "01/10/2025", value: "2025-10-01", hint: "trước khi điểm m có hiệu lực" },
  { label: "01/03/2026", value: "2026-03-01", hint: "bản gốc NĐ 168" },
  { label: "01/09/2026", value: "2026-09-01", hint: "sau NĐ 238" },
];
