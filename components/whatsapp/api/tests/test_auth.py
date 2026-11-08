from tests.conftest import auth_headers


def test_login_returns_token(client, seeded):
    resp = client.post("/auth/login", json=seeded["login_a"])
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]


def test_login_bad_password(client, seeded):
    resp = client.post("/auth/login", json={"email": "a@example.org", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


def test_me_requires_auth(client, seeded):
    assert client.get("/me").status_code == 401


def test_me_returns_memberships(client, seeded):
    headers = auth_headers(client, seeded["login_a"])
    resp = client.get("/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth_subject"] == "a@example.org"
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["organization_id"] == seeded["org_a"]
