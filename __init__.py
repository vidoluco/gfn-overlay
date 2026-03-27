"""
GFN Overlay — Modular AI gaming assistant for macOS.

Import the VisionProvider for integration with other projects:

    from gfn_overlay.vision_provider import VisionProvider, VisionConfig

    provider = VisionProvider(VisionConfig(fps=4))
    provider.start()
    result = provider.latest_result  # VisionResult or None
    provider.stop()
"""

from .vision_provider import VisionProvider, VisionConfig, VisionResult
from .capture import capture_frame, get_backend_name, set_backend

__all__ = [
    "VisionProvider",
    "VisionConfig",
    "VisionResult",
    "capture_frame",
    "get_backend_name",
    "set_backend",
]
