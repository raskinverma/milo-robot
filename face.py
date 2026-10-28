import pygame
import sys
import time
import math

# OLED Target Resolution
SCREEN_WIDTH  = 128
SCREEN_HEIGHT = 64
SCALE_FACTOR  = 4   # Display window: 512 x 256

# Colors (Monochrome OLED simulation)
BLACK = (0,   0,   0)
CYAN  = (87, 224, 199)   # kek.html --oled color: DCE7F5 on dark → teal glow


class VirtualFace:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Milo — Virtual Face")

        self.window = pygame.display.set_mode(
            (SCREEN_WIDTH * SCALE_FACTOR, SCREEN_HEIGHT * SCALE_FACTOR)
        )
        self.canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock  = pygame.time.Clock()

        self.current_emotion   = "NEUTRAL"
        self.blink_counter     = 0
        self.thinking_offset   = 0.0
        self.thinking_direction = 1
        self.search_offset     = 0.0
        self.search_direction  = 1
        self.talking_phase     = 0.0   # drives mouth-like vertical pulse
        self.z_phase           = 0.0   # SLEEP zz animation

    def set_emotion(self, emotion: str):
        self.current_emotion = emotion.upper()

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _eyes(self, lx, rx, y, w, h, radius=6):
        """Draw two rectangular eyes at specified positions."""
        pygame.draw.rect(self.canvas, CYAN, (lx, y, w, h), border_radius=radius)
        pygame.draw.rect(self.canvas, CYAN, (rx, y, w, h), border_radius=radius)

    # ── Expressions ──────────────────────────────────────────────────────────

    def _draw_neutral(self):
        """Standard blink cycle — kek.html 'neutral'."""
        self.blink_counter += 1
        h = 2 if 115 <= (self.blink_counter % 150) <= 120 else 28
        self._eyes(28, 76, (SCREEN_HEIGHT - h) // 2, 24, h)

    def _draw_listening(self):
        """Enlarged pulsing eyes — kek.html 'listening'."""
        pulse = abs(math.sin(time.time() * 4)) * 4
        w, h  = int(26 + pulse), int(30 + pulse)
        y     = (SCREEN_HEIGHT - h) // 2
        self._eyes(int(27 - pulse/2), int(75 - pulse/2), y, w, h, radius=8)

    def _draw_thinking(self):
        """Narrowed eyes shifting side-to-side — kek.html 'thinking' (asymmetric)."""
        self.thinking_offset += self.thinking_direction * 0.6
        if abs(self.thinking_offset) > 8:
            self.thinking_direction *= -1
        off = int(self.thinking_offset)
        # Asymmetric: left eye higher than right (kek.html style)
        pygame.draw.rect(self.canvas, CYAN, (32 + off, 20, 20, 14), border_radius=4)
        pygame.draw.rect(self.canvas, CYAN, (78 + off, 24, 20, 14), border_radius=4)

    def _draw_happy(self):
        """Dome / arc eyes — kek.html 'happy'."""
        for x in [26, 76]:
            rect = pygame.Rect(x, 18, 26, 26)
            pygame.draw.arc(self.canvas, CYAN, rect, 0.15, 2.99, width=5)

    def _draw_searching(self):
        """Eyes dart left-right — kek.html 'searching'."""
        self.search_offset += self.search_direction * 1.4
        if abs(self.search_offset) > 14:
            self.search_direction *= -1
        off = int(self.search_offset)
        self._eyes(28 + off, 76 + off, (SCREEN_HEIGHT - 24) // 2, 20, 24)

    def _draw_sleep(self):
        """Thin bar eyes + floating 'z z' — kek.html 'sleep'."""
        self._eyes(28, 76, (SCREEN_HEIGHT - 4) // 2, 24, 4, radius=2)
        # Floating z
        self.z_phase += 0.04
        y_drift = int(math.sin(self.z_phase) * 3)
        alpha   = int((math.sin(self.z_phase) + 1) / 2 * 200 + 55)
        font    = pygame.font.SysFont("monospace", 7)
        zsurf   = font.render("z z", True, CYAN)
        zsurf.set_alpha(alpha)
        self.canvas.blit(zsurf, (84, 10 + y_drift))

    def _draw_talking(self):
        """Eyes vertically pulse in sync with speech — kek.html 'talking'."""
        self.talking_phase += 0.25
        pulse = abs(math.sin(self.talking_phase)) * 12
        w, h  = 24, int(16 + pulse)
        y     = (SCREEN_HEIGHT - h) // 2
        self._eyes(28, 76, y, w, h)

    def _draw_sad(self):
        """Downward arc eyes — opposite of happy."""
        for x in [26, 76]:
            rect = pygame.Rect(x, 22, 26, 26)
            pygame.draw.arc(self.canvas, CYAN, rect, 3.3, 6.1, width=5)

    def _draw_surprised(self):
        """Large wide circular eyes."""
        for cx in [40, 88]:
            pygame.draw.circle(self.canvas, CYAN, (cx, SCREEN_HEIGHT // 2), 14, width=4)

    # ── Render loop ───────────────────────────────────────────────────────────

    def render(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        self.canvas.fill(BLACK)

        draw_fn = {
            "NEUTRAL":   self._draw_neutral,
            "LISTENING": self._draw_listening,
            "THINKING":  self._draw_thinking,
            "HAPPY":     self._draw_happy,
            "SEARCHING": self._draw_searching,
            "SLEEP":     self._draw_sleep,
            "TALKING":   self._draw_talking,
            "SAD":       self._draw_sad,
            "SURPRISED": self._draw_surprised,
        }.get(self.current_emotion, self._draw_neutral)

        draw_fn()

        scaled = pygame.transform.scale(
            self.canvas,
            (SCREEN_WIDTH * SCALE_FACTOR, SCREEN_HEIGHT * SCALE_FACTOR)
        )
        self.window.blit(scaled, (0, 0))
        pygame.display.flip()
        self.clock.tick(30)


# ── Standalone demo ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    face = VirtualFace()
    emotions = ["NEUTRAL", "LISTENING", "THINKING", "HAPPY",
                "SEARCHING", "SLEEP", "TALKING", "SAD", "SURPRISED"]
    idx = 0
    last_switch = time.time()
    print(f"Demo: cycling all {len(emotions)} expressions every 2.5s")
    print("Emotions:", emotions)

    while True:
        if time.time() - last_switch > 2.5:
            idx = (idx + 1) % len(emotions)
            face.set_emotion(emotions[idx])
            print(f"→ {emotions[idx]}")
            last_switch = time.time()
        face.render()
