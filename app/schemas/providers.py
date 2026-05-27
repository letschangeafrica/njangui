"""
Pydantic schemas for the providers module.

Request schemas  (what the mobile app sends):
  - ProviderRegisterIn  : register as a provider

Response schemas (what the API sends back):
  - CategoryOut         : one category (for dropdown)
  - SubCategoryOut      : one sub-category (for dropdown)
  - LocationNodeOut     : one location node (for dropdown)
  - ProviderOut         : full provider profile
  - ProviderSummaryOut  : condensed card shown in search results list
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Reference data schemas — returned to populate mobile app dropdowns
# ═══════════════════════════════════════════════════════════════════════════════

class CategoryOut(BaseModel):
    id:         int
    name_fr:    str
    name_en:    str
    slug:       str
    icon_name:  str
    sort_order: int

    model_config = {"from_attributes": True}


class SubCategoryOut(BaseModel):
    id:          int
    category_id: int
    name_fr:     str
    name_en:     str
    slug:        str

    model_config = {"from_attributes": True}


class LocationNodeOut(BaseModel):
    id:              int
    name:            str
    display_name_fr: str
    sort_order:      int

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════════
# Request schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderRegisterIn(BaseModel):
    """
    Payload to upgrade a customer account to a provider profile.

    The mobile app populates category_id, sub_category_id, and location_node_id
    from the seeded reference data returned by GET /providers/categories and
    GET /providers/locations — so IDs are always valid integers from a dropdown,
    never free text.
    """
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

    model_config = {"json_schema_extra": {
        "example": {
            "full_name":          "Jean-Baptiste Mbarga",
            "category_id":        1,
            "sub_category_id":    2,
            "location_node_id":   1,
            "is_mobile_provider": False,
            "offers_delivery":    False,
        }
    }}


# ═══════════════════════════════════════════════════════════════════════════════
# Response schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderSummaryOut(BaseModel):
    """
    Condensed provider card shown in search results.
    Only the fields needed to render the card — keeps the list response light
    for 2G connections.
    """
    id:                  uuid.UUID
    full_name:           str
    is_mobile_provider:  bool
    offers_delivery:     bool
    id_card_verified:    bool
    confirmed_tx_count:  int
    thumbs_up_count:     int
    thumbs_down_count:   int
    satisfaction_rate:   Optional[float]
    category:            CategoryOut
    sub_category:        SubCategoryOut
    location_node:       LocationNodeOut

    model_config = {"from_attributes": True}


class ProviderOut(BaseModel):
    """
    Full provider profile — returned for GET /providers/{id}.
    Includes everything ProviderSummaryOut has plus timestamps and user_id.
    """
    id:                  uuid.UUID
    user_id:             uuid.UUID
    full_name:           str
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
