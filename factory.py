"""Builds the service from settings. Used by the FastAPI app, the dev server and the tests."""
from __future__ import annotations

from .config import Settings
from .identity import Authenticator
from .providers.chain import ProviderChain
from .quota import QuotaManager
from .registry import Registry
from .service import MagicService, build_providers


def create_service(settings: Settings | None = None, providers=None, now=None):
    s = settings or Settings.from_env()
    kw = {"now": now} if now else {}
    chain = ProviderChain(providers if providers is not None else build_providers(s), **kw)
    service = MagicService(s, Registry.load(s.registry_path), chain, QuotaManager(s, **kw), **kw)
    return service, Authenticator(s)
