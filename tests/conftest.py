import os
os.environ["ENVIRONMENT"] = "testing"
os.environ["USE_SQLITE_FALLBACK"] = "True"

import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import fakeredis

from app.database import Base, get_db
from app.main import app
from app.core.security import hash_password, create_access_token
from app.models import User, Project, Task, Notification
from app.workers.celery_app import celery_app

celery_app.conf.update(
    broker_url="memory://",
    result_backend="cache+memory://",
    task_always_eager=True,
    task_eager_propagates=True,
)

# Shared SQLite file for tests so FastAPI routes and worker tasks share the same state
TEST_DATABASE_URL = "sqlite:///./test_taskflow.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create fresh database tables before each test and drop them after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def fake_redis_client(monkeypatch):
    """Fixture providing a fakeredis instance to intercept Redis calls in tests."""
    server = fakeredis.FakeServer()
    fake_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    
    # Patch get_redis_client in cache module
    import app.core.cache as cache_module
    monkeypatch.setattr(cache_module, "get_redis_client", lambda: fake_client)
    monkeypatch.setattr(cache_module, "_redis_client", fake_client)
    return fake_client


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Test client overriding the get_db dependency with test database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a standard test user."""
    user = User(
        email="testuser@example.com",
        username="testuser",
        hashed_password=hash_password("Password123!"),
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user_2(db_session: Session) -> User:
    """Create a second test user to test authorization boundaries."""
    user = User(
        email="otheruser@example.com",
        username="otheruser",
        hashed_password=hash_password("Password456!"),
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Return Authorization headers for test_user."""
    token = create_access_token(subject=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_2(test_user_2: User) -> dict:
    """Return Authorization headers for test_user_2."""
    token = create_access_token(subject=test_user_2.id)
    return {"Authorization": f"Bearer {token}"}
