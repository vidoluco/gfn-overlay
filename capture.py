"""
macOS screen capture with two backends:
  - mss: Fast full-screen capture (~90ms, ~11 FPS on M4 Pro)
  - CoreGraphics region: Ultra-fast center-region capture (~40ms, ~25 FPS)

For gaming overlays, mss is the best default — it captures at logical
resolution (not Retina 2x), keeping the pipeline fast.
CG region mode is available for even faster capture of a specific area.
"""

from __future__ import annotations

import base64
import io
import time
from typing import Optional, Tuple

from PIL import Image

# Persistent mss instance (avoid re-creating each frame)
_mss_instance = None

# Check for CoreGraphics availability - DISABLED due to PyObjC version check on macOS 26
_HAS_COREGRAPHICS = False
# try:
#     from Quartz import (
#         CGWindowListCreateImage,
#         kCGWindowListOptionOnScreenOnly,
#         kCGNullWindowID,
#         CGImageGetWidth,
#         CGImageGetHeight,
#         CGImageGetBytesPerRow,
#         CGDataProviderCopyData,
#         CGImageGetDataProvider,
#         CGRectMake,
#         CGMainDisplayID,
#         CGDisplayPixelsWide,
#         CGDisplayPixelsHigh,
#     )
#     _HAS_COREGRAPHICS = True
# except ImportError:
#     pass


def _get_mss():
    global _mss_instance
    if _mss_instance is None:
        import mss
        _mss_instance = mss.mss()
    return _mss_instance


def _capture_mss(scale: float, jpeg_quality: int) -> Optional[str]:
    """Full-screen capture via mss. ~90ms on M4 Pro at 0.25 scale."""
    sct = _get_mss()
    monitor = sct.monitors[1]
    img = sct.grab(monitor)
    pil_img = Image.frombytes("RGB", img.size, img.rgb)

    new_w = int(pil_img.width * scale)
    new_h = int(pil_img.height * scale)
    pil_img = pil_img.resize((new_w, new_h), Image.BILINEAR)

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=jpeg_quality, optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _capture_cg_region(
    scale: float, jpeg_quality: int,
    region: Optional[Tuple[int, int, int, int]] = None
) -> Optional[str]:
    """Region capture via CoreGraphics. ~40ms for half-screen on M4 Pro.

    Args:
        region: (x, y, width, height) in screen points. Defaults to center 50%.
    """
    if not _HAS_COREGRAPHICS:
        return None

    if region is None:
        display = CGMainDisplayID()
        dw = CGDisplayPixelsWide(display)
        dh = CGDisplayPixelsHigh(display)
        # Capture center 60% of screen (good for most games)
        margin_x = int(dw * 0.2)
        margin_y = int(dh * 0.2)
        region = (margin_x, margin_y, dw - 2 * margin_x, dh - 2 * margin_y)

    rect = CGRectMake(*region)
    cg_image = CGWindowListCreateImage(
        rect, kCGWindowListOptionOnScreenOnly, kCGNullWindowID, 0
    )
    if cg_image is None:
        return None

    w = CGImageGetWidth(cg_image)
    h = CGImageGetHeight(cg_image)
    bpr = CGImageGetBytesPerRow(cg_image)
    data = CGDataProviderCopyData(CGImageGetDataProvider(cg_image))

    pil_img = Image.frombuffer("RGBA", (w, h), data, "raw", "BGRA", bpr, 1)

    new_w = int(w * scale)
    new_h = int(h * scale)
    pil_img = pil_img.resize((new_w, new_h), Image.BILINEAR)

    r, g, b, _ = pil_img.split()
    pil_img = Image.merge("RGB", (r, g, b))

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=jpeg_quality, optimize=False)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# Default backend selection
_backend = "mss"


def set_backend(name: str):
    """Set capture backend: 'mss' (default, full screen) or 'cg_region' (fast center region)."""
    global _backend
    if name not in ("mss", "cg_region"):
        raise ValueError(f"Unknown backend: {name}. Use 'mss' or 'cg_region'.")
    if name == "cg_region" and not _HAS_COREGRAPHICS:
        raise RuntimeError("CoreGraphics not available (PyObjC not installed)")
    _backend = name


def capture_frame(scale: float = 0.25, jpeg_quality: int = 35) -> Optional[str]:
    """Capture screen frame as base64 JPEG using the active backend."""
    try:
        if _backend == "cg_region":
            return _capture_cg_region(scale, jpeg_quality)
        return _capture_mss(scale, jpeg_quality)
    except Exception as e:
        print(f"[capture] {e}")
        return None


def get_backend_name() -> str:
    if _backend == "cg_region":
        return "CoreGraphics region (Apple native)"
    return "mss (full screen)"


def benchmark(iterations: int = 20, scale: float = 0.25, quality: int = 35) -> dict:
    """Benchmark capture performance."""
    times = []
    sizes = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        frame = capture_frame(scale, quality)
        elapsed = time.perf_counter() - t0
        if frame:
            times.append(elapsed)
            sizes.append(len(frame) * 3 // 4)

    if not times:
        return {"error": "No frames captured"}

    avg_ms = sum(times) / len(times) * 1000
    max_fps = 1.0 / (sum(times) / len(times)) if times else 0
    avg_kb = sum(sizes) / len(sizes) / 1024

    return {
        "backend": get_backend_name(),
        "iterations": len(times),
        "avg_ms": round(avg_ms, 1),
        "max_fps": round(max_fps, 1),
        "avg_frame_kb": round(avg_kb, 1),
    }
