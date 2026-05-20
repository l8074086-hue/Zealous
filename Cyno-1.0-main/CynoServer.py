from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)
memory = []
max_mem = 4
def load_memory():
    """
    Load memory from a persistent store if needed.
    Currently, this is just an in-memory list.
    """
    
    
def build_prompt(user_msg):
    """
    Build the prompt for Cyno including:
    - User message
    - Previously stored memory
    """
    if len(memory) > max_mem:
        del memory[0]
    if memory:
        # Flatten memory into readable string for the LLM
        memory_text = "\n".join(
            [f"(user): {m['user']}" if 'user' in m else f"(Cyno): {m['Cyno']}" for m in memory]
        )
        prompt = f"{user_msg}\nContext:\n{memory_text}"
    else:
        prompt = user_msg
    return prompt

@app.route("/talk", methods=["POST"])
def talk():
    try:
        user_msg = request.json.get("message", "").strip()
        if not user_msg:
            return jsonify({"reply": "No message received."})

        # Store user message in memory (mark 'remember' explicitly if needed)
        if "%Cyno Remember" in user_msg:
            memory_item = user_msg.replace("%Cyno Remember", "").strip()
            memory.append({"user": f"MEMORY: {memory_item}"})
        else:
            memory.append({"user": user_msg})

        # Build the prompt including memory
        prompt = build_prompt(user_msg)

        # Call Ollama subprocess with single string argument
        result = subprocess.run(
            ["ollama", "run", "Cyno", prompt],
            capture_output=True,
            text=True
        )
        print(memory)
        print(prompt)
        reply = result.stdout.strip() or result.stderr.strip()
        if not reply:
            reply = "Cyno is too sarcastic to respond."

        # Store Cyno's reply in memory
        memory.append({"Cyno": reply})

        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Error: {e}"}), 500

@app.route("/sunset", methods=["POST"])
def sunset():
    try:
        msg = request.json.get("message", "")
        if not msg:
            return jsonify({"reply": "No message provided."})

        result = subprocess.run(
            ["ollama", "run", "sunset", msg],
            capture_output=True,
            text=True
        )

        reply = result.stdout.strip() or result.stderr.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Error: {e}"}), 500
    
@app.route("/reset_memory", methods=["POST"])
def reset_memory():
    memory.clear()
    return jsonify({"reply": "Cyno has forgotten everything. Including banana fart."})
@app.route("/get_memory", methods=["GET"])
def get_memory():
    return jsonify({"memory": memory})
@app.route("/CynoOwner", methods=["POST"])
def Cyno_owner():
    prompt = build_prompt(owner_msg)
    try:
        owner_msg = request.json.get("message", "")
        if not owner_msg:
            return jsonify({"reply": "No message provided."})

        result = subprocess.run(
            ["ollama", "run", "CynoOwner", prompt, ],
            capture_output=True,
            text=True
        )

        reply = result.stdout.strip() or result.stderr.strip()
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Error: {e}"}), 500
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
