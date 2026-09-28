from tests.conftest import auth_headers


def test_signup_login_me(client):
    r = client.post("/auth/signup", json={"name": "A", "email": "A@Example.com", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["email"] == "a@example.com" and "password" not in r.text
    h = auth_headers(client, "a@example.com")
    assert client.get("/auth/me", headers=h).json()["email"] == "a@example.com"


def test_duplicate_signup(client):
    body = {"name": "A", "email": "a@example.com", "password": "password123"}
    assert client.post("/auth/signup", json=body).status_code == 201
    assert client.post("/auth/signup", json=body).status_code == 409


def test_signup_validation(client):
    assert client.post("/auth/signup", json={"name": "A", "email": "nope", "password": "password123"}).status_code == 422
    assert client.post("/auth/signup", json={"name": "A", "email": "a@b.com", "password": "short"}).status_code == 422


def test_login_failures(client):
    auth_headers(client)
    assert client.post("/auth/login", json={"email": "user@example.com", "password": "wrongpass1"}).status_code == 401
    assert client.post("/auth/login", json={"email": "ghost@example.com", "password": "password123"}).status_code == 401


def test_protected_routes_need_valid_token(client):
    assert client.get("/centres/").status_code == 401
    assert client.get("/centres/", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_centres_admin_only_and_listing(client, catalog):
    user = auth_headers(client)
    assert client.post("/centres/", json={"name": "X", "location": "Y"}, headers=user).status_code == 403
    dup = client.post("/centres/", json={"name": "Lab A", "location": "Jabalpur"}, headers=catalog["admin"])
    assert dup.status_code == 409
    page = client.get("/centres/?location=jabalpur&limit=5", headers=user).json()
    assert page["total"] == 1 and page["items"][0]["tests"][0]["name"] == "CBC"
    assert client.get("/centres/999", headers=user).status_code == 404
    bad = client.post(
        f"/centres/{catalog['centre_id']}/tests", json={"name": "T", "price": "-5"}, headers=catalog["admin"]
    )
    assert bad.status_code == 422
