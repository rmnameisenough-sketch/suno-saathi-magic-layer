"""Tiny HTTP helper (standard library only) plus classification of provider errors.

Using only the standard library keeps the backend easy to install and lets us test the
real HTTP code path against a local fake server.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request

from .base import ProviderError


def post_json(url: str, headers: dict, body: dict, timeout: float) -> tuple[int, dict, object]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, dict(resp.headers), _parse(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, dict(e.headers or {}), _parse(raw)
    except (socket.timeout, TimeoutError):
        raise ProviderError("timeout", "request timed out")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ProviderError("timeout", "request timed out")
        raise ProviderError("server", f"network error: {e.reason}")


def _parse(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _retry_after(headers: dict, body) -> float | None:
    """Seconds to wait, from the Retry-After header or Google's RetryInfo ('retryDelay': '34s')."""
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except ValueError:
                pass
    if isinstance(body, dict):
        for d in (body.get("error") or {}).get("details", []) or []:
            delay = d.get("retryDelay") if isinstance(d, dict) else None
            if delay:
                m = re.match(r"^([\d.]+)s$", str(delay))
                if m:
                    return float(m.group(1))
    return None


def classify_http_error(status: int, headers: dict, body) -> ProviderError:
    err = body.get("error", {}) if isinstance(body, dict) else {}
    msg = str(err.get("message") or (body if isinstance(body, str) else ""))[:300]
    low = (msg + " " + str(err.get("status", "")) + " " + str(err.get("code", ""))).lower()
    if status == 429:
        txt = (json.dumps(body) if isinstance(body, (dict, list)) else str(body)).lower()
        daily = any(w in txt for w in ("perday", "per day", "daily", "insufficient_quota"))
        minute = any(w in txt for w in ("perminute", "per minute", "requests per min"))
        ra = _retry_after(headers, body)
        if daily and not minute:
            return ProviderError("quota", msg, retry_after=ra, daily=True, status=status)
        if minute:
            return ProviderError("rate_limit", msg, retry_after=ra, status=status)
        if "quota" in txt or "billing" in txt:
            return ProviderError("quota", msg, retry_after=ra, daily=False, status=status)
        return ProviderError("rate_limit", msg, retry_after=ra, status=status)
    if status in (401, 403) or ("api key" in low and status == 400):
        return ProviderError("auth", msg, status=status)
    if status in (400, 404, 422):
        return ProviderError("bad_request", msg, status=status)
    if status >= 500:
        return ProviderError("server", msg, retry_after=_retry_after(headers, body), status=status)
    return ProviderError("server", msg or f"HTTP {status}", status=status)
