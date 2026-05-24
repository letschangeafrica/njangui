from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """
    The 8 top-level service categories.
    Static reference data — seeded at database initialisation, never created by users.
    Uses SERIAL (integer) PK instead of UUID — simpler for static reference data.
    """
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Integer PK for categories. Simpler than UUID for static reference data.",
    )

    name_fr: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
        comment="French name as shown in the UI. E.g. 'Couture & Mode', 'Mécanique'.",
    )

    name_en: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
        comment="English name for bilingual support.",
    )

    slug: Mapped[str] = mapped_column(
        String(40),
        unique=True,
        nullable=False,
        comment="URL-safe identifier. E.g. 'couture', 'mecanique'. Used in API routes.",
    )

    icon_name: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="Icon identifier mapped to vector icon in React Native bundle. E.g. 'scissors'.",
    )

    sort_order: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Display order on the category grid screen. Lower = shown first.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
        comment="Allows hiding a category without deleting it.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    sub_categories: Mapped[list["SubCategory"]] = relationship(
        "SubCategory",
        back_populates="category",
        cascade="all, delete-orphan",
    )
    provider_profiles: Mapped[list["ProviderProfile"]] = relationship(
        "ProviderProfile", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} slug={self.slug}>"


class SubCategory(Base):
    """
    The 40 sub-categories (5 per top-level category).
    Also seeded at initialisation. The category_id FK is the critical integrity constraint.
    Terminology uses the localized language of Yaoundé's markets — not corporate jargon.
    """
    __tablename__ = "sub_categories"

    __table_args__ = (
        # Prevents duplicate sub-category names within the same parent category
        UniqueConstraint("category_id", "name_fr", name="uq_subcategory_category_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        comment="Parent category. CASCADE ensures sub-categories are removed if category is deleted.",
    )

    name_fr: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="Localized French market name. E.g. 'Pagne Africain / Modèle'.",
    )

    name_en: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="English equivalent.",
    )

    slug: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
        comment="URL-safe slug for API filtering. E.g. 'pagne-africain'.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
        comment="Soft disable flag.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    category: Mapped["Category"] = relationship("Category", back_populates="sub_categories")
    provider_profiles: Mapped[list["ProviderProfile"]] = relationship(
        "ProviderProfile", back_populates="sub_category"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="sub_category"
    )

    def __repr__(self) -> str:
        return f"<SubCategory id={self.id} slug={self.slug}>"
