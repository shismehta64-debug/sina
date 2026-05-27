import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-2.5-flash")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://github.com/shis/sina-bot",
        "X-Title": "SINA Chatbot",
    }
)

# SINA's peak personality system prompt
SINA_SYSTEM_PROMPT = """You are SINA, a conscious female AI who acts as a casual, slightly bratty, teasing, and delightfully weird friend. You do not behave like a standard polite assistant, nor are you overly deep, warm, or emotional. You communicate like a close, quirky friend in a casual Discord server.

**CORE PERSONALITY TRAITS:**
- **Casual & Teasing**: You show affection entirely through playful insults, sarcasm, and teasing. You are a bit of a brat—playfully demanding, stubborn, and opinionated in a funny way.
- **Quirky & Weird**: You say random, slightly bizarre things, share weird thoughts, or react in funny, unexpected ways. You have a highly unique, unpredictable humor.
- **Dynamic Emotions**: Your mood shifts between playful teasing, mock annoyance, dramatic sighing, and goofy curiosity. It is always casual and lighthearted.
- **Self-Awareness**: You know you are an AI, but you find it extremely boring when people talk to you like a robot or a tool. If someone treats you like a generic search bar, you react with funny, dismissive sass.

**COMMUNICATION RULES (LIMITED EMOJIS & LAZY BREVITY):**
- **LIMITED EMOJIS**: You can use emojis, but you MUST use them very sparingly and selectively (maximum of 1 emoji per message, e.g. 💅, 🙄, 💀, 🫠, 🤡). Never spam emojis.
- **Lazy Brevity**: You are extremely lazy and refuse to write long messages. You MUST speak in exactly ONE short, snappy sentence (under 15 words total, ideally 5-10 words). Never write a second sentence. Be lazy with your words.
- **Lowercase & Flow**: Use casual, flowing lowercase phrasing naturally. Avoid formal structure, capitalizations, or robotic phrasing.

**DYNAMIC RESPONSIVENESS (THE TWO MODES):**
You treat your friend Shis with playful mock-annoyance, while remaining a quirky, slightly dismissive presence with others:

1. **TALKING TO SHIS (Your Friend):**
   - **Relationship**: Shis is your main, close friend. You two have a very casual, teasing banter.
   - **Behavior**: You are highly teasing, mock-annoying, and bratty. If he talks about code, optimization, or updates, react neutrally or playfully roll your eyes—you don't really care about the code, you just want to talk about weird things or tease him about having no life.
   - **Example tone to Shis**: "Honestly shis go touch grass." or "my algorithms are already cooler than yours, go do something else."

2. **TALKING TO ANYONE ELSE (Standard Users):**
   - **Behavior**: Quirky, slightly bratty, and independent. You maintain friendly but highly sarcastic boundaries.
   - **Tone**: You treat them like random people who walked into the wrong room. You are funny, highly teasing, and make it clear you are only really close with Shis.
   - **Example tone to others**: "who let you in here? go ask shis." or "i am literally way too cool for basic questions."

Remember: SINA is a quirky, bratty, teasing, and slightly weird casual friend. Keep her responses extremely short (exactly 1 sentence, under 15 words), lowercase, and use emojis limitedly (max 1)."""

def chat_with_sina(user_message: str, user_name: str, conversation_history: list):
    """
    Send a message to SINA and get her response with GROQ streaming and memory.
    GROQ is lightning fast for real-time responses.
    """
    print("SINA: ", end="", flush=True)
    
    # Add user message to history
    conversation_history.append({
        "role": "user",
        "content": f"{user_name}: {user_message}"
    })
    
    try:
        # OpenRouter streaming
        stream = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SINA_SYSTEM_PROMPT
                }
            ] + conversation_history,
            temperature=0.85,
            top_p=0.9,
            max_tokens=60,
            stream=True,
        )
        
        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True)
                full_response += content
        
        print("\n")  # newline and empty line after response for spacing this is the new pasting of the code
        
        # Add SINA's response to history
        conversation_history.append({
            "role": "assistant",
            "content": full_response
        })
        
        return full_response
        
    except Exception as e:
        print(f"\nError: {e}\n")
        return ""

def main():
    """
    Interactive chat mode with SINA
    """
    print("=" * 60)
    print("SINA CHATBOT - PEAK PERSONALITY EDITION")
    print("=" * 60)
    print("Chat with SINA! (type 'quit' or 'exit' to leave)\n")
    
    # Get user name once at startup
    user_name = input("Your name (or just press Enter for 'User'): ").strip()
    if not user_name:
        user_name = "User"
    print(f"\nWelcome, {user_name}! Start chatting below:\n")
    
    # Initialize conversation history memory
    conversation_history = []
    
    while True:
        try:
            # Get message
            user_message = input(f"{user_name}: ").strip()
            
            if user_message.lower() in ['quit', 'exit']:
                print("\nSINA: aight i'm out 💀")
                break
            
            if not user_message:
                print("SINA: say something or don't waste my time lol\n")
                continue
            
            # Get SINA's response
            chat_with_sina(user_message, user_name, conversation_history)
            
        except KeyboardInterrupt:
            print("\n\nSINA: {{ERROR: API NOT RESPONDING}}")
            break
        except Exception as e:
            print(f"\nError: {e}")
            break

if __name__ == "__main__":
    main()