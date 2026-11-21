import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import HTTPException, Request

from .config import Settings

_JWKS_TTL_SECONDS = 300
_ALGORITHMS = ("RS256", "RS384", "RS512")


@dataclass(frozen=True)
class Identity:
    email: str


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._issuer = settings.keycloak_issuer or f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        self._jwks_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
        self._jwks: dict | None = None
        self._jwks_fetched_at = 0.0

    def _fetch_jwks(self, force: bool = False) -> dict:
        if force or self._jwks is None or time.monotonic() - self._jwks_fetched_at > _JWKS_TTL_SECONDS:
            resp = httpx.get(self._jwks_url, timeout=5.0)
            resp.raise_for_status()
            self._jwks = resp.json()
            self._jwks_fetched_at = time.monotonic()
        return self._jwks

    def decode_unverified(self, token: str) -> dict:
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc

    def verify(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
            key = self._find_signing_key(header.get("kid"))
            if key is None:
                key = self._find_signing_key(header.get("kid"), force_refresh=True)
            if key is None:
                raise HTTPException(status_code=401, detail="Unknown signing key")
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            options = {"verify_signature": True, "verify_exp": True, "verify_iat": True}
            return jwt.decode(
                token,
                public_key,
                algorithms=_ALGORITHMS,
                options=options,
                issuer=self._issuer,
                audience=self._settings.jwt_audience,
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="Token expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise HTTPException(status_code=401, detail="Invalid token audience") from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Auth provider unavailable") from exc

    def _find_signing_key(self, kid: str | None, force_refresh: bool = False) -> dict | None:
        try:
            jwks = self._fetch_jwks(force=force_refresh)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Auth provider unavailable") from exc
        return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)


def roles_from(claims: dict) -> frozenset:
    realm_access = claims.get("realm_access") or {}
    return frozenset(str(r) for r in (realm_access.get("roles") or []))


def resolve_identity(request: Request, verifier: TokenVerifier, settings: Settings) -> Identity:
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None

    if token is not None:
        claims = verifier.decode_unverified(token) if settings.auth_disabled else verifier.verify(token)
        email = claims.get("email") or claims.get("preferred_username")
        if not email:
            raise HTTPException(status_code=401, detail="Token has no email claim")
        roles = roles_from(claims)
    elif settings.auth_disabled:
        email = request.headers.get("X-User-Email", "").strip()
        if not email:
            raise HTTPException(status_code=401, detail="Missing Authorization header or X-User-Email header")
        roles = frozenset()
    else:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not settings.auth_disabled and settings.required_roles and not (roles & settings.required_roles):
        raise HTTPException(status_code=403, detail="Insufficient roles")

    return Identity(email=email.strip().lower())