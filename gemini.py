"""Google Gemini via the plain REST API (generateContent).

The API key stays on the server (environment variable GEMINI_API_KEY). It is sent in the
`x-goog-api-key` header and never reaches the browser.

NOTE: tested here only against a local fake server that imitates Gemini's documented response
and error shapes. It has not been run against Google's live API (no network in the build sandbox).
"""
from __future__ import annotations

from .base import AIProvider, AIRequest, AIResponse, ProviderError
from .http import classify_http_error, post_json


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 12.0, thinking_budget: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.thinking_budget = thinking_budget

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def generate(self, req: AIRequest) -> AIResponse:
        if not self.is_configured():
            raise ProviderError("auth", "Gemini API key or model not set")
        url = f"{self.base_url}/models/{self.model}:generateContent"
        gen_cfg: dict = {"temperature": req.temperature, "maxOutputTokens": req.max_tokens}
        if req.json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        if self.thinking_budget.strip().lstrip("-").isdigit():
            gen_cfg["thinkingConfig"] = {"thinkingBudget": int(self.thinking_budget)}
        body = {
            "systemInstruction": {"parts": [{"text": req.system}]},
            "contents": [{"role": "user", "parts": [{"text": req.user}]}],
            "generationConfig": gen_cfg,
        }
        status, headers, data = post_json(url, {"x-goog-api-key": self.api_key}, body, self.timeout)
        if status != 200:
            raise classify_http_error(status, headers, data)
        if not isinstance(data, dict):
            raise ProviderError("server", "unexpected response")
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise ProviderError("blocked", "prompt blocked by provider")
        cands = data.get("candidates") or []
        if not cands:
            raise ProviderError("empty", "no candidates")
        parts = ((cands[0].get("content") or {}).get("parts")) or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        if not text:
            raise ProviderError("empty", "empty text (finishReason=%s)" % cands[0].get("finishReason"))
        usage = data.get("usageMetadata") or {}
        return AIResponse(text=text, provider=self.name, model=self.model,
                          tokens_in=int(usage.get("promptTokenCount", 0) or 0),
                          tokens_out=int(usage.get("candidatesTokenCount", 0) or 0))
