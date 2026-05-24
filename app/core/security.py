"""
Security utilities for Njangui.

What lives here:
  - PIN hashing / verification (bcrypt, cost factor 12)
  - OTP hashing / verification (bcrypt, same context)
  - OTP generation (6-digit, cryptographically random)
  - JWT creation / decoding
  - FastAPI dependency: get_current_user
"""

import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db

# ── bcrypt context ────────────────────────────────────────────────────────────
# Cost factor 12 = 2^12 = 4096 iterations.
# ~250ms per hash on modern hardware — slow enough to deter brute force,
# fast enough that users don't notice during login.
# Used for BOTH 4-digit PINs and 6-digit OTP codes.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

# ── JWT bearer scheme ─────────────────────────────────────────────────────────
bearer_scheme = HTTPBearer()


# ═══════════════════════════════════════════════════════════════════════════════
# PIN utilities
# ═══════════════════════════════════════════════════════════════════════════════

def hash_pin(pin: str) -> str:
    """
    Hash a 4-digit PIN with bcrypt (cost factor 12).
    Returns a 60-character hash string stored in users.pin_hash.
    The raw PIN is NEVER stored anywhere.
    """
    return pwd_context.hash(pin)


def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """
    Compare a plain PIN against a stored bcrypt hash.
    Returns True if they match, False otherwise.
    Timing-safe — takes the same time whether correct or not.
    """
    return pwd_context.verify(plain_pin, hashed_pin)


# ═══════════════════════════════════════════════════════════════════════════════
# OTP utilities
# ═══════════════════════════════════════════════════════════════════════════════

def generate_otp() -> str:
    """
    Generate a cryptographically random 6-digit OTP.
    Uses secrets module via random.SystemRandom for proper randomness.
    Returns a zero-padded string: e.g. "047382"
    """
    return "".join(random.SystemRandom().choices(string.digits, k=6))


def hash_otp(otp: str) -> str:
    """
    Hash a 6-digit OTP with bcrypt for storage in otp_codes.code_hash.
    The raw OTP is NEVER stored — only the hash.
    """
    return pwd_context.hash(otp)


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """
    Compare a plain OTP string against its stored bcrypt hash.
    Returns True if they match, False otherwise.
    """
    return pwd_context.verify(plain_otp, hashed_otp)


# ═══════════════════════════════════════════════════════════════════════════════
# JWT utilities
# ═══════════════════════════════════════════════════════════════════════════════

def create_access_token(user_id: str, phone_number: str, role: str) -> str:
    """
    Create a signed JWT token for an authenticated user.

    Payload contains:
      - sub  : user UUID (the subject — standard JWT claim)
      - phone: phone number for quick lookups
      - role : customer | provider | both (drives UI toggle)
      - exp  : expiry timestamp (7 days from now)

    Signed with SECRET_KEY using HS256 algorithm.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub":   user_id,
        "phone": phone_number,
        "role":  role,
        "exp":   expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Raises HTTPException 401 if the token is invalid or expired.
    Returns the decoded payload dict on success.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré. Veuillez vous reconnecter.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI dependency: get_current_user
# ═══════════════════════════════════════════════════════════════════════════════

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """
    FastAPI dependency injected into any protected route.

    Usage in a router:
        @router.get("/me")
        def get_me(current_user = Depends(get_current_user)):
            return current_user

    Flow:
      1. Extracts Bearer token from Authorization header
      2. Decodes and validates JWT
      3. Loads User from DB by UUID (ensures account still active)
      4. Returns the User ORM object
    """
    # Import here to avoid circular imports (models → security → models)
    from app.models.user import User

    payload = decode_access_token(credentials.credentials)

    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide — identifiant manquant.",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Compte introuvable.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte suspendu. Contactez le support Njangui.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte non vérifié. Complétez la vérification OTP.",
        )

    return user


def get_current_verified_provider(
    current_user=Depends(get_current_user),
):
    """
    Stricter dependency — ensures the user has a provider role.
    Used on provider-only endpoints (e.g. editing provider profile).
    """
    from app.models.user import UserRole
    if current_user.role == UserRole.customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux prestataires enregistrés.",
        )
    return current_user
