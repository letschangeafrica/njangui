"""
pytest fixtures shared across all test files.

Architecture:
  - One PostgreSQL test database (separate from dev DB)
  - Alembic runs the real migration once per test session (creates schema + seed data + triggers)
  - Each test function runs inside a transaction that is ROLLED BACK at the end
  - This gives full isolation without recreating the schema on every test

Environment variable required:
  TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/Njangui_test
  (or set in .env.test — the docker-compose db_test service runs on port 5433)
"""

import os
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.core.security import hash_pin, hash_otp, create_access_token
from app.models.user import User, UserRole
from app.models.otp_code import OtpCode

from datetime import datetime, timedelta, timezone

# ── Test database URL ─────────────────────────────────────────────────────────
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/Njangui_test",
)

# ── Engine and session factory ────────────────────────────────────────────────
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


# ═══════════════════════════════════════════════════════════════════════════════
# Session-scoped: run Alembic migration ONCE for the whole test session
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    Run the full Alembic migration against the test database before any tests run.
    This creates all 9 tables, all 10 indexes, all 6 triggers, and seeds all reference data.
    Drops everything at the end of the test session.
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # Run all migrations up
    command.upgrade(alembic_cfg, "head")

    yield  # run all tests

    # Tear down after the session
    command.downgrade(alembic_cfg, "base")


# ═══════════════════════════════════════════════════════════════════════════════
# Function-scoped: isolated DB session per test (transaction rollback)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def db():
    """
    Provides a database session wrapped in a transaction.
    The transaction is rolled back after each test — no data leaks between tests.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """
    FastAPI TestClient with the real DB dependency overridden to use the test session.
    Every request made through this client uses the same rolled-back transaction.
    """
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Reusable data fixtures
# ═══════════════════════════════════════════════════════════════════════════════

PHONE_NUMBER  = "+237612345678"
PHONE_NUMBER2 = "+237699887766"
VALID_PIN     = "7391"
VALID_OTP     = "847291"


@pytest.fixture()
def existing_user(db) -> User:
    """
    A verified, active user already in the database.
    Use this when you need a logged-in context without going through registration.
    """
    user = User(
        phone_number=PHONE_NUMBER,
        pin_hash=hash_pin(VALID_PIN),
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        language="fr",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def valid_otp_record(db) -> OtpCode:
    """
    A valid, unused, unexpired OTP in the DB for PHONE_NUMBER.
    The plain OTP value is VALID_OTP ("847291").
    """
    otp = OtpCode(
        phone_number=PHONE_NUMBER,
        code_hash=hash_otp(VALID_OTP),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        is_used=False,
        attempt_count=0,
    )
    db.add(otp)
    db.commit()
    db.refresh(otp)
    return otp


@pytest.fixture()
def auth_headers(existing_user) -> dict:
    """
    Bearer token headers for the existing_user fixture.
    Use with: client.get("/auth/me", headers=auth_headers)
    """
    token = create_access_token(
        user_id=str(existing_user.id),
        phone_number=existing_user.phone_number,
        role=existing_user.role.value,
    )
    return {"Authorization": f"Bearer {token}"}
