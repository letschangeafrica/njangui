"""
Tests for the authentication module.

Coverage:
  - OTP request (happy path, rate limiting, invalid phone)
  - Registration (happy path, duplicate phone, invalid OTP, weak PIN)
  - Login (happy path, wrong PIN, wrong OTP, suspended account, locked account)
  - GET /me (valid token, expired/invalid token)
  - Change PIN
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.core.security import hash_otp, hash_pin, create_access_token
from app.models.otp_code import OtpCode
from app.models.user import User, UserRole

from tests.conftest import PHONE_NUMBER, PHONE_NUMBER2, VALID_PIN, VALID_OTP


# ═══════════════════════════════════════════════════════════════════════════════
# POST /auth/otp/request
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequestOTP:

    @pytest.mark.auth
    def test_request_otp_valid_phone(self, client):
        """Happy path — valid Cameroonian phone gets an OTP."""
        response = client.post("/auth/otp/request", json={"phone_number": PHONE_NUMBER})
        assert response.status_code == 200
        data = response.json()
        assert "expires_in" in data
        assert data["expires_in"] == 600
        # In dev/debug mode the OTP is returned
        assert "debug_otp" in data
        if data["debug_otp"]:
            assert len(data["debug_otp"]) == 6
            assert data["debug_otp"].isdigit()

    @pytest.mark.auth
    def test_request_otp_invalid_phone_format(self, client):
        """Phone without +237 prefix is rejected."""
        response = client.post("/auth/otp/request", json={"phone_number": "0612345678"})
        assert response.status_code == 422
        assert "237" in response.text

    @pytest.mark.auth
    def test_request_otp_too_short(self, client):
        """Phone number too short after +237."""
        response = client.post("/auth/otp/request", json={"phone_number": "+23761234"})
        assert response.status_code == 422

    @pytest.mark.auth
    def test_request_otp_rate_limit(self, client, db):
        """After 3 OTP requests in an hour the 4th is blocked with HTTP 429."""
        # Insert 3 OTP records created within the last hour
        for _ in range(3):
            otp = OtpCode(
                phone_number=PHONE_NUMBER,
                code_hash=hash_otp("111111"),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            db.add(otp)
        db.commit()

        response = client.post("/auth/otp/request", json={"phone_number": PHONE_NUMBER})
        assert response.status_code == 429
        assert "Trop de tentatives" in response.json()["detail"]

    @pytest.mark.auth
    def test_request_otp_rate_limit_resets_after_hour(self, client, db):
        """OTPs older than 1 hour don't count toward the rate limit."""
        # Insert 3 OTP records created 2 hours ago (outside the window)
        for _ in range(3):
            otp = OtpCode(
                phone_number=PHONE_NUMBER,
                code_hash=hash_otp("111111"),
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            db.add(otp)
        db.commit()

        # 4th request should succeed because old ones are outside the window
        response = client.post("/auth/otp/request", json={"phone_number": PHONE_NUMBER})
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# POST /auth/register
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegister:

    @pytest.mark.auth
    def test_register_happy_path(self, client, valid_otp_record):
        """Full registration flow — new user with valid OTP and PIN."""
        response = client.post("/auth/register", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
            "language":     "fr",
        })
        assert response.status_code == 201
        data = response.json()

        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["phone_number"] == PHONE_NUMBER
        assert data["user"]["role"] == "customer"
        assert data["user"]["is_verified"] is True
        assert data["user"]["language"] == "fr"

    @pytest.mark.auth
    def test_register_otp_is_consumed(self, client, db, valid_otp_record):
        """After successful registration, the OTP cannot be reused."""
        client.post("/auth/register", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })

        # Try registering again with the same OTP (different phone to avoid duplicate conflict)
        otp2 = OtpCode(
            phone_number=PHONE_NUMBER2,
            code_hash=hash_otp(VALID_OTP),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(otp2)
        db.commit()

        # Same OTP for original phone should now be marked used
        db.refresh(valid_otp_record)
        assert valid_otp_record.is_used is True

    @pytest.mark.auth
    def test_register_duplicate_phone(self, client, existing_user, valid_otp_record):
        """Cannot register twice with the same phone number."""
        response = client.post("/auth/register", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })
        assert response.status_code == 409
        assert "déjà enregistré" in response.json()["detail"]

    @pytest.mark.auth
    def test_register_wrong_otp(self, client, valid_otp_record):
        """Wrong OTP is rejected."""
        response = client.post("/auth/register", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     "000000",
            "pin":          VALID_PIN,
        })
        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"]

    @pytest.mark.auth
    def test_register_expired_otp(self, client, db):
        """Expired OTP is rejected."""
        expired_otp = OtpCode(
            phone_number=PHONE_NUMBER,
            code_hash=hash_otp(VALID_OTP),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
        )
        db.add(expired_otp)
        db.commit()

        response = client.post("/auth/register", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })
        assert response.status_code == 400
        assert "valide" in response.json()["detail"]

    @pytest.mark.auth
    @pytest.mark.parametrize("bad_pin", ["1234", "0000", "123", "abcd", "12345"])
    def test_register_weak_or_invalid_pin(self, client, valid_otp_record, bad_pin):
        """Trivial or malformed PINs are rejected by Pydantic validation."""
        response = client.post("/auth/register", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          bad_pin,
        })
        assert response.status_code == 422

    @pytest.mark.auth
    def test_register_otp_lockout_after_5_failures(self, client, db, valid_otp_record):
        """After 5 wrong OTP attempts, the user account is locked for 30 minutes."""
        # Create the user first so the lockout can be applied
        user = User(
            phone_number=PHONE_NUMBER,
            pin_hash=hash_pin(VALID_PIN),
            role=UserRole.customer,
            is_verified=False,
        )
        db.add(user)
        db.commit()

        for i in range(5):
            client.post("/auth/login", json={
                "phone_number": PHONE_NUMBER,
                "otp_code":     "000000",   # wrong every time
                "pin":          VALID_PIN,
            })

        db.refresh(user)
        assert user.otp_locked_until is not None
        assert user.otp_locked_until > datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /auth/login
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogin:

    @pytest.mark.auth
    def test_login_happy_path(self, client, existing_user, valid_otp_record):
        """Existing user logs in with correct OTP + PIN."""
        response = client.post("/auth/login", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["phone_number"] == PHONE_NUMBER

    @pytest.mark.auth
    def test_login_updates_last_login_at(self, client, db, existing_user, valid_otp_record):
        """Successful login updates last_login_at timestamp."""
        assert existing_user.last_login_at is None

        client.post("/auth/login", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })

        db.refresh(existing_user)
        assert existing_user.last_login_at is not None

    @pytest.mark.auth
    def test_login_wrong_pin(self, client, existing_user, valid_otp_record):
        """Correct OTP but wrong PIN is rejected."""
        response = client.post("/auth/login", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          "9999",
        })
        assert response.status_code == 401
        assert "PIN" in response.json()["detail"]

    @pytest.mark.auth
    def test_login_unregistered_phone(self, client, valid_otp_record):
        """Login attempt for a phone number that has no account."""
        response = client.post("/auth/login", json={
            "phone_number": PHONE_NUMBER2,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })
        assert response.status_code == 404
        assert "non enregistré" in response.json()["detail"]

    @pytest.mark.auth
    def test_login_suspended_account(self, client, db, existing_user, valid_otp_record):
        """Suspended accounts cannot log in."""
        existing_user.is_active = False
        db.commit()

        response = client.post("/auth/login", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })
        assert response.status_code == 403
        assert "suspendu" in response.json()["detail"]

    @pytest.mark.auth
    def test_login_locked_account(self, client, db, existing_user, valid_otp_record):
        """Locked accounts (too many OTP failures) cannot log in."""
        existing_user.otp_locked_until = datetime.now(timezone.utc) + timedelta(minutes=25)
        db.commit()

        response = client.post("/auth/login", json={
            "phone_number": PHONE_NUMBER,
            "otp_code":     VALID_OTP,
            "pin":          VALID_PIN,
        })
        assert response.status_code == 403
        assert "bloqué" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# GET /auth/me
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetMe:

    @pytest.mark.auth
    def test_get_me_valid_token(self, client, existing_user, auth_headers):
        """Valid token returns user profile."""
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["phone_number"] == PHONE_NUMBER
        assert "pin_hash" not in data        # never exposed
        assert data["role"] == "customer"

    @pytest.mark.auth
    def test_get_me_no_token(self, client):
        """Request without Authorization header is rejected."""
        response = client.get("/auth/me")
        assert response.status_code == 403

    @pytest.mark.auth
    def test_get_me_invalid_token(self, client):
        """Malformed token is rejected."""
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.token"}
        )
        assert response.status_code == 401

    @pytest.mark.auth
    def test_get_me_suspended_account(self, client, db, existing_user, auth_headers):
        """Suspended user's token is rejected even if the token itself is valid."""
        existing_user.is_active = False
        db.commit()

        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 403
        assert "suspendu" in response.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# POST /auth/pin/change
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangePIN:

    @pytest.mark.auth
    def test_change_pin_success(self, client, db, existing_user, auth_headers):
        """Correct current PIN + valid new PIN → PIN is updated."""
        new_pin = "8527"
        response = client.post("/auth/pin/change", json={
            "current_pin": VALID_PIN,
            "new_pin":     new_pin,
        }, headers=auth_headers)

        assert response.status_code == 200
        assert "succès" in response.json()["message"]

        # Verify PIN hash was updated in DB
        db.refresh(existing_user)
        from app.core.security import verify_pin
        assert verify_pin(new_pin, existing_user.pin_hash)

    @pytest.mark.auth
    def test_change_pin_wrong_current(self, client, existing_user, auth_headers):
        """Wrong current PIN is rejected."""
        response = client.post("/auth/pin/change", json={
            "current_pin": "0000",
            "new_pin":     "8527",
        }, headers=auth_headers)
        assert response.status_code == 401

    @pytest.mark.auth
    @pytest.mark.parametrize("weak_pin", ["1234", "0000", "9999"])
    def test_change_pin_weak_new_pin(self, client, existing_user, auth_headers, weak_pin):
        """Weak new PINs are rejected by Pydantic before reaching the service."""
        response = client.post("/auth/pin/change", json={
            "current_pin": VALID_PIN,
            "new_pin":     weak_pin,
        }, headers=auth_headers)
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# GET /health
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:

    def test_health_check(self, client):
        """Health endpoint returns 200 and status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["app"] == "Njangui"
