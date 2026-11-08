"""API-010 Google OIDC: code + PKCE flow and ID-token verification."""
from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pytest
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from app import config
from app.auth.oidc import (
    GOOGLE_ISSUERS,
    GoogleOidcProvider,
    OidcError,
    get_oidc_provider,
    verify_id_token,
)
from app.routers.auth import safe_next_path

WEB = "https://app.example.org"


class FakeProvider:
    def __init__(self) -> None:
        self.claims = {"email": "a@example.org", "email_verified": True, "sub": "g-1"}
        self.seen: dict = {}

    def authorization_url(self, *, state, nonce, code_verifier):
        self.seen = {"state": state, "nonce": nonce, "verifier": code_verifier}
        return f"https://accounts.example/auth?state={state}"

    async def exchange(self, *, code, code_verifier, nonce):
        if code == "bad":
            raise OidcError("bad code")
        assert code_verifier == self.seen["verifier"] and nonce == self.seen["nonce"]
        return dict(self.claims)


@pytest.fixture()
def fake(client, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "web_origin", WEB)
    p = FakeProvider()
    client.app.dependency_overrides[get_oidc_provider] = lambda: p
    return p


def _start(client, next_path="/dashboard"):
    r = client.get("/v1/auth/oidc/google/start", params={"next": next_path},
                   follow_redirects=False)
    assert r.status_code == 302
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0]


def _callback(client, state, code="good"):
    return client.get("/v1/auth/oidc/google/callback", params={"code": code, "state": state},
                      follow_redirects=False)


def test_google_sign_in_creates_session_and_redirects(client, staff, fake):
    state = _start(client)
    r = _callback(client, state)
    assert r.status_code == 302
    assert r.headers["location"] == WEB + "/dashboard"
    assert "__Host-sid=" in r.headers["set-cookie"]
    me = client.get("/v1/me").json()
    assert me["session"]["auth_method"] == "oidc_google"
    assert me["active_organization_id"] == staff["org_a"]


def test_flow_cookie_is_httponly_and_short_lived(client, staff, fake):
    r = client.get("/v1/auth/oidc/google/start", follow_redirects=False)
    c = r.headers["set-cookie"].lower()
    assert c.startswith("__host-oidc=") and "httponly" in c and "max-age=300" in c


@pytest.mark.parametrize("claims", [
    {"email": "a@example.org", "email_verified": False, "sub": "1"},
    {"email": "a@example.org", "sub": "1"},
    {"email": "stranger@example.org", "email_verified": True, "sub": "1"},
    {"email_verified": True, "sub": "1"},
])
def test_unverified_or_uninvited_email_rejected(client, staff, fake, claims):
    fake.claims = claims
    r = _callback(client, _start(client))
    assert r.status_code == 302
    assert r.headers["location"] == WEB + "/sign-in?error=sign_in_failed"
    assert client.get("/v1/me").status_code == 401


def test_state_must_match_and_is_single_use(client, staff, fake):
    _start(client)
    assert _callback(client, "forged-state").headers["location"].endswith("error=sign_in_failed")
    state = _start(client)
    assert _callback(client, state).headers["location"] == WEB + "/dashboard"
    # The same state cannot be replayed.
    assert _callback(client, state).headers["location"].endswith("error=sign_in_failed")


def test_callback_requires_the_starting_browser(client, staff, fake):
    from tests.api.conftest import new_client
    state = _start(client)
    other = new_client(client)
    r = _callback(other, state)
    assert r.headers["location"].endswith("error=sign_in_failed")


def test_flow_expires(client, staff, fake, clock):
    state = _start(client)
    clock.advance(minutes=6)
    assert _callback(client, state).headers["location"].endswith("error=sign_in_failed")


def test_failed_code_exchange(client, staff, fake):
    assert _callback(client, _start(client), code="bad").headers["location"].endswith(
        "error=sign_in_failed")


def test_unconfigured_google_returns_404(client):
    assert client.get("/v1/auth/oidc/google/start", follow_redirects=False).status_code == 404


@pytest.mark.parametrize("raw,expected", [
    ("/reports?x=1", "/reports?x=1"),
    ("//evil.example/x", "/"),
    ("https://evil.example", "/"),
    ("/\\evil.example", "/"),
    ("dashboard", "/"),
    (None, "/"),
    ("/a\r\nSet-Cookie: x", "/"),
])
def test_next_path_is_validated(raw, expected):
    assert safe_next_path(raw) == expected


def test_authorization_url_uses_pkce_s256():
    p = GoogleOidcProvider("cid", "secret", "https://api.example.org/cb", "https://x/meta")
    url = p.authorization_url(state="s", nonce="n", code_verifier="v" * 64)
    q = parse_qs(urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["code_challenge"][0] != "v" * 64
    assert q["nonce"] == ["n"] and q["state"] == ["s"] and q["response_type"] == ["code"]
    assert "openid" in q["scope"][0] and "email" in q["scope"][0]


# --- ID token verification with a real RSA key ---------------------------------

KEY = RSAKey.generate_key(2048, parameters={"kid": "k1", "alg": "RS256", "use": "sig"})
JWKS = KeySet([KEY]).as_dict(private=False)


def _token(**over):
    now = int(time.time())
    claims = {"iss": GOOGLE_ISSUERS[0], "aud": "cid", "sub": "g-1", "nonce": "n",
              "email": "a@example.org", "email_verified": True, "iat": now, "exp": now + 600}
    claims.update(over)
    return jwt.encode({"alg": "RS256", "kid": "k1"}, claims, KEY)


def test_valid_id_token():
    claims = verify_id_token(_token(), JWKS, issuers=GOOGLE_ISSUERS, client_id="cid", nonce="n")
    assert claims["email"] == "a@example.org"


@pytest.mark.parametrize("over", [
    {"aud": "someone-else"},
    {"iss": "https://evil.example"},
    {"nonce": "other"},
    {"exp": int(time.time()) - 3600},
])
def test_invalid_id_tokens_rejected(over):
    with pytest.raises(OidcError):
        verify_id_token(_token(**over), JWKS, issuers=GOOGLE_ISSUERS, client_id="cid", nonce="n")


def test_id_token_signed_by_other_key_rejected():
    other = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    now = int(time.time())
    forged = jwt.encode({"alg": "RS256", "kid": "k1"},
                        {"iss": GOOGLE_ISSUERS[0], "aud": "cid", "sub": "x", "nonce": "n",
                         "iat": now, "exp": now + 600}, other)
    with pytest.raises(OidcError):
        verify_id_token(forged, JWKS, issuers=GOOGLE_ISSUERS, client_id="cid", nonce="n")
