import os
import asyncio
import tempfile
import pygame
import speech_recognition as sr
import edge_tts

class AudioPipeline:
    def __init__(self, mic_index=11, voice="en-US-ChristopherNeural"): # Changed to adult male voice & index 11
        self.voice = voice
        self.recognizer = sr.Recognizer()
        
        # Explicitly use the system default virtual audio channel
        self.microphone = sr.Microphone(device_index=mic_index)
        
        pygame.mixer.init()

        # Disable auto-calibration and force a highly sensitive threshold
        self.recognizer.energy_threshold = 300  
        self.recognizer.dynamic_energy_threshold = False
        print("Microphone forced to high sensitivity (Threshold: 300)")

    async def _synthesize(self, text: str, output_path: str):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(output_path)

    def speak(self, text: str):
        """Mouth: Synthesizes high-fidelity neural speech and plays it."""
        if not text:
            return
        print(f"🤖 Robot: {text}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_filename = fp.name

        try:
            asyncio.run(self._synthesize(text, temp_filename))
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        finally:
            pygame.mixer.music.unload()
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    def listen(self) -> str:
        """Ears: Captures voice input with turn-based audio pausing."""
        with self.microphone as source:
            print("\n🎤 Listening... (speak now)")
            try:
                # 6 second silence timeout, 10 second speech limit
                audio_data = self.recognizer.listen(source, timeout=6.0, phrase_time_limit=10.0)
                print("⏳ Transcribing audio...")
                
                text = self.recognizer.recognize_google(audio_data)
                print(f"👤 You: {text}")
                return text
            except sr.WaitTimeoutError:
                print("⚠️ Listening timed out (no speech detected).")
                return ""
            except sr.UnknownValueError:
                print("⚠️ Could not understand audio.")
                return ""
            except Exception as e:
                print(f"⚠️ Audio error: {e}")
                return ""

# --- Standalone Test ---
if __name__ == "__main__":
    # Target ALC257 mic index 4
    audio = AudioPipeline(mic_index=10)
    
    # 1. Mouth Test
    audio.speak("Hello! My neural voice is working. What can I help you with today?")
    
    # 2. Ear Test
    user_speech = audio.listen()
    
    # 3. Echo Test
    if user_speech:
        audio.speak(f"I heard you say: {user_speech}")
    else:
        audio.speak("I didn't hear anything, but the audio output is working!")
