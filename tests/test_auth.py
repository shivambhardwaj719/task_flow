from app.models.user import User


def test_signup_success(client, db_session):
    payload = {
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify database has hashed password, never plain text
    user = db_session.query(User).filter(User.email == "newuser@example.com").first()
    assert user is not None
    assert user.hashed_password != "SecurePassword123!"
    assert user.hashed_password.startswith("$2b$") or user.hashed_password.startswith("$2a$")


def test_signup_duplicate_email(client, test_user):
    payload = {"email": test_user.email, "username": "uniqueusername", "password": "Password123!"}
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


def test_signup_duplicate_username(client, test_user):
    payload = {
        "email": "different@example.com",
        "username": test_user.username,
        "password": "Password123!",
    }
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 400
    assert "username" in response.json()["detail"].lower()


def test_signup_validation_short_password(client):
    payload = {"email": "short@example.com", "username": "shortpass", "password": "123"}
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 422


def test_login_success(client, test_user):
    payload = {"username_or_email": test_user.email, "password": "Password123!"}
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == test_user.email
    assert "hashed_password" not in data["user"]


def test_login_invalid_password(client, test_user):
    payload = {"username_or_email": test_user.email, "password": "WrongPassword!"}
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    payload = {"username_or_email": "nobody@example.com", "password": "Password123!"}
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


def test_get_me_authenticated(client, auth_headers, test_user):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email
    assert "hashed_password" not in data


def test_get_me_unauthorized(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_get_me_invalid_token(client):
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
