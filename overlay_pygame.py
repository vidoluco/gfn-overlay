#!/usr/bin/env python3
"""
GFN Overlay — pygame version for macOS 26 compatibility
No PyObjC hotkeys - uses simple keyboard controls within the window
"""

import sys
import pygame
from pygame.locals import *

from capture import get_backend_name
from vision_provider import VisionProvider, VisionConfig, VisionResult

# ── Config ──────────────────────────────────────────────────────────────────

OVERLAY_WIDTH = 420
OVERLAY_HEIGHT = 260
OVERLAY_ALPHA = 210  # 0-255, 210 ≈ 0.82

VISION_CONFIG = VisionConfig(
    api_url="http://localhost:1234/v1/chat/completions",
    model="qwen/qwen3-8b",
    fps=8,
    frame_buffer_size=2,
    capture_scale=0.25,
    jpeg_quality=35,
    max_tokens=200,
    temperature=0.3,
    system_prompt=(
        "You are a concise gaming assistant. The user is playing a game via GeForce Now. "
        "Analyze the screenshot(s) and give a brief, actionable tip or observation about "
        "what's happening on screen. Keep it under 3 sentences. Focus on gameplay advice, "
        "enemy positions, resource status, map awareness, or any useful info you can spot. "
        "If you can identify the game, mention it once."
    ),
)

# ── Colors ──────────────────────────────────────────────────────────────────

BG_COLOR = (26, 26, 46, OVERLAY_ALPHA)
HEADER_COLOR = (22, 33, 62, OVERLAY_ALPHA)
FOOTER_COLOR = (15, 52, 96, OVERLAY_ALPHA)
TEXT_COLOR = (224, 224, 224)
TITLE_COLOR = (0, 212, 255)
STATUS_IDLE = (102, 102, 102)
STATUS_REC = (255, 68, 68)

# ── Overlay UI ──────────────────────────────────────────────────────────────

class OverlayApp:
    def __init__(self, provider: VisionProvider):
        self.provider = provider
        self.display_text = "Press 'R' to start analysis. 'Q' to quit."
        self.dragging = False
        self.drag_offset = (0, 0)

        pygame.init()

        # Create window
        self.screen = pygame.display.set_mode((OVERLAY_WIDTH, OVERLAY_HEIGHT), NOFRAME)
        pygame.display.set_caption("GFN Overlay")

        # Set window to be always on top (macOS specific)
        try:
            import subprocess
            # Get the window ID and set it to float
            subprocess.run(['osascript', '-e',
                          'tell application "System Events" to set frontmost of process "Python" to true'],
                         capture_output=True)
        except:
            pass

        # Fonts
        pygame.font.init()
        try:
            self.font_title = pygame.font.SysFont("Monaco", 14, bold=True)
            self.font_text = pygame.font.SysFont("Monaco", 12)
            self.font_small = pygame.font.SysFont("Monaco", 10)
        except:
            self.font_title = pygame.font.Font(None, 18)
            self.font_text = pygame.font.Font(None, 16)
            self.font_small = pygame.font.Font(None, 14)

        # Register callback
        self.provider.on_result(self._on_vision_result)

        self.clock = pygame.time.Clock()
        self.running = True

    def _on_vision_result(self, result: VisionResult):
        self.display_text = result.text

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
            elif event.type == KEYDOWN:
                if event.key == K_q:
                    self.running = False
                elif event.key == K_r:
                    if self.provider.is_running:
                        self.provider.stop()
                        self.display_text = "Recording paused. Press 'R' to resume."
                    else:
                        self.provider.start()
                        self.display_text = "Recording started... analyzing frames."
            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    if event.pos[1] < 28:  # Header area
                        self.dragging = True
                        win_pos = pygame.display.get_surface().get_abs_offset()
                        self.drag_offset = (event.pos[0], event.pos[1])
            elif event.type == MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False
            elif event.type == MOUSEMOTION:
                if self.dragging:
                    # Note: pygame doesn't support window dragging directly on macOS
                    # This would need platform-specific code
                    pass

    def draw(self):
        # Clear with background
        self.screen.fill(BG_COLOR[:3])

        # Header
        pygame.draw.rect(self.screen, HEADER_COLOR[:3], (0, 0, OVERLAY_WIDTH, 28))
        title_surf = self.font_title.render("◉ GFN Overlay", True, TITLE_COLOR)
        self.screen.blit(title_surf, (8, 6))

        # Status
        if self.provider.is_running:
            status_text = "● REC"
            status_color = STATUS_REC
        else:
            status_text = "IDLE"
            status_color = STATUS_IDLE

        status_surf = self.font_small.render(status_text, True, status_color)
        self.screen.blit(status_surf, (OVERLAY_WIDTH - 60, 8))

        # Content area - wrap text
        y_offset = 40
        content_width = OVERLAY_WIDTH - 30
        words = self.display_text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_surf = self.font_text.render(test_line, True, TEXT_COLOR)
            if test_surf.get_width() <= content_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))

        for line in lines[:8]:  # Max 8 lines
            text_surf = self.font_text.render(line, True, TEXT_COLOR)
            self.screen.blit(text_surf, (15, y_offset))
            y_offset += 20

        # Footer
        pygame.draw.rect(self.screen, FOOTER_COLOR[:3],
                        (0, OVERLAY_HEIGHT - 22, OVERLAY_WIDTH, 22))

        footer_text = "R: record  Q: quit"
        footer_surf = self.font_small.render(footer_text, True, STATUS_IDLE)
        self.screen.blit(footer_surf, (6, OVERLAY_HEIGHT - 18))

        if self.provider.is_running:
            stats = self.provider.stats
            stats_text = f"f:{stats['frames']} q:{stats['queries']}"
            stats_surf = self.font_small.render(stats_text, True, STATUS_IDLE)
            self.screen.blit(stats_surf, (OVERLAY_WIDTH - 80, OVERLAY_HEIGHT - 18))

        pygame.display.flip()

    def run(self):
        while self.running:
            self.handle_events()
            self.draw()
            self.clock.tick(5)  # 5 FPS for UI updates

        self.provider.stop()
        pygame.quit()

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("GFN Overlay (pygame version) starting...")
    print(f"  Capture backend: {get_backend_name()}")
    print(f"  API endpoint:    {VISION_CONFIG.api_url}")
    print(f"  Model:           {VISION_CONFIG.model}")
    print(f"  Target FPS:      {VISION_CONFIG.fps}")
    print()
    print("  Controls (in overlay window):")
    print("    R → Start/stop recording")
    print("    Q → Quit")
    print()

    provider = VisionProvider(VISION_CONFIG)
    overlay = OverlayApp(provider)
    overlay.run()

    print("GFN Overlay stopped.")

if __name__ == "__main__":
    main()
