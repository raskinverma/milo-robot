import io
import time
import queue
import threading
import struct
import numpy as np
import sounddevice as sd
import edge_tts
import pygame
import asyncio
import webrtcvad
from faster_whisper import WhisperModel


# ─── WebRTC VAD Constants ──────────────────────────────────────────────────────
# webrtcvad requires 16-bit PCM at 8/16/32/48 kHz in fixed frame sizes.
# We use 16 kHz with 20 ms frames (320 samples = 640 bytes of int16 PCM).
_VAD_SAMPLE_RATE    = 16000
_VAD_FRAME_MS       = 20                              # 20 ms per VAD frame
_VAD_FRAME_SAMPLES  = _VAD_SAMPLE_RATE * _VAD_FRAME_MS // 1000  # 320 samples
_VAD_FRAME_BYTES    = _VAD_FRAME_SAMPLES * 2          # 640 bytes (int16 LE)


class FastAudioEngine:
    """
    Audio engine for Milo using:
      • WebRTC VAD  — Google's proven voice-activity detector; immune to fan
                      noise, AC hum, and other stationary background sounds.
      • faster-whisper — local CPU transcription with int8 quantisation.
      • edge-tts + pygame — low-latency streaming TTS.

    WebRTC VAD works on 16-bit signed PCM frames of exactly 10/20/30 ms.
    The sounddevice callback delivers float32 frames; we convert on the fly.

    VAD aggressiveness:
      0 = most permissive (picks up quiet speech, more false positives)
      1 = balanced  ← default
      2 = stricter
      3 = most aggressive (only loud, clear speech; misses soft speech)
    Increase aggressiveness if you still get false triggers from background
    noise; decrease it if Milo cuts off your sentence early.
    """

    def __init__(self, voice: str = "en-US-ChristopherNeural",
                 mic_device: int = 10,
                 vad_aggressiveness: int = 1):
        print("🧠 Loading local Whisper model (base.en / int8)...")
        self.stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.voice      = voice
        self.mic_device = mic_device
        self.sample_rate = _VAD_SAMPLE_RATE

        # WebRTC VAD — the key fix for laptop-fan noise problems
        self._vad = webrtcvad.Vad(vad_aggressiveness)

        self.audio_queue: queue.Queue = queue.Queue()
        self._pcm_buffer = b""   # leftover bytes between VAD frames

        pygame.mixer.init()
        print(f"✅ Audio engine ready. Mic device: {mic_device} | "
              f"WebRTC VAD aggressiveness: {vad_aggressiveness}")

    # ──────────────────────────────────────────────────────────────────────────
    # TTS — Mouth
    # ──────────────────────────────────────────────────────────────────────────

    async def _stream_speak(self, text: str) -> None:
        communicate = edge_tts.Communicate(text, self.voice)
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
        audio_stream.seek(0)
        pygame.mixer.music.load(audio_stream)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(20)

    def speak(self, text: str) -> None:
        """Stream TTS audio in-memory and play via pygame."""
        if not text:
            return
        print(f"🤖 Milo: {text}")
        asyncio.run(self._stream_speak(text))

    # ──────────────────────────────────────────────────────────────────────────
    # VAD helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _float32_to_pcm16(float_array: np.ndarray) -> bytes:
        """Convert float32 [-1, 1] audio to signed 16-bit little-endian PCM."""
        clipped = np.clip(float_array, -1.0, 1.0)
        pcm     = (clipped * 32767).astype(np.int16)
        return pcm.tobytes()

    def _is_speech(self, pcm_bytes: bytes) -> bool:
        """Run one 20 ms frame through WebRTC VAD. Returns True if voice found."""
        try:
            return self._vad.is_speech(pcm_bytes, self.sample_rate)
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # STT — Ears
    # ──────────────────────────────────────────────────────────────────────────

    # Strings Whisper hallucinates from silence or fan noise
    WHISPER_HALLUCINATIONS = {
        "", "you", "thank you", "thanks", "thanks for watching",
        "thank you for watching", "thank you.", "thanks.",
        "bye", "goodbye", ".", "...", "okay", "ok",
        "[music]", "[ music ]", "(music)", "[silence]",
        "you.", "you!", "you?",
    }

    def listen(self,
               silence_duration: float = 1.2,
               max_duration: float = 12.0,
               min_speech_duration: float = 0.4,
               speech_frames_to_start: int = 3) -> str:
        """
        Record until the user stops speaking, then transcribe with Whisper.

        Algorithm (WebRTC VAD):
          1. Accumulate sounddevice float32 chunks into a PCM byte buffer.
          2. Slice the buffer into exact 20 ms frames and run VAD on each.
          3. Recording starts after `speech_frames_to_start` consecutive
             SPEECH frames (avoids triggering on a single noise pop).
          4. Recording stops after `silence_duration` seconds of consecutive
             NON-SPEECH frames (relative to speech onset).
          5. Audio shorter than `min_speech_duration` is discarded.
          6. The full float32 audio (not PCM) is normalised and fed to Whisper.

        Why this beats RMS thresholding for laptop use:
          - Fan noise, AC hum, and keyboard clicks are stationary-spectrum
            sounds that WebRTC VAD's frequency-domain filter rejects cleanly.
          - RMS thresholding cannot distinguish broadband noise from speech.
        """
        print("\n🎤 Listening... (speak now)")

        # Flush stale queue items from previous call
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self._pcm_buffer = b""

        recorded_float  : list[np.ndarray] = []   # full float audio for Whisper
        speech_float    : list[np.ndarray] = []   # speech-only float for duration check

        consecutive_speech  = 0
        consecutive_silence = 0
        is_speaking         = False
        silence_start       = None
        start_time          = time.time()

        # silence_frames = how many 20 ms frames of silence end the recording
        silence_frames_needed = int(silence_duration * 1000 / _VAD_FRAME_MS)

        def _sd_callback(indata: np.ndarray, frames: int,
                         time_info, status) -> None:
            if status:
                print(f"  ⚠️ SD status: {status}")
            self.audio_queue.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.sample_rate, channels=1,
                device=self.mic_device, dtype="float32",
                blocksize=_VAD_FRAME_SAMPLES,   # deliver exactly 320 samples/block
                callback=_sd_callback,
            ):
                while True:
                    # ── Timeout guard ─────────────────────────────────────────
                    elapsed = time.time() - start_time
                    if elapsed > max_duration:
                        print("⏱️  Max recording time reached.")
                        break

                    # ── Fetch one sounddevice block ───────────────────────────
                    try:
                        chunk = self.audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        print("⚠️  Audio stream stalled.")
                        break

                    flat = chunk.flatten()

                    # ── Convert to PCM16 and feed VAD buffer ──────────────────
                    self._pcm_buffer += self._float32_to_pcm16(flat)

                    # Process as many complete 20 ms frames as we have
                    while len(self._pcm_buffer) >= _VAD_FRAME_BYTES:
                        frame_bytes      = self._pcm_buffer[:_VAD_FRAME_BYTES]
                        self._pcm_buffer = self._pcm_buffer[_VAD_FRAME_BYTES:]

                        # Reconstruct the float32 for this frame (for Whisper)
                        frame_floats = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                        speech = self._is_speech(frame_bytes)

                        if speech:
                            consecutive_speech  += 1
                            consecutive_silence  = 0

                            if not is_speaking and consecutive_speech >= speech_frames_to_start:
                                is_speaking   = True
                                silence_start = None
                                print("🗣️  [Voice detected]")

                            if is_speaking:
                                recorded_float.append(frame_floats)
                                speech_float.append(frame_floats)
                        else:
                            consecutive_speech = 0
                            consecutive_silence += 1

                            if is_speaking:
                                # Buffer trailing silence (it may be mid-word pauses)
                                recorded_float.append(frame_floats)

                                if consecutive_silence >= silence_frames_needed:
                                    print("🔕  [Silence detected — end of utterance]")
                                    break
                    else:
                        # Inner while not broken → continue outer loop
                        continue
                    # Inner while was broken (silence detected) → exit outer loop
                    break

        except Exception as e:
            print(f"⚠️  Microphone error: {e}")
            return ""

        # ── Validate speech duration ──────────────────────────────────────────
        if not recorded_float:
            return ""

        speech_duration = len(speech_float) * _VAD_FRAME_MS / 1000.0
        total_duration  = len(recorded_float) * _VAD_FRAME_MS / 1000.0
        print(f"📊 Recorded {total_duration:.2f}s | Speech {speech_duration:.2f}s")

        if speech_duration < min_speech_duration:
            print(f"⚠️  Too short ({speech_duration:.2f}s) — likely noise burst, skipping.")
            return ""

        # ── Normalise and transcribe ──────────────────────────────────────────
        print("⚡ Transcribing locally...")
        audio_data = np.concatenate(recorded_float, axis=0).astype(np.float32)

        max_val = float(np.max(np.abs(audio_data)))
        if max_val > 0.01:
            audio_data = audio_data / max_val * 0.95
            print(f"🔊 Normalised (peak was {max_val:.3f})")

        segments, _ = self.stt_model.transcribe(
            audio_data,
            beam_size=5,
            vad_filter=True,          # ← Re-enabled: WebRTC already filtered the
                                       #   recording, so Whisper VAD is a safe 2nd pass
            condition_on_previous_text=False,
            language="en",
        )
        transcript = " ".join(seg.text for seg in segments).strip()

        # ── Hallucination filter ──────────────────────────────────────────────
        if transcript.lower().strip(".,!? ") in self.WHISPER_HALLUCINATIONS:
            print(f"⚠️  Hallucination filtered: {repr(transcript)}")
            return ""

        if transcript:
            print(f"👤 You: {transcript}")
        return transcript


# ─── Quick Test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Available audio devices:")
    print(sd.query_devices())
    # Device 10 = PipeWire (virtual mixer → routes to ALC257, supports 16 kHz)
    bot = FastAudioEngine(
        voice="en-US-ChristopherNeural",
        mic_device=10,
        vad_aggressiveness=1,   # raise to 2 or 3 if fan noise still triggers
    )
    bot.speak("Hey there! WebRTC VAD ears are ready. Try talking to me.")

    text = bot.listen()
    if text:
        bot.speak(f"Got it! You said: {text}")
    else:
        bot.speak("I didn't catch anything clear. Try again?")
