"""Local fake AI servers for tests. They imitate the documented response and error shapes of Gemini's
generateContent and of OpenAI-style /chat/completions, so provider HTTP/error handling is exercised for real
(without network access or API keys)."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeAI:
    """mode: ok | quota_daily | quota_minute | server | auth | blocked | empty | slow | bad_key_400"""

    def __init__(self):
        self.mode = "ok"
        self.requests: list[dict] = []
        self.text = "The answer is 15 N."
        self.route_json = '{"tool_id": null}'
        handler = self._make_handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _make_handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj, headers=None):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass                                  # client gave up (timeout test); not an error

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                m = outer.mode
                gemini = ":generateContent" in self.path
                if m == "slow":
                    time.sleep(1.5)
                if m == "quota_daily":
                    return self._send(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                        "message": "You exceeded your current quota. Quota exceeded for metric: generate_content_free_tier_requests, limit: 1000 per day",
                        "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}})
                if m == "quota_minute":
                    return self._send(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                        "message": "You exceeded your current quota.",
                        "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "34s"}]}})
                if m == "server":
                    return self._send(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "The model is overloaded."}})
                if m == "auth":
                    return self._send(403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "API key not valid."}})
                if m == "bad_key_400":
                    return self._send(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key."}})
                if gemini:
                    if m == "blocked":
                        return self._send(200, {"promptFeedback": {"blockReason": "SAFETY"}})
                    if m == "empty":
                        return self._send(200, {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]})
                    sys_text = ((body.get("systemInstruction") or {}).get("parts") or [{}])[0].get("text", "")
                    reply = outer.route_json if "routing component" in sys_text else outer.text
                    return self._send(200, {"candidates": [{"content": {"role": "model", "parts": [{"text": reply}]}, "finishReason": "STOP"}],
                                            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7, "totalTokenCount": 18}})
                # OpenAI-style
                if m == "empty":
                    return self._send(200, {"choices": [{"message": {"content": ""}}]})
                return self._send(200, {"choices": [{"message": {"role": "assistant", "content": outer.text}}], "usage": {"prompt_tokens": 9, "completion_tokens": 5}})

        return H
