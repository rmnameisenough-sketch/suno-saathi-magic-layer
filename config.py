"""Settings for the Magic Layer backend.

Everything comes from environment variables so that secrets (API keys) never live in code
or in the website's JavaScript. See `.env.example` for the full list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass
class Settings:
    env: str = "dev"                         # "dev" allows test headers; use "prod" when deployed
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    registry_path: str = ""

    # --- AI providers, tried in this order. Empty list = AI switched off (templates only). ---
    ai_providers: list[str] = field(default_factory=list)       # e.g. ["gemini", "openai_compat"]
    enable_mock_provider: bool = False                          # dev/test only
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"                 # CHECK in AI Studio which models are free for you
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_thinking_budget: str = ""                            # optional; leave empty unless your model needs it
    openai_compat_api_key: str = ""
    openai_compat_base_url: str = ""                            # any OpenAI-compatible /chat/completions host
    openai_compat_model: str = ""
    provider_timeout_s: float = 12.0

    # --- Usage limits (AI calls per day), per tier ---
    anon_daily: int = 5
    free_daily: int = 15
    premium_daily: int = 300
    anon_per_minute: int = 4
    free_per_minute: int = 8
    premium_per_minute: int = 20
    # Ceiling for ALL users together, so we stay under the provider's free quota.
    global_daily: int = 400
    # Free + anonymous users may use at most this share of the global ceiling; the rest is kept for premium.
    free_share: float = 0.8
    quota_timezone: str = "Asia/Kolkata"                        # when "a day" starts for users
    usage_db: str = ":memory:"                                  # a file path makes counters survive restarts

    # --- Limits on what clients may send ---
    max_question_chars: int = 500
    max_result_chars: int = 3000

    # --- Behind a reverse proxy (Render, Cloud Run...) the real visitor IP arrives in X-Forwarded-For. ---
    # Number of trusted proxies in front of the app. 0 = ignore the header (safe default; the header can be faked).
    trust_proxy_hops: int = 0

    # --- Authentication (future) ---
    jwt_secret: str = ""                                        # set to enable JWT login (HS256)
    jwt_tier_claim: str = "tier"

    @classmethod
    def from_env(cls) -> "Settings":
        here = Path(__file__).resolve().parent
        default_registry = str(here / "data" / "registry.json")
        return cls(
            env=os.environ.get("ENV", "dev"),
            cors_origins=_list("CORS_ORIGINS", "*"),
            registry_path=os.environ.get("REGISTRY_PATH", default_registry),
            ai_providers=_list("AI_PROVIDERS", ""),
            enable_mock_provider=os.environ.get("ENABLE_MOCK_PROVIDER", "") in ("1", "true", "yes"),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            gemini_base_url=os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
            gemini_thinking_budget=os.environ.get("GEMINI_THINKING_BUDGET", ""),
            openai_compat_api_key=os.environ.get("OPENAI_COMPAT_API_KEY", ""),
            openai_compat_base_url=os.environ.get("OPENAI_COMPAT_BASE_URL", ""),
            openai_compat_model=os.environ.get("OPENAI_COMPAT_MODEL", ""),
            provider_timeout_s=_float("PROVIDER_TIMEOUT_S", 12.0),
            anon_daily=_int("ANON_DAILY", 5),
            free_daily=_int("FREE_DAILY", 15),
            premium_daily=_int("PREMIUM_DAILY", 300),
            anon_per_minute=_int("ANON_PER_MINUTE", 4),
            free_per_minute=_int("FREE_PER_MINUTE", 8),
            premium_per_minute=_int("PREMIUM_PER_MINUTE", 20),
            global_daily=_int("GLOBAL_DAILY", 400),
            free_share=_float("FREE_SHARE", 0.8),
            quota_timezone=os.environ.get("QUOTA_TIMEZONE", "Asia/Kolkata"),
            usage_db=os.environ.get("USAGE_DB", ":memory:"),
            max_question_chars=_int("MAX_QUESTION_CHARS", 500),
            max_result_chars=_int("MAX_RESULT_CHARS", 3000),
            trust_proxy_hops=_int("TRUST_PROXY_HOPS", 0),
            jwt_secret=os.environ.get("JWT_SECRET", ""),
            jwt_tier_claim=os.environ.get("JWT_TIER_CLAIM", "tier"),
        )
