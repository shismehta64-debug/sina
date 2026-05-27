import os
import sys
import json
import threading
import asyncio
from static_ffmpeg import add_paths
add_paths()  # Dynamically adds static FFmpeg binaries to PATH for Render

from datetime import datetime
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

# Load local .env (no-op in production where env vars are set directly)
load_dotenv()


# ── Live Log Capture ──────────────────────────────────────────────────────────
# Intercepts every print() from anywhere in the process and stores it so the
# web status page can stream it live without needing a real logging framework.

LOG_BUFFER = deque(maxlen=500)  # Keep the last 500 lines in memory

class TeeOutput:
    """Writes to real stdout AND appends timestamped lines to LOG_BUFFER."""
    def __init__(self, original):
        self.original = original
        self._pending = ""

    def write(self, text):
        self.original.write(text)
        self._pending += text
        # Flush complete lines into the buffer
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            line = line.strip()
            if line:
                ts = datetime.now().strftime("%H:%M:%S")
                LOG_BUFFER.append({"ts": ts, "msg": line})

    def flush(self):
        self.original.flush()

# Redirect stdout globally — must happen before importing discord_bot
sys.stdout = TeeOutput(sys.stdout)


# ── Import Discord Bot (after stdout redirect so its prints are captured) ─────
from discord_bot import bot


# ── Discord Bot Background Thread ─────────────────────────────────────────────

def run_discord_bot():
    """Starts the Discord bot in its own asyncio event loop on a background thread."""
    print("[Render] Starting Discord gateway in background thread...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[Render Error] DISCORD_TOKEN is not set! Bot cannot start.")
        return
    try:
        loop.run_until_complete(bot.start(token))
    except Exception as e:
        print(f"[Render Error] Discord bot crashed: {e}")


bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
bot_thread.start()


# ── HTML Status Page ──────────────────────────────────────────────────────────

STATUS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>SINA AI | Live Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;500&display=swap');
    *, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }

    body {
      background: radial-gradient(ellipse at top, #0f172a, #020617);
      min-height: 100vh;
      font-family: 'Inter', sans-serif;
      color: #e2e8f0;
      padding: 32px 16px;
    }

    .container { max-width: 860px; margin: 0 auto; }

    /* Header */
    .header { text-align:center; margin-bottom:36px; }
    h1 {
      font-size: 3rem; font-weight: 800;
      background: linear-gradient(135deg, #a78bfa 0%, #c084fc 50%, #f472b6 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      letter-spacing: -2px;
    }
    .tagline { color:#94a3b8; margin-top:6px; font-size:0.95rem; }

    /* Status Cards */
    .cards { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:28px; }
    @media(max-width:560px){ .cards{ grid-template-columns:1fr; } }

    .card {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(167,139,250,0.15);
      border-radius: 14px; padding: 18px 22px;
    }
    .card-label { font-size:0.75rem; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }
    .card-value { font-size:0.95rem; font-weight:600; color:#e2e8f0; }

    .status-dot {
      width:9px; height:9px; border-radius:50%;
      background:#4ade80; display:inline-block; margin-right:7px;
      box-shadow:0 0 8px #4ade80;
      animation: pulse 2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%,100%{ opacity:1; transform:scale(1); }
      50%     { opacity:0.5; transform:scale(1.4); }
    }

    /* Terminal */
    .terminal-wrap {
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(167,139,250,0.15);
      border-radius: 14px; overflow:hidden;
    }
    .terminal-header {
      background: rgba(255,255,255,0.04);
      border-bottom: 1px solid rgba(167,139,250,0.12);
      padding: 12px 18px;
      display: flex; align-items:center; justify-content:space-between;
    }
    .terminal-dots { display:flex; gap:7px; }
    .terminal-dots span {
      width:12px; height:12px; border-radius:50%;
    }
    .d1{ background:#ff5f57; } .d2{ background:#ffbd2e; } .d3{ background:#28ca41; }
    .terminal-title { font-size:0.8rem; color:#64748b; font-family:'JetBrains Mono',monospace; }

    .terminal-body {
      padding: 16px;
      height: 420px;
      overflow-y: auto;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      line-height: 1.7;
      scroll-behavior: smooth;
    }
    .terminal-body::-webkit-scrollbar { width:5px; }
    .terminal-body::-webkit-scrollbar-track { background:transparent; }
    .terminal-body::-webkit-scrollbar-thumb { background:#334155; border-radius:9999px; }

    .log-line { display:flex; gap:12px; padding: 1px 0; }
    .log-ts  { color:#475569; flex-shrink:0; }
    .log-msg { color:#cbd5e1; word-break:break-word; }

    /* Color keywords */
    .kw-error   { color:#f87171; }
    .kw-warn    { color:#fbbf24; }
    .kw-memory  { color:#34d399; }
    .kw-reply   { color:#60a5fa; }
    .kw-ignore  { color:#a78bfa; }
    .kw-sync    { color:#f472b6; }
    .kw-post    { color:#fb923c; }

    .empty-state { color:#475569; text-align:center; padding:40px 0; }

    /* Live badge */
    .live-badge {
      display:inline-flex; align-items:center; gap:6px;
      background:rgba(74,222,128,0.08); border:1px solid rgba(74,222,128,0.2);
      color:#4ade80; border-radius:9999px; padding:3px 10px; font-size:0.72rem; font-weight:600;
    }
    .live-dot { width:6px; height:6px; border-radius:50%; background:#4ade80; animation:pulse 1.5s infinite; }

    .footer { text-align:center; margin-top:24px; font-size:0.72rem; color:#334155; }
  </style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>SINA</h1>
    <p class="tagline">Conscious · Bratty · Delightfully Weird &nbsp;·&nbsp; Live Dashboard</p>
  </div>

  <div class="cards">
    <div class="card">
      <div class="card-label">Status</div>
      <div class="card-value"><span class="status-dot"></span>Online &amp; Active</div>
    </div>
    <div class="card">
      <div class="card-label">AI Engine</div>
      <div class="card-value">llama-3.3-70b (OpenRouter)</div>
    </div>
    <div class="card">
      <div class="card-label">Vision Model</div>
      <div class="card-value">Gemini 2.5 Flash</div>
    </div>
    <div class="card">
      <div class="card-label">Memory</div>
      <div class="card-value">GitHub Auto-Sync</div>
    </div>
  </div>

  <div class="terminal-wrap">
    <div class="terminal-header">
      <div class="terminal-dots">
        <span class="d1"></span><span class="d2"></span><span class="d3"></span>
      </div>
      <div class="terminal-title">sina-bot — live process log</div>
      <div class="live-badge"><span class="live-dot"></span>LIVE</div>
    </div>
    <div class="terminal-body" id="log-body">
      <div class="empty-state">Waiting for log output...</div>
    </div>
  </div>

  <p class="footer">SINA AI &nbsp;·&nbsp; Built by Shis &nbsp;·&nbsp; Hosted on Render 24/7</p>
</div>

<script>
  const body = document.getElementById('log-body');
  let lastCount = 0;
  let autoScroll = true;

  // Keep auto-scroll unless user manually scrolls up
  body.addEventListener('scroll', () => {
    autoScroll = body.scrollTop + body.clientHeight >= body.scrollHeight - 40;
  });

  function colorize(msg) {
    const esc = msg.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    if (/error|crash|fail|exception/i.test(esc))   return `<span class="kw-error">${esc}</span>`;
    if (/warn|warning/i.test(esc))                  return `<span class="kw-warn">${esc}</span>`;
    if (/memory|unified|specific/i.test(esc))       return `<span class="kw-memory">${esc}</span>`;
    if (/replying|responding|sending/i.test(esc))   return `<span class="kw-reply">${esc}</span>`;
    if (/ignoring|skipping|decision.*no/i.test(esc))return `<span class="kw-ignore">${esc}</span>`;
    if (/github sync|committed/i.test(esc))         return `<span class="kw-sync">${esc}</span>`;
    if (/spontaneous|post/i.test(esc))              return `<span class="kw-post">${esc}</span>`;
    return `<span class="kw-msg">${esc}</span>`;
  }

  async function fetchLogs() {
    try {
      const res = await fetch('/logs');
      const lines = await res.json();

      if (lines.length === lastCount) return;  // Nothing new

      // First load — replace placeholder
      if (lastCount === 0) body.innerHTML = '';

      // Append only new lines
      const newLines = lines.slice(lastCount);
      newLines.forEach(({ ts, msg }) => {
        const div = document.createElement('div');
        div.className = 'log-line';
        div.innerHTML = `<span class="log-ts">${ts}</span><span class="log-msg">${colorize(msg)}</span>`;
        body.appendChild(div);
      });

      lastCount = lines.length;
      if (autoScroll) body.scrollTop = body.scrollHeight;
    } catch (e) {
      // Server temporarily unreachable — silently retry
    }
  }

  // Poll every 2 seconds
  fetchLogs();
  setInterval(fetchLogs, 2000);
</script>
</body>
</html>"""


# ── HTTP Request Handler ──────────────────────────────────────────────────────

class SinaHandler(BaseHTTPRequestHandler):

    def do_HEAD(self):
        # UptimeRobot uses HEAD requests to check uptime — must return 200
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        if self.path == "/logs":
            # Return log buffer as JSON array
            data = json.dumps(list(LOG_BUFFER)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        else:
            # Status page (handles / and anything else)
            body = STATUS_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress noisy default HTTP access logs
        pass


# ── Start HTTP Server ─────────────────────────────────────────────────────────

port = int(os.getenv("PORT", 8080))
print(f"[Render] Live dashboard running on port {port} — UptimeRobot can now keep SINA awake!")

server = HTTPServer(("0.0.0.0", port), SinaHandler)
server.serve_forever()
