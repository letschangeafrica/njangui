"""
Providers router — HTTP layer for provider registration, profiles, and search.

Endpoints:
  POST   /providers/register          → create a provider profile
  GET    /providers/me                → own profile (authenticated)
  PUT    /providers/me                → update own profile (authenticated)
  GET    /providers/{provider_id}     → public profile by UUID
  GET    /providers                   → paginated provider search
  GET    /providers/categories        → reference data: all categories + sub-categories
  GET    /providers/locations         → reference data: all location nodes
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.provider import (
    CategoryWithSubsOut,
    LocationNodeOut,
    ProviderProfileOut,
    ProviderRegisterIn,
    ProviderSearchOut,
    ProviderUpdateIn,
)
from app.services import provider_service

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Reference data (no auth — mobile client calls these at startup to build dropdowns)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/categories",
    response_model=list[CategoryWithSubsOut],
    summary="List all service categories with sub-categories",
    description=(
        "Returns all active top-level categories and their sub-categories. "
        "The mobile client downloads this once and caches it locally — no repeated calls."
    ),
)
def list_categories(db: Session = Depends(get_db)):
    return provider_service.get_categories(db)


@router.get(
    "/locations",
    response_model=list[LocationNodeOut],
    summary="List all Yaoundé location nodes",
    description=(
        "Returns the 16 predefined Yaoundé economic nodes. "
        "Providers pick their zone from this list — no free-text location entry."
    ),
)
def list_locations(db: Session = Depends(get_db)):
    return provider_service.get_location_nodes(db)


# ═══════════════════════════════════════════════════════════════════════════════
# Provider search (no auth — discovery is public)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=ProviderSearchOut,
    summary="Search and discover providers",
    description=(
        "Paginated provider discovery. "
        "Results ranked by confirmed_tx_count DESC, thumbs_up_count DESC. "
        "All filters are optional — no filter = all active providers. "
        "Page size is capped at 50."
    ),
)
def search_providers(
    location_node_id: Optional[int] = Query(None, gt=0, description="Filter by Yaoundé zone ID"),
    category_id:      Optional[int] = Query(None, gt=0, description="Filter by top-level category ID"),
    sub_category_id:  Optional[int] = Query(None, gt=0, description="Filter by sub-category ID (pair with category_id)"),
    mobile_only:      bool          = Query(False,       description="Only show providers who travel to the customer"),
    delivery_only:    bool          = Query(False,       description="Only show providers who offer delivery"),
    page:             int           = Query(1,     ge=1, description="Page number (1-indexed)"),
    page_size:        int           = Query(20,    ge=1, description="Results per page (max 50)"),
    db: Session = Depends(get_db),
):
    return provider_service.search_providers(
        db=db,
        location_node_id=location_node_id,
        category_id=category_id,
        sub_category_id=sub_category_id,
        mobile_only=mobile_only,
        delivery_only=delivery_only,
        page=page,
        page_size=page_size,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Authenticated: own profile
# These two routes MUST come before /{provider_id} to avoid route shadowing
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/register",
    response_model=ProviderProfileOut,
    status_code=201,
    summary="Register as a provider",
    description=(
        "Create a provider profile for the authenticated user. "
        "Each user can only have one profile. "
        "On success, the user's role is updated from 'customer' to 'provider'."
    ),
)
def register_as_provider(
    data: ProviderRegisterIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return provider_service.register_provider(data, current_user, db)


@router.get(
    "/me",
    response_model=ProviderProfileOut,
    summary="Get own provider profile",
    description=(
        "Returns the authenticated user's provider profile. "
        "Returns 404 if the user hasn't registered as a provider yet."
    ),
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return provider_service.get_my_provider_profile(current_user, db)


@router.put(
    "/me",
    response_model=ProviderProfileOut,
    summary="Update own provider profile",
    description=(
        "Partial update — only fields included in the request body are changed. "
        "If changing category_id, also provide sub_category_id to ensure consistency."
    ),
)
def update_my_profile(
    data: ProviderUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return provider_service.update_my_provider_profile(data, current_user, db)


# ═══════════════════════════════════════════════════════════════════════════════
# Public: provider profile by ID (must be last — parameterized route)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{provider_id}",
    response_model=ProviderProfileOut,
    summary="Get a provider's public profile",
    description=(
        "Returns a public provider profile. "
        "Suspended (is_active=FALSE) profiles return 404."
    ),
)
def get_provider_profile(
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    return provider_service.get_provider_by_id(provider_id, db)
