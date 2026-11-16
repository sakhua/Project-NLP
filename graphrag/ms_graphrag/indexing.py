"""Dựng chỉ mục GraphRAG kiểu Microsoft (Edge và cộng sự, 2024, "From Local to Global"), cài đặt lại cho đề tài.

Các bước (giống bản gốc, khác ở chỗ đánh dấu *):
  1. Đơn vị văn bản: *mỗi phiên bản khoản/điểm/Điều (kèm ngữ cảnh: văn bản, Điều, câu dẫn khoản) là một đơn vị,
     thay cho đoạn cắt theo token, để câu trả lời trích dẫn được mã điều khoản và lọc được theo ngày áp dụng.
  2. LLM trích thực thể + quan hệ cho từng đơn vị (*đầu ra JSON, loại thực thể riêng cho luật giao thông), có thể "gleaning".
  3. Gộp thực thể cùng tên, quan hệ cùng cặp; LLM tóm tắt khi một thực thể/quan hệ có nhiều mô tả.
  4. Phân cộng đồng phân cấp bằng Leiden (cộng đồng lớn hơn max_cluster_size được chia tiếp ở cấp sau).
  5. LLM viết báo cáo cho từng cộng đồng, từ cấp sâu nhất lên (cộng đồng quá lớn dùng báo cáo của cộng đồng con).
  6. Embedding mô tả thực thể và tóm tắt cộng đồng (bge-m3, cùng embedder với hệ thống).
Mọi bước gọi LLM đều lưu đệm vào file, chạy lại thì bỏ qua phần đã xong (không tốn tiền lần hai).
Hàm nhận `llm` có .generate(system, user) -> str nên kiểm thử được bằng mô hình giả.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from graphrag.ms_graphrag import prompts as P

_AMEND = re.compile(r"^\s*(Sửa đổi|Bổ sung|Bãi bỏ|Thay thế|Thay cụm từ|Thay từ|Bỏ cụm từ|Bỏ từ)", re.IGNORECASE)
UU_TIEN_VB = ["ND168_2024", "TT38_2024", "L36_2024", "TT65_2024", "ND151_2024"]


# ---------------------------------------------------------------- tiện ích

def chuan_hoa(ten: str) -> str:
    """Khóa gộp thực thể: Unicode NFC, chữ thường, bỏ dấu câu ở hai đầu, gộp khoảng trắng."""
    s = unicodedata.normalize("NFC", str(ten)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .,;:\"'“”‘’()[]")


def doc_json(text: str) -> dict | None:
    """Lấy đối tượng JSON đầu tiên trong câu trả lời của LLM (bỏ ```json … ``` nếu có)."""
    if not text:
        return None
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        try:   # lỗi hay gặp: dấu phẩy thừa trước ] hoặc }
            return json.loads(re.sub(r",\s*([\]}])", r"\1", text[a:b + 1]))
        except json.JSONDecodeError:
            return None


def doc_jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()] if p.exists() else []


def ghi_jsonl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(p)


class Cache:
    """File JSONL chỉ ghi thêm: {"k": khóa, "v": giá trị}. Nhiều luồng cùng ghi an toàn."""

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        self.data = {r["k"]: r["v"] for r in doc_jsonl(path)}

    def __contains__(self, k: str) -> bool:
        return k in self.data

    def get(self, k: str, default=None):
        return self.data.get(k, default)

    def put(self, k: str, v) -> None:
        with self.lock:
            self.data[k] = v
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")


def chay_song_song(items: list, fn: Callable, workers: int, tien_do: Callable[[int, int], None] | None = None) -> None:
    """Chạy fn(item) cho mọi item; lỗi của một item không dừng cả quá trình (fn tự ghi lỗi)."""
    n = len(items)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(fn, it) for it in items]
        for i, f in enumerate(as_completed(futs), 1):
            f.result()
            if tien_do:
                tien_do(i, n)


# ---------------------------------------------------------------- 1. đơn vị văn bản

def don_vi_van_ban(versions: list[dict], van_ban: list[str] | None = None, gioi_han: int | None = None) -> list[dict]:
    """Các phiên bản khoản/điểm/Điều có nội dung (bỏ chương, tiêu đề Điều trống, câu lệnh sửa đổi)."""
    out = []
    for v in versions:
        if v["cap"] == "Chuong" or len(v["noi_dung"] or "") < 25 or _AMEND.match(v["noi_dung"]):
            continue
        if van_ban and v["van_ban_id"] not in van_ban:
            continue
        out.append({"vid": v["vid"], "id": v["id"], "van_ban_id": v["van_ban_id"],
                    "text": f"{v.get('ngu_canh') or ''}\n{v['noi_dung']}".strip()})
    rank = {d: i for i, d in enumerate(UU_TIEN_VB)}
    thu_tu = {v["vid"]: i for i, v in enumerate(versions)}
    out.sort(key=lambda u: (rank.get(u["van_ban_id"], 99), thu_tu[u["vid"]]))
    if gioi_han and gioi_han < len(out):     # lấy rải đều cả văn bản (không chỉ các Điều đầu) để thử chất lượng
        buoc = len(out) / gioi_han
        out = [out[int(i * buoc)] for i in range(gioi_han)]
    return out


# ---------------------------------------------------------------- 2. trích thực thể, quan hệ

def _lam_sach_ket_qua(kq: dict | None) -> dict:
    tt, qh = [], []
    ten_hop_le = set()
    for e in (kq or {}).get("thuc_the") or []:
        if not isinstance(e, dict) or not str(e.get("ten", "")).strip():
            continue
        loai = str(e.get("loai", "")).upper().strip()
        loai = loai if loai in P.LOAI_THUC_THE else "KHAI_NIEM"
        tt.append({"ten": str(e["ten"]).strip(), "loai": loai, "mo_ta": str(e.get("mo_ta", "")).strip()})
        ten_hop_le.add(chuan_hoa(e["ten"]))
    for r in (kq or {}).get("quan_he") or []:
        if not isinstance(r, dict):
            continue
        a, b = chuan_hoa(r.get("nguon", "")), chuan_hoa(r.get("dich", ""))
        if not a or not b or a == b or a not in ten_hop_le or b not in ten_hop_le:
            continue
        try:
            w = float(r.get("do_manh", 5))
        except (TypeError, ValueError):
            w = 5.0
        qh.append({"nguon": str(r["nguon"]).strip(), "dich": str(r["dich"]).strip(),
                   "mo_ta": str(r.get("mo_ta", "")).strip(), "do_manh": max(1.0, min(10.0, w))})
    return {"thuc_the": tt, "quan_he": qh}


def trich_mot(llm, text: str, gleaning: int = 0) -> dict:
    system = P.EXTRACT_SYSTEM.format(loai="\n".join(f"- {k}: {v}" for k, v in P.LOAI_THUC_THE.items()))
    raw = llm.generate(system, P.EXTRACT_USER.format(text=text))
    kq = doc_json(raw)
    if kq is None:   # thử lại một lần
        kq = doc_json(llm.generate(system, P.EXTRACT_USER.format(text=text) + "\n(Chỉ trả về JSON hợp lệ.)"))
    if kq is None:
        raise ValueError("LLM không trả về JSON hợp lệ")
    kq = _lam_sach_ket_qua(kq)
    for _ in range(gleaning):
        them = _lam_sach_ket_qua(doc_json(llm.generate(system, P.GLEANING_USER.format(
            text=text, prev=json.dumps(kq, ensure_ascii=False)))))
        if not them["thuc_the"] and not them["quan_he"]:
            break
        kq["thuc_the"] += them["thuc_the"]
        kq = _lam_sach_ket_qua({"thuc_the": kq["thuc_the"], "quan_he": kq["quan_he"] + them["quan_he"]})
    return kq


class LoiKhongTheTiepTuc(RuntimeError):
    """Lỗi về tài khoản/khóa API (hết hạn mức, sai khóa): gọi tiếp chỉ ra cùng một lỗi nên dừng ngay."""


_LOI_TAI_KHOAN = re.compile(r"lỗi (401|402|403)\b|key limit exceeded|insufficient credits|insufficient_quota|invalid api key|"
                            r"hết khóa dùng được", re.IGNORECASE)


def trich_xuat(llm, units: list[dict], cache: Cache, workers: int = 8, gleaning: int = 0,
               tien_do=None) -> tuple[dict[str, dict], list[str]]:
    """Trả về ({vid: kết quả}, [vid lỗi]). Đơn vị đã có trong cache không gọi lại LLM.
    Gặp lỗi tài khoản (hết hạn mức khóa API, hết credits, sai khóa) thì dừng và ném LoiKhongTheTiepTuc."""
    loi: list[str] = []
    can = [u for u in units if u["vid"] not in cache]
    dung: list[str] = []

    def mot(u):
        if dung:
            return
        try:
            cache.put(u["vid"], trich_mot(llm, u["text"], gleaning))
        except Exception as e:  # noqa: BLE001 – ghi lại, lần chạy sau thử tiếp
            if _LOI_TAI_KHOAN.search(str(e)):
                dung.append(str(e)[:300])
                return
            loi.append(f"{u['vid']}: {type(e).__name__}: {str(e)[:120]}")

    chay_song_song(can, mot, workers, tien_do)
    if dung:
        raise LoiKhongTheTiepTuc(dung[0])
    return {u["vid"]: cache.get(u["vid"]) for u in units if u["vid"] in cache}, loi


# ---------------------------------------------------------------- 3. gộp + tóm tắt

def gop(ket_qua: dict[str, dict], vid_to_id: dict[str, str]) -> tuple[dict[str, dict], dict[tuple, dict]]:
    """Thực thể theo khóa chuẩn hóa; quan hệ theo cặp khóa (không có hướng). Mỗi mục giữ danh sách mô tả và các vid nguồn."""
    tt: dict[str, dict] = {}
    qh: dict[tuple, dict] = {}
    for vid, kq in ket_qua.items():
        for e in kq["thuc_the"]:
            k = chuan_hoa(e["ten"])
            d = tt.setdefault(k, {"id": k, "ten_dem": Counter(), "loai_dem": Counter(), "mo_ta": [], "vids": set()})
            d["ten_dem"][e["ten"]] += 1
            d["loai_dem"][e["loai"]] += 1
            if e["mo_ta"] and e["mo_ta"] not in d["mo_ta"]:
                d["mo_ta"].append(e["mo_ta"])
            d["vids"].add(vid)
        for r in kq["quan_he"]:
            a, b = chuan_hoa(r["nguon"]), chuan_hoa(r["dich"])
            k = tuple(sorted((a, b)))
            d = qh.setdefault(k, {"nguon": a, "dich": b, "mo_ta": [], "trong_so": 0.0, "tan_suat": 0, "vids": set()})
            d["trong_so"] += r["do_manh"]
            d["tan_suat"] += 1
            if r["mo_ta"] and r["mo_ta"] not in d["mo_ta"]:
                d["mo_ta"].append(r["mo_ta"])
            d["vids"].add(vid)
    for d in tt.values():
        d["ten"] = d.pop("ten_dem").most_common(1)[0][0]
        d["loai"] = d.pop("loai_dem").most_common(1)[0][0]
        d["vids"] = sorted(d["vids"])
        d["don_vi"] = sorted({vid_to_id.get(v, v.split("@")[0]) for v in d["vids"]})
        d["tan_suat"] = len(d["vids"])
    for d in qh.values():
        d["vids"] = sorted(d["vids"])
    return tt, qh


def _loc_trung(ds: list[str]) -> list[str]:
    """Bỏ mô tả trùng hoặc gần trùng (chứa trong mô tả khác, hay trùng ≥ 80% từ) để không lặp ý khi ghép."""
    def chuan(x: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", x.lower())).strip()
    giu: list[tuple[str, set, str]] = []
    for m in sorted(ds, key=len, reverse=True):     # mô tả dài trước: mô tả ngắn nằm gọn trong nó thì bỏ
        c = chuan(m)
        if not c:
            continue
        tu = set(c.split())
        if any(c in g or len(tu & t) / max(1, len(tu | t)) >= 0.8 for g, t, _ in giu):
            continue
        giu.append((c, tu, m))
    thu_tu = {m: i for i, m in enumerate(ds)}
    return [m for _, _, m in sorted(giu, key=lambda x: thu_tu[x[2]])]


def tom_tat_mo_ta(llm, tt: dict[str, dict], qh: dict[tuple, dict], cache: Cache, workers: int = 8,
                  nguong_ky_tu: int = 200, toi_da_mo_ta: int = 30, tien_do=None) -> list[str]:
    """Gán d['mo_ta_tong'] cho mọi thực thể, quan hệ. Bỏ mô tả trùng trước; còn từ hai mô tả trở lên và nối lại
    dài hơn nguong_ky_tu thì nhờ LLM tóm tắt thành một đoạn (như bản gốc), ngắn hơn thì nối bằng dấu chấm phẩy."""
    loi: list[str] = []
    viec = []
    for k, d in tt.items():
        viec.append(("E:" + k, d["ten"], d))
    for k, d in qh.items():
        viec.append(("R:" + "|".join(k), f"{tt.get(k[0], {}).get('ten', k[0])} — {tt.get(k[1], {}).get('ten', k[1])}", d))
    can_llm = []
    for key, ten, d in viec:
        d["mo_ta"] = _loc_trung(d["mo_ta"])
        ghep = "; ".join(m.rstrip(" .;") for m in d["mo_ta"])
        key = key + ":" + hashlib.sha1("\n".join(d["mo_ta"]).encode("utf-8")).hexdigest()[:10]
        if len(d["mo_ta"]) <= 1 or len(ghep) <= nguong_ky_tu:
            d["mo_ta_tong"] = ghep
        elif key in cache:
            d["mo_ta_tong"] = cache.get(key)
        else:
            can_llm.append((key, ten, d))

    def mot(item):
        key, ten, d = item
        ds = "\n".join(f"- {m}" for m in d["mo_ta"][:toi_da_mo_ta])
        try:
            out = llm.generate(P.SUMMARIZE_SYSTEM, P.SUMMARIZE_USER.format(ten=ten, mo_ta=ds)).strip()
            cache.put(key, out)
            d["mo_ta_tong"] = out
        except Exception as e:  # noqa: BLE001
            d["mo_ta_tong"] = "; ".join(d["mo_ta"][:5])
            loi.append(f"{key}: {type(e).__name__}")

    chay_song_song(can_llm, mot, workers, tien_do)
    return loi


# ---------------------------------------------------------------- 4. cộng đồng (Leiden phân cấp)

def _chia(G) -> tuple[list[set], str]:
    try:
        import igraph as ig
        import leidenalg as la
    except ImportError:
        import networkx as nx

        return [set(c) for c in nx.community.louvain_communities(G, weight="weight", seed=42)], "louvain"
    nodes = list(G.nodes)
    idx = {n: i for i, n in enumerate(nodes)}
    edges = list(G.edges(data="weight", default=1.0))
    g = ig.Graph(n=len(nodes), edges=[(idx[u], idx[v]) for u, v, _ in edges])
    g.es["weight"] = [float(w) for _, _, w in edges] or []
    part = la.find_partition(g, la.ModularityVertexPartition, weights="weight" if edges else None, seed=42)
    return [{nodes[i] for i in c} for c in part], "leiden"


def cong_dong(tt: dict[str, dict], qh: dict[tuple, dict], max_cluster_size: int = 10, max_level: int = 3,
              co_toi_thieu: int = 2) -> tuple[list[dict], str]:
    """[{id, cap, cha, thanh_vien}] – cấp 0 là phân hoạch toàn đồ thị; cộng đồng lớn hơn max_cluster_size chia tiếp."""
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(tt)
    for (a, b), d in qh.items():
        if a in tt and b in tt:
            G.add_edge(a, b, weight=d["trong_so"])
    out: list[dict] = []
    dem = [0]
    thuat_toan = "leiden"

    def them(nhom: set, cap: int, cha: str | None):
        nonlocal thuat_toan
        if len(nhom) < co_toi_thieu:
            return
        dem[0] += 1
        cid = f"{cap}-{dem[0]}"
        out.append({"id": cid, "cap": cap, "cha": cha, "thanh_vien": sorted(nhom)})
        if len(nhom) > max_cluster_size and cap + 1 < max_level:
            con, thuat_toan = _chia(G.subgraph(nhom))
            if len(con) > 1:
                for c in sorted(con, key=len, reverse=True):
                    them(c, cap + 1, cid)

    goc, thuat_toan = _chia(G)
    for c in sorted(goc, key=len, reverse=True):
        them(c, 0, None)
    return out, thuat_toan


# ---------------------------------------------------------------- 5. báo cáo cộng đồng

def _chu_ky(thanh_vien: list[str]) -> str:
    return hashlib.sha1("\n".join(thanh_vien).encode("utf-8")).hexdigest()[:16]


def _ngu_canh_cong_dong(c: dict, tt: dict, qh_theo_tt: dict, bao_cao_con: list[dict], toi_da: int) -> str:
    tv = set(c["thanh_vien"])
    ents = sorted(tv, key=lambda k: -len(qh_theo_tt.get(k, ())))
    rels = sorted({k for e in tv for k in qh_theo_tt.get(e, ()) if k[0] in tv and k[1] in tv},
                  key=lambda k: -qh_theo_tt["__w"][k])
    dong_tt = [f"- {tt[e]['ten']} ({tt[e]['loai']}): {tt[e].get('mo_ta_tong', '')[:300]}" for e in ents]
    dong_qh = [f"- {tt[a]['ten']} — {tt[b]['ten']}: {qh_theo_tt['__d'][(a, b)][:250]}" for a, b in rels]
    con = ""
    if bao_cao_con and sum(map(len, dong_tt + dong_qh)) > toi_da:
        # quá dài: dùng báo cáo của các cộng đồng con thay cho phần chi tiết (như bản gốc)
        con = "\nBáo cáo các cộng đồng con:\n" + "\n".join(f"- {b['tieu_de']}: {b['tom_tat']}" for b in bao_cao_con) + "\n"
        dong_tt, dong_qh = dong_tt[:15], dong_qh[:20]
    while sum(map(len, dong_tt + dong_qh)) + len(con) > toi_da and (len(dong_tt) > 5 or len(dong_qh) > 5):
        if len(dong_qh) >= len(dong_tt):
            dong_qh.pop()
        else:
            dong_tt.pop()
    return P.REPORT_USER.format(thuc_the="\n".join(dong_tt), quan_he="\n".join(dong_qh) or "(không có)", con=con)


def bao_cao_cong_dong(llm, comms: list[dict], tt: dict, qh: dict, cache: Cache, workers: int = 8,
                      toi_da_ky_tu: int = 9000, tien_do=None) -> list[str]:
    """Gán c['bao_cao'] = {tieu_de, tom_tat, muc_do, ly_do_muc_do, phat_hien}; làm từ cấp sâu nhất lên."""
    qh_theo_tt: dict = defaultdict(list)
    w, dmt = {}, {}
    for k, d in qh.items():
        qh_theo_tt[k[0]].append(k)
        qh_theo_tt[k[1]].append(k)
        w[k], dmt[k] = d["trong_so"], d.get("mo_ta_tong", "")
    qh_theo_tt["__w"], qh_theo_tt["__d"] = w, dmt
    theo_id = {c["id"]: c for c in comms}
    con_cua: dict[str, list[str]] = defaultdict(list)
    for c in comms:
        if c["cha"]:
            con_cua[c["cha"]].append(c["id"])
    loi: list[str] = []
    xong = [0]
    tong = len(comms)

    def mot(c):
        key = _chu_ky(c["thanh_vien"])
        if key in cache:
            c["bao_cao"] = cache.get(key)
        else:
            con = [theo_id[i]["bao_cao"] for i in con_cua.get(c["id"], []) if theo_id[i].get("bao_cao")]
            user = _ngu_canh_cong_dong(c, tt, qh_theo_tt, con, toi_da_ky_tu)
            try:
                kq = doc_json(llm.generate(P.REPORT_SYSTEM, user))
                if not kq or not kq.get("tieu_de"):
                    raise ValueError("báo cáo không hợp lệ")
                try:
                    kq["muc_do"] = float(kq.get("muc_do", 5))
                except (TypeError, ValueError):
                    kq["muc_do"] = 5.0
                kq["phat_hien"] = [p for p in kq.get("phat_hien") or [] if isinstance(p, dict)]
                cache.put(key, kq)
                c["bao_cao"] = kq
            except Exception as e:  # noqa: BLE001
                loi.append(f"{c['id']}: {type(e).__name__}")
        xong[0] += 1
        if tien_do:
            tien_do(xong[0], tong)

    for cap in sorted({c["cap"] for c in comms}, reverse=True):
        chay_song_song([c for c in comms if c["cap"] == cap], mot, workers)
    return loi


def van_ban_bao_cao(c: dict) -> str:
    b = c.get("bao_cao") or {}
    out = [f"# {b.get('tieu_de', c['id'])}", "", b.get("tom_tat", "")]
    for p in b.get("phat_hien", []):
        out += ["", f"## {p.get('tom_tat', '')}", p.get("giai_thich", "")]
    return "\n".join(out).strip()


# ---------------------------------------------------------------- 6. lưu / đọc kết quả

def luu_ket_qua(thu_muc: Path, tt: dict, qh: dict, comms: list[dict], thuat_toan: str) -> None:
    bac = Counter()
    for a, b in qh:
        bac[a] += 1
        bac[b] += 1
    ghi_jsonl(thu_muc / "thuc_the.jsonl", [
        {"id": k, "ten": d["ten"], "loai": d["loai"], "mo_ta": d.get("mo_ta_tong", ""), "tan_suat": d["tan_suat"],
         "bac": bac[k], "vids": d["vids"], "don_vi": d["don_vi"]} for k, d in sorted(tt.items())])
    ghi_jsonl(thu_muc / "quan_he.jsonl", [
        {"nguon": d["nguon"], "dich": d["dich"], "mo_ta": d.get("mo_ta_tong", ""), "trong_so": round(d["trong_so"], 2),
         "tan_suat": d["tan_suat"], "vids": d["vids"]} for _, d in sorted(qh.items())])
    ghi_jsonl(thu_muc / "cong_dong.jsonl", [
        {"id": c["id"], "cap": c["cap"], "cha": c["cha"], "thanh_vien": c["thanh_vien"],
         "tieu_de": (c.get("bao_cao") or {}).get("tieu_de", ""), "tom_tat": (c.get("bao_cao") or {}).get("tom_tat", ""),
         "muc_do": (c.get("bao_cao") or {}).get("muc_do"), "bao_cao": van_ban_bao_cao(c) if c.get("bao_cao") else "",
         "thuat_toan": thuat_toan} for c in comms])
