"""
Pydantic schemas for the providers module.

In  → request bodies (validated before hitting the service)
Out → response shapes (never expose internal fields like pin_hash)
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Nested / shared
# ═══════════════════════════════════════════════════════════════════════════════

class CategoryOut(BaseModel):
    id: int
    name_fr: str
    name_en: str
    slug: str
    icon_name: str

    model_config = {"from_attributes": True}


class SubCategoryOut(BaseModel):
    id: int
    category_id: int
    name_fr: str
    name_en: str
    slug: str

    model_config = {"from_attributes": True}


class LocationNodeOut(BaseModel):
    id: int
    name: str
    display_name_fr: str
    latitude: float
    longitude: float

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# POST /providers/register — request
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderRegisterIn(BaseModel):
    """
    Input for registering as a provider for the first time.
    The authenticated user's ID is taken from the JWT — not from this body.
    """
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Display name shown in search results. Real first name + last name preferred.",
    )
    category_id: int = Field(
        ...,
        gt=0,
        description="Top-level service category ID (from /categories). E.g. 1 for Couture & Mode.",
    )
    sub_category_id: int = Field(
        ...,
        gt=0,
        description="Sub-category ID. Must be a valid child of category_id.",
    )
    location_node_id: int = Field(
        ...,
        gt=0,
        description="One of the 16 Yaoundé location node IDs. No free-text location.",
    )
    is_mobile_provider: bool = Field(
        False,
        description="TRUE if the provider travels to the customer (moto-taxi, mobile repair).",
    )
    offers_delivery: bool = Field(
        False,
        description="TRUE if the provider ships physical goods.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PUT /providers/me — request (all fields optional)
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderUpdateIn(BaseModel):
    """
    Partial update for an existing provider profile.
    Only provided fields are updated (PATCH semantics via model_dump(exclude_unset=True)).
    """
    full_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100,
    )
    category_id: Optional[int] = Field(None, gt=0)
    sub_category_id: Optional[int] = Field(None, gt=0)
    location_node_id: Optional[int] = Field(None, gt=0)
    is_mobile_provider: Optional[bool] = None
    offers_delivery: Optional[bool] = None

    @model_validator(mode="after")
    def category_and_subcategory_together(self) -> "ProviderUpdateIn":
        """
        If only one of category_id / sub_category_id is provided, the service
        must validate they still match. Flag the edge case here so callers notice.
        Both can be None (no change) or both provided (cross-validated in service).
        Providing one without the other is allowed but the service re-validates the pair.
        """
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# Response — full profile (own profile or public profile)
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderProfileOut(BaseModel):
    """
    Full provider profile. Returned after register, on GET /providers/me, and GET /providers/{id}.
    Includes nested category / sub-category / location objects to avoid extra round-trips.
    """
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    id_card_photo_url: Optional[str]
    id_card_verified: bool
    is_mobile_provider: bool
    offers_delivery: bool
    is_active: bool

    # Denormalized performance counters
    confirmed_tx_count: int
    thumbs_up_count: int
    thumbs_down_count: int
    satisfaction_rate: Optional[float]   # None if no ratings yet

    # Nested lookups (avoids extra round-trips from the mobile client on 2G)
    category: CategoryOut
    sub_category: SubCategoryOut
    location_node: LocationNodeOut

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Response — lightweight card for search results list
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderCardOut(BaseModel):
    """
    Compact representation used in search results.
    Omits timestamps and nested objects to keep payloads small on 2G.
    The client fetches the full ProviderProfileOut only when the user taps a card.
    """
    id: uuid.UUID
    full_name: str
    id_card_verified: bool
    is_mobile_provider: bool
    offers_delivery: bool
    confirmed_tx_count: int
    thumbs_up_count: int
    thumbs_down_count: int
    satisfaction_rate: Optional[float]

    # Flat IDs only — the mobile app caches the category / location lookup tables
    category_id: int
    sub_category_id: int
    location_node_id: int

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Response — paginated search results
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderSearchOut(BaseModel):
    total: int              # total matching records (for pagination UI)
    page: int
    page_size: int
    results: list[ProviderCardOut]


# ═══════════════════════════════════════════════════════════════════════════════
# Response — reference data lists (used by the mobile app to populate dropdowns)
# ═══════════════════════════════════════════════════════════════════════════════

class CategoryWithSubsOut(BaseModel):
    id: int
    name_fr: str
    name_en: str
    slug: str
    icon_name: str
    sort_order: int
    sub_categories: list[SubCategoryOut]

    model_config = {"from_attributes": True}
