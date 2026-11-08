"""API-013: CSRF on cookie mutations; credentialed CORS only from the web origin."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import config
from app.auth.store import get_auth_store
from app.db import get_db
from tests.api.conftest import sign_in

BODY = {"reference_code": "CSRF-1",
        "needs": [{"category": "water_delivery", "requested_quantity": 10, "unit": "liters"}]}


def test_cookie_mutation_requires_csrf_token(client, staff, auth_store, clock):
    csrf = sign_in(client, auth_store, clock, "a@example.org")
    missing = client.post("/v1/households", json=BODY)
    assert missing.status_code == 403
    assert missing.json()["code"] == "forbidden"
    assert missing.json()["message_key"] == "errors.csrf"
    wrong = client.post("/v1/households", json=BODY, headers={"X-CSRF-Token": "x" * 43})
    assert wrong.status_code == 403
    ok = client.post("/v1/households", json=BODY, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 201, ok.text


def test_safe_methods_need_no_csrf(client, staff, auth_store, clock):
    sign_in(client, auth_store, clock, "a@example.org")
    assert client.get("/v1/cases").status_code == 200


def test_csrf_token_is_per_session(client, staff, auth_store, clock):
    csrf_a = sign_in(client, auth_store, clock, "a@example.org")
    from tests.api.conftest import new_client
    other = new_client(client)
    sign_in(other, auth_store, clock, "a2@example.org")
    r = other.post("/v1/households", json=BODY, headers={"X-CSRF-Token": csrf_a})
    assert r.status_code == 403


def test_cross_origin_mutation_rejected(client, staff, auth_store, clock, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "web_origin", "https://app.example.org")
    csrf = sign_in(client, auth_store, clock, "a@example.org")
    bad = client.post("/v1/households", json=BODY,
                      headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"})
    assert bad.status_code == 403
    good = client.post("/v1/households", json=BODY,
                       headers={"X-CSRF-Token": csrf, "Origin": "https://app.example.org"})
    assert good.status_code == 201


def test_login_rejects_foreign_origin(client, staff, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "web_origin", "https://app.example.org")
    r = client.post("/v1/auth/password/login",
                    json={"email": "a@example.org", "password": "whatever-123"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def _app_with_origin(monkeypatch, db_session, auth_store):
    monkeypatch.setattr(config.get_settings(), "web_origin", "https://app.example.org")
    from app.main import create_app
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_auth_store] = lambda: auth_store
    return TestClient(app, base_url="https://testserver")


def test_cors_allows_only_web_origin_with_credentials(monkeypatch, db_session, auth_store):
    c = _app_with_origin(monkeypatch, db_session, auth_store)
    pre = {"Access-Control-Request-Method": "POST",
           "Access-Control-Request-Headers": "content-type,x-csrf-token"}
    ok = c.options("/v1/households", headers={"Origin": "https://app.example.org", **pre})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://app.example.org"
    assert ok.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in ok.headers["access-control-allow-headers"].lower()

    bad = c.options("/v1/households", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in bad.headers
    simple = c.get("/livez", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_no_cors_when_origin_unset(client):
    r = client.get("/livez", headers={"Origin": "https://app.example.org"})
    assert "access-control-allow-origin" not in r.headers
