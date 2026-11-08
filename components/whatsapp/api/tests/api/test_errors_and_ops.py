"""CON-040 envelope + request ids, DOM-002 digest, API-110 health, API-111 limits."""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app import config
from app.db import get_db
from tests.conftest import auth_headers

INTAKE = {"reference_code": "ERR-1",
          "needs": [{"category": "water_delivery", "requested_quantity": 10, "unit": "liters"}]}


def _assert_envelope(body: dict) -> None:
    assert set(body) == {"code", "message_key", "details", "request_id"}
    assert body["message_key"].startswith("errors.")
    assert body["request_id"]


def test_error_envelope_shape_and_request_id_header(client, seeded):
    r = client.get("/v1/me")
    _assert_envelope(r.json())
    assert r.headers["x-request-id"] == r.json()["request_id"]


def test_client_request_id_is_echoed_if_well_formed(client, seeded):
    r = client.get("/v1/me", headers={"X-Request-ID": "trace-abc-12345"})
    assert r.headers["x-request-id"] == "trace-abc-12345"
    assert r.json()["request_id"] == "trace-abc-12345"
    bad = client.get("/v1/me", headers={"X-Request-ID": "<script>"})
    assert bad.headers["x-request-id"] != "<script>"


def test_unknown_route_uses_envelope(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    _assert_envelope(r.json())
    assert r.json()["code"] == "not_found"


def test_validation_errors_do_not_echo_input(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    bad = {"reference_code": "X", "contacts": [{"preferred_name": 12345678901234}],
           "needs": [{"category": "water_delivery", "unit": "liters",
                      "requested_quantity": "+58 412 555 0199"}]}
    r = client.post("/v1/households", json=bad, headers=headers)
    assert r.status_code == 422
    body = r.json()
    _assert_envelope(body)
    assert body["code"] == "validation_failed"
    assert "555" not in json.dumps(body)
    assert all(set(d) == {"loc", "type"} for d in body["details"])


def test_unhandled_exception_is_internal_error_envelope(db_session):
    from app.main import create_app
    app = create_app()
    boom = APIRouter()

    @boom.get("/boom")
    def _boom():
        raise RuntimeError("secret detail +58 412 555 0199")

    app.include_router(boom)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500
    _assert_envelope(r.json())
    assert r.json()["code"] == "internal_error"
    assert "secret" not in r.text
    assert r.headers["x-request-id"] == r.json()["request_id"]


def test_idempotency_key_reuse_with_different_body_conflicts(client, seeded):
    headers = {**auth_headers(client, seeded["login_a"]), "Idempotency-Key": "k-1"}
    first = client.post("/v1/households", json=INTAKE, headers=headers)
    assert first.status_code == 201
    same = client.post("/v1/households", json=INTAKE, headers=headers)
    assert same.status_code == 201 and same.json() == first.json()
    changed = client.post("/v1/households", json={**INTAKE, "estimated_member_count": 9},
                          headers=headers)
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"
    assert len(client.get("/v1/cases", headers=headers).json()) == 1


def test_idempotency_key_is_not_shared_across_actors(client, seeded, db_session):
    from app.models.org import OrganizationMembership, User
    from app.security import hash_password
    u = User(auth_subject="a3@example.org", display_name="A3",
             password_hash=hash_password("secret-a3"))
    db_session.add(u)
    db_session.flush()
    db_session.add(OrganizationMembership(organization_id=seeded["org_a"], user_id=u.id))
    db_session.commit()
    h1 = {**auth_headers(client, seeded["login_a"]), "Idempotency-Key": "shared"}
    h2 = {**auth_headers(client, {"email": "a3@example.org", "password": "secret-a3"}),
          "Idempotency-Key": "shared"}
    assert client.post("/v1/households", json=INTAKE, headers=h1).status_code == 201
    r = client.post("/v1/households", json=INTAKE, headers=h2)
    assert r.status_code == 409 and r.json()["code"] == "idempotency_conflict"


def test_legacy_idempotency_rows_still_replay(client, seeded, db_session):
    from app.models.system import IdempotencyKey
    db_session.add(IdempotencyKey(
        organization_id=seeded["org_a"], endpoint="create_intake", key="old",
        response_status=201,
        response_body={"household_id": "h", "case_id": "c", "assessment_id": "a",
                       "need_ids": []}))
    db_session.commit()
    headers = {**auth_headers(client, seeded["login_a"]), "Idempotency-Key": "old"}
    r = client.post("/v1/households", json=INTAKE, headers=headers)
    assert r.status_code == 201 and r.json()["household_id"] == "h"


def test_liveness_and_readiness(client):
    assert client.get("/livez").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"


def test_readiness_fails_when_database_is_down(client):
    class DeadSession:
        def execute(self, *_a, **_k):
            raise ConnectionError("db down")

    client.app.dependency_overrides[get_db] = lambda: DeadSession()
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["code"] == "not_ready"
    assert client.get("/livez").status_code == 200  # liveness unaffected


def test_signin_rate_limit_per_ip(client, seeded, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "rate_limit_signin_per_minute", 3)
    body = {"email": "a@example.org", "password": "wrong-password"}
    codes = [client.post("/v1/auth/password/login", json=body).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    r = client.post("/v1/auth/password/login", json=body)
    assert r.json()["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    # The dev login shares the sign-in bucket.
    assert client.post("/auth/login", json=body).status_code == 429


def test_webhook_rate_limit_per_ip(client, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "rate_limit_webhook_per_minute", 2)
    monkeypatch.setattr(config.get_settings(), "app_secret", "test-secret")
    codes = [client.post("/webhooks/whatsapp", content=b"{}").status_code for _ in range(3)]
    assert codes == [401, 401, 429]


def test_forwarded_for_used_only_with_trusted_hops(client, monkeypatch):
    from app.auth.ratelimit import client_ip
    from starlette.requests import Request
    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"6.6.6.6, 1.2.3.4")],
             "client": ("10.0.0.1", 1234)}
    assert client_ip(Request(scope)) == "10.0.0.1"
    monkeypatch.setattr(config.get_settings(), "forwarded_for_trusted_hops", 1)
    assert client_ip(Request(scope)) == "1.2.3.4"
