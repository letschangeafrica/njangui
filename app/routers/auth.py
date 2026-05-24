"""
Auth router — HTTP layer for authentication endpoints.

This file handles ONLY the HTTP concerns:
  - Route definitions
  - Request/response schemas
  - Calling the service layer
  - Returning the right HTTP status codes

All business logic lives in app/services/auth_service.py.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.database import get_db
from app.schemas.auth import (
    ChangePINIn,
    LoginIn,
    MessageOut,
    OTPRequestedOut,
    RegisterIn,
    RequestOTPIn,
    TokenOut,
    UserOut,
)
from app.services import auth_service

router = APIRouter()


# ── POST /auth/otp/request ────────────────────────────────────────────────────
@router.post(
    "/otp/request",
    response_model=OTPRequestedOut,
    status_code=status.HTTP_200_OK,
    summary="Request an OTP",
    description=(
        "Step 1 for both registration and login. "
        "Sends a 6-digit OTP to the provided Cameroonian phone number. "
        "Rate limited to 3 requests per phone per hour. "
        "OTP expires in 10 minutes."
    ),
)
def request_otp(
    body: RequestOTPIn,
    db: Session = Depends(get_db),
):
    # In development: return the OTP in the response for easy testing
    # In production: DEBUG is False → OTP never appears in response
    debug_mode = settings.DEBUG or settings.ENVIRONMENT == "development"
    return auth_service.request_otp(
        phone_number=body.phone_number,
        db=db,
        debug=debug_mode,
    )


# ── POST /auth/register ───────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Step 2 for NEW users. "
        "Verifies the OTP from /otp/request, creates the account with a 4-digit PIN, "
        "and returns a JWT token. "
        "The user starts as role='customer'. "
        "Provider registration is a separate step (POST /providers/register)."
    ),
)
def register(
    body: RegisterIn,
    db: Session = Depends(get_db),
):
    return auth_service.register_user(data=body, db=db)


# ── POST /auth/login ──────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Login an existing user",
    description=(
        "Step 2 for EXISTING users. "
        "Verifies the OTP from /otp/request AND the 4-digit PIN. "
        "Both must be correct. Returns a JWT token valid for 7 days."
    ),
)
def login(
    body: LoginIn,
    db: Session = Depends(get_db),
):
    return auth_service.login_user(data=body, db=db)


# ── GET /auth/me ──────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Get current user",
    description=(
        "Returns the authenticated user's profile. "
        "Requires a valid Bearer token in the Authorization header. "
        "Used by the mobile app on startup to restore session state."
    ),
)
def get_me(
    current_user=Depends(get_current_user),
):
    return UserOut.model_validate(current_user)


# ── POST /auth/pin/change ─────────────────────────────────────────────────────
@router.post(
    "/pin/change",
    response_model=MessageOut,
    status_code=status.HTTP_200_OK,
    summary="Change PIN",
    description=(
        "Allows an authenticated user to change their 4-digit PIN. "
        "Current PIN must be provided and correct."
    ),
)
def change_pin(
    body: ChangePINIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_pin(
        current_user=current_user,
        current_pin=body.current_pin,
        new_pin=body.new_pin,
        db=db,
    )
    return MessageOut(message="PIN mis à jour avec succès.")
