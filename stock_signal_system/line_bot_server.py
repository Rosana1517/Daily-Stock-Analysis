from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class LineWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        secret = os.getenv("LINE_CHANNEL_SECRET", "")
        signature = self.headers.get("X-Line-Signature", "")
        if not _verify_signature(body, secret, signature):
            self.send_response(401)
            self.end_headers()
            return

        payload = json.loads(body.decode("utf-8"))
        user_ids = _extract_user_ids(payload)
        if user_ids:
            print("LINE user/group IDs:", ", ".join(user_ids))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def run(host: str = "0.0.0.0", port: int = 8080) -> None:
    server = HTTPServer((host, port), LineWebhookHandler)
    print(f"LINE webhook server listening on http://{host}:{port}")
    server.serve_forever()


def _verify_signature(body: bytes, secret: str, signature: str) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _extract_user_ids(payload: dict) -> list[str]:
    ids = []
    for event in payload.get("events", []):
        source = event.get("source", {})
        for key in ("userId", "groupId", "roomId"):
            if source.get(key):
                ids.append(source[key])
    return ids


if __name__ == "__main__":
    run(port=int(os.getenv("PORT", "8080")))

