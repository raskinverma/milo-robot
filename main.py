import threading
import time
from vision import VisionSource
from fast_audio import FastAudioEngine
from face import VirtualFace
from bot_brain import ask_brain

def hardware_loop(face, audio, eyes):
    """Runs the AI pipeline in the background so the Pygame face doesn't freeze."""
    while True:
        input("\n[Press ENTER to talk to Milo...]")

        # TRIGGERED — switch to listening face
        face.set_emotion("LISTENING")

        # INGEST — listen for voice
        user_text = audio.listen()
        if not user_text:
            face.set_emotion("NEUTRAL")
            continue

        # Snap a photo
        print("📸 Snapping photo...")
        image_b64 = eyes.capture_frame()

        # PROCESS — send to brain (memory + LLM + actions)
        face.set_emotion("THINKING")
        response_data = ask_brain(user_text, image_b64)

        # RESPOND — update face, speak reply
        new_emotion = response_data.get("emotion", "NEUTRAL").upper()
        reply_text  = response_data.get("response", "I'm not sure what to say.")

        # Switch to TALKING while speaking, then to the LLM's chosen emotion
        face.set_emotion("TALKING")
        audio.speak(reply_text)

        face.set_emotion(new_emotion)

        # RESET
        time.sleep(1.5)
        face.set_emotion("NEUTRAL")


if __name__ == "__main__":
    print("🤖 Initializing Milo's Systems...")

    eyes  = VisionSource(0)
    audio = FastAudioEngine(voice="en-US-ChristopherNeural", mic_device=10)
    face  = VirtualFace()   # Must run on main thread for Pygame

    # Start the AI pipeline in a background thread
    ai_thread = threading.Thread(
        target=hardware_loop, args=(face, audio, eyes), daemon=True
    )
    ai_thread.start()

    print("✅ Milo is online! Press ENTER in the terminal to speak.")
    while True:
        face.render()
