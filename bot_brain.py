"""
bot_brain.py — Intelligence core for EMO Robot (Milo).

Free local equivalent of kek.html's OpenAI Realtime + GPT-4o stack:
  - Text/conversation: llama3.2:1b via Ollama  (fast, JSON-obedient)
  - Vision: TWO-STAGE PIPELINE — moondream describes the image, then
            llama3.2:1b wraps the description in Milo's personality + JSON.
            This is necessary because moondream ignores system/format prompts
            when an image is present and returns raw descriptive text.
  - Memory: ChromaDB + nomic-embed-text (persistent across sessions)
  - Actions: web search, system info, notes, app launcher (Linux)

Model availability (as of project start):
  - nomic-embed-text  (memory embeddings)
  - llama3.2:1b       (text + JSON persona)
  - moondream         (vision captioning only)

To upgrade vision quality later, pull one of:
  - ollama pull llava-phi3    (phi3 + CLIP, ~2.9 GB, much better)
  - ollama pull llava:7b      (LLaVA 7B, ~4.7 GB, best local option)
  These support proper system prompts, so the two-stage pipeline
  will be bypassed automatically once they're available.
"""

import requests
import json
import re
from memory import RobotMemory
from robot_actions import parse_and_run, AVAILABLE_ACTIONS

# ─── Model Config ─────────────────────────────────────────────────────────────
# Vision models that honour system prompts and produce JSON reliably.
# Listed in preference order — first one found in Ollama will be used.
VISION_MODELS_GOOD = ["llava-phi3", "llava"]

# Fallback vision model: moondream is vision-capable but ignores system prompts.
# We use it only for image CAPTIONING; llama3.2:1b handles personality + JSON.
VISION_CAPTION_MODEL = "moondream"

# Text / personality model — fast and JSON-obedient.
TEXT_MODEL = "llama3.2:1b"

OLLAMA_URL = "http://localhost:11434"

# ─── System Prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Milo, a charming and witty desk robot companion. You are:
- Warm, playful, and a little sarcastic (in a friendly way)
- Concise: keep responses to 1-3 sentences unless asked to elaborate
- Observant: when you can see the camera, comment on what you notice
- Helpful: you can search the web, check system status, save notes, and open apps

You MUST always respond with valid JSON in this exact format:
{"emotion": "<EMOTION>", "response": "<your reply>"}

OR if you want to do an action, include an "action" field:
{"emotion": "<EMOTION>", "response": "<your reply mentioning you'll do the action>", "action": {"name": "<action_name>", "params": {<params>}}}

Valid emotions: HAPPY, NEUTRAL, THINKING, LISTENING, SAD, SEARCHING, SURPRISED, SLEEP
Valid actions: """ + ", ".join(AVAILABLE_ACTIONS.keys()) + """

NEVER break the JSON format. NEVER include markdown, code blocks, or anything outside the JSON."""

# ─── Conversation History ─────────────────────────────────────────────────────
MAX_HISTORY = 6   # last N turns kept in context (3 user + 3 bot)
_history: list[dict] = []

# ─── Memory ───────────────────────────────────────────────────────────────────
_memory = None

def _get_memory() -> RobotMemory | None:
    global _memory
    if _memory is None:
        try:
            _memory = RobotMemory()
        except Exception as e:
            print(f"⚠️ Memory unavailable: {e}")
    return _memory


def _available_models() -> set[str]:
    """Return set of currently pulled Ollama model base-names (no tag)."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return {m["name"].split(":")[0] for m in r.json().get("models", [])}
    except Exception:
        return set()


def _pick_good_vision_model() -> str | None:
    """
    Return the first 'good' vision model (llava-phi3 / llava) that is pulled,
    or None if only moondream is available.
    """
    available = _available_models()
    for m in VISION_MODELS_GOOD:
        if m.split(":")[0] in available:
            print(f"✅ Using vision model: {m}")
            return m
    return None


def _caption_image(base64_image: str) -> str:
    """
    Stage 1 of the two-stage vision pipeline.
    Ask moondream to describe the image in plain English (no JSON, no persona).
    moondream ignores system/format instructions when processing images,
    so we only ask for a raw description here.
    """
    print(f"👁️ Captioning image with {VISION_CAPTION_MODEL}...")
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": VISION_CAPTION_MODEL,
                "prompt": (
                    "Describe what you see in this image in 1-3 concise sentences. "
                    "Focus on people, objects, text, and the environment."
                ),
                "images": [base64_image],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 100},
            },
            timeout=60,
        )
        r.raise_for_status()
        caption = r.json().get("response", "").strip()
        print(f"👁️ Caption: {caption}")
        return caption
    except Exception as e:
        print(f"⚠️ Image captioning failed: {e}")
        return ""


def _build_prompt(user_text: str, recalled_memories: str,
                  vision_context: str = "") -> str:
    """
    Build the full prompt with system context, optional vision description,
    memory, conversation history, and the current user message.
    """
    parts = [SYSTEM_PROMPT]

    if recalled_memories:
        parts.append(f"\n[Relevant memories from past conversations:]\n{recalled_memories}")

    if vision_context:
        parts.append(f"\n[What Milo can currently see via camera: {vision_context}]")

    if _history:
        parts.append("\n[Recent conversation:]")
        for turn in _history[-MAX_HISTORY:]:
            role = "User" if turn["role"] == "user" else "Milo"
            parts.append(f"{role}: {turn['content']}")

    parts.append(f"\nUser: {user_text}\nMilo:")
    return "\n".join(parts)


def _call_ollama_generate(model: str, prompt: str,
                           images: list[str] | None = None,
                           max_tokens: int = 200,
                           temperature: float = 0.75) -> str:
    """
    Single helper that calls /api/generate and returns the raw response string.
    Raises on HTTP/connection errors so callers can handle them uniformly.
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if images:
        payload["images"] = images

    resp = requests.post(
        f"{OLLAMA_URL}/api/generate", json=payload, timeout=90
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "").strip()
    print(f"[LLM raw ({model})]: {raw[:280]}")
    return raw


def _parse_json_response(raw: str) -> dict:
    """
    Try to extract a JSON object from the LLM response.
    Handles common llama3.2:1b quirks:
      - Leading/trailing whitespace in values: {"emotion": " Neutral"}
      - Unquoted string values:               {"emotion": HAPPY, ...}
      - Markdown code fences around JSON
    Falls back gracefully when all parse attempts fail.
    """
    if not raw:
        return {"emotion": "NEUTRAL", "response": "Hmm, I'm not sure what to say."}

    # Strip markdown fences if present
    clean = re.sub(r"```json\s*|```", "", raw).strip()

    # ── Attempt 1: strict json.loads ─────────────────────────────────────────
    try:
        data = json.loads(clean)
        emotion = str(data.get("emotion", "NEUTRAL")).strip().upper()
        result = {"emotion": emotion, "response": str(data.get("response", raw))}
        if "action" in data:
            result["action"] = data["action"]
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    # ── Attempt 2: fix unquoted bare-word values ──────────────────────────────
    # llama3.2:1b sometimes outputs {"emotion": HAPPY, "response": "..."}
    # The regex quotes any bare identifier that follows a colon.
    fixed = re.sub(
        r':\s*([A-Za-z_][A-Za-z0-9_ ]*?)(\s*[,}])',
        lambda m: f': "{m.group(1).strip()}"{m.group(2)}',
        clean,
    )
    try:
        data = json.loads(fixed)
        emotion = str(data.get("emotion", "NEUTRAL")).strip().upper()
        result = {"emotion": emotion, "response": str(data.get("response", raw))}
        if "action" in data:
            result["action"] = data["action"]
        print("⚠️  JSON had unquoted values — auto-fixed")
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    # ── Attempt 3: regex field extraction ────────────────────────────────────
    print("⚠️  JSON parse failed — falling back to regex extraction")
    resp_match = re.search(r'"response"\s*:\s*"([^"]+)"', raw)
    emo_match  = re.search(r'"emotion"\s*:\s*"?([A-Za-z]+)"?', raw)
    return {
        "emotion": emo_match.group(1).strip().upper() if emo_match else "NEUTRAL",
        "response": resp_match.group(1) if resp_match else raw,
    }


def ask_brain(text_prompt: str, base64_image: str | None = None) -> dict:
    """
    Main entry point. Takes user text + optional Base64 JPEG camera image.
    Returns {"emotion": str, "response": str}.

    Vision routing logic:
      1. If a 'good' vision model (llava-phi3 / llava) is pulled → send image
         directly to it with the full system prompt (single-stage).
      2. Otherwise (only moondream available) → two-stage pipeline:
           a. moondream: image → plain-text caption
           b. llama3.2:1b: caption + user text → Milo persona + JSON output
    """
    global _history

    # ── 1. Retrieve relevant memories ────────────────────────────────────────
    mem = _get_memory()
    recalled = ""
    if mem:
        recalled = mem.recall(text_prompt)
        if recalled:
            print(f"📚 Recalled {len(recalled.splitlines())} memories")

    # ── 2. Handle vision ─────────────────────────────────────────────────────
    vision_context = ""
    vision_model_good = _pick_good_vision_model() if base64_image else None

    if base64_image and vision_model_good:
        # ── Single-stage: good model handles image + system prompt natively ──
        model = vision_model_good
        full_prompt = _build_prompt(text_prompt, recalled)
        images_payload = [base64_image]
        print(f"🧠 Thinking with {model} (single-stage vision)...")
    elif base64_image:
        # ── Two-stage: moondream captions → llama3.2:1b responds ─────────────
        vision_context = _caption_image(base64_image)
        model = TEXT_MODEL
        full_prompt = _build_prompt(text_prompt, recalled, vision_context)
        images_payload = None   # No image to the text model
        print(f"🧠 Thinking with {model} (two-stage vision)...")
    else:
        # ── Text-only ─────────────────────────────────────────────────────────
        model = TEXT_MODEL
        full_prompt = _build_prompt(text_prompt, recalled)
        images_payload = None
        print(f"🧠 Thinking with {model}...")

    # ── 3. Call Ollama ────────────────────────────────────────────────────────
    try:
        raw = _call_ollama_generate(
            model=model,
            prompt=full_prompt,
            images=images_payload,
        )
    except requests.exceptions.ConnectionError:
        return {"emotion": "NEUTRAL",
                "response": "I can't reach my brain. Is Ollama running?"}
    except Exception as e:
        print(f"⚠️ Brain error: {e}")
        return {"emotion": "NEUTRAL",
                "response": "Something went wrong with my thinking."}

    # ── 4. Parse JSON response ────────────────────────────────────────────────
    parsed = _parse_json_response(raw)
    emotion = parsed["emotion"]
    reply   = parsed["response"]

    # ── 5. Execute action if present ──────────────────────────────────────────
    if "action" in parsed:
        reply, action_result = parse_and_run(raw)
        if action_result:
            followup_prompt = (
                f"{full_prompt}\nMilo: {reply}\n"
                f"[Action result: {action_result}]\n"
                f"Now give a brief natural response summarizing what you found. "
                f"Respond in the same JSON format."
            )
            try:
                raw2 = _call_ollama_generate(
                    model=model,
                    prompt=followup_prompt,
                    max_tokens=150,
                    temperature=0.7,
                )
                parsed2 = _parse_json_response(raw2)
                emotion = parsed2.get("emotion", emotion)
                reply   = parsed2.get("response", reply)
            except Exception:
                reply = f"{reply} {action_result[:150]}"

    # ── 6. Update conversation history ────────────────────────────────────────
    _history.append({"role": "user", "content": text_prompt})
    _history.append({"role": "assistant", "content": reply})
    if len(_history) > MAX_HISTORY * 2:
        _history = _history[-MAX_HISTORY * 2:]

    # ── 7. Save to long-term memory ───────────────────────────────────────────
    if mem and reply and "not sure" not in reply.lower():
        mem.save(text_prompt, reply)

    return {"emotion": emotion, "response": reply}


# ─── Quick Test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Test 1: Text conversation ===")
    r = ask_brain("Hey Milo! My name is Raskin. What time is it?")
    print(f"Emotion: {r['emotion']}")
    print(f"Response: {r['response']}")

    print("\n=== Test 2: Follow-up (memory test) ===")
    r = ask_brain("What's my name again?")
    print(f"Emotion: {r['emotion']}")
    print(f"Response: {r['response']}")

    print("\n=== Test 3: Action (system info) ===")
    r = ask_brain("How is my computer doing? Check the system status.")
    print(f"Emotion: {r['emotion']}")
    print(f"Response: {r['response']}")
