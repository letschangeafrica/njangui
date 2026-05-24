"""
Pydantic schemas for the authentication flow.

Pydantic validates every incoming request automatically.
If a field fails validation, FastAPI returns HTTP 422 before the code even runs.

Schemas are separate from SQLAlchemy models:
  - SQLAlchemy models   = what lives in the database
  - Pydantic schemas    = what travels over the API (requests and responses)
"""

import re
import uuid
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


# ── Shared validators ─────────────────────────────────────────────────────────

CAMEROON_PHONE_REGEX = re.compile(r"^\+237[0-9]{9}$")


def validate_cameroon_phone(phone: str) -> str:
    """
    Validates Cameroonian phone format: +237 followed by 9 digits.
    Covers MTN (+237 6XX), Orange (+237 6XX), Camtel (+237 2XX).
    """
    phone = phone.strip()
    if not CAMEROON_PHONE_REGEX.match(phone):
        raise ValueError(
            "Numéro invalide. Format requis: +237XXXXXXXXX (9 chiffres après +237)"
        )
    return phone


def validate_pin(pin: str) -> str:
    """
    4-digit numeric PIN only.
    Common sequences (1234, 0000) are blocked — too easy to guess.
    """
    pin = pin.strip()
    if not pin.isdigit() or len(pin) != 4:
        raise ValueError("Le PIN doit contenir exactement 4 chiffres.")
    blocked = {"1234", "0000", "1111", "2222", "3333", "4444",
               "5555", "6666", "7777", "8888", "9999", "0123", "4321"}
    if pin in blocked:
        raise ValueError("Ce PIN est trop simple. Choisissez un PIN plus sécurisé.")
    return pin


def validate_otp(otp: str) -> str:
    """6-digit numeric OTP."""
    otp = otp.strip()
    if not otp.isdigit() or len(otp) != 6:
        raise ValueError("Le code OTP doit contenir exactement 6 chiffres.")
    return otp


# ═══════════════════════════════════════════════════════════════════════════════
# Request schemas (incoming data from mobile app)
# ═══════════════════════════════════════════════════════════════════════════════

class RequestOTPIn(BaseModel):
    """Step 1 of both registration and login flows."""
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def phone_must_be_cameroonian(cls, v: str) -> str:
        return validate_cameroon_phone(v)

    model_config = {"json_schema_extra": {
        "example": {"phone_number": "+237612345678"}
    }}


class RegisterIn(BaseModel):
    """
    Step 2 for NEW users.
    Combines OTP verification + PIN creation in one request
    to minimise round trips on 2G connections.
    """
    phone_number: str
    otp_code:     str
    pin:          str
    language:     str = "fr"

    @field_validator("phone_number")
    @classmethod
    def phone_valid(cls, v: str) -> str:
        return validate_cameroon_phone(v)

    @field_validator("otp_code")
    @classmethod
    def otp_valid(cls, v: str) -> str:
        return validate_otp(v)

    @field_validator("pin")
    @classmethod
    def pin_valid(cls, v: str) -> str:
        return validate_pin(v)

    @field_validator("language")
    @classmethod
    def language_valid(cls, v: str) -> str:
        if v not in ("fr", "en"):
            raise ValueError("Langue non supportée. Valeurs acceptées: 'fr', 'en'.")
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "phone_number": "+237612345678",
            "otp_code":     "847291",
            "pin":          "5923",
            "language":     "fr",
        }
    }}


class LoginIn(BaseModel):
    """
    Step 2 for EXISTING users.
    OTP proves phone ownership. PIN proves identity.
    Both must be correct — neither alone is enough.
    """
    phone_number: str
    otp_code:     str
    pin:          str

    @field_validator("phone_number")
    @classmethod
    def phone_valid(cls, v: str) -> str:
        return validate_cameroon_phone(v)

    @field_validator("otp_code")
    @classmethod
    def otp_valid(cls, v: str) -> str:
        return validate_otp(v)

    @field_validator("pin")
    @classmethod
    def pin_valid(cls, v: str) -> str:
        pin = v.strip()
        if not pin.isdigit() or len(pin) != 4:
            raise ValueError("Le PIN doit contenir exactement 4 chiffres.")
        return pin

    model_config = {"json_schema_extra": {
        "example": {
            "phone_number": "+237612345678",
            "otp_code":     "847291",
            "pin":          "5923",
        }
    }}


class ChangePINIn(BaseModel):
    """Allows a logged-in user to change their PIN."""
    current_pin: str
    new_pin:     str

    @field_validator("current_pin")
    @classmethod
    def current_pin_valid(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 4:
            raise ValueError("PIN actuel invalide.")
        return v

    @field_validator("new_pin")
    @classmethod
    def new_pin_valid(cls, v: str) -> str:
        return validate_pin(v)


# ═══════════════════════════════════════════════════════════════════════════════
# Response schemas (what the API sends back)
# ═══════════════════════════════════════════════════════════════════════════════

class OTPRequestedOut(BaseModel):
    """Returned after a successful OTP send."""
    message:          str
    expires_in:       int   # seconds until OTP expires (always 600 = 10 minutes)
    # In development mode, the OTP is returned here for testing.
    # In production this field is NEVER populated.
    debug_otp: Optional[str] = None


class UserOut(BaseModel):
    """Safe user representation — never exposes pin_hash or sensitive fields."""
    id:           uuid.UUID
    phone_number: str
    role:         str
    is_verified:  bool
    language:     str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    """Returned after successful registration or login."""
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut

    model_config = {"json_schema_extra": {
        "example": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type":   "bearer",
            "user": {
                "id":           "a1b2c3d4-...",
                "phone_number": "+237612345678",
                "role":         "customer",
                "is_verified":  True,
                "language":     "fr",
            }
        }
    }}


class MessageOut(BaseModel):
    """Generic success message response."""
    message: str
