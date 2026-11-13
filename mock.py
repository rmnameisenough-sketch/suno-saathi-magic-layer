"""A fake AI used for development and automated tests. It needs no key and no network.

It can imitate failures (`behavior`) so the quota/fallback logic can be tested for real:
  ok | quota_daily | rate_limit | server | auth | garbage | invented_numbers
It is NOT intelligent. Do not enable it in production (ENABLE_MOCK_PROVIDER stays off).
"""
from __future__ import annotations

import json

from .base import AIProvider, AIRequest, AIResponse, ProviderError


class MockProvider(AIProvider):
    name = "mock"

    def __init__(self, behavior: str = "ok"):
        self.behavior = behavior
        self.calls = 0

    def generate(self, req: AIRequest) -> AIResponse:
        self.calls += 1
        b = self.behavior
        if b == "quota_daily":
            raise ProviderError("quota", "mock: daily quota exhausted (PerDay)", daily=True, status=429)
        if b == "rate_limit":
            raise ProviderError("rate_limit", "mock: too many requests per minute", retry_after=7, status=429)
        if b == "server":
            raise ProviderError("server", "mock: 503", status=503)
        if b == "auth":
            raise ProviderError("auth", "mock: bad key", status=403)
        try:
            ctx = json.loads(req.user)
        except ValueError:
            ctx = {}
        if b == "garbage":
            return AIResponse("not json at all", self.name, "mock")
        if req.task == "route":
            q = ctx.get("student_question", "")
            tools = ctx.get("TOOLS", "")
            first = next((ln.split()[1] for ln in tools.splitlines() if ln.startswith("TOOL ")), None)
            return AIResponse(json.dumps({"tool_id": first, "mode": "", "inputs": {}, "confidence": 0.5, "reason": "mock"}), self.name, "mock")
        lang = ctx.get("language", "en")
        out = str(ctx.get("calculator_output", ""))
        number = next((t for t in out.replace("\n", " ").split() if any(c.isdigit() for c in t)), "")
        if b == "invented_numbers":
            number = "98765.4321"
        if req.task == "formula":
            text = "Mock summary: use the first formula in the list." if lang == "en" else "मॉक सारांश: सूची का पहला सूत्र उपयोग करें।"
        elif req.task == "steps":
            text = (f"1. Write the formula.\n2. Put in the values.\n3. The answer is {number}."
                    if lang == "en" else f"1. सूत्र लिखिए।\n2. मान रखिए।\n3. उत्तर {number} आता है।")
        else:
            text = (f"Mock explanation: the calculator gave {number}. Check your units."
                    if lang == "en" else f"मॉक व्याख्या: कैलकुलेटर का उत्तर {number} है। इकाइयाँ जाँच लें।")
        return AIResponse(text, self.name, "mock", tokens_in=10, tokens_out=20)
