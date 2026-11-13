"""Who is calling, and which tier are they on?

Today: everyone is anonymous (identified by a hash of an anonymous browser id + IP).
Ready for later: a signed login token (JWT) carrying the user id and subscription tier.

Future plan (see docs/ARCHITECTURE.md):
  * Login: Supabase Auth / Firebase Auth / any provider that issues JWTs. The frontend sends
    `Authorization: Bearer <token>`; this backend only VERIFIES it (JwtAuth) and never stores passwords.
  * Subscriptions: a payment provider's webhook updates a `tier` in your database. A TierResolver
    reads it, so the tier is never trusted from the browser. ClaimsTierResolver (tier inside the
    signed token) is the simple starting point.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import Settings

VALID_TIERS = ("anonymous", "free", "premium")


class AuthError(Exception):
    """Invalid or expired credentials (HTTP 401)."""


@dataclass
class User:
    id: str
    tier: str = "anonymous"
    source: str = "anonymous"       # anonymous | jwt | dev
    ip_key: str = ""                # hash of the IP address, used for a second, larger cap on anonymous users


class TierResolver:
    def resolve(self, user_id: str, claimed_tier: str | None) -> str:
        raise NotImplementedError


class ClaimsTierResolver(TierResolver):
    """Trust the tier inside a token that WE verified. Swap for a database lookup when payments exist."""

    def resolve(self, user_id: str, claimed_tier: str | None) -> str:
        return claimed_tier if claimed_tier in ("free", "premium") else "free"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class Authenticator:
    def __init__(self, settings: Settings, tier_resolver: TierResolver | None = None):
        self.s = settings
        self.resolver = tier_resolver or ClaimsTierResolver()
        self._jwt = None
        if settings.jwt_secret:
            try:
                import jwt as pyjwt          # PyJWT; listed in requirements.txt
            except ImportError as e:         # pragma: no cover
                raise RuntimeError("JWT_SECRET is set but PyJWT is not installed") from e
            self._jwt = pyjwt

    def authenticate(self, headers: dict[str, str], client_ip: str) -> User:
        h = {k.lower(): v for k, v in headers.items()}
        auth = h.get("authorization", "")
        if auth.lower().startswith("bearer "):
            if not self._jwt:
                raise AuthError("login is not enabled on this server")
            token = auth[7:].strip()
            try:
                claims = self._jwt.decode(token, self.s.jwt_secret, algorithms=["HS256"],
                                          options={"require": ["exp", "sub"]})
            except Exception as e:
                raise AuthError("invalid or expired token") from e
            claimed = claims.get(self.s.jwt_tier_claim) or (claims.get("app_metadata") or {}).get("tier")
            tier = self.resolver.resolve(str(claims["sub"]), claimed)
            return User(id="u:" + str(claims["sub"]), tier=tier, source="jwt")
        if self.s.env == "dev" and h.get("x-dev-tier") in VALID_TIERS:
            # Development only: lets you test tiers without a login system. Ignored when ENV=prod.
            ident = h.get("x-client-id") or client_ip
            return User(id="dev:" + _hash(ident), tier=h["x-dev-tier"], source="dev")
        ident = (h.get("x-client-id") or "") + "|" + client_ip
        return User(id="anon:" + _hash(ident), tier="anonymous", source="anonymous", ip_key=_hash("ip|" + client_ip))


def client_ip(headers: dict[str, str], peer_ip: str, trusted_hops: int) -> str:
    """The visitor's IP. Only reads X-Forwarded-For when told how many trusted proxies sit in front of us."""
    if trusted_hops > 0:
        xff = {k.lower(): v for k, v in headers.items()}.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= trusted_hops:
            return parts[-trusted_hops]
    return peer_ip or "unknown"
