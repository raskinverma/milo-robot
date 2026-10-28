# **System Architecture Overview** 

The system uses a **client-server architecture** divided into two layers: 

- **The Physical Interface (Client / Hardware Node):** Captures sensory data (camera frames, audio) and renders outputs (facial expressions on a display, audio output). 

- **The Intelligence Core (Server / Host Brain):** A Python-based orchestrator running locally on your computer that handles speech-to-text, visual understanding, large language model (LLM) reasoning, long-term memory, and text-to-speech synthesis. 

By designing the software with modular interfaces, the **Intelligence Core** runs on your PC using simulated hardware (webcam, monitor, PC mic) during development, allowing you to swap in physical microcontroller endpoints with minimal refactoring. 

+-------------------------------------------------------+ |               Python Host Brain (PC) | | | |  +------------------+         +--------------------+  | |  | Speech-to-Text   | ------> | Vision-Language    |  | |  | (STT Engine)     |         | Model (Ollama/VLM) |  | |  +------------------+         +--------------------+  | |          ^                               |            | |          |                               v            | |  +------------------+         +--------------------+  | |  | Frame Ingestion  |         | Text-to-Speech     |  | |  | (Vision Capture) |         | (TTS Engine)       |  | |  +------------------+         +--------------------+  | +-------------------------------------------------------+ 

^                                 | 

| (HTTP / WebSockets / OpenCV)    | (Display State) v                                 v +-------------------------------------------------------+ 

|             Phase 1: PC Mock Hardware                 | |  [PC Webcam]  [PC Mic]  [PC Speakers]  [Pygame Face]  | | ----------------------------------------------------- | |            Phase 2: Physical Hardware                 | |  [ESP32-S3 + Camera]  [OLED Face]  [Onboard Mic]      | +-------------------------------------------------------+ 

# **Phase 1: PC-First Prototyping (Software** 

# **Implementation)** 

Build and test every software module on your computer before touching physical hardware. 

## **1. The Vision Pipeline (Simulated Eyes)** 

- **Mechanism:** Capture frames from your computer's built-in webcam using an abstraction wrapper. 

### ● **Workflow:** 

1. Initialize a capture stream via OpenCV. 

2. Implement an on-demand frame grabber function (capture_frame()) that grabs the latest video frame, resizes it to standard vision dimensions (e.g., $640 \times 480$), encodes it into a JPEG format, and converts it to a Base64 string or byte array. 

3. Wrap this in a generic VisionSource interface so changing to an IP camera stream later requires changing only one URL parameter. 

## **2. The Audio Pipeline (Simulated Ears & Mouth)** 

### ● **Ears (Audio Input & Transcription):** 

- Use a microphone stream wrapper to listen for speech. 

- Implement **Voice Activity Detection (VAD)** or push-to-talk to detect when you start and stop speaking. 

- Feed the recorded audio buffer to a local transcription model (such as OpenAI Whisper running locally via whisper.cpp or faster-whisper) to convert speech to a text prompt. 

### ● **Mouth (Speech Synthesis):** 

- Implement a text-to-speech (TTS) worker that takes string responses from the language model and streams natural-sounding audio back through your PC speakers (using local engines like piper-tts, pyttsx3, or coqui-tts). 

## **3. The Virtual Face (Simulated Display)** 

- **Mechanism:** A standalone window that mimics the dimensions and resolution of a $128 \times 64$ monochrome OLED screen. 

- **Implementation:** 

   - Create a lightweight UI loop using Pygame or Tkinter fixed to a $128 \times 64$ canvas (scaled up on your monitor for visibility). 

   - Design primitive-based procedural eye states: 

      - NEUTRAL: Two rounded rectangles with subtle blinking cycles. 

      - LISTENING: Slightly enlarged eyes with a pulsing outline. 

      - THINKING: Narrowed eyes shifting side-to-side. 

      - HAPPY: Inverted arc/crescent shapes. 

      - TALKING: Vertically resizing shapes keyed to TTS audio output. 

   - Control states via an event queue or a simple local state variable (current_emotion). 

## **4. The Intelligence Engine (Local Multimodal LLM)** 

- **Framework:** Run Ollama locally on your machine to manage models without cloud dependencies or API keys. 

- **Model Selection:** 

   - **Vision-Language Model (VLM):** Use llava, moondream2, or llama3.2-vision to process text prompts along with image frames. 

   - **Text-Only Fast Model:** Use llama3 or mistral for quick, conversation-only queries that don't require visual analysis. 

- **Prompt Architecture:** 

- Define a system prompt giving the robot a distinct personality, concise desk-companion tone, and instructions to append an emotion tag to every response (e.g., {"emotion": "happy", "response": "I see a coffee mug on your desk!"}). 

## **5. The Master Orchestration Loop** 

Write the central Python controller script that coordinates the pipeline: 

1. **State IDLE:** Eye animation runs a background idle/blink loop. 

2. **State TRIGGERED:** User initiates interaction (via spacebar, wake word, or voice activity detection). The virtual face switches to LISTENING. 

3. **State INGEST:** The microphone records your voice command while the camera simultaneously grabs a snapshot of your workspace. 

4. **State PROCESS:** Audio is transcribed to text. The text and the captured image frame are bundled into a payload sent to Ollama via its local REST API (http://localhost:11434/api/generate). The virtual face switches to THINKING. 

5. **State RESPOND:** The LLM output is parsed. The emotion tag updates the virtual face state, and the text is passed to the TTS engine to play through the speakers. 

6. **State RESET:** The system returns to IDLE. 

# **Phase 2: Hardware Acquisition & Setup** 

Once the software loop operates reliably on the PC, acquire the physical hardware. 

|**Component**|**Function**|**Notes**|
|---|---|---|
|**LILYGO T-Camera S3**<br>_(or Seeed XIAO_<br>_ESP32S3 + OLED)_|Core microcontroller, Wi-Fi<br>node, camera, screen,<br>and mic.|Houses ESP32-S3,<br>OV2640 camera, and<br>SSD1306 OLED in a<br>single unit.|
|**USB-C Data Cable**|Power delivery and<br>firmware flashing.|Must support high-speed<br>data transfer, not<br>power-only.|
|**3D Printing Filament**<br>**(PLA/PETG)**|Material for custom<br>structural housing.|Matte black or neutral<br>tones work well for OLED<br>enclosures.|



|**M2/M2.5 Machine**|Internal structural|Used to secure the PCB|
|---|---|---|
|**Screws & Inserts**|fastening.|inside the printed housing.|



# **Phase 3: CAD Modeling & Enclosure Design** 

Create a custom body from scratch around the hardware's precise dimensions. 



<!-- Start of picture text -->
      +-----------------------------------+<br>       |       [ Camera Lens Cutout ]      |  <-- Upper Faceplate<br>       |                                   |<br>       |     +-----------------------+     |<br>       |     |  OLED Screen Window   |     |  <-- Recessed Bezel<br>       |     +-----------------------+     |<br>       |                                   |<br>       |       [ Mic Sound Port ]          |  <-- Lower Faceplate<br>       +-----------------------------------+<br>                         |<br>                         v<br>       +-----------------------------------+<br>       |     Internal Mounting Chassis     |  <-- Stand-offs & M2 Screws<br>       |  +-----------------------------+  |<br>       |  |      LILYGO / ESP32 PCB     |  |<br>       |  +-----------------------------+  |<br>       |                                   |<br>       |      [ Rear USB-C Pass-through ]  |  <-- Cable Strain Relief<br>       +-----------------------------------+<br><!-- End of picture text -->

## **1. Dimension Extraction** 

- Measure the board using digital calipers or download the official manufacturer STEP/CAD files for the exact PCB outline, lens height, screen center point, and mounting hole coordinates. 

## **2. Modeling the Internal Chassis & Outer Shell** 

- **Faceplate Alignment:** Place precise cutouts for the camera lens and the rectangular active area of the $0.96"$ OLED display. Add a thin interior bezel to frame the screen cleanly. 

- **Microphone Port:** Include a small ($1.0 - 1.5\text{ mm}$) acoustic hole aligned over the onboard microphone sensor to ensure clear voice reception. 

- **PCB Mounting:** Add internal standoffs with pilot holes for direct screw threading or brass heat-set inserts. 

- **Rear Shell & Cable Channel:** Design a snap-fit or screw-fastened back cover with a dedicated relief slot for the USB-C power connection. 

- **Thermal & Ventilation Vents:** Include small slotted vents near the ESP32-S3 SoC module to dissipate heat during extended camera streaming. 

# **Phase 4: ESP32 Firmware Development** 

Write modular C++ firmware using **PlatformIO** in VS Code to handle peripheral tasks. 

+-------------------------------+ 

|      ESP32-S3 Initialization   | 

|  (PSRAM, Camera, I2C Display) | 

+-------------------------------+ 

| 

v 

+-------------------------------+ 

- |      Connect to Local Wi-Fi   | 

- |      Start Web Server         | 

+-------------------------------+ 

| 

+------------+------------+ 

|                         | 

v                         v 

[ GET /camera/frame ]         [ POST /face/emotion ] 

- Read OV2640 Framebuffer     - Parse JSON Payload 

- Return JPEG Stream/Bytes    - Update SSD1306 Framebuffer 

## **1. Display Controller (The Physical Face)** 

- Integrate display drivers (Adafruit_SSD1306 / U8g2) mapped to the internal I2C pins. 

- Port the procedural eye drawing logic developed in Phase 1 (converting Pygame coordinates to low-level display buffer calls). 

- Create a local display state machine updated via network commands. 

## **2. Camera Streaming Endpoint** 

- Initialize the Espressif camera driver with the internal frame buffer mapped into PSRAM. 

- Implement an HTTP REST endpoint (e.g., GET /capture) that triggers an image capture, reads the frame from the camera buffer, and returns a binary JPEG image payload. 

## **3. Network & Command Server** 

- Configure the ESP32 to connect to your local 2.4 GHz Wi-Fi network and print its assigned local IP address to the Serial Monitor. 

- Expose endpoints: 

   - POST /emotion: Accepts a JSON payload (e.g., {"state": "happy"}) and updates the OLED face. 

- GET /audio/stream _(Optional)_ : Streams raw microphone data back to the PC over a WebSocket or HTTP chunked stream. 

# **Phase 5: Hardware-Software Integration** 

Connect the physical hardware to the tested Python backend. 

+---------------------------+                           +---------------------------+ |      ESP32 Hardware       |                           |      Python PC Brain      | |                           |   HTTP GET /capture       |                           | |  [Camera Module] -------- | ------------------------> |  [Vision Ingestion]       | |                           |   JPEG Image Payload      |             |             | |                           |                           |             v             | |                           |                           |  [Ollama Vision LLM]      | 

|                           |                           |             |             | 

|                           |   HTTP POST /emotion      |             v             | 

|  [OLED Display] <-------- | <------------------------ |  [Emotion Dispatcher]     | 

|                           |   JSON State: "happy"     |                           | 

+---------------------------+                           +---------------------------+ 

1. **Re-point Vision Input:** In your Python VisionSource module, replace the OpenCV local webcam capture call with a simple HTTP requests.get("http://<ESP32-IP>/capture") request. 

2. **Re-point Facial Output:** Replace the local Pygame UI updates with a background network call sending the desired emotion state to http://<ESP32-IP>/emotion. 

3. **End-to-End Validation:** Run the master Python orchestrator on your PC. When you speak, the PC processes your voice, requests a frame from the ESP32 camera, runs the Ollama model, changes the expression on the ESP32's OLED screen, and replies with voice audio. 

# **Phase 6: Iterations & Future Expansions** 

Once the base system is fully operational, you can explore modular upgrades: 

- **Custom Power Management:** Transition from a tethered USB-C setup to an onboard LiPo battery by designing a small power regulation PCB. 

- **Extended Knowledge & Memory:** Connect the Python reasoning loop to a vector database or local document index to give the companion long-term conversational memory. 

- **Hardware Wake-Word Detection:** Offload simple wake-word listening directly onto the ESP32 using lightweight edge neural networks (such as ESP-SR), only waking the PC when the robot is called. 

