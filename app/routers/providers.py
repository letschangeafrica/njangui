"""
Providers router — HTTP layer for provider endpoints.

Endpoints:
  GET  /providers/categories     → list all categories (mobile dropdown)
  GET  /providers/locations      → list all location nodes (mobile dropdown)
  POST /providers/register       → register current user as a provider
  GET  /providers/me             → get own provider profile (authenticated)
  GET  /providers                → search providers (filter by location + category)
  GET  /providers/{provider_id}  → get one provider's full profile

Route ordering matters in FastAPI:
  /providers/categories, /providers/locations, and /providers/me MUST be
  defined BEFORE /providers/{provider_id} — otherwise FastAPI would try to
  match those literal strings as a UUID and return a 422 validation error.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.schemas.providers import (
    CategoryOut,
    LocationNodeOut,
    ProviderOut,
    ProviderRegisterIn,
    ProviderSummaryOut,
)
from app.services import providers_service

router = APIRouter()


# ── GET /providers/categories ─────────────────────────────────────────────────
@router.get(
    "/categories",
    response_model=list[CategoryOut],
    status_code=status.HTTP_200_OK,
    summary="List all categories",
    description=(
        "Returns the 8 active service categories in sort order. "
        "Used by the mobile app to populate the category picker. "
        "No authentication required."
    ),
)
def list_categories(db: Session = Depends(get_db)):
    return providers_service.get_categories(db)


# ── GET /providers/locations ──────────────────────────────────────────────────
@router.get(
    "/locations",
    response_model=list[LocationNodeOut],
    status_code=status.HTTP_200_OK,
    summary="List all location nodes",
    description=(
        "Returns the 16 predefined Yaoundé economic nodes in sort order. "
        "Used by the mobile app to populate the neighbourhood picker. "
        "No authentication required."
    ),
)
def list_locations(db: Session = Depends(get_db)):
    return providers_service.get_location_nodes(db)


# ── POST /providers/register ──────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=ProviderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register as a provider",
    description=(
        "Upgrades the authenticated user's account to include a provider profile. "
        "The user's role changes from 'customer' to 'both'. "
        "A user can only have one provider profile. "
        "Requires a valid Bearer token."
    ),
)
def register_provider(
    body: ProviderRegisterIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return providers_service.register_provider(
        data=body,
        current_user=current_user,
        db=db,
    )


# ── GET /providers/me ─────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=ProviderOut,
    status_code=status.HTTP_200_OK,
    summary="Get own provider profile",
    description=(
        "Returns the authenticated user's own provider profile. "
        "Returns 404 if the user hasn't registered as a provider yet. "
        "Requires a valid Bearer token."
    ),
)
def get_my_profile(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return providers_service.get_my_provider_profile(
        current_user=current_user,
        db=db,
    )


# ── GET /providers ────────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=list[ProviderSummaryOut],
    status_code=status.HTTP_200_OK,
    summary="Search providers",
    description=(
        "Returns active providers filtered by location and/or category. "
        "Results are ranked by reputation: confirmed_tx_count DESC, thumbs_up_count DESC. "
        "Both filters are optional. Supports pagination."
    ),
)
def search_providers(
    location_node_id: Optional[int] = Query(None, description="Filter by neighbourhood ID"),
    category_id:      Optional[int] = Query(None, description="Filter by category ID"),
    limit:            int           = Query(20,   ge=1, le=50),
    offset:           int           = Query(0,    ge=0),
    db: Session = Depends(get_db),
):
    return providers_service.search_providers(
        db=db,
        location_node_id=location_node_id,
        category_id=category_id,
        limit=limit,
        offset=offset,
    )


# ── GET /providers/{provider_id} ──────────────────────────────────────────────
@router.get(
    "/{provider_id}",
    response_model=ProviderOut,
    status_code=status.HTTP_200_OK,
    summary="Get a provider profile",
    description=(
        "Returns the full profile for a single provider by their profile UUID. "
        "Returns 404 if the provider does not exist or is suspended."
    ),
)
def get_provider(
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    return providers_service.get_provider_by_id(
        provider_id=provider_id,
        db=db,
    )
