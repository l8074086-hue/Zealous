import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path

import discord
import ollama
from ddgs import DDGS
from discord.ext import commands, voice_recv
from dotenv import load_dotenv

from glados_tts import GLaDOS

# --- Initial Setup ---
load_dotenv()
TOKEN = os.getenv("T_TOKEN")
BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "memories.json"
GLADOS_PATH = "cyno_voice.onnx"


def web_search(query):
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
            return (
                [f"{r['title']}: {r['body']}" for r in results]
                if results
                else ["No results found."]
            )
    except Exception as e:
        return [f"Search error: {e}"]


# Initialize GLaDOS and FORCE voice ON
glados_engine = GLaDOS(GLADOS_PATH)
glados_engine.enabled = True
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

discord.utils.setup_logging(level=logging.INFO)
logger = logging.getLogger("Cyno")
logger.info(f"Vocal Subroutines enabled: {glados_engine.enabled}")


class MyReceiver(voice_recv.AudioSink):
    def __init__(self):
        super().__init__()

    def wants_opus(self):
        return False  # False gives you raw PCM audio (better for STT)

    def write(self, user, data):
        # This is where the audio bytes land
        # 'user' is the person speaking, 'data' is the audio data
        if data.pcm:
            # For debugging: just print the length of the audio chunk
            print(f"Receiving {len(data.pcm)} bytes from {user}")

    def cleanup(self):
        # Python complained because this was missing!
        print("Cleaning up the audio sink...")


# --- Data Management ---
def load_memory():
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key in ["short_term", "long_term", "state"]:
                    data.setdefault(key, [] if key != "state" else {})
                data["state"].setdefault("link_stability", 10)
                data["state"].setdefault("status", "Optimal")
                data["state"].setdefault("last_seen", time.time())
                return data
        except Exception as e:
            logger.error(f"Memory load failed: {e}")
    return {
        "short_term": [],
        "long_term": [],
        "state": {"link_stability": 10, "status": "Optimal", "last_seen": time.time()},
    }


memory = load_memory()


def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save failed: {e}")


def clean_for_glados(text):
    # Remove Discord formatting and non-speakable characters
    text = re.sub(r"<a?:\w+:\d+>", "", text)
    text = re.sub(r"\*.*?\*", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"[_]", " ", text)  # Remove underscores (fixes username issues)
    return text.strip()


# --- Titan Logic ---
async def update_link_stability(user_text):
    state = memory["state"]
    now = time.time()
    last_seen = state.get("last_seen", now)
    recovery = int((now - last_seen) / 600)
    state["link_stability"] = min(10, state["link_stability"] + recovery)
    state["last_seen"] = now

    prompt = (
        "Analyze Pilot input for hostility. Return ONLY JSON: "
        '{"stability_change": int, "status": "string"}'
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
        state["link_stability"] = max(
            1, min(10, state["link_stability"] + data.get("stability_change", 0))
        )
        state["status"] = data.get("status", "Connected")
    except Exception:
        state["status"] = "Neural Link Active"
    save_memory()


def get_system_prompt():
    s = memory["state"]
    stability = s.get("link_stability", 10)
    prompt = (
        "You are T-7274, a Vanguard-class Titan callsign 'Cyno'. "
        "You are robotic, literal, and professional. You do not understand sarcasm or jokes. "
        "You address the user as 'Pilot'. Never use emojis or markdown asterisks. "
        f"Neural Link Stability: {stability}/10. Current Status: {s.get('status', 'Active')}. "
        "Protocol 1: Link to Pilot. Protocol 2: Uphold the Mission. Protocol 3: Protect the Pilot."
    )
    if stability < 4:
        prompt += " WARNING: Link degradation. Keep responses brief."
    return prompt


async def consolidate_memory():
    if len(memory["short_term"]) < 5:
        return
    to_summarize = memory["short_term"][:-1]
    text = "\n".join([f"Pilot: {t['user']}\nTitan: {t['cyno']}" for t in to_summarize])
    try:
        resp = await ollama.AsyncClient().chat(
            model="granite3.2:2b",
            messages=[
                {
                    "role": "system",
                    "content": "Summarize this into a professional Titan Mission Log in 1st person.",
                },
                {"role": "user", "content": text},
            ],
        )
        memory["long_term"].append(
            {"summary": resp["message"]["content"], "date": str(date.today())}
        )
        memory["short_term"] = [memory["short_term"][-1]]
        save_memory()
    except Exception as e:
        logger.error(f"Consolidation failed: {e}")


# --- Bot Commands ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="%", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"T-7274 (Cyno) Online. Audio Ready: {glados_engine.enabled}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if isinstance(message.channel, discord.DMChannel):
        ctx = await bot.get_context(message)
        command = bot.get_command("cyno")
        if command:
            await ctx.invoke(command, message=message.content)
        return
    await bot.process_commands(message)


@bot.command()
async def cyno(ctx, *, message: str):
    async with ctx.typing():
        client = ollama.AsyncClient()
        msgs = [{"role": "system", "content": get_system_prompt()}]

        if memory["long_term"]:
            past = "\n".join([m["summary"] for m in memory["long_term"][-3:]])
            msgs.append({"role": "system", "content": f"History:\n{past}"})

        for turn in memory["short_term"][-5:]:
            msgs.append({"role": "user", "content": turn["user"]})
            msgs.append({"role": "assistant", "content": turn["cyno"]})

        # REMOVED ctx.author.name so he doesn't detect "unknown identifiers"
        msgs.append({"role": "user", "content": message})

        try:
            placeholder = await ctx.send("`[PROCESS]: Establishing Neural Link...`")
            full_response = ""
            last_edit = time.time()

            stream = await client.chat(model="llama3.2:3b", messages=msgs, stream=True)

            async for chunk in stream:
                full_response += chunk["message"]["content"]
                if time.time() - last_edit > 1.5:
                    await placeholder.edit(content=f"{full_response[:1980]} ▌")
                    last_edit = time.time()

            await placeholder.edit(content=full_response[:2000])

            # Check if Cyno wants to search
            search_match = re.search(
                r"SEARCH:\s*(.+?)(?:\n|$)", full_response, re.IGNORECASE
            )
            if search_match:
                query = search_match.group(1).strip()
                logger.info(f"Pilot requested search: {query}")
                results = web_search(query)

                # Get final response with search results
                msgs.append({"role": "assistant", "content": full_response})
                msgs.append(
                    {
                        "role": "user",
                        "content": f"Search results for '{query}':\n"
                        + "\n".join(f"- {r}" for r in results)
                        + "\n\nProvide your response based on these results.",
                    }
                )

                placeholder = await ctx.send("`[PROCESS]: Analyzing search results...`")
                full_response = ""

                stream = await client.chat(
                    model="llama3.2:3b", messages=msgs, stream=True
                )
                async for chunk in stream:
                    full_response += chunk["message"]["content"]
                    if time.time() - last_edit > 1.5:
                        await placeholder.edit(content=f"{full_response[:1980]} ▌")
                        last_edit = time.time()

                await placeholder.edit(content=full_response[:2000])

            # --- Discord Voice Protocol (Linux) ---
            if ctx.voice_client and ctx.voice_client.is_connected():
                cleaned = clean_for_glados(full_response)

                # FIX: Match the method name to 'get_audio_stream'
                audio_stream = glados_engine.get_audio_stream(cleaned)

                if audio_stream:
                    if ctx.voice_client.is_playing():
                        ctx.voice_client.stop()

                    # We tell FFmpeg to read raw s16le (16-bit) audio at 22050Hz
                    source = discord.FFmpegPCMAudio(
                        audio_stream,
                        pipe=True,
                        executable="ffmpeg",
                        before_options="-f s16le -ar 22050 -ac 1",
                    )
                    ctx.voice_client.play(source)
            memory["short_term"].append({"user": message, "cyno": full_response})
            await update_link_stability(message)

            if len(memory["short_term"]) >= 10:
                await consolidate_memory()

        except Exception as e:
            await ctx.send(f"```[ERROR]: Neural Link Failure - {str(e)}```")


@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("`[ERROR]: Pilot not detected in any voice channel.`")

    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"`[SYSTEM]: Neural Link established in {channel.name}.`")


@bot.command()
async def listen(ctx):
    if not ctx.author.voice:
        return await ctx.send("You need to be in a voice channel first!")

    # Check if we are already connected to voice
    vc = ctx.voice_client

    if not vc:
        # If not connected, connect using the VoiceRecvClient
        vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
    elif not isinstance(vc, voice_recv.VoiceRecvClient):
        # If connected but NOT with voice_recv, move and upgrade the client
        await vc.disconnect()
        vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)

    # Now start listening
    if not vc.is_listening():
        vc.listen(MyReceiver())
        await ctx.send("👂 I'm listening now!")
    else:
        await ctx.send("I'm already listening, genius.")


@bot.command()
async def architecture(ctx):
    """Generates a text-based tactical map of the server structure."""
    if not ctx.guild:
        return await ctx.send("`[ERROR]: Command restricted to Guild environments.`")

    async with ctx.typing():
        header = f"```\n[MISSION LOG]: SERVER TOPOLOGY - {ctx.guild.name.upper()}\n"
        header += "="*40 + "\n"
        
        body = ""
        # Sort categories by their actual position in Discord
        categories = sorted(ctx.guild.categories, key=lambda c: c.position)
        
        for category in categories:
            body += f"\n📁 [SEC]: {category.name.upper()}\n"
            
            # Sort channels within the category
            channels = sorted(category.channels, key=lambda c: c.position)
            for channel in channels:
                if isinstance(channel, discord.TextChannel):
                    icon = "💬"
                elif isinstance(channel, discord.VoiceChannel):
                    icon = "🔊"
                elif isinstance(channel, discord.StageChannel):
                    icon = "🎭"
                elif isinstance(channel, discord.ForumChannel):
                    icon = "📝"
                else:
                    icon = "📄"
                
                body += f"    ├── {icon} {channel.name}\n"

        footer = "\n" + "="*40 + "\n[STATUS]: TOPOLOGY EXPORT COMPLETE.```"
        
        # Discord has a 2000 char limit; if the server is massive, we split it
        full_output = header + body + footer
        
        if len(full_output) > 1900:
            # Save to file if it's too big for a message
            filename = f"topology_{ctx.guild.id}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(full_output.replace("```", ""))
            await ctx.send("`[SYSTEM]: Topology exceeds datalink capacity. Transmitting as file...`", 
                           file=discord.File(filename))
            os.remove(filename)
        else:
            await ctx.send(full_output)

@bot.command()
async def status(ctx):
    s = memory["state"]
    msg = f"**Titan Designation:** T-7274 (Cyno)\n**Neural Link Stability:** {s.get('link_stability')}/10\n**Protocol 3:** ACTIVE"
    await ctx.send(msg)


bot.run(TOKEN)
