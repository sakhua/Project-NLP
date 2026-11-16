// F1 Trò chuyện hỏi đáp (nhiều lượt, chọn 1 trong 3 hệ thống hoặc so sánh cả ba) + F4 đánh giá câu trả lời. Phụ trách: TV3.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUp, Boxes, Check, Columns3, Copy, ListTree, LoaderCircle, PanelRightClose, PanelRightOpen, RotateCcw, Scale,
  Sparkles, Square, ThumbsDown, ThumbsUp, TriangleAlert, Waypoints, Workflow,
} from "lucide-react";
import { api, askStream, today } from "../api.js";
import AnswerPanel from "../components/AnswerPanel.jsx";
import AnswerText from "../components/AnswerText.jsx";
import DatePicker from "../components/DatePicker.jsx";
import { SUGGESTIONS } from "../lib/demo.js";
import { fmtDate, fmtMs, fmtNum, storage, uid } from "../lib/format.js";
import { STEP_PENDING, stepOrder, SYS_ORDER, SYSTEMS, sysOf } from "../lib/systems.js";
import { navigate } from "../lib/router.js";
import { nearBottom } from "../lib/scroll.js";

const INTENT_LABEL = {
  chao: "Lời chào", cam_on: "Lời cảm ơn", tam_biet: "Lời tạm biệt",
  gioi_thieu: "Giới thiệu trợ lý", ngoai_pham_vi: "Ngoài phạm vi hỗ trợ",
};

// Lịch sử gửi kèm câu hỏi mới: chỉ các lượt hỏi đáp pháp luật đã trả lời xong (bỏ lời chào, câu ngoài phạm vi, câu lỗi),
// tối đa 3 lượt gần nhất. Dùng để hiểu câu tiếp nối như "Còn xe máy thì sao?".
function buildHistory(messages) {
  const out = [];
  for (let i = 1; i < messages.length; i++) {
    const u = messages[i - 1];
    const b = messages[i].kind === "compare" ? messages[i].runs?.hybrid_graphrag : messages[i];   // so sánh: dùng câu của hệ thống đề xuất
    if (u.role !== "user" || messages[i].role !== "assistant" || !b || b.status !== "done" || !b.content) continue;
    if (b.result?.intent && b.result.intent !== "luat") continue;
    out.push({ role: "user", content: u.content }, { role: "assistant", content: b.content });
  }
  return out.slice(-6);
}

// Bộ điều khiển dừng của các câu đang trả lời (giữ ngoài component: trang được tạo lại khi chuyển sang cuộc trò chuyện mới)
const controllers = new Map();

const PREF_KEY = "graphrag.he_thong";

// Các lượt trả lời trong một tin nhắn: tin nhắn thường có 1 lượt, tin nhắn "so sánh" có 3 lượt (mỗi hệ thống một lượt)
const runsOf = (m) => (m.kind === "compare" ? SYS_ORDER.map((k) => m.runs?.[k]).filter(Boolean) : [m]);
const isStreaming = (m) => runsOf(m).some((r) => r.status === "streaming");

function LiveSteps({ msg, hasHistory }) {
  const done = msg.steps || [];
  const doneKeys = new Set(done.map((s) => s.key));
  const order = stepOrder(sysOf(msg), msg.che_do).filter((k) => k !== "rewrite" || hasHistory);
  const next = order.find((k) => !doneKeys.has(k));
  return (
    <div className="live-steps">
      {done.map((s) => (
        <div key={s.key} className="live-step">
          <span className="check"><Check size={12} strokeWidth={3} /></span>
          <span>{s.label}</span><span className="detail">· {s.detail}</span>
        </div>
      ))}
      {next && (
        <div className="live-step pending">
          <LoaderCircle size={16} className="spin" /> <span>{STEP_PENDING[next]}</span>
        </div>
      )}
    </div>
  );
}

function SysTag({ sys, cheDo }) {
  const s = SYSTEMS[sys] || SYSTEMS.hybrid_graphrag;
  return <span className="sys-tag" style={{ "--c": s.color }} title={s.desc}>{s.short}{sys === "ms_graphrag" && cheDo === "global" ? " · global" : ""}</span>;
}

function RunView({ msg, onSelect, onCite, onRate, onRetry, hasHistory, compact }) {
  const [copied, setCopied] = useState(false);
  const r = msg.result;
  const units = r?.units || msg.context?.units || [];
  const streaming = msg.status === "streaming";
  const notes = r?.notes || msg.context?.notes || [];
  const sys = sysOf(msg);
  const gctx = r?.graph_context || msg.context?.graph_context;
  const fromGraph = units.filter((u) => u.origin === "graph").length;
  return (
      <div style={{ minWidth: 0 }}>
        {!compact && (r?.question_rewritten || (msg.steps || []).find((s) => s.key === "rewrite" && s.question)) && (
          <div className="rewritten"><Sparkles size={13} /> Hiểu câu hỏi là: <b>{r?.question_rewritten || msg.steps.find((s) => s.key === "rewrite").question}</b></div>
        )}
        {streaming && !msg.content && <LiveSteps msg={msg} hasHistory={hasHistory} />}
        {msg.content && <AnswerText text={msg.content} units={units} onCite={onCite} streaming={streaming} />}
        {msg.status === "error" && (
          <div className="banner error"><TriangleAlert size={16} style={{ flex: "none", marginTop: 2 }} />
            <div className="grow">{msg.error}</div>
            <button className="btn sm" onClick={onRetry}><RotateCcw size={13} /> Thử lại</button>
          </div>
        )}
        {notes.length > 0 && !streaming && compact && (
          <div className="banner warn note-inline small"><TriangleAlert size={15} style={{ flex: "none", marginTop: 2 }} />
            <div>{notes.length} quy định liên quan chưa/hết hiệu lực tại ngày đã chọn</div>
          </div>
        )}
        {notes.length > 0 && !streaming && !compact && (
          <div className="banner warn note-inline small"><TriangleAlert size={15} style={{ flex: "none", marginTop: 2 }} />
            <div>{notes.map((n) => `${n.ten} ${n.trang_thai === "chua_hieu_luc" ? `chỉ có hiệu lực từ ${fmtDate(n.ngay)}` : `hết hiệu lực từ ${fmtDate(n.ngay)}`}`).join("; ")}.</div>
          </div>
        )}
        {msg.status === "done" && r && (
          <div className="msg-meta">
            {!compact && <SysTag sys={sys} cheDo={r.che_do} />}
            {r.intent && r.intent !== "luat" ? (
              <span className="badge">{INTENT_LABEL[r.intent] || "Không cần tra cứu"}</span>
            ) : (<>
            {r.che_do === "global" ? (
              <button className="meta-pill" onClick={() => onSelect("sources")}><Boxes size={14} /> {gctx?.cong_dong?.length || 0} cộng đồng</button>
            ) : (
              <button className="meta-pill" onClick={() => onSelect("sources")}><ListTree size={14} /> {units.length} căn cứ · {r.citations.length} trích dẫn</button>
            )}
            {sys === "hybrid_graphrag" && <button className="meta-pill" onClick={() => onSelect("graph")}><Waypoints size={14} /> {fromGraph} từ đồ thị</button>}
            {sys === "ms_graphrag" && r.che_do !== "global" && <button className="meta-pill" onClick={() => onSelect("graph")}><Waypoints size={14} /> {gctx?.thuc_the?.length || 0} thực thể</button>}
            <button className="meta-pill" onClick={() => onSelect("steps")}><Workflow size={14} /> {fmtMs(r.latency_ms)}</button>
            </>)}
            <span className="grow" />
            <button className="icon-btn" title="Sao chép" onClick={() => {
              navigator.clipboard?.writeText(msg.content); setCopied(true); setTimeout(() => setCopied(false), 1500);
            }}>{copied ? <Check size={15} /> : <Copy size={15} />}</button>
            {r.log_id && (!r.intent || r.intent === "luat") && (
              <>
                <button className={`icon-btn ${msg.rating === 1 ? "on" : ""}`} title="Hữu ích" onClick={() => onRate(1)}><ThumbsUp size={15} /></button>
                <button className={`icon-btn ${msg.rating === -1 ? "on" : ""}`} title="Chưa đúng" onClick={() => onRate(-1)}><ThumbsDown size={15} /></button>
              </>
            )}
          </div>
        )}
      </div>
  );
}

function BotMessage({ msg, selected, ...rest }) {
  return (
    <div className={`msg-bot ${selected ? "selected" : ""}`}>
      <div className="avatar"><Scale size={16} /></div>
      <RunView msg={msg} {...rest} />
    </div>
  );
}

// Một câu hỏi, ba hệ thống trả lời song song
function CompareMessage({ msg, selKey, onSelect, onCite, onRate, onRetry, hasHistory }) {
  return (
    <div className="compare">
      <div className="compare-head"><Columns3 size={14} /> So sánh ba hệ thống trên cùng câu hỏi</div>
      <div className="compare-grid">
        {SYS_ORDER.map((k) => msg.runs?.[k] && (
          <div key={k} className={`compare-col ${selKey === k ? "selected" : ""}`}>
            <div className="compare-col-head">
              <SysTag sys={k} cheDo={msg.runs[k].che_do} />
              <span className="muted small grow nowrap">{SYSTEMS[k].tag}</span>
              {msg.runs[k].result?.latency_ms != null && <span className="muted small">{fmtMs(msg.runs[k].result.latency_ms)}</span>}
            </div>
            <div className="compare-body">
              <RunView msg={msg.runs[k]} compact hasHistory={hasHistory}
                onSelect={(t) => onSelect(k, t)} onCite={(id) => onCite(k, id)} onRate={(v) => onRate(k, v)} onRetry={() => onRetry(k)} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SystemPicker({ pref, setPref, disabled }) {
  return (
    <div className="sys-picker">
      {!pref.compare && SYS_ORDER.map((k) => (
        <button key={k} type="button" disabled={disabled} title={SYSTEMS[k].desc}
          className={`seg ${pref.sys === k ? "on" : ""}`} style={{ "--c": SYSTEMS[k].color }}
          onClick={() => setPref({ ...pref, sys: k })}>{SYSTEMS[k].short}</button>
      ))}
      {!pref.compare && pref.sys === "ms_graphrag" && (
        <select className="seg-select" value={pref.cheDo} disabled={disabled} title="Local: câu hỏi cụ thể · Global: câu hỏi tổng quan"
          onChange={(e) => setPref({ ...pref, cheDo: e.target.value })}>
          <option value="local">local</option><option value="global">global</option>
        </select>
      )}
      <button type="button" disabled={disabled} className={`seg compare-toggle ${pref.compare ? "on" : ""}`}
        title="Gửi câu hỏi tới cả ba hệ thống và xem song song" onClick={() => setPref({ ...pref, compare: !pref.compare })}>
        <Columns3 size={13} /> So sánh
      </button>
    </div>
  );
}

function Welcome({ onPick, date }) {
  const [ov, setOv] = useState(null);
  useEffect(() => { api.overview().then(setOv).catch(() => {}); }, []);
  const pg = ov?.postgres, g = ov?.neo4j;
  return (
    <div className="welcome">
      <h2>Hỏi về luật giao thông đường bộ</h2>
      <p>Trả lời dựa trên Luật 36/2024, Nghị định 168/2024 và các văn bản sửa đổi, có trích dẫn từng điều khoản
        và đúng với ngày áp dụng bạn chọn ({fmtDate(date)}).</p>
      <div className="sugg-grid">
        {SUGGESTIONS.map((s) => (
          <button key={s.question} className="sugg" onClick={() => onPick(s)}>
            <span className="badge">{s.tag}{s.date ? ` · ${fmtDate(s.date)}` : ""}</span>
            <div>{s.question}</div>
          </button>
        ))}
      </div>
      {pg && (
        <div className="facts">
          <span><b>{pg.van_ban}</b> văn bản</span>
          <span><b>{fmtNum(pg.don_vi)}</b> điều khoản</span>
          <span><b>{fmtNum(pg.phien_ban)}</b> phiên bản theo thời gian</span>
          {g?.tong_canh != null && <span><b>{fmtNum(g.tong_canh)}</b> quan hệ trên đồ thị</span>}
        </div>
      )}
    </div>
  );
}

export default function AskPage({ convId, convs, query }) {
  const conv = convs.list.find((c) => c.id === convId);
  const [draftDate, setDraftDate] = useState(query.get("date") || today());
  const date = conv?.date || draftDate;
  const [input, setInput] = useState(query.get("q") || "");
  const [sel, setSel] = useState(null);
  const [tab, setTab] = useState("sources");
  const [panelOpen, setPanelOpen] = useState(true);
  const [flash, setFlash] = useState(null);
  const [pref, setPrefState] = useState(() => ({ sys: "hybrid_graphrag", cheDo: "local", compare: false, ...storage.get(PREF_KEY, {}) }));
  const setPref = (p) => { setPrefState(p); storage.set(PREF_KEY, p); };
  const scrollRef = useRef(null);   // khung cuộn của danh sách tin nhắn
  const stickRef = useRef(true);     // người dùng đang ở cuối khung → tự cuộn theo chữ mới
  const createdRef = useRef(null);   // cuộc trò chuyện vừa tạo ở trang này (không xóa trạng thái khi URL đổi sang nó)
  const taRef = useRef(null);
  const messages = conv?.messages || [];
  const busy = messages.some(isStreaming);
  const lastBot = [...messages].reverse().find((m) => m.role === "assistant");
  // sel = "<id tin nhắn>" hoặc "<id tin nhắn so sánh>:<hệ thống>"
  const [selId, selKey] = (sel || "").split(":");
  const selBase = messages.find((m) => m.id === selId) || lastBot;
  const selMsg = selBase?.kind === "compare" ? selBase.runs?.[selKey || "hybrid_graphrag"] : selBase;

  // Đổi sang cuộc trò chuyện khác (hoặc bấm "Cuộc trò chuyện mới"): đặt lại trạng thái trang, KHÔNG tạo lại trang.
  // Khi vừa gửi câu đầu tiên, URL đổi từ #/chat sang #/chat/<id>: giữ nguyên mọi thứ để không bị nhảy.
  const qs = query.toString();
  const prevConv = useRef(convId);
  useEffect(() => {
    if (prevConv.current === convId) return;
    prevConv.current = convId;
    if (convId && convId === createdRef.current) return;
    setSel(null); setTab("sources"); setFlash(null); setPanelOpen(true);
    setInput(query.get("q") || "");
    if (!convId) setDraftDate(query.get("date") || today());
    stickRef.current = true;
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [convId, qs]); // eslint-disable-line react-hooks/exhaustive-deps

  // Tự cuộn xuống khi có tin nhắn mới hoặc chữ đang chạy, trừ khi người dùng đã cuộn lên để đọc.
  const lastLen = lastBot ? runsOf(lastBot).reduce((n, r) => n + (r.content?.length || 0) + (r.steps?.length || 0)
    + (r.status === "done" ? 1 : 0), 0) : 0;
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [messages.length, lastLen]);
  useEffect(() => {
    const ta = taRef.current;
    if (ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 180) + "px"; }
  }, [input]);

  const setDate = (d) => (conv ? convs.update(conv.id, (c) => ({ ...c, date: d })) : setDraftDate(d));

  // key: hệ thống trong tin nhắn so sánh (null = tin nhắn thường)
  const run = useCallback((cid, question, d, history, botId, sys, cheDo, key = null) => {
    const patch = (fn) => convs.update(cid, (c) => ({ ...c, messages: c.messages.map((m) => {
      if (m.id !== botId) return m;
      return key ? { ...m, runs: { ...m.runs, [key]: fn(m.runs[key]) } } : fn(m);
    }) }));
    const ctrl = new AbortController();
    controllers.set(key ? `${botId}:${key}` : botId, ctrl);
    askStream({ question, date: d, history, he_thong: sys, che_do: cheDo }, (ev) => {
      if (ev.type === "step") patch((m) => ({ ...m, steps: [...(m.steps || []), ev] }));
      else if (ev.type === "context") patch((m) => ({ ...m, context: ev }));
      else if (ev.type === "token") patch((m) => ({ ...m, content: (m.content || "") + ev.text }));
      else if (ev.type === "done") patch((m) => ({ ...m, status: "done", content: ev.answer, result: ev }));
      else if (ev.type === "error") patch((m) => ({ ...m, status: "error", error: ev.message }));
    }, ctrl.signal)
      .then(() => patch((m) => (m.status === "streaming" ? { ...m, status: "error", error: "Kết nối bị ngắt giữa chừng." } : m)))
      .catch((e) => patch((m) => (e.name === "AbortError" ? { ...m, status: "error", error: "Đã dừng." }
        : { ...m, status: "error", error: e.message })))
      .finally(() => controllers.delete(key ? `${botId}:${key}` : botId));
  }, [convs]);

  const send = (text, presetDate) => {
    const q = (text ?? input).trim();
    if (q.length < 3 || busy) return;
    const d = presetDate || date;
    let cid = conv?.id;
    if (!cid) { cid = convs.create(q, d); createdRef.current = cid; }
    else if (presetDate) convs.update(cid, (c) => ({ ...c, date: d }));
    const history = buildHistory(messages);
    const botId = uid();
    const fresh = (sys, cheDo) => ({ id: uid(), role: "assistant", content: "", status: "streaming", steps: [], date: d,
      he_thong: sys, che_do: cheDo });
    const bot = pref.compare
      ? { id: botId, role: "assistant", kind: "compare", date: d,
        runs: Object.fromEntries(SYS_ORDER.map((k) => [k, fresh(k, "local")])) }
      : { ...fresh(pref.sys, pref.cheDo), id: botId };
    convs.update(cid, (c) => ({ ...c, messages: [...c.messages, { id: uid(), role: "user", content: q, date: d }, bot] }));
    setInput("");
    stickRef.current = true;
    setSel(pref.compare ? `${botId}:hybrid_graphrag` : botId);
    setTab("sources");
    if (pref.compare) setPanelOpen(false);   // ba cột cần rộng; bấm vào nút ở mỗi cột để mở chi tiết
    if (!conv) navigate("chat", cid);
    if (pref.compare) SYS_ORDER.forEach((k) => run(cid, q, d, history, botId, k, "local", k));
    else run(cid, q, d, history, botId, pref.sys, pref.cheDo);
  };

  const retry = (botId, key = null) => {
    const i = messages.findIndex((m) => m.id === botId);
    const userMsg = messages[i - 1];
    if (!userMsg) return;
    const history = buildHistory(messages.slice(0, i - 1));
    const reset = (m) => ({ ...m, status: "streaming", error: null, content: "", steps: [], context: null, result: null });
    const m0 = messages[i];
    const target = key ? m0.runs[key] : m0;
    convs.update(conv.id, (c) => ({ ...c, messages: c.messages.map((m) => (m.id !== botId ? m
      : key ? { ...m, runs: { ...m.runs, [key]: reset(m.runs[key]) } } : reset(m))) }));
    run(conv.id, userMsg.content, userMsg.date || date, history, botId, key || sysOf(target), target.che_do || "local", key);
  };

  const rate = (m, v, key = null) => {
    const target = key ? m.runs[key] : m;
    if (!target.result?.log_id) return;
    convs.update(conv.id, (c) => ({ ...c, messages: c.messages.map((x) => (x.id !== m.id ? x
      : key ? { ...x, runs: { ...x.runs, [key]: { ...x.runs[key], rating: v } } } : { ...x, rating: v })) }));
    api.feedback(target.result.log_id, v).catch(() => {});
  };

  const cite = (m, id, key = null) => {
    setSel(key ? `${m.id}:${key}` : m.id); setTab("sources"); setPanelOpen(true);
    setFlash(null); setTimeout(() => setFlash(id), 20);
  };

  const showPanel = panelOpen && messages.length > 0;
  const comparing = messages.some((m) => m.kind === "compare");
  return (
    <div className={`chat ${showPanel ? "with-panel" : ""} ${showPanel && tab === "graph" ? "wide" : ""} ${comparing ? "has-compare" : ""}`}>
      <div className="chat-col">
        <div className="topbar">
          <h1>{conv ? conv.title : "Cuộc trò chuyện mới"}</h1>
          <DatePicker value={date} onChange={setDate} />
          {messages.length > 0 && (
            <button className="icon-btn" title={panelOpen ? "Ẩn chi tiết" : "Hiện chi tiết"} onClick={() => setPanelOpen(!panelOpen)}>
              {panelOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
            </button>
          )}
        </div>
        <div className="messages" ref={scrollRef} onScroll={(e) => { stickRef.current = nearBottom(e.currentTarget); }}>
          {messages.length === 0 ? (
            <Welcome date={date} onPick={(s) => send(s.question, s.date)} />
          ) : (
            <div className="messages-inner">
              {messages.map((m, i) => m.role === "user"
                ? <div key={m.id} className="msg-user">{m.content}</div>
                : m.kind === "compare"
                  ? <CompareMessage key={m.id} msg={m} hasHistory={i > 1} selKey={selBase?.id === m.id ? (selKey || "hybrid_graphrag") : null}
                    onSelect={(k, t) => { setSel(`${m.id}:${k}`); setTab(t); setPanelOpen(true); }}
                    onCite={(k, id) => cite(m, id, k)} onRate={(k, v) => rate(m, v, k)} onRetry={(k) => retry(m.id, k)} />
                  : <BotMessage key={m.id} msg={m} selected={selBase?.id === m.id} hasHistory={i > 1}
                    onSelect={(t) => { setSel(m.id); setTab(t); setPanelOpen(true); }}
                    onCite={(id) => cite(m, id)} onRate={(v) => rate(m, v)} onRetry={() => retry(m.id)} />)}
            </div>
          )}
        </div>
        <div className="composer-wrap">
          <div className="composer">
            <textarea ref={taRef} rows={1} value={input} placeholder={messages.length ? "Hỏi tiếp, ví dụ: Còn xe máy thì sao?" : "Nhập câu hỏi về luật giao thông…"}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />
            <div className="composer-bar">
              <SystemPicker pref={pref} setPref={setPref} disabled={busy} />
              <span className="grow" />
              {busy ? (
                <button className="send" title="Dừng" onClick={() => controllers.forEach((c) => c.abort())}><Square size={13} fill="#fff" /></button>
              ) : (
                <button className="send" title="Gửi (Enter)" disabled={input.trim().length < 3} onClick={() => send()}><ArrowUp size={18} /></button>
              )}
            </div>
          </div>
          <div className="composer-hint">Thông tin chỉ mang tính tham khảo; đối chiếu văn bản gốc trước khi áp dụng. <span className="kbd">Enter</span> gửi · <span className="kbd">Shift+Enter</span> xuống dòng</div>
        </div>
      </div>
      {showPanel && <AnswerPanel msg={selMsg} tab={tab} setTab={setTab} flashId={flash} onClose={() => setPanelOpen(false)} />}
    </div>
  );
}
