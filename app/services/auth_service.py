"""
Auth service — all authentication business logic lives here.

Routers call these functions. Routers handle HTTP. Services handle logic.
This separation makes the logic testable without spinning up a web server.

Functions:
  - request_otp()   : rate-check, generate, hash, store, (send SMS)
  - _verify_otp()   : internal helper — find + verify + consume OTP record
  - register_user() : verify OTP → create user → return JWT
  - login_user()    : verify OTP → verify PIN → update last_login → return JWT
  - change_pin()    : verify current PIN → update hash
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    generate_otp,
    hash_otp,
    hash_pin,
    verify_otp,
    verify_pin,
)
from app.models.otp_code import OtpCode
from app.models.user import User, UserRole
from app.schemas.auth import RegisterIn, LoginIn, OTPRequestedOut, TokenOut, UserOut

# ── Constants ─────────────────────────────────────────────────────────────────
OTP_EXPIRY_SECONDS       = 600     # 10 minutes
OTP_RATE_LIMIT_PER_HOUR  = 3      # max OTP requests per phone per hour
OTP_MAX_ATTEMPTS         = 5      # failed attempts before account lockout
ACCOUNT_LOCKOUT_MINUTES  = 30     # lockout duration after OTP_MAX_ATTEMPTS failures


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Request OTP
# ═══════════════════════════════════════════════════════════════════════════════

def request_otp(phone_number: str, db: Session, debug: bool = False) -> OTPRequestedOut:
    """
    Generate and store an OTP for the given phone number.

    Rate limiting: max 3 requests per phone per hour.
    If exceeded → HTTP 429.

    The OTP is hashed before storage (bcrypt cost 12).
    In production: the plain OTP is sent via SMS and immediately discarded.
    In debug/dev mode: the plain OTP is returned in the response for testing.
    """
    _check_otp_rate_limit(phone_number, db)

    plain_otp = generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_EXPIRY_SECONDS)

    otp_record = OtpCode(
        phone_number=phone_number,
        code_hash=hash_otp(plain_otp),
        expires_at=expires_at,
    )
    db.add(otp_record)
    db.commit()

    # TODO: replace with real SMS gateway call (Twilio / local Cameroonian provider)
    # _send_sms(phone_number, f"Votre code Njangui: {plain_otp}. Valide 10 minutes.")
    _log_otp_dev(phone_number, plain_otp)

    return OTPRequestedOut(
        message=f"Code OTP envoyé au {phone_number}. Valide 10 minutes.",
        expires_in=OTP_EXPIRY_SECONDS,
        debug_otp=plain_otp if debug else None,
    )


def _check_otp_rate_limit(phone_number: str, db: Session) -> None:
    """
    Count OTP requests from this phone in the last hour.
    Raises HTTP 429 if limit exceeded.
    Uses idx_otp_phone_created index — fast even under load.
    """
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_count = (
        db.query(func.count(OtpCode.id))
        .filter(
            OtpCode.phone_number == phone_number,
            OtpCode.created_at >= one_hour_ago,
        )
        .scalar()
    )
    if recent_count >= OTP_RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Trop de tentatives. Maximum {OTP_RATE_LIMIT_PER_HOUR} codes "
                f"par heure. Réessayez dans quelques minutes."
            ),
        )


def _log_otp_dev(phone_number: str, otp: str) -> None:
    """Development-only logger. Remove/disable in production."""
    print(f"\n{'='*50}")
    print(f"[DEV] OTP for {phone_number}: {otp}")
    print(f"{'='*50}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Internal — Verify and consume an OTP
# ═══════════════════════════════════════════════════════════════════════════════

def _verify_and_consume_otp(phone_number: str, plain_otp: str, db: Session) -> None:
    """
    Find the most recent valid OTP for this phone, verify it, and mark it used.

    Raises HTTP 400 with specific messages for:
    - No valid OTP found (never requested or all expired)
    - Wrong code (increments attempt_count; locks account at OTP_MAX_ATTEMPTS)
    - OTP already used

    On success: sets otp_record.is_used = True and commits.
    """
    now = datetime.now(timezone.utc)

    # Find the most recent unused, unexpired OTP for this phone
    otp_record: Optional[OtpCode] = (
        db.query(OtpCode)
        .filter(
            OtpCode.phone_number == phone_number,
            OtpCode.is_used      == False,          # noqa: E712
            OtpCode.expires_at   >  now,
        )
        .order_by(OtpCode.created_at.desc())
        .first()
    )

    if otp_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun code OTP valide trouvé. Demandez un nouveau code.",
        )

    # Check attempt count before verifying (avoid timing oracle)
    if otp_record.attempt_count >= OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code OTP bloqué après trop de tentatives. Demandez un nouveau code.",
        )

    # Verify the hash
    if not verify_otp(plain_otp, otp_record.code_hash):
        otp_record.attempt_count += 1

        # Lock the user account if they've hit the attempt limit
        if otp_record.attempt_count >= OTP_MAX_ATTEMPTS:
            user = db.query(User).filter(User.phone_number == phone_number).first()
            if user:
                user.otp_locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=ACCOUNT_LOCKOUT_MINUTES
                )

        db.commit()
        remaining = OTP_MAX_ATTEMPTS - otp_record.attempt_count
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Code OTP incorrect. {remaining} tentative(s) restante(s).",
        )

    # OTP is valid — mark as used
    otp_record.is_used = True
    db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2a — Register new user
# ═══════════════════════════════════════════════════════════════════════════════

def register_user(data: RegisterIn, db: Session) -> TokenOut:
    """
    Create a new user account.

    Flow:
      1. Verify OTP (raises if invalid)
      2. Check phone number not already registered
      3. Create User with hashed PIN
      4. Return JWT token

    The user starts as role='customer'. They can register as a provider
    separately (which creates a ProviderProfile and updates role to 'provider' or 'both').
    """
    # 1. Verify and consume OTP
    _verify_and_consume_otp(data.phone_number, data.otp_code, db)

    # 2. Check phone not already registered
    existing = db.query(User).filter(User.phone_number == data.phone_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ce numéro est déjà enregistré. "
                "Utilisez 'Connexion' si vous avez déjà un compte."
            ),
        )

    # 3. Create user
    user = User(
        phone_number=data.phone_number,
        pin_hash=hash_pin(data.pin),
        role=UserRole.customer,
        is_verified=True,     # OTP was just verified — account is verified at creation
        language=data.language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 4. Return JWT
    token = create_access_token(
        user_id=str(user.id),
        phone_number=user.phone_number,
        role=user.role.value,
    )

    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2b — Login existing user
# ═══════════════════════════════════════════════════════════════════════════════

def login_user(data: LoginIn, db: Session) -> TokenOut:
    """
    Authenticate an existing user.

    Flow:
      1. Find user by phone number
      2. Check account status (active, not locked)
      3. Verify OTP
      4. Verify PIN
      5. Update last_login_at
      6. Return JWT

    Both OTP and PIN must be correct.
    OTP proves phone ownership. PIN proves identity.
    """
    # 1. Find user
    user: Optional[User] = (
        db.query(User).filter(User.phone_number == data.phone_number).first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Numéro non enregistré. "
                "Créez un compte avec 'Inscription'."
            ),
        )

    # 2. Check account status
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte suspendu. Contactez le support Njangui.",
        )

    now = datetime.now(timezone.utc)
    if user.otp_locked_until and user.otp_locked_until > now:
        minutes_left = int((user.otp_locked_until - now).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Compte temporairement bloqué après trop de tentatives. "
                f"Réessayez dans {minutes_left} minute(s)."
            ),
        )

    # 3. Verify and consume OTP
    _verify_and_consume_otp(data.phone_number, data.otp_code, db)

    # 4. Verify PIN
    if not verify_pin(data.pin, user.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN incorrect.",
        )

    # 5. Update last_login_at and reset lockout
    user.last_login_at    = now
    user.otp_locked_until = None
    user.otp_attempts     = 0
    db.commit()
    db.refresh(user)

    # 6. Return JWT
    token = create_access_token(
        user_id=str(user.id),
        phone_number=user.phone_number,
        role=user.role.value,
    )

    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Change PIN (authenticated action)
# ═══════════════════════════════════════════════════════════════════════════════

def change_pin(current_user: User, current_pin: str, new_pin: str, db: Session) -> None:
    """
    Update a user's PIN.
    Requires the current PIN to be provided and correct.
    The new PIN is validated by the Pydantic schema before reaching here.
    """
    if not verify_pin(current_pin, current_user.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN actuel incorrect.",
        )

    current_user.pin_hash = hash_pin(new_pin)
    db.commit()
