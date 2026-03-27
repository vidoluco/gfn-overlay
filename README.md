# GFN Overlay

A minimal AI gaming assistant overlay for macOS. Captures screen frames and sends them to a local vision LLM (via [LM Studio](https://lmstudio.ai/)) for real-time gameplay tips.

> **Note:** Currently macOS-only (tested on Apple Silicon / M4 Pro). Contributions to add Linux and Windows support are very welcome!

![Python](https://img.shields.io/badge/python-3.9+-blue) ![macOS](https://img.shields.io/badge/platform-macOS-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

## What It Does

- Captures your screen at configurable FPS using `mss` or Apple CoreGraphics
- Sends frames to a local vision model via LM Studio's OpenAI-compatible API
- Displays concise gameplay tips in a small, always-on-top translucent overlay
- Designed for cloud gaming (GeForce NOW, Xbox Cloud Gaming, etc.) but works with any game

## Controls

| Shortcut | Action |
|----------|--------|
| `Cmd+Shift+G` | Toggle overlay visibility |
| `Cmd+Shift+R` | Start/stop recording & analysis |
| `Cmd+Shift+Q` | Quit |

## Setup

### Prerequisites

- **macOS** (Apple Silicon recommended)
- **Python 3.9+**
- **[LM Studio](https://lmstudio.ai/)** with a vision model loaded and the local API server running on port 1234

### Install

```bash
git clone https://github.com/vidoluco/gfn-overlay.git
cd gfn-overlay
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
python3 overlay.py
```

Or use the launcher script:

```bash
chmod +x run.sh
./run.sh
```

## Architecture

| File | Purpose |
|------|---------|
| `overlay.py` | Main entry point, Tkinter overlay UI, hotkey handling |
| `capture.py` | Screen capture with two backends: `mss` (default) and CoreGraphics region |
| `vision_provider.py` | Thread-safe vision LLM client, captures frames and queries the model |
| `mock_server.py` | Mock LM Studio server for testing without a real model |
| `simulate.py` | Simulation/testing utilities |

## Configuration

Edit the `VISION_CONFIG` in `overlay.py`:

```python
VISION_CONFIG = VisionConfig(
    api_url="http://localhost:1234/v1/chat/completions",
    fps=8,                # frames analyzed per second
    frame_buffer_size=2,  # frames sent per request
    capture_scale=0.25,   # downscale factor (lower = faster)
    jpeg_quality=35,      # JPEG quality (lower = smaller payload)
    max_tokens=200,
    temperature=0.3,
)
```

### Capture Backends

- **mss** (default): Full-screen capture, ~90ms per frame on M4 Pro
- **CoreGraphics region**: Center-region capture, ~40ms per frame (requires `pyobjc-framework-Quartz`)

## Contributing

This project is in early stages and there's a lot of room to improve it:

- **Linux/Windows support** -- the capture and overlay layers need platform-specific backends
- **Better vision models** -- test with different LM Studio models and share what works
- **Performance tuning** -- optimize for different hardware
- **Game-specific prompts** -- contribute system prompts tailored to specific games
- **UI improvements** -- themes, resizing, positioning options

Feel free to open an issue to discuss ideas or submit a pull request. All contributions welcome!

## License

MIT
