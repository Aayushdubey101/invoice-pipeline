"""Phase 14.8: Clerk bearer-token verification.

Manual JWKS fetch (httpx, cached) + PyJWT RS256 verify — not the full
clerk-backend-api SDK, which pulls in user/org management for what's really
just "verify a bearer JWT, extract `sub`."
"""

import time
from typing import Any

import httpx
import jwt
import structlog
from jwt.algorithms import RSAAlgorithm

from invoice_pipeline.config import settings

log = structlog.get_logger()

_JWKS_CACHE_TTL_SECONDS = 3600

_jwks_cache: dict[str, Any] | None = None
_jwks_cache_at: float = 0.0


class ClerkTokenInvalid(Exception):
    """Raised when a Clerk bearer token fails verification."""


async def _get_jwks(force_refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_at
    if (
        not force_refresh
        and _jwks_cache is not None
        and time.monotonic() - _jwks_cache_at < _JWKS_CACHE_TTL_SECONDS
    ):
        return _jwks_cache

    async with httpx.AsyncClient(timeout=5.0) as client:
        res = await client.get(settings.CLERK_JWKS_URL)
        res.raise_for_status()

    _jwks_cache = res.json()
    _jwks_cache_at = time.monotonic()
    return _jwks_cache


def _find_key(jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def verify_clerk_token(token: str) -> str:
    """Verify a Clerk-issued RS256 JWT and return its `sub` (Clerk user id)."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise ClerkTokenInvalid(str(exc)) from exc

    kid = header.get("kid")
    if not kid:
        raise ClerkTokenInvalid("token header missing kid")

    jwks = await _get_jwks()
    jwk = _find_key(jwks, kid)
    if jwk is None:
        # key rotation: refresh once before giving up
        jwks = await _get_jwks(force_refresh=True)
        jwk = _find_key(jwks, kid)
    if jwk is None:
        raise ClerkTokenInvalid("no matching JWKS key for token")

    try:
        public_key = RSAAlgorithm.from_jwk(jwk)
        decode_options = {"verify_aud": bool(settings.CLERK_AUDIENCE)}
        payload = jwt.decode(
            token,
            public_key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            issuer=settings.CLERK_ISSUER,
            audience=settings.CLERK_AUDIENCE or None,
            options=decode_options,
        )
    except jwt.PyJWTError as exc:
        raise ClerkTokenInvalid(str(exc)) from exc

    sub = payload.get("sub")
    if not sub:
        raise ClerkTokenInvalid("token missing sub claim")
    return str(sub)
