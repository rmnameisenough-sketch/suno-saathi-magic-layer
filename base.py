"""The one interface every AI provider implements.

To add a provider (Groq, OpenRouter, Claude, a local model...) write a class with `generate()`
that raises ProviderError with the right `kind` on failure. The rest of the app does not change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AIRequest:
    task: str                 # "route" | "explain" | "steps" | "formula"
    system: str
    user: str
    json_mode: bool = False
    max_tokens: int = 600
    temperature: float = 0.2


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


class ProviderError(Exception):
    """kind: quota | rate_limit | auth | bad_request | server | timeout | blocked | empty

    quota       the (daily) allowance is used up. `daily=True` means it will not recover until tomorrow.
    rate_limit  too many requests per minute; recovers after `retry_after` seconds.
    auth        bad or missing API key / no permission: a configuration problem.
    """

    def __init__(self, kind: str, message: str = "", retry_after: float | None = None, daily: bool = False, status: int = 0):
        super().__init__(message or kind)
        self.kind = kind
        self.retry_after = retry_after
        self.daily = daily
        self.status = status


class AIProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(self, req: AIRequest) -> AIResponse:
        """Return the model's text, or raise ProviderError."""

    def is_configured(self) -> bool:
        return True
