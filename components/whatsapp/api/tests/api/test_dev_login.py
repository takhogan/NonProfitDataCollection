"""API-014: the JWT bearer login is development-only."""
from __future__ import annotations

import pytest

from app import config
from app.security import DevAuthDisabled, create_access_token
from tests.conftest import auth_headers

PROD = dict(
    app_env="production",
    database_url="postgresql+psycopg://u:p@/db",
    jwt_secret="prod-secret-xyz",
    verify_token="prod-verify",
    app_secret="s", whatsapp_token="t", phone_number_id="p",
    seed_demo_password="x",
    kms_key_name="projects/p/locations/us-east4/keyRings/metron/cryptoKeys/field-data",
    wrapped_data_key="d3JhcHBlZA==",
)


def test_dev_login_and_bearer_refused_in_production(client, seeded, monkeypatch):
    headers = auth_headers(client, seeded["login_a"])  # minted while in dev
    monkeypatch.setattr(config.get_settings(), "app_env", "production")
    assert client.post("/auth/login", json=seeded["login_a"]).status_code == 404
    assert client.get("/v1/me", headers=headers).status_code == 401
    assert client.get(f"/orgs/{seeded['org_a']}/cases", headers=headers).status_code == 401
    with pytest.raises(DevAuthDisabled):
        create_access_token(seeded["user_a"])


def test_production_app_does_not_mount_dev_login(monkeypatch):
    monkeypatch.setattr(config, "_settings", config.Settings(**PROD))
    from app.main import create_app
    paths = set(create_app().openapi()["paths"])
    assert "/auth/login" not in paths
    assert "/v1/auth/password/login" in paths


def test_production_rejects_insecure_cookie(monkeypatch):
    monkeypatch.setattr(config, "_settings",
                        config.Settings(**PROD, session_cookie_secure=False))
    from app.main import create_app
    with pytest.raises(config.ConfigError):
        create_app()
