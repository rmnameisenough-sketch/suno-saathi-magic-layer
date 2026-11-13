"""Any service that offers an OpenAI-style /chat/completions endpoint (Groq, OpenRouter, Together, local servers...).

Set OPENAI_COMPAT_BASE_URL (for example https://api.groq.com/openai/v1), OPENAI_COMPAT_API_KEY and
OPENAI_COMPAT_MODEL. Free tiers and limits differ per host and change often; check the host's own page.

NOTE: tested here only against a local fake server, not against any real host.
"""
from __future__ import annotations

from .base import AIProvider, AIRequest, AIResponse, ProviderError
from .http import classify_http_error, post_json


class OpenAICompatProvider(AIProvider):
    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 12.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def generate(self, req: AIRequest) -> AIResponse:
        if not self.is_configured():
            raise ProviderError("auth", "OpenAI-compatible provider is not configured")
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        status, headers, data = post_json(f"{self.base_url}/chat/completions",
                                          {"Authorization": f"Bearer {self.api_key}"}, body, self.timeout)
        if status != 200:
            raise classify_http_error(status, headers, data)
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise ProviderError("server", "unexpected response")
        if not text:
            raise ProviderError("empty", "empty text")
        usage = data.get("usage") or {}
        return AIResponse(text=text, provider=self.name, model=self.model,
                          tokens_in=int(usage.get("prompt_tokens", 0) or 0),
                          tokens_out=int(usage.get("completion_tokens", 0) or 0))
