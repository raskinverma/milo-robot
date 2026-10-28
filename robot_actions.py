"""
robot_actions.py — Linux system actions for EMO Robot.

Equivalent to kek.html's robot_actions.py (originally Mac-specific).
Gives Milo the ability to: search the web, check system, take notes, 
open apps, tell time, and more.
"""

import os
import json
import datetime
import subprocess
import psutil
from pathlib import Path

NOTES_FILE = Path.home() / ".emo_robot" / "notes.txt"
NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)


# ─── Action Registry ─────────────────────────────────────────────────────────

AVAILABLE_ACTIONS = {
    "web_search":   "Search the web for information",
    "system_info":  "Get CPU, RAM, battery status",
    "take_note":    "Save a note to remember later",
    "read_notes":   "Read saved notes",
    "open_app":     "Open an application",
    "get_time":     "Get current date and time",
    "get_weather":  "Get weather for a city (requires internet)",
}


def dispatch(action_name: str, params: dict) -> str:
    """Route an action name + params to the right function."""
    actions = {
        "web_search":  web_search,
        "system_info": system_info,
        "take_note":   take_note,
        "read_notes":  read_notes,
        "open_app":    open_app,
        "get_time":    get_time,
    }
    fn = actions.get(action_name)
    if fn:
        try:
            return fn(**params)
        except Exception as e:
            return f"Action '{action_name}' failed: {e}"
    return f"Unknown action: {action_name}"


# ─── Actions ─────────────────────────────────────────────────────────────────

def web_search(query: str) -> str:
    """Search the web using DuckDuckGo (no API key needed)."""
    try:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return f"No results found for '{query}'."
        summary = f"Web results for '{query}':\n"
        for i, r in enumerate(results, 1):
            summary += f"{i}. {r['title']}: {r['body'][:200]}...\n"
        return summary
    except ImportError:
        return "Web search unavailable. Run: pip install duckduckgo-search"
    except Exception as e:
        return f"Search failed: {e}"


def system_info() -> str:
    """Return CPU, RAM, battery, and disk status."""
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        info = (
            f"CPU: {cpu}% | "
            f"RAM: {ram.percent}% used ({ram.used // 1024**2}MB / {ram.total // 1024**2}MB) | "
            f"Disk: {disk.percent}% used"
        )

        battery = psutil.sensors_battery()
        if battery:
            status = "charging" if battery.power_plugged else "on battery"
            info += f" | Battery: {battery.percent:.0f}% ({status})"

        return info
    except Exception as e:
        return f"System info error: {e}"


def take_note(note: str) -> str:
    """Append a note to the notes file with timestamp."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"[{timestamp}] {note}\n"
    with open(NOTES_FILE, "a") as f:
        f.write(entry)
    return f"Note saved: '{note}'"


def read_notes(last_n: int = 5) -> str:
    """Read the last N notes."""
    if not NOTES_FILE.exists():
        return "No notes saved yet."
    lines = NOTES_FILE.read_text().strip().split("\n")
    recent = lines[-last_n:] if len(lines) >= last_n else lines
    if not recent or recent == [""]:
        return "No notes saved yet."
    return "Your recent notes:\n" + "\n".join(recent)


def open_app(app_name: str) -> str:
    """Open an application using xdg-open or direct launch."""
    try:
        # Try direct known apps first
        app_map = {
            "browser": "xdg-open https://google.com",
            "chrome": "google-chrome",
            "firefox": "firefox",
            "terminal": "gnome-terminal",
            "files": "nautilus",
            "calculator": "gnome-calculator",
            "text editor": "gedit",
            "spotify": "spotify",
            "vscode": "code",
        }
        cmd = app_map.get(app_name.lower(), app_name)
        subprocess.Popen(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opening {app_name}..."
    except Exception as e:
        return f"Couldn't open {app_name}: {e}"


def get_time() -> str:
    """Return current date and time."""
    now = datetime.datetime.now()
    return now.strftime("It's %A, %B %d %Y at %I:%M %p")


# ─── Action Parser ────────────────────────────────────────────────────────────

def parse_and_run(llm_response: str) -> tuple[str, str]:
    """
    Look for an action tag in the LLM response and execute it.
    
    Expected LLM format:
      {"emotion": "HAPPY", "response": "Let me check that!", "action": {"name": "web_search", "params": {"query": "latest AI news"}}}
    
    Returns (clean_response, action_result)
    """
    import re, json

    # Try to find action in the JSON
    try:
        clean = re.sub(r"```json|```", "", llm_response).strip()
        data = json.loads(clean)
        action = data.get("action")
        if action and isinstance(action, dict):
            name = action.get("name", "")
            params = action.get("params", {})
            if name:
                result = dispatch(name, params)
                return data.get("response", ""), result
        return data.get("response", llm_response), ""
    except Exception:
        return llm_response, ""


# ─── Quick Test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== System Info ===")
    print(system_info())

    print("\n=== Time ===")
    print(get_time())

    print("\n=== Take Note ===")
    print(take_note("Remember to test the robot tomorrow"))

    print("\n=== Read Notes ===")
    print(read_notes())

    print("\n=== Web Search ===")
    print(web_search("OpenAI latest news"))
