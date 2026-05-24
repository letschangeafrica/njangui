import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProviderProfile(Base):
    """
    Extended profile data for users who have completed provider registration.
    One-to-one with the Users table.
    Separated from Users to keep the authentication table lean and fast.

    confirmed_tx_count, thumbs_up_count, thumbs_down_count are DENORMALISED counters.
    They are updated by PostgreSQL TRIGGERS (defined in Alembic migration) — NOT by
    application code. This avoids COUNT() queries on the hot search path, which is
    critical for performance on 2G connections.
    """
    __tablename__ = "provider_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        unique=True,   # UNIQUE enforces one phone number = one provider profile
        nullable=False,
        comment="One-to-one with Users. UNIQUE = one phone cannot have two provider profiles.",
    )

    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Provider display name as they enter it. Shown in search results.",
    )

    id_card_photo_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Cloudinary URL of national ID card photo. NULLABLE during pilot phase.",
    )

    id_card_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
        comment="Manually set TRUE by admin after reviewing ID card. Shows verified badge.",
    )

    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False,
        comment="Primary service category. Required at registration. Drives search filtering.",
    )

    sub_category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sub_categories.id"),
        nullable=False,
        comment="Primary sub-category. Must be valid child of category_id.",
    )

    location_node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("location_nodes.id"),
        nullable=False,
        comment="Selected from the 16 predefined Yaoundé nodes. NOT free text.",
    )

    is_mobile_provider: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
        comment="TRUE = provider travels to customer (moto-taxi, mobile repair). Badge in search.",
    )

    offers_delivery: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
        comment="TRUE = provider ships physical goods. Enables delivery filter in search.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
        comment="Soft delete flag. FALSE hides from search without deleting records.",
    )

    suspension_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Admin note if account is suspended. Used for fraud review workflow.",
    )

    # ── Denormalized counters (updated by DB triggers, not application code) ─
    confirmed_tx_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="DENORMALISED. Updated by trigger on transaction confirmation. Avoids COUNT().",
    )

    thumbs_up_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="DENORMALISED. Updated by trigger on rating insertion. Used for ranking formula.",
    )

    thumbs_down_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="DENORMALISED. Paired with thumbs_up_count for satisfaction rate calculation.",
    )

    created_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
    )

    updated_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
        comment="Updated on every profile change. Useful for cache invalidation.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="provider_profile")
    category: Mapped["Category"] = relationship("Category", back_populates="provider_profiles")
    sub_category: Mapped["SubCategory"] = relationship(
        "SubCategory", back_populates="provider_profiles"
    )
    location_node: Mapped["LocationNode"] = relationship(
        "LocationNode", back_populates="provider_profiles"
    )

    @property
    def satisfaction_rate(self) -> float | None:
        """Returns thumbs-up percentage. None if no ratings yet."""
        total = self.thumbs_up_count + self.thumbs_down_count
        if total == 0:
            return None
        return round((self.thumbs_up_count / total) * 100, 1)

    def __repr__(self) -> str:
        return f"<ProviderProfile name={self.full_name} tx={self.confirmed_tx_count}>"
