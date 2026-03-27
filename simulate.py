#!/usr/bin/env python3
"""
GFN Overlay Simulation — Full end-to-end test with performance metrics.
Starts mock server, runs capture+API loop, measures everything.

Usage:
    python simulate.py [--duration 15] [--fps 6] [--no-ui]
"""

import argparse
import json
import multiprocessing
import os
import resource
import sys
import threading
import time

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

from capture import capture_frame, benchmark, get_backend_name
from mock_server import run_server


def get_memory_mb() -> float:
    """Current process RSS in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def run_mock_server_process(port: int, latency: float):
    """Run mock server in a separate process."""
    run_server(port=port, latency=latency)


def run_simulation(duration: int, fps: int, show_ui: bool, port: int):
    """Run the full capture → API → display loop with metrics."""
    import requests
    from collections import deque

    LM_STUDIO_URL = f"http://127.0.0.1:{port}/v1/chat/completions"
    SYSTEM_PROMPT = (
        "You are a concise gaming assistant. The user is playing a game via GeForce Now. "
        "Analyze the screenshot(s) and give a brief, actionable tip. Keep it under 3 sentences."
    )

    interval = 1.0 / fps
    frame_buffer = deque(maxlen=2)

    # Metrics
    capture_times = []
    api_times = []
    api_responses = []
    api_errors = 0
    frames_captured = 0
    api_calls = 0
    total_payload_bytes = 0

    print(f"\n{'='*60}")
    print(f"  GFN OVERLAY SIMULATION")
    print(f"{'='*60}")
    print(f"  Capture backend : {get_backend_name()}")
    print(f"  Target FPS      : {fps}")
    print(f"  Duration        : {duration}s")
    print(f"  API endpoint    : {LM_STUDIO_URL}")
    print(f"  Memory at start : {get_memory_mb():.1f} MB")
    print(f"{'='*60}\n")

    # Wait for mock server
    print("[sim] Waiting for mock server...", end=" ", flush=True)
    for _ in range(20):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/v1/models", timeout=1)
            if r.status_code == 200:
                print("OK")
                break
        except Exception:
            time.sleep(0.25)
    else:
        print("FAILED — mock server not reachable")
        return

    # Optional: run capture benchmark first
    print("\n[bench] Running capture benchmark (20 iterations)...")
    bench = benchmark(iterations=20)
    for k, v in bench.items():
        print(f"  {k}: {v}")

    print(f"\n[sim] Starting {duration}s simulation loop at {fps} FPS...\n")

    start = time.time()
    last_api_call = 0
    api_in_flight = False
    lock = threading.Lock()

    def _fire_api(frames_to_send, call_num):
        """Run API call in background thread so capture loop stays fast."""
        nonlocal api_in_flight, api_errors, total_payload_bytes

        content = []
        payload_bytes = 0
        for b64 in frames_to_send:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
            payload_bytes += len(b64) * 3 // 4
        content.append({"type": "text", "text": "What's happening? Quick tip."})

        payload = {
            "model": "default",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content}
            ],
            "max_tokens": 200,
            "temperature": 0.3,
            "stream": False
        }

        t0 = time.perf_counter()
        try:
            resp = requests.post(LM_STUDIO_URL, json=payload, timeout=10)
            api_ms = (time.perf_counter() - t0) * 1000
            with lock:
                api_times.append(api_ms)
                total_payload_bytes += payload_bytes

            if resp.status_code == 200:
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
                with lock:
                    api_responses.append(reply)
                elapsed_s = time.time() - start
                print(f"  [{elapsed_s:5.1f}s] API #{call_num} ({api_ms:.0f}ms): {reply[:80]}...")
            else:
                with lock:
                    api_errors += 1
                print(f"  [!] API error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            api_ms = (time.perf_counter() - t0) * 1000
            with lock:
                api_errors += 1
                api_times.append(api_ms)
            print(f"  [!] API exception: {e}")
        finally:
            api_in_flight = False

    while time.time() - start < duration:
        loop_start = time.perf_counter()

        # 1. Capture frame
        t0 = time.perf_counter()
        frame = capture_frame(scale=0.35, jpeg_quality=40)
        capture_ms = (time.perf_counter() - t0) * 1000

        if frame:
            frames_captured += 1
            capture_times.append(capture_ms)
            frame_buffer.append(frame)

        # 2. Fire API in background when buffer is full and no call in flight
        now = time.time()
        if len(frame_buffer) >= 2 and (now - last_api_call) >= 0.5 and not api_in_flight:
            last_api_call = now
            api_calls += 1
            api_in_flight = True

            frames_snapshot = list(frame_buffer)
            frame_buffer.clear()

            t = threading.Thread(target=_fire_api, args=(frames_snapshot, api_calls), daemon=True)
            t.start()

        # 3. Sleep to maintain FPS
        elapsed = time.perf_counter() - loop_start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Wait for any in-flight API call
    time.sleep(0.5)

    # Print results
    total_time = time.time() - start
    print(f"\n{'='*60}")
    print(f"  SIMULATION RESULTS")
    print(f"{'='*60}")
    print(f"  Total time      : {total_time:.1f}s")
    print(f"  Frames captured : {frames_captured}")
    print(f"  Effective FPS   : {frames_captured / total_time:.1f}")
    print(f"  Target FPS      : {fps}")
    print()

    if capture_times:
        avg_cap = sum(capture_times) / len(capture_times)
        max_cap = max(capture_times)
        min_cap = min(capture_times)
        print(f"  Capture avg     : {avg_cap:.1f} ms")
        print(f"  Capture min/max : {min_cap:.1f} / {max_cap:.1f} ms")
        print(f"  Capture max FPS : {1000 / avg_cap:.1f}")
    print()

    if api_times:
        avg_api = sum(api_times) / len(api_times)
        print(f"  API calls       : {api_calls}")
        print(f"  API errors      : {api_errors}")
        print(f"  API avg latency : {avg_api:.0f} ms")
        print(f"  API min/max     : {min(api_times):.0f} / {max(api_times):.0f} ms")
        print(f"  Payload total   : {total_payload_bytes / 1024:.0f} KB")
        print(f"  Payload avg/call: {total_payload_bytes / api_calls / 1024:.0f} KB")
    print()

    print(f"  Memory peak     : {get_memory_mb():.1f} MB")
    print(f"  Backend         : {get_backend_name()}")
    print(f"{'='*60}")

    # Verdict
    effective_fps = frames_captured / total_time
    if effective_fps >= fps * 0.9 and api_errors == 0:
        print(f"\n  PASS — hitting target FPS, zero API errors\n")
    elif effective_fps >= fps * 0.7:
        print(f"\n  WARN — slightly below target FPS ({effective_fps:.1f}/{fps})\n")
    else:
        print(f"\n  FAIL — FPS too low ({effective_fps:.1f}/{fps}), check capture backend\n")


def main():
    parser = argparse.ArgumentParser(description="GFN Overlay Simulation")
    parser.add_argument("--duration", type=int, default=15, help="Simulation duration in seconds")
    parser.add_argument("--fps", type=int, default=6, help="Target capture FPS")
    parser.add_argument("--port", type=int, default=11234, help="Mock server port (avoids conflict with real LM Studio)")
    parser.add_argument("--latency", type=float, default=0.3, help="Mock server simulated latency")
    parser.add_argument("--no-ui", action="store_true", help="Skip UI overlay (headless test)")
    args = parser.parse_args()

    # Start mock server in separate process
    server_proc = multiprocessing.Process(
        target=run_mock_server_process,
        args=(args.port, args.latency),
        daemon=True
    )
    server_proc.start()
    time.sleep(0.5)

    try:
        run_simulation(
            duration=args.duration,
            fps=args.fps,
            show_ui=not args.no_ui,
            port=args.port
        )
    finally:
        server_proc.terminate()
        server_proc.join(timeout=2)
        print("[sim] Mock server stopped.")


if __name__ == "__main__":
    main()
