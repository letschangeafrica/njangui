import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TransactionStatus(str, enum.Enum):
    """
    Lifecycle of a transaction.
    CRITICAL: Once status = 'confirmed', it is IMMUTABLE.
    The ledger is permanent — confirmed transactions cannot be updated or deleted.
    This immutability is what makes the reputation system trustworthy enough
    to form the basis of a credit identity.
    """
    pending   = "pending"    # Initiated, waiting for both parties to confirm
    confirmed = "confirmed"  # Both confirmed within 24h — IMMUTABLE from this point
    expired   = "expired"    # 24h window passed — set by Celery sweep every 15 minutes
    disputed  = "disputed"   # Flagged for admin review


class Transaction(Base):
    """
    The core reputation ledger.
    Every confirmed transaction is a permanent, immutable record.

    The Mutual Handshake:
    - Either party (provider OR customer) initiates by entering amount + sub-category
    - The transaction stays 'pending' until the OTHER party confirms within 24 hours
    - A Celery background task sweeps every 15 minutes to expire stale pending transactions

    Fraud constraints enforced at BOTH application layer AND database layer:
    - Rule A: max 10 confirmed tx per provider per 24-hour cycle
    - Rule B: max 3 confirmed tx between same provider-customer pair per rolling 7 days
    - Self-transaction: CHECK (provider_id != customer_id) — cannot be bypassed
    """
    __tablename__ = "transactions"

    __table_args__ = (
        # Self-transaction prevention — database-level, cannot be bypassed by application
        CheckConstraint("provider_id != customer_id", name="chk_no_self_transaction"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="UUID primary key. Prevents enumeration.",
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="The provider party. Must have role = provider or both.",
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="The customer party.",
    )

    sub_category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sub_categories.id"),
        nullable=False,
        comment="Service sub-category. Critical for price intelligence aggregation.",
    )

    amount_xaf: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Transaction amount in XAF. INTEGER is exact for currency — NEVER FLOAT.",
    )

    initiated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="Which party (provider or customer) created this transaction record.",
    )

    initiated_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
        comment="When the transaction was initiated. Confirmation window calculated from this.",
    )

    provider_confirmed_at: Mapped[TIMESTAMPTZ | None] = mapped_column(
        TIMESTAMPTZ,
        nullable=True,
        comment="Timestamp of provider confirmation tap. NULL = not yet confirmed by provider.",
    )

    customer_confirmed_at: Mapped[TIMESTAMPTZ | None] = mapped_column(
        TIMESTAMPTZ,
        nullable=True,
        comment="Timestamp of customer confirmation tap. NULL = not yet confirmed by customer.",
    )

    expires_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        comment="Set to initiated_at + 24 hours. Celery task checks this to expire transactions.",
    )

    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status_enum", create_type=True),
        nullable=False,
        default=TransactionStatus.pending,
        server_default=TransactionStatus.pending.value,
        comment="Once 'confirmed', status is IMMUTABLE. The ledger is permanent.",
    )

    is_mobile_money_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
        comment="TRUE when MTN MoMo API cross-reference confirms matching transfer. Phase 3.",
    )

    location_node_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("location_nodes.id"),
        nullable=True,
        comment="Neighbourhood where transaction occurred. Inherited from provider profile.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    provider: Mapped["User"] = relationship(
        "User", foreign_keys=[provider_id], back_populates="transactions_as_provider"
    )
    customer: Mapped["User"] = relationship(
        "User", foreign_keys=[customer_id], back_populates="transactions_as_customer"
    )
    initiator: Mapped["User"] = relationship(
        "User", foreign_keys=[initiated_by]
    )
    sub_category: Mapped["SubCategory"] = relationship(
        "SubCategory", back_populates="transactions"
    )
    location_node: Mapped["LocationNode"] = relationship(
        "LocationNode", back_populates="transactions"
    )
    rating: Mapped["Rating"] = relationship(
        "Rating", back_populates="transaction", uselist=False
    )

    @property
    def is_confirmed(self) -> bool:
        return self.status == TransactionStatus.confirmed

    @property
    def is_fully_confirmed(self) -> bool:
        """Both parties have tapped confirm."""
        return (
            self.provider_confirmed_at is not None
            and self.customer_confirmed_at is not None
        )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} amount={self.amount_xaf} XAF status={self.status}>"
