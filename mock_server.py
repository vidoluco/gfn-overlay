#!/usr/bin/env python3
"""
Mock LM Studio server — simulates the OpenAI-compatible vision API.
Returns realistic gaming tips without needing a real model loaded.
Validates request format to ensure correct API integration.

Usage:
    python mock_server.py [--port 1234] [--latency 0.3]
"""

import argparse
import json
import random
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_RESPONSES = [
    "I can see you're in a combat encounter. Watch your health bar in the top-left — it's getting low. Consider using a healing item before engaging the next enemy.",
    "You're approaching a choke point on the map. There could be enemies flanking from the right side. Stay near cover and check your minimap.",
    "Your ammo count is running low. I'd recommend switching to your secondary weapon or looking for an ammo pickup nearby.",
    "The objective marker is pointing northeast. You seem to be heading slightly off course — adjust your path to the right.",
    "I notice an enemy indicator on your minimap at your 7 o'clock. You might want to turn around and deal with it before it flanks you.",
    "Good positioning! You have high ground advantage here. Use this spot to scout ahead before moving to the next area.",
    "Your shield/armor is depleted. Find cover and let it regenerate before pushing forward into the open area ahead.",
    "There's a collectible or item drop visible on the right side of the screen. Might be worth picking up before continuing.",
    "Multiple enemies ahead — I count at least 3 health bars visible. Consider a more tactical approach or use your special ability.",
    "The safe zone or objective timer is counting down. You have about a minute to reach the next checkpoint — prioritize movement over combat.",
]

MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {
            "id": "mock-vision-model",
            "object": "model",
            "created": 1700000000,
            "owned_by": "mock-server",
        }
    ]
}


class MockLMStudioHandler(BaseHTTPRequestHandler):
    latency = 0.3  # simulated inference time

    def log_message(self, format, *args):
        # Compact logging
        print(f"[mock] {args[0]}")

    def do_GET(self):
        if "/models" in self.path:
            self._respond(200, MODELS_RESPONSE)
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if "/v1/chat/completions" not in self.path:
            self._respond(404, {"error": "not found"})
            return

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return

        # Validate request format
        errors = self._validate_request(payload)
        if errors:
            print(f"[mock] VALIDATION ERRORS: {errors}")
            self._respond(400, {"error": {"message": f"Invalid request: {'; '.join(errors)}"}})
            return

        # Count images in request
        image_count = 0
        messages = payload.get("messages", [])
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "image_url":
                        image_count += 1

        print(f"[mock] model={payload.get('model')} images={image_count} max_tokens={payload.get('max_tokens')}")

        # Simulate inference latency
        time.sleep(self.latency)

        response_text = random.choice(MOCK_RESPONSES)

        self._respond(200, {
            "id": f"mock-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", "mock-vision-model"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100 + image_count * 500,
                "completion_tokens": len(response_text.split()),
                "total_tokens": 100 + image_count * 500 + len(response_text.split())
            }
        })

    def _validate_request(self, payload: dict) -> list[str]:
        """Validate the request matches LM Studio's expected format."""
        errors = []

        if "messages" not in payload:
            errors.append("missing 'messages' field")
            return errors

        messages = payload["messages"]
        if not isinstance(messages, list) or len(messages) == 0:
            errors.append("'messages' must be a non-empty array")
            return errors

        # Check system message
        if messages[0].get("role") != "system":
            errors.append("first message should have role 'system'")

        # Check for user message with vision content
        has_user_msg = False
        has_image = False
        for msg in messages:
            if msg.get("role") == "user":
                has_user_msg = True
                content = msg.get("content", "")
                if isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            errors.append("content array items must be objects")
                            continue
                        item_type = item.get("type")
                        if item_type == "image_url":
                            has_image = True
                            url = item.get("image_url", {}).get("url", "")
                            if not url.startswith("data:image/"):
                                errors.append(f"image_url must start with 'data:image/', got: {url[:30]}...")
                        elif item_type == "text":
                            if not item.get("text"):
                                errors.append("text content item has empty 'text'")
                        elif item_type is not None:
                            errors.append(f"unknown content type: {item_type}")

        if not has_user_msg:
            errors.append("no user message found")

        # Check optional fields
        if "model" not in payload:
            errors.append("missing 'model' field (LM Studio requires it)")

        if "max_tokens" in payload and not isinstance(payload["max_tokens"], int):
            errors.append("'max_tokens' must be an integer")

        if "temperature" in payload:
            t = payload["temperature"]
            if not isinstance(t, (int, float)) or t < 0 or t > 2:
                errors.append(f"'temperature' must be 0-2, got {t}")

        return errors

    def _respond(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


def run_server(port: int = 1234, latency: float = 0.3):
    MockLMStudioHandler.latency = latency
    server = HTTPServer(("127.0.0.1", port), MockLMStudioHandler)
    print(f"Mock LM Studio server running on http://127.0.0.1:{port}")
    print(f"  Simulated latency: {latency}s")
    print(f"  Endpoints: GET /v1/models, POST /v1/chat/completions")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMock server stopped.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock LM Studio server")
    parser.add_argument("--port", type=int, default=1234)
    parser.add_argument("--latency", type=float, default=0.3, help="Simulated inference latency in seconds")
    args = parser.parse_args()
    run_server(args.port, args.latency)
