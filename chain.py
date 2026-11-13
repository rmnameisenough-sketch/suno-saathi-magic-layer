"""Tries AI providers in order and handles quota exhaustion automatically.

Behaviour (this is the "quota exhaustion is handled automatically" requirement):
  * A provider that reports a DAILY quota error is skipped until its quota resets (Google's daily
    quota resets at midnight Pacific time), without wasting time retrying it on every request.
  * A per-minute rate limit puts it to rest for Retry-After seconds (default 60).
  * Repeated server errors or timeouts open a short, growing cool-down (circuit breaker).
  * A provider with a bad key (auth error) is switched off until the server restarts, and an
    operator should see it in /v1/health.
  * If every provider is unavailable the caller gets AllProvidersUnavailable and the service
    falls back to template answers, so the calculators and basic help keep working.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .base import AIProvider, AIRequest, AIResponse, ProviderError


class AllProvidersUnavailable(Exception):
    def __init__(self, reason: str, attempts: list[dict]):
        super().__init__(reason)
        self.reason = reason          # ai_disabled | provider_quota | provider_cooling | provider_error
        self.attempts = attempts


@dataclass
class Health:
    failures: int = 0
    open_until: float = 0.0
    disabled: bool = False
    last_kind: str = ""
    last_message: str = ""


def seconds_until_pacific_midnight(now: float) -> float:
    tz = ZoneInfo("America/Los_Angeles")
    cur = datetime.fromtimestamp(now, tz)
    nxt = (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60.0, (nxt - cur).total_seconds())


class ProviderChain:
    def __init__(self, providers: list[AIProvider], now=time.time):
        self.providers = [p for p in providers if p.is_configured()]
        self.now = now
        self.health: dict[str, Health] = {p.name: Health() for p in self.providers}
        self._lock = threading.Lock()

    def has_providers(self) -> bool:
        return bool(self.providers)

    def _usable(self, p: AIProvider) -> bool:
        h = self.health[p.name]
        return not h.disabled and self.now() >= h.open_until

    def available(self) -> bool:
        return any(self._usable(p) for p in self.providers)

    def unavailable_reason(self) -> str | None:
        """None if at least one provider can be tried now; otherwise why AI cannot be used."""
        if not self.providers:
            return "ai_disabled"
        if self.available():
            return None
        if any(self.health[p.name].last_kind in ("quota", "rate_limit") for p in self.providers):
            return "provider_quota"
        if all(self.health[p.name].disabled for p in self.providers):
            return "provider_error"
        return "provider_cooling"

    def status(self) -> list[dict]:
        t = self.now()
        out = []
        for p in self.providers:
            h = self.health[p.name]
            state = "disabled" if h.disabled else ("cooling" if t < h.open_until else "ok")
            out.append({"name": p.name, "state": state, "retry_in_s": max(0, int(h.open_until - t)) if state == "cooling" else 0,
                        "last_error": h.last_kind or None})
        return out

    def _record_failure(self, p: AIProvider, e: ProviderError) -> None:
        with self._lock:
            h = self.health[p.name]
            h.last_kind, h.last_message = e.kind, str(e)[:200]
            t = self.now()
            if e.kind == "auth":
                h.disabled = True
            elif e.kind == "quota":
                if e.daily:
                    h.open_until = t + seconds_until_pacific_midnight(t)
                else:
                    h.open_until = t + (e.retry_after or 900)
            elif e.kind == "rate_limit":
                h.open_until = t + min(600.0, e.retry_after or 60.0)
            elif e.kind in ("server", "timeout", "empty"):
                h.failures += 1
                if h.failures >= 2:
                    h.open_until = t + min(300.0, 30.0 * 2 ** (h.failures - 2))

    def generate(self, req: AIRequest) -> AIResponse:
        if not self.providers:
            raise AllProvidersUnavailable("ai_disabled", [])
        attempts: list[dict] = []
        for p in self.providers:
            if not self._usable(p):
                attempts.append({"provider": p.name, "result": "skipped_cooling"})
                continue
            try:
                resp = p.generate(req)
                with self._lock:
                    self.health[p.name].failures = 0
                attempts.append({"provider": p.name, "result": "ok"})
                return resp
            except ProviderError as e:
                self._record_failure(p, e)
                attempts.append({"provider": p.name, "result": e.kind})
        kinds = {a["result"] for a in attempts}
        if kinds <= {"quota", "rate_limit", "skipped_cooling"} and ("quota" in kinds or "rate_limit" in kinds):
            reason = "provider_quota"
        elif kinds == {"skipped_cooling"}:
            reason = "provider_cooling"
        else:
            reason = "provider_error"
        raise AllProvidersUnavailable(reason, attempts)
