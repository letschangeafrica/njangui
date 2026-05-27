import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SAEnum, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    """
    Drives the UI toggle between 'Je suis Client' and 'Je suis Prestataire'.
    - customer : default on registration
    - provider : unlocked after provider profile registration is complete
    - both     : a user who has completed provider registration but also transacts as customer
    """
    customer = "customer"
    provider = "provider"
    both = "both"


class User(Base):
    """
    Master identity table.
    Every phone number in the system — whether provider, customer, or both —
    creates exactly ONE User record. This is the Unified Single-Identity Account Model.

    UUID primary key prevents enumeration attacks (no sequential IDs exposed to the API).
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID prevents enumeration attacks — no sequential IDs exposed to API.",
    )

    phone_number: Mapped[str] = mapped_column(
        String(15),
        unique=True,
        nullable=False,
        index=True,  # idx_users_phone — critical path for every auth request
        comment="Cameroonian format: +237XXXXXXXXX. The single source of identity.",
    )

    pin_hash: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="bcrypt hash of the 4-digit PIN. Never stored in plain text. Cost factor 12.",
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role_enum", create_type=False),
        nullable=False,
        default=UserRole.customer,
        server_default=UserRole.customer.value,
        comment="Values: customer, provider, both. Updated when provider registration completes.",
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
        comment="Set TRUE after successful OTP verification. Unverified accounts cannot transact.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
        comment="Soft delete flag. FALSE suspends the account without destroying data integrity.",
    )

    otp_attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Tracks failed OTP attempts. Resets after successful auth or lockout expiry.",
    )

    otp_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="If not NULL and in future: account is locked. Set to NOW() + 30min after 5 failures.",
    )

    language: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        default="fr",
        server_default=text("'fr'"),
        comment="UI language. Values: 'fr' (French), 'en' (English). Set once at onboarding.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        comment="Account creation timestamp. UTC always. Used for cohort analysis.",
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Updated on every successful authentication. Used to identify inactive accounts.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    provider_profile: Mapped["ProviderProfile"] = relationship(
        "ProviderProfile",
        back_populates="user",
        uselist=False,  # one-to-one
        cascade="all, delete-orphan",
    )
    # otp_codes has no FK back to users (OTPs exist before the user record does)
    # Query them directly: db.query(OtpCode).filter(OtpCode.phone_number == user.phone_number)
    transactions_as_provider: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="Transaction.provider_id",
        back_populates="provider",
    )
    transactions_as_customer: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        foreign_keys="Transaction.customer_id",
        back_populates="customer",
    )
    fraud_flags_submitted: Mapped[list["FraudFlag"]] = relationship(
        "FraudFlag",
        foreign_keys="FraudFlag.flagged_by",
        back_populates="reporter",
    )
    fraud_flags_received: Mapped[list["FraudFlag"]] = relationship(
        "FraudFlag",
        foreign_keys="FraudFlag.flagged_provider_id",
        back_populates="flagged_provider",
    )

    def __repr__(self) -> str:
        return f"<User phone={self.phone_number} role={self.role}>"
