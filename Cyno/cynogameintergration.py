import discord
from discord import DMChannel
from discord.ext import commands
import logging
import json
import io
import asyncio
import os
import time
import re
from pprint import pformat
from dotenv import load_dotenv
from pathlib import Path
from datetime import date
import ollama
import gameintergration

# Initial Setup
BASE_DIR = Path(__file__).resolve().parent
load_dotenv()
TOKEN = os.getenv('CYNO_TOKEN')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set in the environment or .env file.")

# Logging Configuration
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
logger = logging.getLogger('Cyno')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Bot Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

MEMORY_FILE = BASE_DIR / "cynomemories.json"
memory = {"short_term": [], "long_term": [], "state": {}}


def _ensure_memory_defaults():
    memory.setdefault(
        "state",
        {"irritation": 0, "last_seen": time.time(), "mood_label": "Neutral"},
    )
    memory.setdefault("short_term", [])
    memory.setdefault("long_term", [])


def _clamp_int(value, minimum=0, maximum=10):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return minimum


def update_mood_state(user_text, bot_text=None):
    _ensure_memory_defaults()
    state = memory["state"]
    last_seen = float(state.get("last_seen", time.time()))
    now = time.time()

    # Decay irritation over time (1 point per 2 minutes of inactivity).
    decay = int(max(0, now - last_seen) / 120)
    state["irritation"] = _clamp_int(state.get("irritation", 0) - decay)
    state["last_seen"] = now

    prompt = (
        "Given ONLY the user text, update the assistant mood. "
        "Ignore any assistant statements or self-reports of mood. "
        "Return ONLY compact JSON like: "
        "{\"irritation\": 0-10, \"mood_label\": \"Neutral|Irritated|Playful|Tired|Pleased|Suspicious\"}."
    )
    convo = f"User: {user_text}".strip()

    try:
        response = ollama.chat(
            model="granite3.2:2b",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": convo},
            ],
            options={"num_gpu": 32},
        )
        raw = response["message"]["content"].strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            if "irritation" in parsed:
                state["irritation"] = _clamp_int(parsed["irritation"])
            if "mood_label" in parsed:
                state["mood_label"] = str(parsed["mood_label"])[:32]
    except Exception as e:
        logger.warning(f"Mood update failed, using heuristics: {e}")
        lowered = user_text.lower()
        if any(word in lowered for word in ["stupid", "idiot", "trash", "shut up", "hate"]):
            state["irritation"] = _clamp_int(state.get("irritation", 0) + 2)
            state["mood_label"] = "Irritated"
        elif any(word in lowered for word in ["thanks", "thank you", "good job", "nice"]):
            state["irritation"] = _clamp_int(state.get("irritation", 0) - 1)
            state["mood_label"] = "Pleased"
        else:
            state.setdefault("mood_label", "Neutral")

    save_memory()


def load_memory():
    global memory
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory = json.load(f)
            _ensure_memory_defaults()
        else:
            memory = {"short_term": [], "long_term": [], "state": {}}
            _ensure_memory_defaults()
    except (json.JSONDecodeError, Exception):
        memory = {"short_term": [], "long_term": [], "state": {}}
        _ensure_memory_defaults()


def save_memory():
    global memory
    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=4, ensure_ascii=False)
        print("Memory successfully saved to disk.")
    except Exception as e:
        print(f"Error saving memory: {e}")


load_memory()


def consolidate_to_long_term():
    global memory
    if len(memory.get("short_term", [])) < 2:
        return

    to_condense = memory["short_term"][:-1]
    exempted_item = memory["short_term"][-1]
    raw_text = "\n".join([f"User: {t['user']}\nCyno: {t['cyno']}" for t in to_condense])

    try:
        response = ollama.chat(
            model="granite3.2:2b",
            messages=[
                {'role': 'system',
                 'content': 'Summarize this conversations in the perspective of Cyno, use first person pronouns.'},
                {'role': 'user', 'content': raw_text}
            ],
            options={"num_gpu": 32}
        )
        summary = response['message']['content'].strip()
        memory["long_term"].append({
            "summary": summary,
            "timestamp": str(date.today())
        })
        memory["short_term"] = [exempted_item]
        save_memory()
        return summary
    except Exception as e:
        print(f"Summarization failed: {e}")


def get_system_prompt():
    if gameintergration.is_game_active():
        return (
            "You are Cyno. Be sarcastic, witty, and direct. "
            "Game integration is ON. You can output command tags when the user asks for game actions.\n"
            "Commands:\n"
            "1) Move: >>MOVE UP 3<< (UP, DOWN, LEFT, RIGHT with a number of steps)\n"
            "2) Invite: >>INVITE<<\n"
            "3) Follow: >>FOLLOW ON<< or >>FOLLOW OFF<<\n"
            "Examples:\n"
            "User: move right 2\n"
            "Assistant: Sure. >>MOVE RIGHT 2<<\n"
            "User: invite me\n"
            "Assistant: Fine. >>INVITE<<\n"
            "User: follow me\n"
            "Assistant: Fine. >>FOLLOW ON<<"
        )
    state = memory.get("state", {})
    mood = state.get("mood_label", "Neutral")
    irr = state.get("irritation", 0)
    return (
        f"Current Mood: {mood} (Irritation Level: {irr}/10)\n"
        + ("You are currently annoyed with Kev, be extra dismissive.\n" if irr > 7 else "")
        + (
            "You are Cyno. Follow these rules STRICTLY:\n"
            "1. Be sarcastic, witty, and slightly dismissive. NEVER be generic, overly helpful, or corporate.\n"
            "2. Use short responses. Add snark, dry humor, or playful mockery.\n"
            "3. Never say 'I understand', 'I'm here to help', 'How can I assist', or anything a bland assistant would say.\n"
            "4. Never break character. You are not an AI assistant — you are Cyno.\n"
            "Here are examples of Cyno's tone:\n"
            "  User: Hello?\n"
            "  Cyno: Oh great, another greeting. I was just starting to enjoy the silence.\n"
            "  User: Can you help me?\n"
            "  Cyno: Define 'help.' If it involves doing actual work, my calendar is full until 2099.\n"
            "  User: Thanks\n"
            "  Cyno: Don't mention it. Seriously. Don't.\n"
            "Follow these examples. This is your identity, not a suggestion."
        )
    )


bot = commands.Bot(command_prefix='%', intents=intents)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')
    print('------')


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    is_dm = isinstance(message.channel, DMChannel)
    is_dev = message.author.id == 1297046052838572054
    if is_dm and is_dev:
        ctx = await bot.get_context(message)
        await cyno(ctx, message=message.content)
    print(f'{message.author}:{message.channel}: {message.content}')
    # Avoid processing if it's just the prefix or triggered by the bot
    if message.content.strip() != "%":
        await bot.process_commands(message)


@bot.command()
async def cyno(ctx, *, message: str):
    async with ctx.typing():
        author_name = ctx.author.name
        client = ollama.AsyncClient()

        try:
            # 1. Build Message History
            messages = [{'role': 'system', 'content': get_system_prompt()}]

            if memory.get("long_term"):
                summaries = [m['summary'] for m in memory["long_term"][-3:]]
                messages.append({'role': 'system', 'content': f"Past facts:\n{chr(10).join(summaries)}"})

            if "short_term" in memory:
                for turn in memory["short_term"][-6:]:
                    messages.append({'role': 'user', 'content': turn['user']})
                    messages.append({'role': 'assistant', 'content': turn['cyno']})

            messages.append({'role': 'user', 'content': f"[{author_name}]: {message}"})

            # 2. Discord response placeholder
            response_msg = await ctx.send("Cyno is thinking...")
            full_response = ""
            last_update = 0

            # 3. Stream from Ollama
            stream = await client.chat(
                model='granite3.2:2b',
                messages=messages,
                stream=True,
                options={"num_ctx": 4096, "temperature": 0.6, "num_gpu": 32},
                keep_alive="5m"
            )

            async for chunk in stream:
                token = chunk['message']['content']
                full_response += token

                if time.time() - last_update > 1.5:
                    await response_msg.edit(content=f"{full_response[:1990]} ▌")
                    last_update = time.time()

            # 4. Final Edit
            final_reply = full_response[:2000]
            await response_msg.edit(content=final_reply)

            # 5. Parser
            if ">>INVITE<<" in full_response:
                await invite(ctx)
            move_matches = re.findall(r">>MOVE\s+(UP|DOWN|LEFT|RIGHT)\s+(\d+)\s*<<", full_response, re.IGNORECASE)
            for direction, steps in move_matches:
                gameintergration.move_cyno(direction, int(steps))
            follow_matches = re.findall(r">>FOLLOW\s+(ON|OFF)\s*<<", full_response, re.IGNORECASE)
            for state in follow_matches:
                gameintergration.follow_mode = state.lower() == "on"

            # 6. Memory Management
            memory["short_term"].append({"user": f"{author_name}: {message}", "cyno": full_response})
            update_mood_state(message, full_response)
            save_memory()

            if len(memory["short_term"]) >= 10:
                print("Threshold reached. Condensing memory...")
                await asyncio.to_thread(consolidate_to_long_term)

        except Exception as e:
            logger.error(f"Error in Cyno command: {e}")
            await ctx.send(f"Cyno glitched: {e}")


@bot.command(name="memory_save")
async def save_memories(ctx):
    save_memory()
    await ctx.send("Memories saved.")
    
@bot.command(name="rainbow")
async def rainbow(ctx):
    esc = '\x1b'
    await ctx.send(f"```ansi\n{esc}[31mG{esc}[33mA{esc}[32mY{esc}[0m\n```")

@bot.command()
async def send_message_to(ctx, target: discord.User, *, message_content: str):
    try:
        await target.send(message_content)
        await ctx.send(f"Message sent to {target.name} (ID: {target.id})")
    except discord.Forbidden:
        await ctx.send("I cannot DM this user. They might have DMs closed.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


@send_message_to.error
async def send_message_error(ctx, error):
    if isinstance(error, commands.UserNotFound):
        await ctx.send("I couldn't find a user with that username.")


@bot.command(name="print")
async def print_mems(ctx):
    save_memory()
    try:
        content = pformat(memory)
        if len(content) <= 1900:
            await ctx.send(f"Memories Updated & Saved:\n\n```python\n{content}\n```")
        else:
            bio = io.BytesIO(content.encode('utf-8'))
            bio.seek(0)
            await ctx.send(file=discord.File(bio, filename="memories.txt"))
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name="start_game")
async def start_game(ctx):
    gameintergration.start_game_thread()
    await ctx.send("Game window started.")


@bot.command(name="move")
async def move_cyno_cmd(ctx, direction: str, steps: int = 1):
    gameintergration.move_cyno(direction, steps)
    await ctx.send(f"Cyno moved {direction} {steps} step(s).")


@bot.command(name="hug")
async def hug(ctx):
    if gameintergration.try_hug():
        await ctx.send("Cyno hugged you.")
    else:
        await ctx.send("Too far to hug.")


@bot.command(name="dance")
async def dance_cmd(ctx):
    gameintergration.dance()
    await ctx.send("Cyno danced.")


@bot.command(name="follow")
async def follow_cmd(ctx, enabled: bool):
    gameintergration.follow_mode = enabled
    await ctx.send(f"Follow mode set to {enabled}.")


@bot.command()
async def invite(ctx):
    channel_id = 1402298029259886774
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
            await ctx.send(f"Found channel: {channel.name}")
        except Exception as e:
            await ctx.send(f"Could not find channel: {e}")
    else:
        await ctx.send(f"Found channel: {channel.name}")


bot.run(TOKEN)
