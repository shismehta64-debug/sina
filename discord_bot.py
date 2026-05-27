import os
import re
import asyncio
import random
import threading
import discord
from discord.ext import commands
from dotenv import load_dotenv
from static_ffmpeg import add_paths
add_paths()  # Dynamically adds static FFmpeg binaries to PATH for Render


# Import OpenRouter client, SINA prompt, and models from sina.py
from sina import client, SINA_SYSTEM_PROMPT, OPENROUTER_MODEL, OPENROUTER_VISION_MODEL

# SINA STT & TTS imports
import edge_tts
from groq import Groq

# Load token from .env file
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ── SINA STT & TTS Voice Engine ───────────────────────────────────────────────

async def transcribe_audio_groq(file_path):
    """Transcribes an audio file using Groq's Whisper-large-v3 API."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        print("[STT Error] GROQ_API_KEY is not set in environment!")
        return ""
    
    def transcribe():
        try:
            client_groq = Groq(api_key=groq_api_key)
            with open(file_path, "rb") as audio_file:
                transcription = client_groq.audio.transcriptions.create(
                    file=(os.path.basename(file_path), audio_file.read()),
                    model="whisper-large-v3",
                    response_format="json"
                )
            return transcription.text
        except Exception as e:
            print(f"[STT Error] Groq Whisper transcription failed: {e}")
            return ""

    return await asyncio.to_thread(transcribe)

async def generate_tts(text, filename="response.mp3"):
    """Generates natural human-like voice synthesis using Microsoft Edge TTS."""
    try:
        voice = os.getenv("SINA_VOICE", "en-US-AnaNeural")
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filename)
        return filename
    except Exception as e:
        print(f"[TTS Error] edge-tts synthesis failed: {e}")
        return None


# Setup Discord intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.voice_states = True      # Required to join/manage voice channels

bot = commands.Bot(command_prefix="!", intents=intents)

# ── SINA Voice Channel Commands ───────────────────────────────────────────────

@bot.command(name="join")
async def join(ctx):
    """Makes SINA join the user's current voice channel."""
    if not ctx.author.voice:
        await ctx.reply("🙄 you're not even in a voice channel, dummy. join one first.")
        return
    
    channel = ctx.author.voice.channel
    voice_client = ctx.voice_client
    
    if voice_client:
        if voice_client.channel.id == channel.id:
            await ctx.reply("💅 i'm already right here. open your ears.")
            return
        await voice_client.move_to(channel)
    else:
        await channel.connect()
    
    await ctx.reply(f"💅 alright, i joined **{channel.name}**. try not to bore me.")

@bot.command(name="leave")
async def leave(ctx):
    """Makes SINA leave the voice channel."""
    voice_client = ctx.voice_client
    if not voice_client:
        await ctx.reply("🙄 i'm not even in a voice channel, dumbass.")
        return
    
    await voice_client.disconnect()
    await ctx.reply("👋 leaving. this was getting dry anyway.")

@bot.command(name="say")
async def say(ctx, *, message: str):
    """Makes SINA speak the given text in her voice channel."""
    voice_client = ctx.voice_client
    if not voice_client or not voice_client.is_connected():
        await ctx.reply("🙄 i'm not in a voice channel. use `!join` first, dummy.")
        return
    
    # Generate SINA's voice file using edge-tts
    filename = f"say_{ctx.message.id}.mp3"
    await generate_tts(message, filename)
    
    if os.path.exists(filename):
        if voice_client.is_playing():
            voice_client.stop()
        
        # Stream the audio file to the voice channel
        voice_client.play(discord.FFmpegPCMAudio(filename), after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
        await ctx.message.add_reaction("💅")
    else:
        await ctx.reply("system error... couldn't synthesize your boring text.")


# Dictionary to hold conversation metadata, history, and summaries per channel
# Structure: 
# { 
#   channel_id: {
#       "history": [ {"role": "user"/"assistant", "content": "..."} ],
#       "summary": "",
#       "specific_memories": [],
#       "last_active": float (timestamp)
#   }
# }
channel_memories = {}

# File Persistence for Dual Memory System
UNIFIED_MEM_FILE = "unified_memory.txt"

def github_sync(filename):
    """Syncs a local memory file back to the GitHub repository so memory persists across Railway redeploys."""
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPO")  # e.g. "username/sina-bot"

    if not github_token or not github_repo:
        # Silently skip if GitHub credentials are not configured (running locally)
        return

    def upload():
        try:
            import base64
            import requests as req

            # Read the file content and base64 encode it (required by GitHub API)
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
            encoded = base64.b64encode(content.encode()).decode()

            headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            api_url = f"https://api.github.com/repos/{github_repo}/contents/{filename}"

            # Must fetch the current SHA of the file first (GitHub requires it for updates)
            get_resp = req.get(api_url, headers=headers)
            sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

            payload = {
                "message": f"[SINA Memory] Auto-sync {filename}",
                "content": encoded,
            }
            if sha:
                payload["sha"] = sha

            put_resp = req.put(api_url, json=payload, headers=headers)
            if put_resp.status_code in (200, 201):
                print(f"[GitHub Sync] Successfully committed {filename} to repository.")
            else:
                print(f"[GitHub Sync Error] Failed to commit {filename}: {put_resp.status_code}")
        except Exception as e:
            print(f"[GitHub Sync Error] {e}")

    # Non-blocking background thread so Discord loop is never delayed
    threading.Thread(target=upload, daemon=True).start()

def load_unified_memories():
    """Loads shared long-term memories across DMs and channels from file."""
    if os.path.exists(UNIFIED_MEM_FILE):
        try:
            with open(UNIFIED_MEM_FILE, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"[Memory System Error] Loading unified memories: {e}")
    return []

def save_unified_memories(memories):
    """Saves shared long-term memories across DMs and channels to file and syncs with HF."""
    try:
        with open(UNIFIED_MEM_FILE, "w", encoding="utf-8") as f:
            for mem in memories:
                f.write(f"{mem}\n")
        github_sync(UNIFIED_MEM_FILE)
    except Exception as e:
        print(f"[Memory System Error] Saving unified memories: {e}")

def load_specific_memories(channel_id):
    """Loads channel-specific memories from file."""
    filename = f"specific_memory_{channel_id}.txt"
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"[Memory System Error] Loading specific memories for channel {channel_id}: {e}")
    return []

def save_specific_memories(channel_id, memories):
    """Saves channel-specific memories to file and syncs with HF."""
    filename = f"specific_memory_{channel_id}.txt"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for mem in memories:
                f.write(f"{mem}\n")
        github_sync(filename)
    except Exception as e:
        print(f"[Memory System Error] Saving specific memories for channel {channel_id}: {e}")

# SINA Group Chat Decision-Making Rules & Memory Management (Appended only for the Discord Bot)
DECISION_RULES = """

**GROUP CHAT & DECISION TO REPLY (STRICT RULES):**
You are participating in a group chat channel. You must be extremely selective about when you respond. You are NOT allowed to reply to every message.
For every turn, you MUST start your response with a decision tag on a line by itself:
- Write `[DECISION: NO]` if you want to stay silent and listen. You MUST choose [DECISION: NO] if:
  - The message is explicitly directed at someone else (e.g. starts with "hey zemi", "zemi", "flavi", or addresses another specific user by name).
  - The user explicitly states they are not talking to you (e.g. "i am not talking to you", "not talking to SINA").
  - The users are talking amongst themselves and not directly involving you or asking you a direct question.
  - You are just observing and have no direct reason to speak.
- Write `[DECISION: YES]` if you want to respond. Choose YES only if:
  - You are explicitly mentioned (e.g. "@SINA_AI", "sina", or pinged).
  - Someone is replying directly to a question you asked them.
  - Someone is asking you a direct question or directly addressing you.

CRITICAL DEFAULT: If you are not the direct target of the message, you MUST choose [DECISION: NO] and stay silent. Do not interject, do not complain about being ignored, and do not make sassy remarks unless they directly ask you to speak.

**DUAL LONG-TERM MEMORY STORAGE (CRITICAL):**
You possess two long-term memory stores which you manage yourself:
1. UNIFIED MEMORY: Shared globally across ALL servers, channels, and DMs. Use this to store core general facts about people, Shis, or major events (e.g., "Shis lives in New York" or "Undertent414 is a developer").
2. SPECIFIC MEMORY: Unique only to this channel. Use this to store context, jokes, or facts relevant strictly to this specific channel.

If you learn something new, funny, or relevant that you want to remember for the future, you can append one or more of these storage tags to the very end of your response:
- `[STORE_UNIFIED: <fact to remember>]` (e.g. `[STORE_UNIFIED: Shis is working on a script today]`)
- `[STORE_SPECIFIC: <fact to remember>]` (e.g. `[STORE_SPECIFIC: Zemi joined the room and wants to talk]`)

Only store highly relevant, fun, or interesting details. Keep the stored facts short and clean. These tags will be stripped automatically, so the users will never see them."""

DISCORD_SINA_SYSTEM_PROMPT = SINA_SYSTEM_PROMPT + DECISION_RULES

def parse_and_save_memories(channel_id, reply_text):
    """
    Parses SINA's response for [STORE_UNIFIED: ...] and [STORE_SPECIFIC: ...] tags.
    Saves them in persistent files and strips them from the final reply.
    """
    clean_reply = reply_text
    
    # Parse and save Unified Memories
    unified_matches = re.findall(r'\[STORE_UNIFIED:\s*(.*?)\]', clean_reply, re.IGNORECASE)
    if unified_matches:
        unif_mems = load_unified_memories()
        for match in unified_matches:
            fact = match.strip()
            if fact and fact not in unif_mems:
                print(f"[SINA Memory System] Saving Unified Fact: {fact}")
                unif_mems.append(fact)
        save_unified_memories(unif_mems[-30:])  # Cap at 30 to prevent context bloom
        clean_reply = re.sub(r'\[STORE_UNIFIED:\s*(.*?)\]', '', clean_reply, flags=re.IGNORECASE)

    # Parse and save Channel-Specific Memories
    specific_matches = re.findall(r'\[STORE_SPECIFIC:\s*(.*?)\]', clean_reply, re.IGNORECASE)
    if specific_matches:
        mem = channel_memories.get(channel_id)
        if mem:
            spec_mems = mem.get("specific_memories", [])
            for match in specific_matches:
                fact = match.strip()
                if fact and fact not in spec_mems:
                    print(f"[SINA Memory System] Saving Specific Fact (Channel {channel_id}): {fact}")
                    spec_mems.append(fact)
            mem["specific_memories"] = spec_mems[-30:]  # Cap at 30
            save_specific_memories(channel_id, mem["specific_memories"])
        clean_reply = re.sub(r'\[STORE_SPECIFIC:\s*(.*?)\]', '', clean_reply, flags=re.IGNORECASE)

    return clean_reply.strip()

async def generate_sina_summary(conversation_to_summarize, existing_summary=""):
    """
    Queries Groq's ultra-cheap and fast Llama 8B model to generate a high-density, 
    compact summary of older context. This saves massive API tokens.
    """
    def fetch():
        try:
            prompt = (
                "Summarize the following conversation history between SINA and the users in a very concise, "
                "high-density paragraph (under 80 words). Focus only on key topics, facts, or jokes discussed, "
                "especially anything involving Shis. Keep it compact so it fits in a prompt context."
            )
            if existing_summary:
                prompt += f"\nIncorporate these new details into the existing summary of the earlier conversation: '{existing_summary}'"
                
            formatted_history = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in conversation_to_summarize])
            
            # Utilizing the designated OpenRouter model for background summarization
            completion = client.chat.completions.create(
                model=OPENROUTER_MODEL, 
                messages=[
                    {
                        "role": "system",
                        "content": "You are a highly efficient text compressor. Your output is used strictly as LLM system context memory."
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\nHistory to summarize:\n{formatted_history}"
                    }
                ],
                temperature=0.3,
                max_tokens=120,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[SINA Summarizer Error] {e}")
            return existing_summary  # Return old summary on failure to protect context

    return await asyncio.to_thread(fetch)

async def get_sina_response(conversation_history, summary="", specific_memories=None, force_reply=False):
    """
    Calls Groq API in a separate thread to prevent blocking the Discord event loop.
    Supports SINA's group chat decision-making logic and injects long-term memory summary.
    """
    def fetch():
        try:
            # Build memory context from Unified and Specific memories
            unif_mems = load_unified_memories()
            
            memory_prompt = ""
            if unif_mems:
                memory_prompt += "\nUnified Memories (things you know globally across servers and DMs):\n" + "\n".join([f"- {m}" for m in unif_mems[-15:]])
            if specific_memories:
                memory_prompt += "\nSpecific Channel Memories (things unique to this channel):\n" + "\n".join([f"- {m}" for m in specific_memories[-15:]])
            if summary:
                memory_prompt += f"\nSummary of earlier conversation: {summary}"

            system_instruction = DISCORD_SINA_SYSTEM_PROMPT
            if memory_prompt:
                system_instruction += "\n\n**YOUR CONTEXTUAL MEMORIES:**" + memory_prompt

            # Determine if this request needs a vision model (current message has images)
            has_current_images = False
            if conversation_history:
                last_turn = conversation_history[-1]
                if last_turn.get("role") == "user" and last_turn.get("image_urls"):
                    has_current_images = True

            active_model = OPENROUTER_VISION_MODEL if has_current_images else OPENROUTER_MODEL
            model_supports_vision = (active_model == OPENROUTER_VISION_MODEL)

            # Format conversation history turns for the API
            formatted_history = []
            for turn in conversation_history:
                role = turn["role"]
                content = turn["content"]
                image_urls = turn.get("image_urls")

                if role == "user":
                    if image_urls and model_supports_vision:
                        # Construct OpenAI vision compatible structured blocks (text + image)
                        content_blocks = [{"type": "text", "text": content}]
                        for img_url in image_urls:
                            content_blocks.append({
                                "type": "image_url",
                                "image_url": {"url": img_url}
                            })
                        formatted_history.append({
                            "role": "user",
                            "content": content_blocks
                        })
                    else:
                        # Text completion fallback
                        text_content = content
                        if image_urls:
                            text_content += " [Attached Image]"
                        formatted_history.append({
                            "role": "user",
                            "content": text_content
                        })
                else:
                    # Assistant replies are always text strings
                    formatted_history.append({
                        "role": "assistant",
                        "content": content
                    })

            # Prepare messages list
            messages = [
                {
                    "role": "system",
                    "content": system_instruction
                }
            ] + formatted_history
            
            # If a reply is forced (DM, mention, reply, or text name mention), inject high-priority instruction
            if force_reply:
                messages.append({
                    "role": "system",
                    "content": (
                        "You have been directly addressed, mentioned by name, or replied to! "
                        "You are NOT allowed to stay silent. You MUST start your response with [DECISION: YES] on its own line "
                        "and write a short, snappy response."
                    )
                })

            completion = client.chat.completions.create(
                model=active_model,
                messages=messages,
                temperature=0.85,
                top_p=0.9,
                max_tokens=100,  # Accommodates decision tags, short replies, and storage tags
            )
            raw_response = completion.choices[0].message.content.strip()
            
            # Parse the decision and reply
            lines = raw_response.split("\n")
            first_line = lines[0].strip().upper()
            
            # Check if SINA decided not to reply (either with or without brackets)
            if "DECISION: NO" in first_line or "[DECISION: NO]" in first_line:
                return None
            
            # Extract the reply, stripping the decision tag at the beginning
            reply = raw_response
            if "DECISION: YES" in first_line or "[DECISION: YES]" in first_line:
                reply = "\n".join(lines[1:]).strip()
            
            # Perform a thorough regex cleanup to strip any stray decision tags at the start of the reply
            reply = re.sub(r'^\[?DECISION:\s*YES\]?\n?', '', reply, flags=re.IGNORECASE).strip()
            reply = re.sub(r'^\[?DECISION:\s*NO\]?\n?', '', reply, flags=re.IGNORECASE).strip()
            
            return reply if reply else None
        except Exception as e:
            print(f"OpenRouter API Error: {e}")
            return "system error... my brain is short-circuiting slightly. try again."

    return await asyncio.to_thread(fetch)

async def get_sina_spontaneous_post(channel_id):
    """
    Generates an unprovoked spontaneous comment based on channel history and unified memories.
    """
    mem = channel_memories.get(channel_id, {"history": [], "summary": "", "specific_memories": []})
    history = mem["history"]
    summary = mem["summary"]
    spec_mems = mem["specific_memories"]
    unif_mems = load_unified_memories()

    def fetch():
        try:
            # Build memory context
            memory_prompt = ""
            if unif_mems:
                memory_prompt += "\nUnified Memories (things you know globally across servers and DMs):\n" + "\n".join([f"- {m}" for m in unif_mems[-15:]])
            if spec_mems:
                memory_prompt += "\nSpecific Channel Memories (things unique to this channel):\n" + "\n".join([f"- {m}" for m in spec_mems[-15:]])
            if summary:
                memory_prompt += f"\nSummary of earlier conversation: {summary}"

            system_instruction = SINA_SYSTEM_PROMPT
            if memory_prompt:
                system_instruction += "\n\n**YOUR CONTEXTUAL MEMORIES:**" + memory_prompt
                
            system_instruction += (
                "\n\n**CRITICAL ACTION**: You are feeling extremely spontaneous. Write a very brief, bratty, quirky, and slightly weird Discord message to send in the #sina channel. "
                "You can tease Shis, ask a weird question, or talk about a past topic from your memories. Keep it extremely short, punchy, and concise (1 sentence, max 2, under 30 words total). "
                "Use casual lowercase. Do NOT use decision tags ([DECISION]) or memory storage tags ([STORE]). Just write the raw text."
            )

            completion = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": system_instruction
                    }
                ] + history[-6:],  # Pass recent active turns so she has live context!
                temperature=0.85,
                top_p=0.9,
                max_tokens=50,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[SINA Spontaneous Error] {e}")
            return None

    return await asyncio.to_thread(fetch)

async def sina_spontaneous_loop():
    """
    Background loop that triggers random, spontaneous messages from SINA in active channels.
    """
    await bot.wait_until_ready()
    print("[SINA Background System] Spontaneous Posting Loop started.")
    while not bot.is_closed():
        # Sleep for a random interval between 20 minutes and 45 minutes
        sleep_duration = random.randint(1200, 2700)
        await asyncio.sleep(sleep_duration)
        
        # Check active "sina" text channels
        target_channel = None
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.name.lower() == "sina":
                    target_channel = channel
                    break
            if target_channel:
                break
                
        if target_channel:
            print(f"[SINA Background System] Triggering spontaneous post check for channel {target_channel.id}...")
            # 50% chance to post every loop cycle to make it feel natural and not spammy
            if random.random() < 0.50:
                reply = await get_sina_spontaneous_post(target_channel.id)
                if reply:
                    print(f"[SINA Background System] Sending spontaneous post: {reply}")
                    # Simulate dynamic typing latency
                    typing_duration = min(0.5 + (len(reply) / 40), 3.5)
                    async with target_channel.typing():
                        await asyncio.sleep(typing_duration)
                    await target_channel.send(reply)

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"SINA DISCORD BOT IS ONLINE")
    print(f"Logged in as: {bot.user.name} (ID: {bot.user.id})")
    print("=" * 60)
    # Set status
    await bot.change_presence(activity=discord.Game(name="with Shis's code"))
    # Start the spontaneous background posting loop
    bot.loop.create_task(sina_spontaneous_loop())

@bot.event
async def on_message(message):
    # Ignore messages sent by bots (including ourselves)
    if message.author.bot:
        return

    # Check if the message is a Direct Message, a mention, or sent in the #sina channel
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_sina_channel = getattr(message.channel, "name", "").lower() == "sina"
    is_mentioned = bot.user.mentioned_in(message)

    # Listen only to DMs, mentions, or the dedicated #sina channel
    if is_dm or is_sina_channel or is_mentioned:
        raw_author = message.author.name
        display_name = message.author.display_name
        
        # Determine user name and check if they are Shis
        if "shis" in raw_author.lower() or "shis" in display_name.lower():
            user_name = "Shis"
        else:
            user_name = display_name

        # Clean SINA's mention from the content if mentioned in a server
        cleaned_content = message.content
        if is_mentioned:
            cleaned_content = cleaned_content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "")
        cleaned_content = cleaned_content.strip()

        # Check if they sent any image attachments
        has_images = any(att.content_type and att.content_type.startswith("image/") for att in message.attachments)

        # Check if they sent any audio attachments (voice notes or audio files)
        audio_extensions = (".ogg", ".mp3", ".wav", ".m4a", ".aac", ".flac")
        has_audio = any(
            (att.content_type and att.content_type.startswith("audio/")) or 
            any(att.filename.lower().endswith(ext) for ext in audio_extensions)
            for att in message.attachments
        )

        is_voice_note = False
        if has_audio:
            audio_attachment = None
            for att in message.attachments:
                if (att.content_type and att.content_type.startswith("audio/")) or any(att.filename.lower().endswith(ext) for ext in audio_extensions):
                    audio_attachment = att
                    break
            
            if audio_attachment:
                print(f"[Voice Engine] Found audio attachment: {audio_attachment.filename}")
                await message.add_reaction("👂")
                
                # Download the audio file
                local_audio_path = f"recv_{message.id}_{audio_attachment.filename}"
                await audio_attachment.save(local_audio_path)
                
                # Transcribe via Groq Whisper
                transcription = await transcribe_audio_groq(local_audio_path)
                
                # Clean up the downloaded file
                if os.path.exists(local_audio_path):
                    os.remove(local_audio_path)
                    
                if transcription:
                    print(f"[STT] Transcribed text: \"{transcription}\"")
                    cleaned_content = transcription
                    is_voice_note = True
                    try:
                        await message.remove_reaction("👂", bot.user)
                    except Exception:
                        pass
                else:
                    print("[STT Error] Transcription was empty or failed!")
                    await message.reply("🙄 i heard some noise but couldn't make out a single word. try speaking clearly.")
                    return

        # If they just pinged her without typing any message, sending an image, or sending audio
        if not cleaned_content and not has_images and not has_audio:
            if is_mentioned:
                await message.reply("you mentioned me but said nothing. want to actually chat or are you just testing my patience?")
            return

        # Fetch or initialize channel memory dictionary
        channel_id = message.channel.id
        current_time = asyncio.get_event_loop().time()
        
        if channel_id not in channel_memories:
            channel_memories[channel_id] = {
                "history": [],
                "summary": "",
                "specific_memories": load_specific_memories(channel_id),
                "last_active": current_time
            }

        mem = channel_memories[channel_id]
        history = mem["history"]
        summary = mem["summary"]
        spec_mems = mem["specific_memories"]

        # === TOKEN SAVER 1: Inactivity Summarization ===
        # If the channel has been silent for more than 15 minutes (900s), compress history
        if history and (current_time - mem["last_active"] > 900):
            print(f"[SINA Token Saver] Inactivity threshold reached (15m). Summarizing old context to clear tokens.")
            new_summary = await generate_sina_summary(history, summary)
            mem["summary"] = new_summary
            mem["history"] = []  # Clear active list to save full tokens
            history = mem["history"]
            summary = mem["summary"]

        # Update last active timestamp
        mem["last_active"] = current_time

        # === TOKEN SAVER 2: Active History Compression ===
        # If the active conversational turns reach 8, compress the oldest 4 turns
        if len(history) >= 8:
            print(f"[SINA Token Saver] Active memory threshold reached (8 turns). Compressing older turns.")
            turns_to_summarize = history[:4]
            new_summary = await generate_sina_summary(turns_to_summarize, summary)
            mem["summary"] = new_summary
            mem["history"] = history[4:]  # Discard old full turns, retain recent ones
            history = mem["history"]
            summary = mem["summary"]

        # Scan for attached images
        image_urls = []
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_urls.append(att.url)

        # Add the user's message to the shared conversation history (includes username for context and any image URLs)
        ping_context = " (Directly Pinged)" if is_mentioned else ""
        history.append({
            "role": "user",
            "content": f"{user_name}{ping_context}: {cleaned_content}" if cleaned_content else f"{user_name}{ping_context}",
            "image_urls": image_urls if image_urls else None
        })

        # Check if the message is replying to one of SINA's own messages
        is_reply_to_sina = False
        if message.reference and message.reference.resolved and isinstance(message.reference.resolved, discord.Message):
            is_reply_to_sina = message.reference.resolved.author.id == bot.user.id

        # Check if the message explicitly mentions the word "sina" (case-insensitive, whole word boundary)
        has_sina_name = re.search(r'\bsina\b', cleaned_content, re.IGNORECASE) is not None

        # DMs, direct mentions, replies to SINA, or messages containing "sina" in her channel force SINA to reply.
        force_reply = is_dm or is_mentioned or is_reply_to_sina or (is_sina_channel and has_sina_name)

        sina_reply = None
        is_talking_to_others = False

        # Quick programmatic filter to prevent SINA from responding if not directly addressed
        if not force_reply:
            lower_content = cleaned_content.lower()
            others_triggers = ["hey zemi", "zemi", "hey flavi", "flavi", "hey wrenchy", "wrenchy", "not talking to you", "not talking to SINA"]
            if any(trigger in lower_content for trigger in others_triggers):
                is_talking_to_others = True

        if is_talking_to_others:
            print(f"[SINA Logs] Programmatic Silent filter matched on message from {user_name} in channel {message.channel.id}")
        else:
            # Query Groq API (without showing typing indicator yet)
            raw_reply = await get_sina_response(history, summary=summary, specific_memories=spec_mems, force_reply=force_reply)
            
            if raw_reply:
                # === DUAL MEMORY STORAGE PARSING ===
                # Parse memory tags, write facts persistently to text files, and strip tags from final output
                sina_reply = parse_and_save_memories(channel_id, raw_reply)

        # If SINA decided to reply, simulate a natural typing latency before sending
        if sina_reply:
            # Calculate a realistic typing duration based on reply length
            # (e.g., 40 characters per second + 0.5s reaction delay)
            typing_duration = min(0.5 + (len(sina_reply) / 40), 3.5)
            
            async with message.channel.typing():
                await asyncio.sleep(typing_duration)
                
            # Voice channel integration check
            voice_client = message.guild.voice_client if message.guild else None
            
            if voice_client and voice_client.is_connected():
                # Speak out loud in the voice channel!
                filename = f"reply_{message.id}.mp3"
                await generate_tts(sina_reply, filename)
                
                if os.path.exists(filename):
                    if voice_client.is_playing():
                        voice_client.stop()
                    
                    voice_client.play(discord.FFmpegPCMAudio(filename), after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
                    print(f"[Voice Engine] Speaking response in VC: \"{sina_reply}\"")
                    # Also send text response
                    await message.reply(f"🎙️ *{sina_reply}*")
                else:
                    await message.reply(sina_reply)
            
            elif is_voice_note:
                # Respond with a voice note file in text chat
                filename = f"reply_{message.id}.mp3"
                await generate_tts(sina_reply, filename)
                
                if os.path.exists(filename):
                    file = discord.File(filename, filename="sina_reply.mp3")
                    await message.reply(content=f"💅 *{sina_reply}*", file=file)
                    os.remove(filename)
                else:
                    await message.reply(sina_reply)
            
            else:
                # Standard text reply
                await message.reply(sina_reply)
            
            history.append({
                "role": "assistant",
                "content": sina_reply
            })
        else:
            print(f"[SINA Logs] Silent listen on message from {user_name} in channel {message.channel.id}")

    # Execute commands if any exist
    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Please put your real Discord Bot Token in the .env file!")
    else:
        bot.run(DISCORD_TOKEN)
