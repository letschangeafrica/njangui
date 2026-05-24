from sqlalchemy import Boolean, Index, Integer, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OtpCode(Base):
    """
    Temporary OTP code storage.

    Redis is PREFERRED for production (auto-TTL, no cleanup job needed).
    This table serves as the PostgreSQL fallback during MVP phase.

    TTL is enforced by:
    1. expires_at field checked at verification time
    2. A scheduled Celery cleanup job that deletes expired/used rows

    Rate limiting: max 3 OTP requests per phone number per hour.
    This is checked via idx_otp_phone_created index on (phone_number, created_at).

    After 5 failed verification attempts on a single OTP code:
    → parent user account is locked (users.otp_locked_until = NOW() + 30 minutes)
    """
    __tablename__ = "otp_codes"

    __table_args__ = (
        # idx_otp_phone_created: rate limiting query — count OTP requests per phone in last hour
        Index("idx_otp_phone_created", "phone_number", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Integer PK for OTP records.",
    )

    phone_number: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        comment=(
            "The phone number this OTP was sent to. "
            "No FK constraint — OTPs can be requested before a User record exists "
            "(first step of registration flow)."
        ),
    )

    code_hash: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="bcrypt hash of the 6-digit OTP. NEVER stored plain. Compared at verification.",
    )

    expires_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        comment="Set to NOW() + 10 minutes. Expired codes are rejected and cleaned up.",
    )

    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
        comment="Set TRUE immediately after successful verification. Used codes are rejected.",
    )

    attempt_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Incremented on each failed attempt. At 5: lock the parent user account.",
    )

    created_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
        comment="Creation timestamp. Used for rate limiting: max 3 OTP requests per phone per hour.",
    )

    def __repr__(self) -> str:
        return f"<OtpCode phone={self.phone_number} used={self.is_used} expires={self.expires_at}>"
