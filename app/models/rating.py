import enum
import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, text
from sqlalchemy.dialects.postgresql import TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RatingValue(str, enum.Enum):
    """
    Deliberately binary. No star ratings, no text reviews.

    Why binary?
    - Star ratings introduce interpretation ambiguity (is 3 stars good or bad?)
    - Text reviews require moderation infrastructure
    - A thumbs up or thumbs down is unambiguous in any language and any literacy level
    - It maps exactly to what providers said they want: "sérieux ou pas sérieux"

    thumbs_up   → increments provider_profiles.thumbs_up_count (via DB trigger)
    thumbs_down → increments provider_profiles.thumbs_down_count (via DB trigger)
    """
    thumbs_up   = "thumbs_up"
    thumbs_down = "thumbs_down"


class Rating(Base):
    """
    One rating per confirmed transaction, submitted ONLY by the customer.

    IMMUTABILITY RULE:
    Once a rating is inserted, no UPDATE or DELETE is permitted — ever.
    The UNIQUE constraint on transaction_id means one rating per transaction forever.
    If a customer claims they submitted the wrong rating: ratings are final.

    The trigger that updates provider_profiles counters is defined in the
    Alembic migration — not here. SQLAlchemy models describe structure only.
    """
    __tablename__ = "ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id"),
        unique=True,   # UNIQUE = one rating per transaction, forever
        nullable=False,
        comment="UNIQUE enforces one rating per transaction. Cannot be changed after submission.",
    )

    rated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="Must match the customer_id on the referenced transaction. Enforced at app layer.",
    )

    rating: Mapped[RatingValue] = mapped_column(
        SAEnum(RatingValue, name="rating_value_enum", create_type=True),
        nullable=False,
        comment="Binary: thumbs_up increments thumbs_up_count, thumbs_down the opposite.",
    )

    created_at: Mapped[TIMESTAMPTZ] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
        comment="Submission timestamp.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="rating")
    rater: Mapped["User"] = relationship("User", foreign_keys=[rated_by])

    @property
    def is_positive(self) -> bool:
        return self.rating == RatingValue.thumbs_up

    def __repr__(self) -> str:
        return f"<Rating transaction={self.transaction_id} value={self.rating}>"
