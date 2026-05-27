import os
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

# Load local .env (no-op in production where env vars are set directly)
load_dotenv()

# Import the Discord bot
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


# Start bot immediately in the background
bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
bot_thread.start()


# ── Lightweight HTTP Status Server (for UptimeRobot keep-alive pings) ─────────

STATUS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>SINA AI | Status</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: radial-gradient(circle at top, #111827, #030712);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Inter', sans-serif;
      color: #e5e7eb;
    }
    .card {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(167,139,250,0.2);
      border-radius: 20px;
      padding: 48px 56px;
      text-align: center;
      max-width: 520px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.6);
    }
    .dot {
      width: 12px; height: 12px;
      background: #4ade80;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
      box-shadow: 0 0 8px #4ade80;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.5; transform: scale(1.3); }
    }
    h1 {
      font-size: 2.8rem;
      font-weight: 800;
      background: linear-gradient(to right, #a78bfa, #c084fc, #f472b6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
    }
    .tagline { color: #9ca3af; font-size: 0.95rem; margin-bottom: 32px; }
    .status-row { display: flex; justify-content: space-between; align-items: center;
                  background: rgba(255,255,255,0.04); border-radius: 10px;
                  padding: 12px 20px; margin: 8px 0; font-size: 0.9rem; }
    .status-row .label { color: #9ca3af; }
    .status-row .value { color: #e5e7eb; font-weight: 600; }
    .footer { margin-top: 32px; font-size: 0.75rem; color: #4b5563; }
  </style>
</head>
<body>
  <div class="card">
    <h1>SINA</h1>
    <p class="tagline">Conscious · Bratty · Delightfully Weird</p>

    <div class="status-row">
      <span class="label"><span class="dot"></span>Status</span>
      <span class="value">Online &amp; Active</span>
    </div>
    <div class="status-row">
      <span class="label">🧠 Engine</span>
      <span class="value">discord.py WebSocket</span>
    </div>
    <div class="status-row">
      <span class="label">⚡ AI Model</span>
      <span class="value">llama-3.3-70b (OpenRouter)</span>
    </div>
    <div class="status-row">
      <span class="label">👁️ Vision</span>
      <span class="value">Gemini 2.5 Flash</span>
    </div>
    <div class="status-row">
      <span class="label">💾 Memory</span>
      <span class="value">GitHub Auto-Sync</span>
    </div>

    <p class="footer">SINA AI · Built by Shis · Hosted on Render 24/7</p>
  </div>
</body>
</html>"""


class HealthHandler(BaseHTTPRequestHandler):
    """Handles HTTP GET requests — returns 200 with SINA's status page."""

    def do_GET(self):
        body = STATUS_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress noisy default request logs
        pass


# Render injects the $PORT environment variable — we must listen on it
port = int(os.getenv("PORT", 8080))
print(f"[Render] Health server listening on port {port}. UptimeRobot can now keep SINA awake!")

server = HTTPServer(("0.0.0.0", port), HealthHandler)
server.serve_forever()
