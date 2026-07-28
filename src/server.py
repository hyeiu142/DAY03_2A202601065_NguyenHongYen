"""
🌐 WEB UI SERVER — VinUni Lab 3: ReAct Agent Studio (Multi-Turn & Memory Enabled)
Chạy bằng thư viện chuẩn Python (http.server). Hỗ trợ Bộ Nhớ Ngắn Hạn (Short-Term Memory) cho Hội Thoại Đa Bước.
Khởi động: python3 src/server.py
"""

import json
import os
import sys
import traceback
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Setup paths ──────────────────────────────────────────────────────────────
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
sys.path.insert(0, SRC_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from tools import AVAILABLE_TOOLS
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_SYSTEM_PROMPT,
    MAX_ITERATIONS,
    GUARDRAIL_TRIGGERED_MESSAGE,
)
from providers import get_llm_provider
from app import load_test_cases, parse_llm_response, call_tool, POSITIONAL_PARAMS

# ── Session Memories Store (Short-Term Memory) ─────────────────────────────
# Key: session_id, Value: list of message objects {"role": "user"|"assistant", "content": "..."}
SESSION_MEMORIES: dict[str, list[dict[str, str]]] = {}

# ── HTML UI ──────────────────────────────────────────────────────────────────
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VinUni Lab 3 — ReAct Agent Studio (Memory Enabled)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:'Outfit',sans-serif;
  background:#07101f;
  color:#e2e8f0;
  min-height:100vh;
  background-image:
    radial-gradient(ellipse at 10% 5%, rgba(99,102,241,.18) 0,transparent 55%),
    radial-gradient(ellipse at 90% 90%, rgba(6,182,212,.12) 0,transparent 55%);
}

header{
  background:rgba(10,18,35,.85);
  backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(255,255,255,.07);
  padding:0 32px;
  height:64px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  position:sticky;top:0;z-index:50;
}
.hd-left{display:flex;align-items:center;gap:14px}
.hd-icon{
  background:linear-gradient(135deg,#6366f1,#0ea5e9);
  width:40px;height:40px;border-radius:12px;
  display:flex;align-items:center;justify-content:center;font-size:20px;
  box-shadow:0 0 18px rgba(99,102,241,.45);
}
.hd-title{font-size:17px;font-weight:700;
  background:linear-gradient(90deg,#fff 0%,#a5b4fc 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}
.hd-sub{font-size:11px;color:#64748b;margin-top:1px}
.hd-actions{display:flex;align-items:center;gap:12px}

.badge-provider{
  display:flex;align-items:center;gap:8px;
  background:rgba(99,102,241,.12);
  border:1px solid rgba(99,102,241,.3);
  padding:6px 14px;border-radius:20px;
  font-size:13px;font-weight:600;color:#a5b4fc;
}
.dot-live{width:8px;height:8px;border-radius:50%;
  background:#22c55e;box-shadow:0 0 8px #22c55e}

.btn-reset-mem{
  background:rgba(239,68,68,.15);
  border:1px solid rgba(239,68,68,.3);
  color:#f87171;border-radius:20px;
  padding:6px 14px;font-size:12px;font-weight:600;
  cursor:pointer;transition:all .2s;font-family:inherit;
}
.btn-reset-mem:hover{background:rgba(239,68,68,.25);transform:scale(1.05)}

.main{display:grid;grid-template-columns:300px 1fr;gap:20px;padding:20px;max-width:1600px;margin:0 auto}
.sidebar{display:flex;flex-direction:column;gap:16px}
.card{
  background:rgba(17,28,50,.7);
  border:1px solid rgba(255,255,255,.07);
  border-radius:16px;padding:18px;
  backdrop-filter:blur(10px);
}
.card-title{
  font-size:11px;font-weight:700;letter-spacing:1px;
  text-transform:uppercase;color:#64748b;
  margin-bottom:12px;display:flex;align-items:center;gap:6px;
}
.tc-btn{
  display:block;width:100%;
  background:rgba(255,255,255,.03);
  border:1px solid rgba(255,255,255,.07);
  border-radius:10px;padding:10px 12px;
  color:#e2e8f0;text-align:left;cursor:pointer;
  transition:all .2s;margin-bottom:8px;font-family:inherit;
}
.tc-btn:hover{background:rgba(99,102,241,.15);border-color:rgba(99,102,241,.4);transform:translateX(4px)}
.tc-tag{
  font-size:10px;font-weight:700;padding:2px 8px;
  border-radius:20px;margin-bottom:5px;display:inline-block;
}
.tc-q{font-size:12px;color:#94a3b8;line-height:1.4;margin-top:3px}
.g-green{background:rgba(34,197,94,.15);color:#4ade80}
.g-yellow{background:rgba(234,179,8,.15);color:#fbbf24}
.g-red{background:rgba(239,68,68,.15);color:#f87171}

.guard-row{font-size:12px;color:#64748b;line-height:1.8}
.guard-row b{color:#94a3b8}

.content{display:flex;flex-direction:column;gap:16px}

.query-bar{display:flex;gap:10px}
.q-input{
  flex:1;
  background:rgba(10,18,35,.9);
  border:1px solid rgba(255,255,255,.1);
  border-radius:12px;padding:14px 18px;
  color:#fff;font-size:14px;font-family:inherit;outline:none;
  transition:all .2s;
}
.q-input:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.2)}
.q-input::placeholder{color:#475569}
.run-btn{
  background:linear-gradient(135deg,#6366f1,#0ea5e9);
  border:none;border-radius:12px;
  padding:0 24px;color:#fff;font-size:14px;font-weight:700;
  cursor:pointer;transition:all .2s;font-family:inherit;
  white-space:nowrap;
  box-shadow:0 4px 18px rgba(99,102,241,.35);
}
.run-btn:hover{opacity:.9;transform:translateY(-2px)}
.run-btn:disabled{opacity:.5;cursor:wait;transform:none}

.results{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}

.r-card{
  background:rgba(17,28,50,.7);
  border:1px solid rgba(255,255,255,.07);
  border-radius:16px;overflow:hidden;
}
.r-header{
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 18px;
  border-bottom:1px solid rgba(255,255,255,.06);
  background:rgba(0,0,0,.2);
}
.r-title{font-size:14px;font-weight:700;display:flex;align-items:center;gap:8px}
.r-body{padding:16px;max-height:650px;overflow-y:auto}

.history-turn{
  border-bottom:1px dashed rgba(255,255,255,.1);
  padding-bottom:14px;margin-bottom:14px;
}
.turn-user{
  font-size:12px;font-weight:700;color:#38bdf8;margin-bottom:6px;
  display:flex;align-items:center;gap:6px;
}

.step-box{
  background:rgba(10,18,35,.6);
  border:1px solid rgba(255,255,255,.05);
  border-radius:10px;padding:12px 14px;margin-bottom:10px;font-size:12px;
}
.step-label{
  font-size:10px;font-weight:700;letter-spacing:.8px;
  text-transform:uppercase;color:#6366f1;margin-bottom:6px;
}
.thought-txt{color:#cbd5e1;line-height:1.5}
.action-pill{
  display:inline-block;
  background:rgba(6,182,212,.12);border:1px solid rgba(6,182,212,.25);
  color:#38bdf8;border-radius:6px;padding:4px 10px;
  font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:600;
  margin:6px 0;
}
.obs-block{
  background:rgba(0,0,0,.4);
  border-left:3px solid #f59e0b;
  border-radius:0 6px 6px 0;
  padding:8px 10px;margin-top:6px;
  font-family:'JetBrains Mono',monospace;font-size:10px;color:#94a3b8;
  max-height:120px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;
}

.final-answer{
  background:rgba(34,197,94,.08);
  border:1px solid rgba(34,197,94,.25);
  border-radius:10px;padding:14px 16px;
  font-size:13px;color:#86efac;line-height:1.6;margin-top:6px;
}
.final-label{
  font-size:10px;font-weight:700;letter-spacing:.8px;
  text-transform:uppercase;color:#22c55e;margin-bottom:6px;
}

.baseline-answer{
  background:rgba(59,130,246,.08);
  border:1px solid rgba(59,130,246,.2);
  border-radius:10px;padding:14px 16px;
  font-size:13px;color:#93c5fd;line-height:1.6;
}

.empty-state{
  padding:40px 20px;text-align:center;color:#334155;
}
.empty-ico{font-size:36px;margin-bottom:8px;opacity:.5}
.empty-txt{font-size:12px}

.spin{
  display:inline-block;width:16px;height:16px;
  border:2px solid rgba(255,255,255,.2);border-radius:50%;
  border-top-color:#fff;animation:_spin .7s linear infinite;vertical-align:middle;
}
@keyframes _spin{to{transform:rotate(360deg)}}

::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#334155;border-radius:4px}
</style>
</head>
<body>

<header>
  <div class="hd-left">
    <div class="hd-icon">🏫</div>
    <div>
      <div class="hd-title">ĐẠI HỌC VINUNI — AI LAB 3 STUDIO</div>
      <div class="hd-sub">So Sánh Baseline Chatbot vs ReAct Agent | Đa Lượt (Multi-Turn Memory)</div>
    </div>
  </div>
  <div class="hd-actions">
    <button class="btn-reset-mem" onclick="resetMemory()">🗑️ Reset Bộ Nhớ (New Session)</button>
    <div class="badge-provider">
      <div class="dot-live"></div>
      <span id="llm-badge">Loading...</span>
    </div>
  </div>
</header>

<div class="main">

  <div class="sidebar">
    <div class="card">
      <div class="card-title">🧪 Test Cases (Click để thử)</div>
      <div id="tc-list"><div class="empty-state"><span class="spin"></span></div></div>
    </div>
    <div class="card">
      <div class="card-title">🧠 Short-Term Memory Status</div>
      <div class="guard-row">• <b>Session ID:</b> <span id="session-id-txt">default</span></div>
      <div class="guard-row">• <b>Memory Turns:</b> <span id="turn-count-txt">0 lượt</span></div>
      <div class="guard-row">• <b>State:</b> Lưu mã đơn, item_id & câu trả lời cũ</div>
      <div class="guard-row">• <b>Multi-turn Chat:</b> Đã bật (Có thể hỏi tiếp)</div>
    </div>
  </div>

  <div class="content">

    <div class="query-bar">
      <input id="qinput" class="q-input" type="text"
        placeholder="Nhập câu hỏi hoặc nói 'Có, hãy tạo phiếu hoàn tiền cho tôi'..."
        onkeydown="if(event.key==='Enter') doRun()">
      <button class="run-btn" id="runbtn" onclick="doRun()">Gửi Chat ⚡</button>
    </div>

    <div class="results">
      <div class="r-card">
        <div class="r-header">
          <div class="r-title">💬 Baseline Chatbot <small style="font-size:11px;color:#475569">(Level 2)</small></div>
          <span class="tc-tag g-yellow">No Memory / No Tools</span>
        </div>
        <div class="r-body" id="out-baseline">
          <div class="empty-state"><div class="empty-ico">🤖</div><div class="empty-txt">Chưa có cuộc trò chuyện nào</div></div>
        </div>
      </div>

      <div class="r-card">
        <div class="r-header">
          <div class="r-title">🧠 ReAct Agent <small style="font-size:11px;color:#475569">(Level 3)</small></div>
          <span class="tc-tag g-green">Short-Term Memory Active</span>
        </div>
        <div class="r-body" id="out-react">
          <div class="empty-state"><div class="empty-ico">⚡</div><div class="empty-txt">Chưa có cuộc trò chuyện nào</div></div>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
let sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
document.getElementById('session-id-txt').textContent = sessionId;

let historyTurns = [];

fetch('/api/meta').then(r=>r.json()).then(d=>{
  document.getElementById('llm-badge').textContent = d.provider + ' (' + d.model + ')';
});

fetch('/api/test-cases').then(r=>r.json()).then(tcs=>{
  const el = document.getElementById('tc-list');
  el.innerHTML = '';
  tcs.forEach(tc=>{
    const isGreen = tc.category.includes('Đơn giản');
    const isRed   = tc.category.includes('Edge');
    const cls     = isGreen ? 'g-green' : (isRed ? 'g-red' : 'g-yellow');
    const btn = document.createElement('button');
    btn.className = 'tc-btn';
    btn.innerHTML = `<span class="tc-tag ${cls}">Test #${tc.id}</span><div class="tc-q">${tc.question}</div>`;
    btn.onclick = () => { document.getElementById('qinput').value = tc.question; doRun(); };
    el.appendChild(btn);
  });
});

function resetMemory(){
  fetch('/api/reset-memory', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sessionId})
  })
  .then(r=>r.json())
  .then(d=>{
    historyTurns = [];
    document.getElementById('turn-count-txt').textContent = '0 lượt';
    document.getElementById('out-baseline').innerHTML = '<div class="empty-state"><div class="empty-ico">🤖</div><div class="empty-txt">Đã reset bộ nhớ hội thoại</div></div>';
    document.getElementById('out-react').innerHTML = '<div class="empty-state"><div class="empty-ico">⚡</div><div class="empty-txt">Đã reset bộ nhớ hội thoại</div></div>';
  });
}

function doRun(){
  const q = document.getElementById('qinput').value.trim();
  if(!q) return;

  const btn = document.getElementById('runbtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Đang suy luận...';

  document.getElementById('qinput').value = '';

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({query: q, session_id: sessionId})
  })
  .then(r => r.json())
  .then(data => {
    btn.disabled = false;
    btn.innerHTML = 'Gửi Chat ⚡';

    historyTurns.push({
      query: q,
      baseline: data.baseline,
      react: data.react
    });

    document.getElementById('turn-count-txt').textContent = historyTurns.length + ' lượt';
    renderAllTurns();
  })
  .catch(err => {
    btn.disabled = false;
    btn.innerHTML = 'Gửi Chat ⚡';
    alert('Lỗi: ' + err);
  });
}

function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function renderAllTurns(){
  let baseHtml = '';
  let reactHtml = '';

  historyTurns.forEach((turn, turnIdx) => {
    baseHtml += `
      <div class="history-turn">
        <div class="turn-user">💬 Lượt ${turnIdx+1}: ${esc(turn.query)}</div>
        <div class="baseline-answer">${esc(turn.baseline).replace(/\n/g,'<br>')}</div>
      </div>
    `;

    reactHtml += `
      <div class="history-turn">
        <div class="turn-user">💬 Lượt ${turnIdx+1}: ${esc(turn.query)}</div>
    `;
    turn.react.steps.forEach(s => {
      reactHtml += `<div class="step-box">
        <div class="step-label">🔄 Step ${s.step} / ${turn.react.max_steps}</div>
        <div class="thought-txt">💭 ${esc(s.thought)}</div>`;
      if(s.action){
        reactHtml += `<div><span class="action-pill">🛠️ ${esc(s.action)}</span></div>`;
      }
      if(s.observation){
        let obs = s.observation;
        try { obs = JSON.stringify(JSON.parse(obs), null, 2); } catch(e){}
        reactHtml += `<div class="obs-block">👁️ ${esc(obs)}</div>`;
      }
      reactHtml += `</div>`;
    });

    if(turn.react.final_answer){
      reactHtml += `<div class="final-answer"><div class="final-label">🏁 Final Answer</div>${esc(turn.react.final_answer).replace(/\n/g,'<br>')}</div>`;
    }
    reactHtml += `</div>`;
  });

  const baseContainer = document.getElementById('out-baseline');
  const reactContainer = document.getElementById('out-react');

  baseContainer.innerHTML = baseHtml;
  reactContainer.innerHTML = reactHtml;

  baseContainer.scrollTop = baseContainer.scrollHeight;
  reactContainer.scrollTop = reactContainer.scrollHeight;
}
</script>
</body>
</html>
"""


# ── Business Logic ────────────────────────────────────────────────────────────
_provider = None


def get_provider():
    global _provider
    if _provider is None:
        _provider = get_llm_provider()
    return _provider


def run_baseline(query: str) -> str:
    try:
        return get_provider().generate(query, system_prompt=CHATBOT_BASELINE_PROMPT)
    except Exception as e:
        return f"[Lỗi Baseline]: {e}"


def run_react_trace(query: str, session_id: str = "default") -> dict:
    provider = get_provider()

    if session_id not in SESSION_MEMORIES:
        SESSION_MEMORIES[session_id] = []

    history = SESSION_MEMORIES[session_id]

    # Build memory context from previous turns
    memory_context = ""
    if history:
        memory_context = "BỘ NHỚ HỘI THOẠI TRƯỚC ĐÓ (SHORT-TERM MEMORY):\n"
        for turn in history[-4:]:  # Keep last 4 turns for context
            memory_context += f"Người dùng: {turn['user']}\nAgent: {turn['assistant']}\n---\n"
        memory_context += "\n"

    scratchpad = f"{memory_context}Câu hỏi hiện tại của người dùng: {query}\n"
    steps = []
    final_answer = None

    for step_num in range(1, MAX_ITERATIONS + 1):
        try:
            raw = provider.generate(scratchpad, system_prompt=REACT_SYSTEM_PROMPT)
        except Exception as e:
            steps.append({"step": step_num, "thought": f"LLM lỗi: {e}", "action": None, "observation": None})
            final_answer = f"Hệ thống gặp lỗi khi gọi LLM: {e}"
            break

        parsed = parse_llm_response(raw)

        if parsed[0] == "invalid":
            steps.append({"step": step_num, "thought": raw.strip()[:300], "action": None, "observation": None})
            final_answer = raw.strip() or "Xin lỗi, tôi chưa có câu trả lời."
            break

        if parsed[0] == "final":
            thought_display = raw.split("Final Answer:")[0].replace("Thought:", "").strip()
            steps.append({"step": step_num, "thought": thought_display or parsed[1], "action": None, "observation": None})
            final_answer = parsed[1]
            break

        # Action
        _, tool_name, args = parsed
        param_order = POSITIONAL_PARAMS.get(tool_name, list(args.keys()))
        args_display = ", ".join(str(args.get(p, "")) for p in param_order)
        action_str = f"{tool_name}[{args_display}]"
        observation = call_tool(tool_name, args)

        thought_part = raw.split("Action:")[0].replace("Thought:", "").strip() if "Action:" in raw else raw.strip()
        steps.append({
            "step": step_num,
            "thought": thought_part[:300],
            "action": action_str,
            "observation": observation
        })
        scratchpad += f"\n{raw.strip()}\nObservation: {observation}\n"

    if final_answer is None:
        final_answer = GUARDRAIL_TRIGGERED_MESSAGE

    # Save turn to short-term memory
    history.append({"user": query, "assistant": final_answer})

    return {"max_steps": MAX_ITERATIONS, "steps": steps, "final_answer": final_answer}


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.date_time_string()}] {fmt % args}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_html(HTML_PAGE)
        elif path == "/api/test-cases":
            try:
                tests = load_test_cases()
                self._send_json(tests)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif path == "/api/meta":
            p = get_provider()
            self._send_json({
                "provider": p.__class__.__name__.replace("Provider", ""),
                "model": getattr(p, "model_name", "Unknown"),
            })
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/run":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                query = body.get("query", "").strip()
                session_id = body.get("session_id", "default")
                if not query:
                    self._send_json({"error": "query is empty"}, 400)
                    return

                baseline = run_baseline(query)
                react = run_react_trace(query, session_id=session_id)

                self._send_json({
                    "query": query,
                    "baseline": baseline,
                    "react": react,
                })
            except Exception:
                tb = traceback.format_exc()
                print(tb)
                self._send_json({"error": tb}, 500)

        elif path == "/api/reset-memory":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                session_id = body.get("session_id", "default")
                SESSION_MEMORIES[session_id] = []
                self._send_json({"status": "ok", "message": f"Memory cleared for session {session_id}"})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self.send_error(404)


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    p = get_provider()
    print(f"🔌 Provider: {p.__class__.__name__} | Model: {getattr(p, 'model_name', '?')}")
    print(f"═══════════════════════════════════════════════════")
    print(f"  🚀  Web UI đang chạy tại:  http://localhost:{port}")
    print(f"  🧠  Short-Term Memory Enabled (Multi-Turn Chat Supported)")
    print(f"═══════════════════════════════════════════════════")
    server = HTTPServer(("0.0.0.0", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server đã dừng.")
