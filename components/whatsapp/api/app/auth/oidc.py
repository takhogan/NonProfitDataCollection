"""Google OpenID Connect: authorization code + PKCE (S256).

Building blocks come from maintained libraries; nothing here parses or checks
signatures by hand:
- Authlib builds the PKCE code challenge and the authorization URL.
- joserfc (Authlib's JOSE successor) verifies the ID token signature against
  Google's JWKS and validates iss, aud, exp, iat and nonce.

`OidcProvider` is the seam tests replace with a fake. The real
`GoogleOidcProvider` discovers endpoints from the metadata URL and caches the
metadata and JWKS for an hour.
"""
from __future__ import annotations

import time
from typing import Any, Protocol

import httpx
from authlib.common.urls import add_params_to_uri
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from app.config import get_settings

GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]


class OidcError(Exception):
    """Any failure in the OIDC round trip. Mapped to a generic 401."""


class OidcProvider(Protocol):
    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str: ...
    async def exchange(self, *, code: str, code_verifier: str, nonce: str) -> dict[str, Any]:
        """Redeem the code and return verified ID-token claims."""
        ...


def verify_id_token(
    id_token: str,
    jwks: dict,
    *,
    issuers: list[str],
    client_id: str,
    nonce: str,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        token = jwt.decode(id_token, KeySet.import_key_set(jwks), algorithms=["RS256"])
        registry = jwt.JWTClaimsRegistry(
            now=now,
            leeway=60,
            iss={"essential": True, "values": issuers},
            aud={"essential": True, "value": client_id},
            nonce={"essential": True, "value": nonce},
            exp={"essential": True},
            iat={"essential": True},
            sub={"essential": True},
        )
        registry.validate(token.claims)
    except (JoseError, ValueError, KeyError) as exc:
        raise OidcError(type(exc).__name__) from None
    return dict(token.claims)


class GoogleOidcProvider:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, metadata_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.metadata_url = metadata_url
        self._meta: dict | None = None
        self._jwks: dict | None = None
        self._fetched_at = 0.0

    async def _load(self) -> tuple[dict, dict]:
        if self._meta is None or time.monotonic() - self._fetched_at > 3600:
            async with httpx.AsyncClient(timeout=10) as http:
                meta = (await http.get(self.metadata_url)).raise_for_status().json()
                jwks = (await http.get(meta["jwks_uri"])).raise_for_status().json()
            self._meta, self._jwks, self._fetched_at = meta, jwks, time.monotonic()
        return self._meta, self._jwks  # type: ignore[return-value]

    def authorization_url(self, *, state: str, nonce: str, code_verifier: str) -> str:
        # Google's authorization endpoint is stable; using it directly keeps
        # the start step synchronous and free of network calls.
        endpoint = (self._meta or {}).get(
            "authorization_endpoint", "https://accounts.google.com/o/oauth2/v2/auth"
        )
        return add_params_to_uri(endpoint, [
            ("response_type", "code"),
            ("client_id", self.client_id),
            ("redirect_uri", self.redirect_uri),
            ("scope", "openid email profile"),
            ("state", state),
            ("nonce", nonce),
            ("code_challenge", create_s256_code_challenge(code_verifier)),
            ("code_challenge_method", "S256"),
            ("prompt", "select_account"),
        ])

    async def exchange(self, *, code: str, code_verifier: str, nonce: str) -> dict[str, Any]:
        try:
            meta, jwks = await self._load()
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.post(meta["token_endpoint"], data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code_verifier": code_verifier,
                })
            if resp.status_code != 200:
                raise OidcError("token_endpoint_error")
            id_token = resp.json().get("id_token")
            if not id_token:
                raise OidcError("no_id_token")
        except httpx.HTTPError:
            raise OidcError("network") from None
        return verify_id_token(
            id_token, jwks, issuers=GOOGLE_ISSUERS, client_id=self.client_id, nonce=nonce
        )


_provider: OidcProvider | None = None


def get_oidc_provider() -> OidcProvider | None:
    """FastAPI dependency; None when Google sign-in is not configured."""
    global _provider
    s = get_settings()
    if not (s.oidc_google_client_id and s.oidc_google_client_secret and s.oidc_google_redirect_uri):
        return None
    if _provider is None:
        _provider = GoogleOidcProvider(
            s.oidc_google_client_id, s.oidc_google_client_secret,
            s.oidc_google_redirect_uri, s.oidc_google_metadata_url,
        )
    return _provider
