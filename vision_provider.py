"""
Shared vision provider interface — pluggable module for both
gfn-overlay and xbox-llm-controller.

This module provides screen analysis that either project can import:
  - gfn-overlay uses it for the overlay display
  - xbox-llm-controller can use it to feed visual context to the LLM
"""

from __future__ import annotations

import base64
import io
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

import requests
from PIL import Image

from capture import capture_frame, get_backend_name


@dataclass
class VisionConfig:
    api_url: str = "http://localhost:1234/v1/chat/completions"
    model: str = "default"
    fps: int = 4
    frame_buffer_size: int = 2
    capture_scale: float = 0.35
    jpeg_quality: int = 40
    max_tokens: int = 200
    temperature: float = 0.3
    timeout: int = 30
    system_prompt: str = (
        "You are a concise gaming assistant. Analyze the screenshot(s) and give "
        "a brief, actionable tip or observation. Keep it under 3 sentences."
    )


@dataclass
class VisionResult:
    text: str
    timestamp: float
    latency_ms: float
    frame_count: int


class VisionProvider:
    """
    Captures screen frames and sends them to a vision LLM.
    Thread-safe, can be shared across modules.

    Usage:
        provider = VisionProvider(VisionConfig())
        provider.start()
        # ... later ...
        result = provider.latest_result  # most recent analysis
        provider.stop()

    Integration with xbox-llm-controller:
        from gfn_overlay.vision_provider import VisionProvider, VisionConfig
        provider = VisionProvider(VisionConfig(fps=2))
        provider.start()
        # In your LLM query, add visual context:
        visual_context = provider.latest_result.text if provider.latest_result else ""
        llm.query(controller_state, game_context=visual_context)
    """

    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_buffer: deque = deque(maxlen=self.config.frame_buffer_size)
        self._latest_result: Optional[VisionResult] = None
        self._on_result_callbacks: list = []
        self._stats = {"frames": 0, "queries": 0, "errors": 0}

    @property
    def latest_result(self) -> Optional[VisionResult]:
        with self._lock:
            return self._latest_result

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def on_result(self, callback):
        """Register a callback for new results: callback(VisionResult)."""
        self._on_result_callbacks.append(callback)

    def start(self):
        """Start the capture & analysis loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def query_once(self, frames: Optional[List[str]] = None) -> Optional[VisionResult]:
        """Run a single capture+query synchronously. Useful for one-off analysis."""
        if frames is None:
            frame = capture_frame(self.config.capture_scale, self.config.jpeg_quality)
            if not frame:
                return None
            frames = [frame]

        text, latency = self._call_api(frames)
        result = VisionResult(
            text=text,
            timestamp=time.time(),
            latency_ms=latency,
            frame_count=len(frames)
        )
        with self._lock:
            self._latest_result = result
        return result

    def _loop(self):
        interval = 1.0 / self.config.fps

        while self._running:
            t0 = time.perf_counter()

            frame = capture_frame(self.config.capture_scale, self.config.jpeg_quality)
            if frame:
                self._frame_buffer.append(frame)
                with self._lock:
                    self._stats["frames"] += 1

            if len(self._frame_buffer) >= self.config.frame_buffer_size:
                frames = list(self._frame_buffer)
                self._frame_buffer.clear()

                text, latency = self._call_api(frames)
                result = VisionResult(
                    text=text,
                    timestamp=time.time(),
                    latency_ms=latency,
                    frame_count=len(frames)
                )

                with self._lock:
                    self._latest_result = result
                    self._stats["queries"] += 1

                for cb in self._on_result_callbacks:
                    try:
                        cb(result)
                    except Exception:
                        pass

            elapsed = time.perf_counter() - t0
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _call_api(self, frames: List[str]) -> Tuple[str, float]:
        """Call the vision API. Returns (text, latency_ms)."""
        content = []
        for b64 in frames:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        content.append({
            "type": "text",
            "text": "What's happening on screen? Give a quick gameplay tip."
        })

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self.config.system_prompt},
                {"role": "user", "content": content}
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": False
        }

        t0 = time.perf_counter()
        try:
            resp = requests.post(
                self.config.api_url, json=payload, timeout=self.config.timeout
            )
            latency = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip(), latency
        except requests.ConnectionError:
            latency = (time.perf_counter() - t0) * 1000
            with self._lock:
                self._stats["errors"] += 1
            return "[Error] Cannot reach LM Studio. Is it running?", latency
        except requests.Timeout:
            latency = (time.perf_counter() - t0) * 1000
            with self._lock:
                self._stats["errors"] += 1
            return "[Error] LM Studio timed out.", latency
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            with self._lock:
                self._stats["errors"] += 1
            return f"[Error] {e}", latency
