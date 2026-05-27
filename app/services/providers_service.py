"""
Providers service — all provider business logic lives here.

Functions:
  - get_categories()       : return all active categories (for mobile dropdown)
  - get_location_nodes()   : return all active location nodes (for mobile dropdown)
  - register_provider()    : create provider profile, update user role
  - search_providers()     : filter providers by location + category, ranked by reputation
  - get_provider_by_id()   : fetch a single provider profile
"""

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.category import Category, SubCategory
from app.models.location_node import LocationNode
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole
from app.schemas.providers import ProviderRegisterIn


# ═══════════════════════════════════════════════════════════════════════════════
# Reference data — for mobile dropdown population
# ═══════════════════════════════════════════════════════════════════════════════

def get_categories(db: Session) -> list[Category]:
    """Return all active categories ordered by sort_order."""
    return (
        db.query(Category)
        .filter(Category.is_active == True)        # noqa: E712
        .order_by(Category.sort_order)
        .all()
    )


def get_location_nodes(db: Session) -> list[LocationNode]:
    """Return all active location nodes ordered by sort_order."""
    return (
        db.query(LocationNode)
        .filter(LocationNode.is_active == True)    # noqa: E712
        .order_by(LocationNode.sort_order)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Provider registration
# ═══════════════════════════════════════════════════════════════════════════════

def register_provider(
    data: ProviderRegisterIn,
    current_user: User,
    db: Session,
) -> ProviderProfile:
    """
    Upgrade a customer account to a provider profile.

    Flow:
      1. Check user doesn't already have a provider profile
      2. Validate category_id exists and is active
      3. Validate sub_category_id exists, is active, and belongs to category_id
      4. Validate location_node_id exists and is active
      5. Create ProviderProfile record
      6. Update user role to 'both' (they remain a customer + become a provider)
      7. Return the new profile

    Why 'both' and not 'provider'?
    A registered provider can still hire other providers as a customer.
    The 'both' role drives the UI toggle in the mobile app.
    """

    # 1. No duplicate profiles
    existing = (
        db.query(ProviderProfile)
        .filter(ProviderProfile.user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vous avez déjà un profil prestataire.",
        )

    # 2. Validate category
    category = db.query(Category).filter(
        Category.id == data.category_id,
        Category.is_active == True,         # noqa: E712
    ).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Catégorie {data.category_id} introuvable ou inactive.",
        )

    # 3. Validate sub-category belongs to category
    sub_category = db.query(SubCategory).filter(
        SubCategory.id == data.sub_category_id,
        SubCategory.category_id == data.category_id,
        SubCategory.is_active == True,      # noqa: E712
    ).first()
    if not sub_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Sous-catégorie {data.sub_category_id} introuvable "
                f"ou n'appartient pas à la catégorie {data.category_id}."
            ),
        )

    # 4. Validate location node
    location_node = db.query(LocationNode).filter(
        LocationNode.id == data.location_node_id,
        LocationNode.is_active == True,     # noqa: E712
    ).first()
    if not location_node:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zone géographique {data.location_node_id} introuvable ou inactive.",
        )

    # 5. Create provider profile
    profile = ProviderProfile(
        user_id=current_user.id,
        full_name=data.full_name,
        category_id=data.category_id,
        sub_category_id=data.sub_category_id,
        location_node_id=data.location_node_id,
        is_mobile_provider=data.is_mobile_provider,
        offers_delivery=data.offers_delivery,
    )
    db.add(profile)

    # 6. Update user role
    current_user.role = UserRole.both
    db.commit()
    db.refresh(profile)

    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# Provider search
# ═══════════════════════════════════════════════════════════════════════════════

def search_providers(
    db: Session,
    location_node_id: Optional[int] = None,
    category_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[ProviderProfile]:
    """
    Search active providers filtered by location and/or category.

    Ranking: confirmed_tx_count DESC, thumbs_up_count DESC
    — providers with more verified transactions rank higher.
    This uses the idx_provider_ranking partial index defined in the migration.

    Both filters are optional:
    - No filters → returns top-ranked providers across all locations/categories
    - location only → all providers in that neighbourhood
    - category only → all providers in that trade
    - both → most common mobile app query (e.g. "tailors near Mokolo")

    Pagination via limit/offset for 2G-friendly page sizes.
    """
    query = (
        db.query(ProviderProfile)
        .filter(ProviderProfile.is_active == True)  # noqa: E712
    )

    if location_node_id is not None:
        query = query.filter(ProviderProfile.location_node_id == location_node_id)

    if category_id is not None:
        query = query.filter(ProviderProfile.category_id == category_id)

    return (
        query
        .order_by(
            ProviderProfile.confirmed_tx_count.desc(),
            ProviderProfile.thumbs_up_count.desc(),
        )
        .limit(limit)
        .offset(offset)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Own profile lookup (authenticated)
# ═══════════════════════════════════════════════════════════════════════════════

def get_my_provider_profile(current_user: User, db: Session) -> ProviderProfile:
    """
    Return the authenticated user's own provider profile.
    Raises 404 if they haven't registered as a provider yet.
    """
    profile = (
        db.query(ProviderProfile)
        .filter(ProviderProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vous n'avez pas encore de profil prestataire. Utilisez POST /providers/register.",
        )
    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# Single provider lookup
# ═══════════════════════════════════════════════════════════════════════════════

def get_provider_by_id(provider_id: uuid.UUID, db: Session) -> ProviderProfile:
    """
    Fetch a single provider profile by its UUID.
    Raises 404 if not found or inactive.
    """
    profile = (
        db.query(ProviderProfile)
        .filter(
            ProviderProfile.id == provider_id,
            ProviderProfile.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil prestataire introuvable.",
        )
    return profile
