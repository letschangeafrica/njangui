import enum
import uuid

from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FraudFlagStatus(str, enum.Enum):
    """
    Admin review workflow for fraud reports.
    - pending          : submitted by customer, awaiting admin review
    - reviewed_valid   : admin confirmed it is genuine fraud → provider stays suspended
    - reviewed_invalid : admin dismissed it → provider account restored
    """
    pending          = "pending"
    reviewed_valid   = "reviewed_valid"
    reviewed_invalid = "reviewed_invalid"


class FraudFlag(Base):
    """
    Customer-submitted fraud reports.

    Auto-suspension rule (enforced by DB trigger defined in Alembic migration):
    3 pending flags from 3 SEPARATE eligible customer accounts
    → provider is_active set to FALSE automatically
    → admin queue entry created with priority = HIGH

    Eligibility requirement: the flagging customer must have confirmed_tx_count >= 10.
    This prevents new fake accounts from weaponizing the flag system.

    UNIQUE(flagged_provider_id, flagged_by): one customer can only flag a given
    provider once — prevents harassment through repeated flagging.
    """
    __tablename__ = "fraud_flags"

    __table_args__ = (
        UniqueConstraint(
            "flagged_provider_id",
            "flagged_by",
            name="uq_fraud_flag_one_per_customer",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    flagged_provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="The provider being reported.",
    )

    flagged_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="The customer submitting the flag. Must have confirmed_tx_count >= 10.",
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional free-text reason from the customer. Reviewed by admin.",
    )

    status: Mapped[FraudFlagStatus] = mapped_column(
        SAEnum(FraudFlagStatus, name="fraud_flag_status_enum", create_type=False),
        nullable=False,
        default=FraudFlagStatus.pending,
        server_default=FraudFlagStatus.pending.value,
        comment="Admin updates after manual review.",
    )

    admin_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal admin note after review. NEVER shown to either party.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    flagged_provider: Mapped["User"] = relationship(
        "User",
        foreign_keys=[flagged_provider_id],
        back_populates="fraud_flags_received",
    )
    reporter: Mapped["User"] = relationship(
        "User",
        foreign_keys=[flagged_by],
        back_populates="fraud_flags_submitted",
    )

    def __repr__(self) -> str:
        return f"<FraudFlag provider={self.flagged_provider_id} status={self.status}>"
