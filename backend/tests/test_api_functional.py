def test_login_success_returns_token(client):
    response = client.post(
        "/api/admin/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "token-123"
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "admin@example.com"


def test_login_rejects_bad_password(client):
    response = client.post(
        "/api/admin/auth/login",
        json={"email": "admin@example.com", "password": "wrong-pass"},
    )

    assert response.status_code == 401


def test_login_rejects_invalid_email_shape(client):
    response = client.post(
        "/api/admin/auth/login",
        json={"email": "not-an-email", "password": "secret123"},
    )

    assert response.status_code == 422
