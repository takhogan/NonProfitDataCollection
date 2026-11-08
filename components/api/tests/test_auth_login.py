"""Login with bad credentials must be a clean 403, not a 500."""


def test_login_wrong_password_is_403(client):
    r = client.post("/auth/login", json={"email": "demo@metron.org", "password": "wrong"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "permission_denied"


def test_login_unknown_user_is_403(client):
    r = client.post("/auth/login", json={"email": "nobody@example.org", "password": "x"})
    assert r.status_code == 403
