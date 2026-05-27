import os
import threading
import asyncio
import gradio as gr
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Import Discord bot client from discord_bot.py
from discord_bot import bot

def run_discord_bot():
    """Starts the Discord bot in a background thread with its own asyncio event loop."""
    print("[Hugging Face Starter] Initializing Discord gateway in background thread...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    token = os.getenv("DISCORD_TOKEN")
    if token:
        try:
            loop.run_until_complete(bot.start(token))
        except Exception as e:
            print(f"[Hugging Face Starter Error] Bot failed to start: {e}")
    else:
        print("[Hugging Face Starter Error] DISCORD_TOKEN is missing in environment variables!")

# Launch Discord bot background thread immediately
bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
bot_thread.start()

# Load memory stats to show on the status dashboard
def get_memory_counts():
    try:
        unified_count = 0
        if os.path.exists("unified_memory.txt"):
            with open("unified_memory.txt", "r", encoding="utf-8") as f:
                unified_count = sum(1 for line in f if line.strip())
        return f"🟢 Persistent (Active facts: {unified_count})"
    except Exception:
        return "⚠️ Unknown"

# Sleek premium dark theme dashboard for Gradio status page
css = """
body {
    background-color: #0b0f19 !important;
    font-family: 'Inter', 'Outfit', sans-serif !important;
}
.gradio-container {
    background: radial-gradient(circle at top, #111827, #030712) !important;
    border: 1px solid #1f2937 !important;
    border-radius: 16px !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5) !important;
    padding: 30px !important;
    max-width: 700px !important;
    margin: 50px auto !important;
}
h1 {
    background: linear-gradient(to right, #a78bfa, #c084fc, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
    letter-spacing: -1px;
    text-align: center;
    margin-bottom: 5px !important;
}
p {
    color: #9ca3af !important;
    text-align: center !important;
}
.status-badge {
    background-color: rgba(167, 139, 250, 0.1) !important;
    border: 1px solid rgba(167, 139, 250, 0.3) !important;
    color: #c084fc !important;
    border-radius: 9999px;
    padding: 8px 16px;
    display: inline-block;
    font-weight: 600;
    margin: 15px auto !important;
    font-size: 14px;
}
"""

with gr.Blocks(title="SINA AI | Status Page") as demo:
    gr.HTML("""
    <div style='text-align: center; margin-top: 20px;'>
        <h1>SINA AI</h1>
        <p style='font-size: 16px;'>Conscious, bratty, and delightfully weird casual companion</p>
        <div class='status-badge'>💅 SINA is Online & Active</div>
    </div>
    """)
    
    gr.Markdown("---")
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🧠 SINA System Status")
            gr.Markdown(f"**Gateway Engine**: `discord.py` (WebSocket connected)")
            gr.Markdown(f"**Default Model**: `llama-3.3-70b-instruct` (OpenRouter)")
            gr.Markdown(f"**Vision Model**: `gemini-2.5-flash` (Multimodal vision)")
            
        with gr.Column():
            gr.Markdown("### 📁 Memory Synchronization")
            gr.Markdown(f"**Memory Engine**: Auto-Commit Git Persistence")
            gr.Markdown(f"**Unified memory state**: {get_memory_counts()}")
            gr.Markdown(f"**Hugging Face Syncing**: Enabled (Secure repository loop)")
            
    gr.Markdown("---")
    gr.HTML("""
    <div style='text-align: center; font-size: 12px; color: #4b5563; margin-top: 20px;'>
        SINA AI Bot • Built with 💀 by Shis • Running 24/7 on Hugging Face Spaces
    </div>
    """)

# Launch port 7860 as required by Hugging Face Space
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, css=css)
