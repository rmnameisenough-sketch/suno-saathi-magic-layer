"""FastAPI web layer.

Deliberately thin: it only handles HTTP (CORS, JSON, status codes, who is calling). All the real
logic lives in service.py, which is tested without any web framework.

Run locally:   uvicorn app.main:app --reload
Production:    uvicorn app.main:app --host 0.0.0.0 --port $PORT

IMPORTANT: this file has NOT been executed in the build environment (FastAPI could not be installed
there). It uses only basic FastAPI features. Run `python -m pytest` or the dev server first and
see docs/DEPLOYMENT.md for the first-run check.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import Settings
from .factory import create_service
from .identity import AuthError, client_ip
from .service import ServiceError

MAX_BODY_BYTES = 20_000


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    service, auth = create_service(s)

    app = FastAPI(title="Suno Saathi Magic Layer", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Client-Id", "X-Dev-Tier"],
    )

    def _user(request: Request):
        peer = request.client.host if request.client else ""
        headers = dict(request.headers)
        return auth.authenticate(headers, client_ip(headers, peer, s.trust_proxy_hops))

    async def _handle(request: Request, fn, with_body: bool):
        try:
            user = _user(request)
        except AuthError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        body: dict = {}
        if with_body:
            raw = await request.body()
            if len(raw) > MAX_BODY_BYTES:
                return JSONResponse({"ok": False, "error": "too_long"}, status_code=413)
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        try:
            data = await run_in_threadpool(fn, user, body)
        except ServiceError as e:
            return JSONResponse({"ok": False, "error": e.code}, status_code=e.status)
        return JSONResponse(data)

    @app.get("/v1/health")
    async def health():
        return JSONResponse(service.health())

    @app.get("/v1/usage")
    async def usage(request: Request):
        return await _handle(request, lambda user, body: service.usage(user), with_body=False)

    @app.post("/v1/route")
    async def route(request: Request):
        return await _handle(request, service.route, with_body=True)

    @app.post("/v1/explain")
    async def explain(request: Request):
        return await _handle(request, service.explain, with_body=True)

    @app.post("/v1/formula")
    async def formula(request: Request):
        return await _handle(request, service.formula, with_body=True)

    return app


app = create_app()
