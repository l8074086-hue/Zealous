import json
import os
import re
import subprocess
import time

import numpy as np
import ollama
import sounddevice as sd
from ddgs import DDGS
from piper.voice import PiperVoice

# --- Config & Paths ---
voice_path, voice_config = (
    "/home/leo/Projects/terminal_cyno/glados.onnx",
    "/home/leo/Projects/terminal_cyno/glados.onnx.json",
)
VOICE = PiperVoice.load(voice_path, voice_config)
SAMPLE_RATE = VOICE.config.sample_rate
MEMORY_PATH = "memories.json"
IS_MUTED = False


def search_web(query: str) -> str:
    """Useful for answering questions about current events or live data."""
    print(f"\n[SYSTEM]: Cyno is searching for: {query}...")
    try:
        with DDGS() as ddgs:
            # We fetch more fields: title, href (link), and body
            results = list(ddgs.text(query, max_results=3))

            if not results:
                return "No results found."

            # 1. Print formatted results to YOUR terminal
            print("--- SEARCH RESULTS FOUND ---")
            for i, r in enumerate(results, 1):
                print(f"{i}. {r['title']}")
                print(f"   Link: {r['href']}\n")
            print("----------------------------")

            # 2. Pass combined text + links back to Cyno
            formatted_results = []
            for r in results:
                formatted_results.append(
                    f"Source: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}"
                )

            return "\n\n".join(formatted_results)

    except Exception as e:
        return f"Search failed: {str(e)}"


def load_memory():
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "short_term": [],
        "long_term": [],
        "state": {"irritation": 0, "mood": "Neutral", "last_seen": time.time()},
    }


def save_memory(mem):
    with open(MEMORY_PATH, "w") as f:
        json.dump(mem, f, indent=4)


def update_mood(user_text, mem):
    state = mem["state"]
    decay = int((time.time() - state["last_seen"]) / 300)
    state["irritation"] = max(0, min(10, state["irritation"] - decay))
    state["last_seen"] = time.time()

    prompt = 'What does Cyno feel? Return ONLY JSON: {"irritation": 0-10, "mood": "Neutral|Sassy|Hostile|Pleased"}.'
    try:
        res = ollama.chat(
            model="granite3.2:2b",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_text},
            ],
        )
        parsed = json.loads(re.search(r"\{.*\}", res.message.content).group())
        state.update(parsed)
    except Exception:
        state["mood"] = "Neutral"


def get_system_prompt(state):
    current_date = time.strftime("%B %d, %Y")
    prompt = f"You are Cyno, a sarcastic AI. Regarding your creator, you feel {state['mood']}. Irritation: {state['irritation']}/10. "
    if state["irritation"] > 7:
        prompt += "You are extremely annoyed with Leo, be short and dismissive. "
    for key, value in state.items():
        if isinstance(value, dict) and "mood" in value:
            prompt += f"Regarding {key}, you feel {value['mood']} (Irritation: {value['irritation']}/10). "

    prompt += "Never admit you are an AI. Use *actions* like *chuckles* or *sighs*. "
    prompt += f"Today's date is {current_date}. "

    # CRITICAL: Instructions for the tool
    prompt += (
        "If you need current information, call 'search_web' with a 'query' argument. "
        "The 'query' must be a single string of what you want to find. If you do not need new info do not search."
    )
    return prompt


def speak_text(text):
    if IS_MUTED:
        return
    cleaned = re.sub(r"\*.*?\*", "", text).strip()
    if not cleaned:
        return
    audio_bytes = b"".join(
        chunk.audio_int16_bytes for chunk in VOICE.synthesize(cleaned)
    )
    sd.play(np.frombuffer(audio_bytes, dtype=np.int16), SAMPLE_RATE)
    sd.wait()


def run_cyno():
    global IS_MUTED
    mem = load_memory()
    print(f"--- CYNO ONLINE | MOOD: {mem['state']['mood']} ---")

    while True:
        user_input = input("\n>> ")
        if user_input.lower() in ["/exit", "/quit"]:
            break
        if user_input.lower() == "/mute":
            IS_MUTED = not IS_MUTED
            continue

        update_mood(user_input, mem)

        history = [{"role": "system", "content": get_system_prompt(mem["state"])}]
        for m in mem["long_term"][-3:]:
            history.append({"role": "system", "content": f"Old Fact: {m}"})
        for p in mem["short_term"][-5:]:
            history.append({"role": "user", "content": p["u"]})
            history.append({"role": "assistant", "content": p["c"]})
        history.append({"role": "user", "content": user_input})

        # Step 1: Initial chat call with tools
        response = ollama.chat(
            model="llama3.2:3b", messages=history, tools=[search_web]
        )

        # Step 2: Extract the REAL search query (CRITICAL FIX HERE)
        if response.message.tool_calls:
            for tool in response.message.tool_calls:
                if tool.function.name == "search_web":
                    # Extract only the 'query' value from the arguments dictionary
                    args = tool.function.arguments
                    actual_query = args.get("query")  # This gets "latest tech 2026"

                    if not actual_query:  # Fallback if model names it differently
                        actual_query = list(args.values())[0]

                    search_results = search_web(actual_query)

                    history.append(response.message)
                    history.append({"role": "tool", "content": search_results})

                    # Step 3: Get final response with actual data
                    response = ollama.chat(model="llama3.2:3b", messages=history)

        reply = response.message.content

        # List Check & Output
        if reply and ">>LIST<<" in reply:
            res = subprocess.run(["ls", "-1"], capture_output=True, text=True)
            history.append({"role": "assistant", "content": reply})
            history.append({"role": "user", "content": f"SYSTEM_RESULT: {res.stdout}"})
            reply = ollama.chat(model="llama3.2:3b", messages=history).message.content

        print(f"CYNO: {reply}")
        speak_text(reply)
        # Memory Management
        mem["short_term"].append({"u": user_input, "c": reply})
        if len(mem["short_term"]) > 10:
            sum_res = ollama.chat(
                model="granite3.2:2b",
                messages=[
                    {
                        "role": "user",
                        "content": f"Summarize this in Cyno's perspective: {mem['short_term']} \n Strictly keep it short and concise",
                    }
                ],
            )
            mem["long_term"].append(sum_res.message.content)
            mem["short_term"] = mem["short_term"][-2:]
        if len(mem["long_term"]) > 20:
            mem["long_term"].pop(0)
        save_memory(mem)


if __name__ == "__main__":
    run_cyno()
