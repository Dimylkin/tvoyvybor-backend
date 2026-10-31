from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_api import require_admin
from app.database import Base, get_session
from app.main import app
from app.models import User, UserRole
from app.security import create_access_token


@pytest.fixture
def auth_client() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def test_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_register_login_and_me(auth_client) -> None:
    client, sessions = auth_client
    registration = client.post(
        "/auth/register",
        json={"email": " Alice@Example.com ", "password": "safe-password"},
    )
    assert registration.status_code == 201
    user = registration.json()
    assert user == {
        "id": 1,
        "email": "alice@example.com",
        "role": "user",
        "onboarding_completed": False,
    }

    with sessions() as session:
        stored = session.get(User, user["id"])
        assert stored is not None
        assert stored.password_hash != "safe-password"
        assert stored.password_hash.startswith("pbkdf2_sha256$")

    login = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "safe-password"}
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == user

    completed = client.put(
        "/auth/me/onboarding-complete", headers={"Authorization": f"Bearer {token}"}
    )
    assert completed.status_code == 200
    assert completed.json() == {**user, "onboarding_completed": True}
    assert (
        client.put(
            "/auth/me/onboarding-complete", headers={"Authorization": f"Bearer {token}"}
        ).json()
        == completed.json()
    )


def test_duplicate_bad_password_and_public_role(auth_client) -> None:
    client, _ = auth_client
    credentials = {"email": "alice@example.com", "password": "safe-password"}
    assert client.post("/auth/register", json=credentials).status_code == 201
    assert client.post("/auth/register", json=credentials).status_code == 409
    assert (
        client.post(
            "/auth/login", json={**credentials, "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/register",
            json={**credentials, "email": "other@example.com", "role": "admin"},
        ).status_code
        == 422
    )


def test_me_rejects_missing_tampered_expired_and_deleted_user(
    auth_client, monkeypatch
) -> None:
    client, sessions = auth_client
    assert client.get("/auth/me").status_code == 401
    assert (
        client.get("/auth/me", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )

    client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "safe-password"},
    )
    token = create_access_token(1)
    signature_start = token.rfind(".") + 1
    tampered = (
        token[:signature_start]
        + ("A" if token[signature_start] != "A" else "B")
        + token[signature_start + 1 :]
    )
    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {tampered}"}
        ).status_code
        == 401
    )

    monkeypatch.setattr("app.security.time.time", lambda: 1000)
    expired = create_access_token(1)
    monkeypatch.setattr("app.security.time.time", lambda: 5000)
    assert (
        client.get(
            "/auth/me", headers={"Authorization": f"Bearer {expired}"}
        ).status_code
        == 401
    )

    with sessions() as session:
        session.delete(session.get(User, 1))
        session.commit()
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_admin_check_uses_database_role(auth_client) -> None:
    client, sessions = auth_client
    client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "safe-password"},
    )
    token = create_access_token(1)
    with sessions() as session:
        user = session.get(User, 1)
        assert user is not None
        assert user.role == UserRole.USER
        user.role = UserRole.ADMIN
        session.commit()

    with sessions() as session:
        user = session.get(User, 1)
        assert require_admin(user) is user
        user.role = UserRole.USER
        session.commit()
        with pytest.raises(HTTPException) as error:
            require_admin(user)
        assert error.value.status_code == 403
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
            "role"
        ]
        == "user"
    )
