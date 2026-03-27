#!/usr/bin/env python3
"""
GFN Overlay — Minimal AI gaming assistant overlay for macOS.
Uses Apple CoreGraphics for fast capture on M4 Pro.
Sends frames to local LM Studio vision model.

Controls:
  Cmd+Shift+G  → Toggle overlay visibility
  Cmd+Shift+R  → Start/stop recording & analysis
  Cmd+Shift+Q  → Quit
"""

import sys
import os
import threading
import tkinter as tk

# Disabled due to PyObjC compatibility issue on macOS 26 alpha
# from pynput import keyboard

from capture import get_backend_name
from vision_provider import VisionProvider, VisionConfig, VisionResult

# ── Config ──────────────────────────────────────────────────────────────────

OVERLAY_WIDTH = 420
OVERLAY_HEIGHT = 260
OVERLAY_ALPHA = 0.82

# M4 Pro optimized defaults
VISION_CONFIG = VisionConfig(
    api_url="http://localhost:1234/v1/chat/completions",
    model="qwen/qwen3-8b",
    fps=8,                # M4 Pro handles 8+ FPS with mss backend
    frame_buffer_size=2,
    capture_scale=0.25,   # 25% — fast capture, small payloads (~48 KB)
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


# ── Overlay UI ──────────────────────────────────────────────────────────────

class OverlayApp:
    def __init__(self, provider: VisionProvider):
        self.provider = provider
        self.visible = False
        self.display_text = "Press Cmd+Shift+R to start analysis."

        self.root = tk.Tk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", OVERLAY_ALPHA)

        screen_w = self.root.winfo_screenwidth()
        x = screen_w - OVERLAY_WIDTH - 20
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+{x}+40")
        self.root.configure(bg="#1a1a2e")

        # Header (draggable)
        header = tk.Frame(self.root, bg="#16213e", height=28)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_lbl = tk.Label(
            header, text="◉ GFN Overlay", font=("SF Mono", 11, "bold"),
            fg="#00d4ff", bg="#16213e", anchor="w", padx=8
        )
        title_lbl.pack(side=tk.LEFT)

        self.status_lbl = tk.Label(
            header, text="IDLE", font=("SF Mono", 9),
            fg="#666", bg="#16213e", padx=8
        )
        self.status_lbl.pack(side=tk.RIGHT)

        for w in (header, title_lbl):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # Content
        content = tk.Frame(self.root, bg="#1a1a2e", padx=10, pady=8)
        content.pack(fill=tk.BOTH, expand=True)

        self.text_lbl = tk.Label(
            content, text=self.display_text,
            font=("SF Mono", 12), fg="#e0e0e0", bg="#1a1a2e",
            wraplength=OVERLAY_WIDTH - 30, justify=tk.LEFT, anchor="nw"
        )
        self.text_lbl.pack(fill=tk.BOTH, expand=True)

        # Footer
        footer = tk.Frame(self.root, bg="#0f3460", height=22)
        footer.pack(fill=tk.X)
        footer.pack_propagate(False)

        tk.Label(
            footer, text="⌘⇧G hide  ⌘⇧R rec  ⌘⇧Q quit",
            font=("SF Mono", 9), fg="#555", bg="#0f3460", padx=6
        ).pack(side=tk.LEFT)

        self.fps_lbl = tk.Label(
            footer, text="", font=("SF Mono", 9), fg="#555", bg="#0f3460", padx=6
        )
        self.fps_lbl.pack(side=tk.RIGHT)

        # Register callback for new vision results
        self.provider.on_result(self._on_vision_result)

        self.root.withdraw()
        self._poll_ui()

    def _on_vision_result(self, result: VisionResult):
        self.display_text = result.text

    def _poll_ui(self):
        self.text_lbl.configure(text=self.display_text)

        if self.provider.is_running:
            stats = self.provider.stats
            self.status_lbl.configure(text="● REC", fg="#ff4444")
            self.fps_lbl.configure(text=f"f:{stats['frames']} q:{stats['queries']}")
        else:
            self.status_lbl.configure(text="IDLE", fg="#666")
            self.fps_lbl.configure(text="")

        self.root.after(200, self._poll_ui)

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def toggle_visibility(self):
        if self.visible:
            self.root.withdraw()
            self.visible = False
        else:
            self.root.deiconify()
            self.visible = True

    def show(self):
        self.root.deiconify()
        self.visible = True

    def quit_app(self):
        self.provider.stop()
        self.root.quit()

    def run(self):
        self.root.mainloop()


# ── Hotkeys ─────────────────────────────────────────────────────────────────

def setup_hotkeys(overlay: OverlayApp):
    pressed = set()
    TOGGLE = {keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char("g")}
    RECORD = {keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char("r")}
    QUIT = {keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char("q")}

    def on_press(key):
        pressed.add(key)
        norm = set()
        for k in pressed:
            if k in (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift):
                norm.add(keyboard.Key.shift)
            elif k in (keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd):
                norm.add(keyboard.Key.cmd)
            elif hasattr(k, "char") and k.char:
                norm.add(keyboard.KeyCode.from_char(k.char.lower()))
            else:
                norm.add(k)

        if TOGGLE.issubset(norm):
            overlay.root.after(0, overlay.toggle_visibility)
        elif RECORD.issubset(norm):
            if overlay.provider.is_running:
                overlay.provider.stop()
                overlay.display_text = "Recording paused."
            else:
                overlay.provider.start()
                overlay.display_text = "Recording started... analyzing frames."
                overlay.root.after(0, overlay.show)
        elif QUIT.issubset(norm):
            overlay.root.after(0, overlay.quit_app)

    def on_release(key):
        pressed.discard(key)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("GFN Overlay starting...")
    print(f"  Capture backend: {get_backend_name()}")
    print(f"  API endpoint:    {VISION_CONFIG.api_url}")
    print(f"  Target FPS:      {VISION_CONFIG.fps}")
    print("  Cmd+Shift+G → Toggle overlay")
    print("  Cmd+Shift+R → Start/stop recording")
    print("  Cmd+Shift+Q → Quit")
    print()

    provider = VisionProvider(VISION_CONFIG)
    overlay = OverlayApp(provider)

    # TODO: Hotkeys disabled due to PyObjC version check issue on macOS 26 alpha
    # setup_hotkeys(overlay)
    print("  NOTE: Hotkeys disabled - use window controls")
    print("  Click 'Start' button in overlay to begin recording")

    overlay.show()  # Show overlay immediately
    overlay.run()

    print("GFN Overlay stopped.")


if __name__ == "__main__":
    main()
