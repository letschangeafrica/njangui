from sqlalchemy import Boolean, Integer, Numeric, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LocationNode(Base):
    """
    The 16 predefined Yaoundé economic nodes.
    Hardcoded geographic reference data — free-text location entry is ELIMINATED entirely.
    This prevents search index fragmentation across spelling variations and
    neighbourhood name ambiguities.

    Approximate coordinates allow future distance calculations (PostGIS)
    without continuous GPS tracking.

    The 16 nodes:
    Mokolo · Biyem-Assi · Mendong · Bastos
    Mfoundi · Nlongkak · Melen · Obili
    Elig-Edzoa · Essos · Nkoldongo · Mvog-Mbi
    Madagascar · Nkomkana · Etoa-Meki · Omnisports
    """
    __tablename__ = "location_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
        comment="Official node name. E.g. 'Mokolo', 'Biyem-Assi', 'Bastos'.",
    )

    display_name_fr: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="Display name shown in dropdown. E.g. 'Mokolo (Grand Marché)'.",
    )

    latitude: Mapped[float] = mapped_column(
        Numeric(9, 6),
        nullable=False,
        comment="Approximate centre latitude of the neighbourhood. Used for future radius queries.",
    )

    longitude: Mapped[float] = mapped_column(
        Numeric(9, 6),
        nullable=False,
        comment="Approximate centre longitude.",
    )

    sort_order: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Dropdown display order. Most commercially important nodes listed first.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
        comment="Allows hiding a node without breaking existing provider profiles.",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    provider_profiles: Mapped[list["ProviderProfile"]] = relationship(
        "ProviderProfile", back_populates="location_node"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="location_node"
    )

    def __repr__(self) -> str:
        return f"<LocationNode id={self.id} name={self.name}>"
