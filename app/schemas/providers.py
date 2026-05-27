"""
Pydantic schemas for the providers module.

Request schemas:
  - ProviderRegisterIn  : register as a provider
  - ProviderUpdateIn    : partial update of own provider profile

Response schemas:
  - CategoryOut         : one category with its sub-categories (for dropdown)
  - SubCategoryOut      : one sub-category
  - LocationNodeOut     : one location node with coordinates
  - ProviderOut         : full provider profile (register / me / get-by-id)
  - ProviderSummaryOut  : condensed card shown in search results
  - ProviderSearchOut   : paginated search response
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Reference data schemas — populate mobile app dropdowns
# ═══════════════════════════════════════════════════════════════════════════════

class SubCategoryOut(BaseModel):
    id:          int
    category_id: int
    name_fr:     str
    name_en:     str
    slug:        str

    model_config = {"from_attributes": True}


class CategoryOut(BaseModel):
    id:              int
    name_fr:         str
    name_en:         str
    slug:            str
    icon_name:       str
    sort_order:      int
    sub_categories:  list[SubCategoryOut] = []

    model_config = {"from_attributes": True}


class LocationNodeOut(BaseModel):
    id:              int
    name:            str
    display_name_fr: str
    latitude:        float
    longitude:       float
    sort_order:      int

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Request schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderRegisterIn(BaseModel):
    full_name:          str
    category_id:        int
    sub_category_id:    int
    location_node_id:   int
    is_mobile_provider: bool = False
    offers_delivery:    bool = False

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Le nom complet ne peut pas être vide.")
        if len(v) < 2:
            raise ValueError("Le nom complet doit contenir au moins 2 caractères.")
        if len(v) > 100:
            raise ValueError("Le nom complet ne peut pas dépasser 100 caractères.")
        return v


class ProviderUpdateIn(BaseModel):
    """Partial update — every field is optional."""
    full_name:          Optional[str]  = None
    category_id:        Optional[int]  = None
    sub_category_id:    Optional[int]  = None
    location_node_id:   Optional[int]  = None
    is_mobile_provider: Optional[bool] = None
    offers_delivery:    Optional[bool] = None

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Le nom complet ne peut pas être vide.")
        if len(v) < 2:
            raise ValueError("Le nom complet doit contenir au moins 2 caractères.")
        if len(v) > 100:
            raise ValueError("Le nom complet ne peut pas dépasser 100 caractères.")
        return v


# ═══════════════════════════════════════════════════════════════════════════════
# Response schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderSummaryOut(BaseModel):
    """Condensed card for search results — light payload for 2G."""
    id:                  uuid.UUID
    full_name:           str
    # Flat IDs — used by mobile app to filter / verify results
    category_id:         int
    sub_category_id:     int
    location_node_id:    int
    is_mobile_provider:  bool
    offers_delivery:     bool
    id_card_verified:    bool
    confirmed_tx_count:  int
    thumbs_up_count:     int
    thumbs_down_count:   int
    satisfaction_rate:   Optional[float]
    # Nested objects for display
    category:            CategoryOut
    sub_category:        SubCategoryOut
    location_node:       LocationNodeOut

    model_config = {"from_attributes": True}


class ProviderOut(BaseModel):
    """Full provider profile."""
    id:                  uuid.UUID
    user_id:             uuid.UUID
    full_name:           str
    category_id:         int
    sub_category_id:     int
    location_node_id:    int
    is_mobile_provider:  bool
    offers_delivery:     bool
    is_active:           bool
    id_card_verified:    bool
    suspension_reason:   Optional[str]
    confirmed_tx_count:  int
    thumbs_up_count:     int
    thumbs_down_count:   int
    satisfaction_rate:   Optional[float]
    created_at:          datetime
    updated_at:          datetime
    category:            CategoryOut
    sub_category:        SubCategoryOut
    location_node:       LocationNodeOut

    model_config = {"from_attributes": True}


class ProviderSearchOut(BaseModel):
    """Paginated search response."""
    total:     int
    page:      int
    page_size: int
    results:   list[ProviderSummaryOut]
