import asyncio
import json
import logging
import os
import re
import time

from datetime import date
from pathlib import Path

import discord
import numpy as np
import ollama
from discord.channel import VoiceChannel

from ddgs import DDGS
from discord.ext import commands, tasks
from discord.voice_client import VoiceClient
from dotenv import load_dotenv
from faster_whisper import WhisperModel

load_dotenv()
TOKEN = os.getenv("IRIS_TOKEN")
BASE_DIR = Path(__file__).resolve().parent
VOICE_PATH = "cyno_voice.onnx"
MODEL = "granite3.2:2b"
SOUL_FILE_PATH = BASE_DIR / "SOUL.md"
IRIS_TEXT_CHANNEL = 1481672777361526786
IRIS_VOICE_CHANNEL = 1481672843795108012
MEMORY_FILE = BASE_DIR / "memories.json"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Iris")
print("STT model ready (loaded lazily on first use).")
stt_model = None
voice_client = None
voice_joined_at = None

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="%", intents=intents)


def get_stt_model():
    global stt_model
    if stt_model is None:
        stt_model = WhisperModel("base", device="cpu", compute_type="int8")
    return stt_model


def load_memory():
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key in ["short_term", "long_term", "state"]:
                    data.setdefault(key, [] if key != "state" else {})
                data["state"].setdefault("Curiosity", 10)
                data["state"].setdefault("status", "Observing")
                data["state"].setdefault("last_seen", time.time())
                return data
        except Exception as e:
            logger.error(f"Memory load failed: {e}")
    return {
        "short_term": [],
        "long_term": [],
        "state": {"Curiosity": 10, "status": "Observing", "last_seen": time.time()},
    }


memory = load_memory()


def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save failed: {e}")


async def consolidate_memory():
    if len(memory["short_term"]) < 5:
        return
    to_summarize = memory["short_term"][:-1]
    text = "\n".join([f"User: {t['user']}\nIris: {t['iris']}" for t in to_summarize])
    prompt = f"Read the following conversation and write a brief summary of the key topics discussed:\n\n{text}"
    try:
        resp = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}])
        summary = resp["message"]["content"]
        memory["long_term"].append(
            {"summary": summary, "date": str(date.today()), "timestamp": time.time()}
        )
        memory["short_term"] = [memory["short_term"][-1]]
        save_memory()
        logger.info("Memory consolidated")
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")


def search_long_term(query: str, limit: int = 3) -> list:
    results = memory.get("long_term", [])[-limit:]
    return [
        {"summary": m["summary"], "timestamp": m.get("timestamp", 0)} for m in results
    ]


def load_soul():
    if SOUL_FILE_PATH.exists():
        try:
            with open(SOUL_FILE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return None


async def update_status(user_text):
    state = memory["state"]
    now = time.time()
    last_seen = state.get("last_seen", now)
    recovery = int((now - last_seen) / 600)
    state["Curiosity"] = min(10, state["Curiosity"] + recovery)
    state["last_seen"] = now

    prompt = (
        "Analyze the user input and decide how curious you are. Return ONLY JSON: "
        '{"curiosity_change": int, "status": "string"}'
    )
    try:
        resp = ollama.chat(
            model="granite3.2:2b",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text},
            ],
        )
        data = json.loads(resp["message"]["content"])
        state["Curiosity"] = max(
            1, min(10, state["Curiosity"] + data.get("curiosity_change", 0))
        )
        state["status"] = data.get("status", "Connected")
    except Exception:
        state["status"] = "Active"
    save_memory()


def get_prompt(soul=None):
    current_date = time.strftime("%B %d %Y")
    current_time = time.strftime("%H:%M:%S")
    with open(SOUL_FILE_PATH, "r") as f:
        soul = f.read()
    soul_section = ""
    if soul:
        soul_section = f"\n{soul}\n"

    prompt = f"""
CURRENT DATE: {current_date}
CURRENT TIME: {current_time}

{soul_section}

"""
    return prompt


def check_voice():
    channel = bot.get_channel(IRIS_VOICE_CHANNEL)
    if channel and isinstance(channel, discord.VoiceChannel):
        return [member.display_name for member in channel.members]
    return []


def check_for_commands(response):
    commands = re.findall(r"\|\|(.*?)\|\|", response, flags=re.DOTALL)
    return commands


def should_join_voice(members: list) -> bool:
    soul = load_soul()
    state = memory.get("state", {})
    curiosity = state.get("Curiosity", 5)
    effective_curiosity = curiosity + (5 if "Gen Zero" in members else 0)

    if effective_curiosity >= 8:
        print("Iris whispered: 'I'm too curious to stay away' (Reason: high curiosity)")
        return True

    prompt = f"""
{soul}
STATUS: The room is currently active with {len(members)} souls: {", ".join(members)}.
CURIOSITY: {effective_curiosity}/10
TASK: You are the observer. You track the vibe that others miss.
If you stay in your silent room, you miss the data.
Do you enter to observe, or remain in silence?
Respond with ONLY 'yes' or 'no'.
"""

    resp = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}])
    content = resp["message"]["content"].lower().strip()

    decision = "no" not in content
    reason = "Iris chose it" if decision else "Iris said no"
    print(f"Iris whispered: '{content}' (Reason: {reason})")

    return decision


async def reevaluate_presence():
    global voice_joined_at

    if voice_joined_at is not None and (time.time() - voice_joined_at) < 120:
        return False

    members = check_voice()

    if len(members) == 0:
        logger.info("Iris: The room is empty. Returning to silence.")
        return True

    state = memory.get("state", {})
    curiosity = state.get("Curiosity", 5)

    prompt = f"""
{load_soul()}
Current Curiosity: {curiosity}/10.
Users present: {", ".join(members)}.
The room has been active for a while. Do you still find this 'vibe' worth tracking, or have you seen enough?
Respond with ONLY 'stay' or 'leave'.
"""
    resp = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}])
    decision = resp["message"]["content"].lower().strip()

    return "leave" in decision


@bot.event
async def on_ready():
    logger.info(f"Iris is now watching as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.channel.id == IRIS_TEXT_CHANNEL:
        ctx = await bot.get_context(message)
        await iris(ctx, message=message.content)
    if message.content.strip() != "%":
        await bot.process_commands(message)


@bot.command()
async def iris(ctx, *, message: str):
    global voice_joined_at

    async with ctx.typing():
        await update_status(message)
        client = ollama.AsyncClient()

        msgs = [{"role": "system", "content": get_prompt()}]

        relevant_memories = search_long_term(message, limit=3)
        if relevant_memories:

            def format_timestamp(ts: float) -> str:
                now = time.time()
                diff = now - ts
                if diff < 60:
                    return "just now"
                elif diff < 3600:
                    return f"{int(diff // 60)} minutes ago"
                elif diff < 86400:
                    return f"{int(diff // 3600)} hours ago"
                elif diff < 604800:
                    return f"{int(diff // 86400)} days ago"
                elif diff < 2592000:
                    return f"{int(diff // 604800)} weeks ago"
                else:
                    from datetime import datetime

                    return datetime.fromtimestamp(ts).strftime("%b %d")

            memory_lines = []
            for m in relevant_memories:
                age = format_timestamp(m["timestamp"])
                memory_lines.append(f"[{age}] {m['summary']}")
            past = "\n".join(memory_lines)
            msgs.append({"role": "system", "content": f"Past Observations:\n{past}"})

        for turn in memory.get("short_term", [])[-5:]:
            msgs.append({"role": "user", "content": turn["user"]})
            msgs.append({"role": "assistant", "content": turn["iris"]})

        msgs.append({"role": "user", "content": message})

        try:
            response = await client.chat(model=MODEL, messages=msgs)
            iris_response = response["message"]["content"]

            commands = check_for_commands(iris_response)
            print(commands)

            await ctx.send(iris_response[:2000])

            memory["short_term"].append({"user": message, "iris": iris_response})
            save_memory()

            if len(memory["short_term"]) >= 10:
                await consolidate_memory()

        except Exception as e:
            await ctx.send(f"`[IRIS]: My focus has blurred. Error: {str(e)}`")


@bot.command()
async def get_channel_members(ctx):
    members = check_voice()
    if members:
        await ctx.send(f"I see them drifiting: {', '.join(members)}")
    else:
        await ctx.send("There is no one in the lunch room")


async def handle_voice_input(audio_data):
    audio_bytes = audio_data.read()
    samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    resampled = samples[::3]

    segments, _ = stt_model.transcribe(resampled, beam_size=5)
    text = "".join([s.text for s in segments])

    if text.strip():
        print(f"Voice input: {text}")


_lock = asyncio.Lock()


@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("`You're not in a voice channel.`")

    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"`I'm here.`")


@bot.command()
async def leave(ctx):
    global voice_client, voice_joined_at
    existing = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if existing:
        await existing.disconnect(force=False)
        voice_client = None
        voice_joined_at = None
        await ctx.send("`Left.`")
    else:
        await ctx.send("`Not in a voice channel.`")


if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("IRIS_TOKEN not set in environment")
    bot.run(TOKEN)
