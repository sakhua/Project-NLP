// F1 Trò chuyện hỏi đáp (GraphRAG, nhiều lượt) + F4 đánh giá câu trả lời. Phụ trách: TV3.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUp, Check, Copy, ListTree, LoaderCircle, PanelRightClose, PanelRightOpen, RotateCcw, Scale, Sparkles,
  Square, ThumbsDown, ThumbsUp, TriangleAlert, Waypoints, Workflow,
} from "lucide-react";
import { api, askStream, today } from "../api.js";
import AnswerPanel from "../components/AnswerPanel.jsx";
import AnswerText from "../components/AnswerText.jsx";
import DatePicker from "../components/DatePicker.jsx";
import { SUGGESTIONS } from "../lib/demo.js";
import { fmtDate, fmtMs, fmtNum, uid } from "../lib/format.js";
import { navigate } from "../lib/router.js";

// Bộ điều khiển dừng của các câu đang trả lời (giữ ngoài component: trang được tạo lại khi chuyển sang cuộc trò chuyện mới)
const controllers = new Map();

const STEP_ORDER = ["rewrite", "search", "rerank", "graph", "context", "generate"];
const STEP_PENDING = {
  rewrite: "Đang hiểu câu hỏi theo ngữ cảnh…",
  search: "Đang tìm kiếm BM25 + vector…",
  rerank: "Đang lọc theo ngày áp dụng và xếp hạng…",
  graph: "Đang mở rộng trên đồ thị tri thức…",
  context: "Đang ghép ngữ cảnh…",
  generate: "Đang soạn câu trả lời…",
};

function LiveSteps({ msg, hasHistory }) {
  const done = msg.steps || [];
  const doneKeys = new Set(done.map((s) => s.key));
  const order = STEP_ORDER.filter((k) => k !== "rewrite" || hasHistory);
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

function BotMessage({ msg, selected, onSelect, onCite, onRate, onRetry, hasHistory }) {
  const [copied, setCopied] = useState(false);
  const r = msg.result;
  const units = r?.units || msg.context?.units || [];
  const streaming = msg.status === "streaming";
  const notes = r?.notes || msg.context?.notes || [];
  const fromGraph = units.filter((u) => u.origin === "graph").length;
  return (
    <div className={`msg-bot ${selected ? "selected" : ""}`}>
      <div className="avatar"><Scale size={16} /></div>
      <div style={{ minWidth: 0 }}>
        {(r?.question_rewritten || (msg.steps || []).find((s) => s.key === "rewrite" && s.question)) && (
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
        {notes.length > 0 && !streaming && (
          <div className="banner warn note-inline small"><TriangleAlert size={15} style={{ flex: "none", marginTop: 2 }} />
            <div>{notes.map((n) => `${n.ten} ${n.trang_thai === "chua_hieu_luc" ? `chỉ có hiệu lực từ ${fmtDate(n.ngay)}` : `hết hiệu lực từ ${fmtDate(n.ngay)}`}`).join("; ")}.</div>
          </div>
        )}
        {msg.status === "done" && r && (
          <div className="msg-meta">
            <button className="meta-pill" onClick={() => onSelect("sources")}><ListTree size={14} /> {units.length} căn cứ · {r.citations.length} trích dẫn</button>
            <button className="meta-pill" onClick={() => onSelect("graph")}><Waypoints size={14} /> {fromGraph} từ đồ thị</button>
            <button className="meta-pill" onClick={() => onSelect("steps")}><Workflow size={14} /> {fmtMs(r.latency_ms)}</button>
            <span className="grow" />
            <button className="icon-btn" title="Sao chép" onClick={() => {
              navigator.clipboard?.writeText(msg.content); setCopied(true); setTimeout(() => setCopied(false), 1500);
            }}>{copied ? <Check size={15} /> : <Copy size={15} />}</button>
            {r.log_id && (
              <>
                <button className={`icon-btn ${msg.rating === 1 ? "on" : ""}`} title="Hữu ích" onClick={() => onRate(1)}><ThumbsUp size={15} /></button>
                <button className={`icon-btn ${msg.rating === -1 ? "on" : ""}`} title="Chưa đúng" onClick={() => onRate(-1)}><ThumbsDown size={15} /></button>
              </>
            )}
          </div>
        )}
      </div>
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
  const endRef = useRef(null);
  const taRef = useRef(null);
  const messages = conv?.messages || [];
  const busy = messages.some((m) => m.status === "streaming");
  const lastBot = [...messages].reverse().find((m) => m.role === "assistant");
  const selMsg = messages.find((m) => m.id === sel) || lastBot;

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, lastBot?.content?.length > 0, lastBot?.status]);
  useEffect(() => {
    const ta = taRef.current;
    if (ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 180) + "px"; }
  }, [input]);

  const setDate = (d) => (conv ? convs.update(conv.id, (c) => ({ ...c, date: d })) : setDraftDate(d));

  const run = useCallback((cid, question, d, history, botId) => {
    const patch = (fn) => convs.update(cid, (c) => ({ ...c, messages: c.messages.map((m) => (m.id === botId ? fn(m) : m)) }));
    const ctrl = new AbortController();
    controllers.set(botId, ctrl);
    askStream({ question, date: d, history }, (ev) => {
      if (ev.type === "step") patch((m) => ({ ...m, steps: [...(m.steps || []), ev] }));
      else if (ev.type === "context") patch((m) => ({ ...m, context: ev }));
      else if (ev.type === "token") patch((m) => ({ ...m, content: (m.content || "") + ev.text }));
      else if (ev.type === "done") patch((m) => ({ ...m, status: "done", content: ev.answer, result: ev }));
      else if (ev.type === "error") patch((m) => ({ ...m, status: "error", error: ev.message }));
    }, ctrl.signal)
      .then(() => patch((m) => (m.status === "streaming" ? { ...m, status: "error", error: "Kết nối bị ngắt giữa chừng." } : m)))
      .catch((e) => patch((m) => (e.name === "AbortError" ? { ...m, status: "error", error: "Đã dừng." }
        : { ...m, status: "error", error: e.message })))
      .finally(() => controllers.delete(botId));
  }, [convs]);

  const send = (text, presetDate) => {
    const q = (text ?? input).trim();
    if (q.length < 3 || busy) return;
    const d = presetDate || date;
    let cid = conv?.id;
    if (!cid) cid = convs.create(q, d);
    else if (presetDate) convs.update(cid, (c) => ({ ...c, date: d }));
    const history = messages.filter((m) => m.status !== "error" && m.content)
      .map((m) => ({ role: m.role, content: m.content })).slice(-6);
    const botId = uid();
    convs.update(cid, (c) => ({
      ...c,
      messages: [...c.messages, { id: uid(), role: "user", content: q, date: d },
        { id: botId, role: "assistant", content: "", status: "streaming", steps: [], date: d }],
    }));
    setInput("");
    setSel(botId);
    setTab("sources");
    if (!conv) navigate("chat", cid);
    run(cid, q, d, history, botId);
  };

  const retry = (botId) => {
    const i = messages.findIndex((m) => m.id === botId);
    const userMsg = messages[i - 1];
    if (!userMsg) return;
    const history = messages.slice(0, i - 1).filter((m) => m.content && m.status !== "error")
      .map((m) => ({ role: m.role, content: m.content })).slice(-6);
    convs.update(conv.id, (c) => ({ ...c, messages: c.messages.map((m) => (m.id === botId
      ? { ...m, status: "streaming", error: null, content: "", steps: [], context: null, result: null } : m)) }));
    run(conv.id, userMsg.content, userMsg.date || date, history, botId);
  };

  const rate = (m, v) => {
    if (!m.result?.log_id) return;
    convs.update(conv.id, (c) => ({ ...c, messages: c.messages.map((x) => (x.id === m.id ? { ...x, rating: v } : x)) }));
    api.feedback(m.result.log_id, v).catch(() => {});
  };

  const cite = (m, id) => {
    setSel(m.id); setTab("sources"); setPanelOpen(true);
    setFlash(null); setTimeout(() => setFlash(id), 20);
  };

  const showPanel = panelOpen && messages.length > 0;
  return (
    <div className={`chat ${showPanel ? "with-panel" : ""} ${showPanel && tab === "graph" ? "wide" : ""}`}>
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
        <div className="messages">
          {messages.length === 0 ? (
            <Welcome date={date} onPick={(s) => send(s.question, s.date)} />
          ) : (
            <div className="messages-inner">
              {messages.map((m, i) => m.role === "user"
                ? <div key={m.id} className="msg-user">{m.content}</div>
                : <BotMessage key={m.id} msg={m} selected={selMsg?.id === m.id} hasHistory={i > 1}
                  onSelect={(t) => { setSel(m.id); setTab(t); setPanelOpen(true); }}
                  onCite={(id) => cite(m, id)} onRate={(v) => rate(m, v)} onRetry={() => retry(m.id)} />)}
              <div ref={endRef} />
            </div>
          )}
        </div>
        <div className="composer-wrap">
          <div className="composer">
            <textarea ref={taRef} rows={1} value={input} placeholder={messages.length ? "Hỏi tiếp, ví dụ: Còn xe máy thì sao?" : "Nhập câu hỏi về luật giao thông…"}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />
            <div className="composer-bar">
              <span className="muted small grow">Áp dụng tại ngày {fmtDate(date)} · GraphRAG</span>
              {busy ? (
                <button className="send" title="Dừng" onClick={() => messages.forEach((m) => controllers.get(m.id)?.abort())}><Square size={13} fill="#fff" /></button>
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
