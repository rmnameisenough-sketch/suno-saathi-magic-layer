"""Zero-install development server (Python standard library only).

It exposes the SAME API as the FastAPI app (app/main.py), using the same MagicService, and can also
serve the website folder so frontend and backend run on one address:

    python dev_server.py --site ../website --port 8000
    then open  http://localhost:8000/magic/

Use it to try the Magic Layer on a PC or in Termux without installing FastAPI. For production use
the FastAPI app (see docs/DEPLOYMENT.md). This server is for development and testing only.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import Settings                      # noqa: E402
from app.factory import create_service               # noqa: E402
from app.identity import AuthError, client_ip         # noqa: E402
from app.service import ServiceError                  # noqa: E402

MAX_BODY = 20_000


def make_handler(service, auth, settings, site_dir: Path | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SunoSaathiDev/0.1"

        def log_message(self, fmt, *args):            # quiet; set DEV_LOG=1 to see requests
            if os.environ.get("DEV_LOG"):
                super().log_message(fmt, *args)

        # ---- helpers ----
        def _cors(self):
            origin = self.headers.get("Origin")
            allowed = settings.cors_origins
            if origin and ("*" in allowed or origin in allowed):
                self.send_header("Access-Control-Allow-Origin", "*" if "*" in allowed else origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Client-Id, X-Dev-Tier")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, status: int, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def _user(self):
            headers = {k: v for k, v in self.headers.items()}
            return auth.authenticate(headers, client_ip(headers, self.client_address[0], settings.trust_proxy_hops))

        # ---- verbs ----
        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/v1/health":
                return self._json(200, service.health())
            if path == "/v1/usage":
                try:
                    return self._json(200, service.usage(self._user()))
                except AuthError:
                    return self._json(401, {"ok": False, "error": "unauthorized"})
            if site_dir is not None:
                return self._static(path)
            self._json(404, {"ok": False, "error": "not_found"})

        def do_POST(self):
            path = urlparse(self.path).path
            routes = {"/v1/route": service.route, "/v1/explain": service.explain, "/v1/formula": service.formula}
            fn = routes.get(path)
            if not fn:
                return self._json(404, {"ok": False, "error": "not_found"})
            try:
                user = self._user()
            except AuthError:
                return self._json(401, {"ok": False, "error": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length > MAX_BODY:
                return self._json(413, {"ok": False, "error": "too_long"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"ok": False, "error": "bad_request"})
            try:
                self._json(200, fn(user, body))
            except ServiceError as e:
                self._json(e.status, {"ok": False, "error": e.code})

        def _static(self, path: str):
            rel = unquote(path).lstrip("/")
            target = (site_dir / rel).resolve()
            if site_dir.resolve() not in target.parents and target != site_dir.resolve():
                return self._json(403, {"ok": False, "error": "forbidden"})
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                alt = target.with_suffix(".html")           # mimic extensionless URLs
                target = alt if alt.is_file() else target
            if not target.is_file():
                self.send_response(404)
                self.end_headers()
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--site", default="", help="path to the website folder to serve at /")
    ap.add_argument("--mock", action="store_true", help="enable the fake AI provider (development only)")
    args = ap.parse_args()
    settings = Settings.from_env()
    if args.mock:
        settings.enable_mock_provider = True
        if "mock" not in settings.ai_providers:
            settings.ai_providers.append("mock")
    service, auth = create_service(settings)
    site = Path(args.site).resolve() if args.site else None
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(service, auth, settings, site))
    print(f"Magic Layer dev server on http://{args.host}:{args.port}  (AI providers: {[p.name for p in service.chain.providers] or 'none, templates only'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
