def test_uploader_accounts_require_authentication(client, auth_state):
    auth_state(authenticated=False)

    response = client.get("/api/admin/uploader/accounts")

    assert response.status_code == 401


def test_storyline_sessions_require_authentication(client, auth_state):
    auth_state(authenticated=False)

    response = client.get("/api/admin/storyline/sessions")

    assert response.status_code == 401
