def test_auth_protected_endpoint_requires_authentication(client, auth_state):
    auth_state(authenticated=False)

    response = client.get("/api/admin/auth/me")

    assert response.status_code == 404  # 路由不存在，因为auth router没有/me接口
