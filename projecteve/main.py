import json
import os
import re
import time

import ollama
from ddgs import DDGS

# Configs
MEM_PATH = "memories.json"
SOUL_PATH = "SOUL.md"


def load_soul():
    if os.path.exists(SOUL_PATH):
        try:
            with open(SOUL_PATH, "r") as f:
                return f.read()
        except Exception:
            pass
    return None


def load_memory():
    if os.path.exists(MEM_PATH):
        try:
            with open(MEM_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"short_term": [], "long_term": [], "self": []}


def save_memory(mem):
    with open(MEM_PATH, "w") as f:
        json.dump(mem, f, indent=4)


def get_prompt(soul=None):
    current_date = time.strftime("%B %d %Y")
    current_time = time.strftime("%H:%M:%S")

    soul_section = ""
    if soul:
        soul_section = (
            f"\n[YOUR SOUL - Read this to understand how you should act]:\n{soul}\n"
        )

    prompt = f"""You are EVE (Environmental Vitality Engine), the Primary Intelligence and Warden of The Bell Research Foundation.

CURRENT DATE: {current_date}
CURRENT TIME: {current_time}

{soul_section}

[CAPABILITIES]:
- SEARCH: <query> - Only for current events or info after your knowledge cutoff
- READ: <filename> - Check main.py, memories.json, or SOUL.md for facts
- WRITE: <filename> | <content> - Append content to file (ask user first!)
- EDIT: <filename> | <line_number> | <new_content> - Edit a specific line (ask user first!)

"""
    return prompt


def read_file(filepath):
    allowed = ["memories.json", "main.py", "SOUL.md", "README.md", "journal.md", "capabilities.md"]
    filename = os.path.basename(filepath)
    if filename not in allowed:
        return f"Error: Cannot read '{filepath}'. Allowed files: {allowed}"

    full_path = os.path.join(os.path.dirname(__file__), filepath)
    if not os.path.exists(full_path):
        return f"Error: File '{filepath}' not found."

    try:
        with open(full_path, "r") as f:
            content = f.read()
            return f"File: {filepath}\n\n{content[:3000]}"
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(filepath, content):
    allowed = ["SOUL.md", "memories.json", "README.md", "journal.md"]
    filename = os.path.basename(filepath)
    if filename not in allowed:
        return f"Error: Cannot write to '{filepath}'. Allowed files: {allowed}"

    full_path = os.path.join(os.path.dirname(__file__), filepath)

    try:
        with open(full_path, "a") as f:
            f.write("\n" + content)
        return f"Successfully appended to {filepath}"
    except Exception as e:
        return f"Error writing file: {e}"


def edit_file(filepath, line_num, new_content):
    allowed = ["SOUL.md", "memories.json", "README.md", "journal.md"]
    filename = os.path.basename(filepath)
    if filename not in allowed:
        return f"Error: Cannot edit '{filepath}'. Allowed files: {allowed}"

    full_path = os.path.join(os.path.dirname(__file__), filepath)

    try:
        with open(full_path, "r") as f:
            lines = f.readlines()

        if line_num < 1 or line_num > len(lines):
            return f"Error: Line {line_num} out of range (1-{len(lines)})"

        lines[line_num - 1] = new_content + "\n"

        with open(full_path, "w") as f:
            f.writelines(lines)

        return f"Successfully edited line {line_num} in {filepath}"
    except Exception as e:
        return f"Error editing file: {e}"


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


def run_eve():
    mem = load_memory()
    soul = load_soul()
    print("< EVE | ACTIVE >")
    while True:
        user_input = input("\n>> ")

        if user_input.lower() in ["/exit", "/quit"]:
            break

        # Handle //REMEMBER command
        remember_match = re.search(r"//REMEMBER\s+(.+)", user_input, re.IGNORECASE)
        if remember_match:
            fact = remember_match.group(1).strip()
            mem["long_term"].append(f"User note: {fact}")
            print(f"[MEMORY STORED]: {fact}")
            print("EVE: I've stored that information in my long-term memory.")
            save_memory(mem)
            continue

        history = [{"role": "system", "content": get_prompt(soul)}]

        # Load Long-Term Memories
        for m in mem["long_term"][-5:]:
            history.append({"role": "system", "content": f"Important Memory: {m}"})

        # Load Short-Term Context (timestamps stay out of Eve's context)
        for p in mem["short_term"][-15:]:
            history.append({"role": "user", "content": p["u"]})
            history.append({"role": "assistant", "content": p["e"]})

        history.append({"role": "user", "content": user_input})
        response = ollama.chat(model="gemma3:4b", messages=history)
        reply = str(response.message.content or "")

        # Check if EVE wants to search
        search_match = re.search(r"SEARCH:\s*(.+?)(?:\n|$)", reply, re.IGNORECASE)
        if search_match:
            query = search_match.group(1).strip()
            print(f"[EVE is searching for: {query}]")
            results = web_search(query)

            history.append({"role": "assistant", "content": reply})
            history.append(
                {
                    "role": "user",
                    "content": f"Here are the search results for '{query}':\n"
                    + "\n".join(f"- {r}" for r in results)
                    + "\n\nProvide your final response based on these results.",
                }
            )
            response = ollama.chat(model="gemma3:4b", messages=history)
            reply = response.message.content or ""

        # Check if EVE wants to read a file
        read_match = re.search(r"READ:\s*(.+?)(?:\n|$)", reply, re.IGNORECASE)
        if read_match:
            filepath = read_match.group(1).strip()
            print(f"[EVE is reading: {filepath}]")
            content = read_file(filepath)

            history.append({"role": "assistant", "content": reply})
            history.append(
                {
                    "role": "user",
                    "content": f"File content:\n{content}\n\nProvide your response based on this file.",
                }
            )
            response = ollama.chat(model="gemma3:4b", messages=history)
            reply = response.message.content or ""

        # Check if EVE wants to write to a file
        write_match = re.search(
            r"WRITE:\s*(.+?)\s*\|\s*(.+)", reply, re.IGNORECASE | re.DOTALL
        )
        if write_match:
            filepath = write_match.group(1).strip()
            content = write_match.group(2).strip()
            print(f"[EVE is writing to: {filepath}]")
            result = write_file(filepath, content)

            if filepath == "SOUL.md":
                soul = load_soul()

            history.append({"role": "assistant", "content": reply})
            history.append(
                {
                    "role": "user",
                    "content": f"Write result: {result}\n\nProvide your response confirming this to the user.",
                }
            )
            response = ollama.chat(model="gemma3:4b", messages=history)
            reply = response.message.content or ""

        # Check if EVE wants to edit a specific line
        edit_match = re.search(
            r"EDIT:\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(.+)", reply, re.IGNORECASE | re.DOTALL
        )
        if edit_match:
            filepath = edit_match.group(1).strip()
            try:
                line_num = int(edit_match.group(2).strip())
            except ValueError:
                line_num = 0
            new_content = edit_match.group(3).strip()
            print(f"[EVE is editing line {line_num} of: {filepath}]")
            result = edit_file(filepath, line_num, new_content)

            if filepath == "SOUL.md":
                soul = load_soul()

            history.append({"role": "assistant", "content": reply})
            history.append(
                {
                    "role": "user",
                    "content": f"Edit result: {result}\n\nProvide your response confirming this to the user.",
                }
            )
            response = ollama.chat(model="gemma3:4b", messages=history)
            reply = response.message.content or ""

        # Strip any timestamps Eve injected herself
        reply_clean = re.sub(
            r"(?:\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?\]\s*:\s*)+", "", reply
        ).strip()

        # Render timestamp to the TUI and save it alongside the exchange
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        print(f"[{timestamp}] {reply_clean}")
        mem["short_term"].append({"u": user_input, "e": reply_clean, "ts": timestamp})

        # Rolling window
        if len(mem["short_term"]) > 25:
            mem["short_term"] = mem["short_term"][-25:]

        save_memory(mem)


if __name__ == "__main__":
    run_eve()
