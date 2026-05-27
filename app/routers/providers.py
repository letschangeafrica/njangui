"""
Providers router.

Route ordering matters in FastAPI:
  /providers/categories, /providers/locations, /providers/me
  MUST be before /providers/{provider_id} — otherwise FastAPI tries to parse
  "categories", "locations", "me" as UUIDs and returns 422.
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
    ProviderSearchOut,
    ProviderUpdateIn,
)
from app.services import providers_service

router = APIRouter()


# ── GET /providers/categories ─────────────────────────────────────────────────
@router.get(
    "/categories",
    response_model=list[CategoryOut],
    status_code=status.HTTP_200_OK,
    summary="List all categories",
)
def list_categories(db: Session = Depends(get_db)):
    return providers_service.get_categories(db)


# ── GET /providers/locations ──────────────────────────────────────────────────
@router.get(
    "/locations",
    response_model=list[LocationNodeOut],
    status_code=status.HTTP_200_OK,
    summary="List all location nodes",
)
def list_locations(db: Session = Depends(get_db)):
    return providers_service.get_location_nodes(db)


# ── POST /providers/register ──────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=ProviderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register as a provider",
)
def register_provider(
    body: ProviderRegisterIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return providers_service.register_provider(data=body, current_user=current_user, db=db)


# ── GET /providers/me ─────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=ProviderOut,
    status_code=status.HTTP_200_OK,
    summary="Get own provider profile",
)
def get_my_profile(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return providers_service.get_my_provider_profile(current_user=current_user, db=db)


# ── PUT /providers/me ─────────────────────────────────────────────────────────
@router.put(
    "/me",
    response_model=ProviderOut,
    status_code=status.HTTP_200_OK,
    summary="Update own provider profile",
)
def update_my_profile(
    body: ProviderUpdateIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return providers_service.update_provider(data=body, current_user=current_user, db=db)


# ── GET /providers ────────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=ProviderSearchOut,
    status_code=status.HTTP_200_OK,
    summary="Search providers",
)
def search_providers(
    location_node_id: Optional[int] = Query(None, description="Filter by neighbourhood ID"),
    category_id:      Optional[int] = Query(None, description="Filter by category ID"),
    sub_category_id:  Optional[int] = Query(None, description="Filter by sub-category ID"),
    mobile_only:      bool          = Query(False, description="Only mobile providers"),
    delivery_only:    bool          = Query(False, description="Only providers with delivery"),
    page:             int           = Query(1,  ge=1),
    page_size:        int           = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    page_size = min(page_size, 50)  # hard cap even if validation is bypassed
    return providers_service.search_providers(
        db=db,
        location_node_id=location_node_id,
        category_id=category_id,
        sub_category_id=sub_category_id,
        mobile_only=mobile_only,
        delivery_only=delivery_only,
        page=page,
        page_size=page_size,
    )


# ── GET /providers/{provider_id} ──────────────────────────────────────────────
@router.get(
    "/{provider_id}",
    response_model=ProviderOut,
    status_code=status.HTTP_200_OK,
    summary="Get a provider profile",
)
def get_provider(
    provider_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    return providers_service.get_provider_by_id(provider_id=provider_id, db=db)
