"""
Providers service — all provider business logic.
"""

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.category import Category, SubCategory
from app.models.location_node import LocationNode
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole
from app.schemas.providers import ProviderRegisterIn, ProviderUpdateIn


# ═══════════════════════════════════════════════════════════════════════════════
# Reference data
# ═══════════════════════════════════════════════════════════════════════════════


def get_categories(db: Session) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.is_active == True)  # noqa: E712
        .order_by(Category.sort_order)
        .all()
    )


def get_location_nodes(db: Session) -> list[LocationNode]:
    return (
        db.query(LocationNode)
        .filter(LocationNode.is_active == True)  # noqa: E712
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
    # 1. No duplicate profiles
    if db.query(ProviderProfile).filter(ProviderProfile.user_id == current_user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vous avez déjà un profil prestataire.",
        )

    # 2. Validate category
    category = db.query(Category).filter(
        Category.id == data.category_id,
        Category.is_active == True,  # noqa: E712
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
        SubCategory.is_active == True,  # noqa: E712
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
        LocationNode.is_active == True,  # noqa: E712
    ).first()
    if not location_node:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zone géographique {data.location_node_id} introuvable ou inactive.",
        )

    # 5. Create profile
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

    # 6. Upgrade user role to provider
    current_user.role = UserRole.provider
    db.commit()
    db.refresh(profile)
    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# Provider profile update
# ═══════════════════════════════════════════════════════════════════════════════


def update_provider(
    data: ProviderUpdateIn,
    current_user: User,
    db: Session,
) -> ProviderProfile:
    profile = (
        db.query(ProviderProfile)
        .filter(ProviderProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vous n'avez pas encore de profil prestataire.",
        )

    # Effective category: new one if being changed, otherwise existing
    effective_category_id = (
        data.category_id if data.category_id is not None else profile.category_id
    )

    if data.category_id is not None:
        cat = db.query(Category).filter(
            Category.id == data.category_id,
            Category.is_active == True,  # noqa: E712
        ).first()
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Catégorie {data.category_id} introuvable.",
            )

    if data.sub_category_id is not None:
        sub = db.query(SubCategory).filter(
            SubCategory.id == data.sub_category_id,
            SubCategory.category_id == effective_category_id,
            SubCategory.is_active == True,  # noqa: E712
        ).first()
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Sous-catégorie {data.sub_category_id} introuvable "
                    f"ou n'appartient pas à la catégorie {effective_category_id}."
                ),
            )

    if data.location_node_id is not None:
        loc = db.query(LocationNode).filter(
            LocationNode.id == data.location_node_id,
            LocationNode.is_active == True,  # noqa: E712
        ).first()
        if not loc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zone géographique {data.location_node_id} introuvable.",
            )

    if data.full_name is not None:
        profile.full_name = data.full_name
    if data.category_id is not None:
        profile.category_id = data.category_id
    if data.sub_category_id is not None:
        profile.sub_category_id = data.sub_category_id
    if data.location_node_id is not None:
        profile.location_node_id = data.location_node_id
    if data.is_mobile_provider is not None:
        profile.is_mobile_provider = data.is_mobile_provider
    if data.offers_delivery is not None:
        profile.offers_delivery = data.offers_delivery

    db.commit()
    db.refresh(profile)
    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# Provider search — paginated
# ═══════════════════════════════════════════════════════════════════════════════


def search_providers(
    db: Session,
    location_node_id: Optional[int] = None,
    category_id: Optional[int] = None,
    sub_category_id: Optional[int] = None,
    mobile_only: bool = False,
    delivery_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Search active providers with optional filters.
    Returns {total, page, page_size, results}.
    """
    query = db.query(ProviderProfile).filter(ProviderProfile.is_active == True)  # noqa: E712

    if location_node_id is not None:
        query = query.filter(ProviderProfile.location_node_id == location_node_id)
    if category_id is not None:
        query = query.filter(ProviderProfile.category_id == category_id)
    if sub_category_id is not None:
        query = query.filter(ProviderProfile.sub_category_id == sub_category_id)
    if mobile_only:
        query = query.filter(ProviderProfile.is_mobile_provider == True)  # noqa: E712
    if delivery_only:
        query = query.filter(ProviderProfile.offers_delivery == True)  # noqa: E712

    total = query.count()
    results = (
        query.order_by(
            ProviderProfile.confirmed_tx_count.desc(),
            ProviderProfile.thumbs_up_count.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {"total": total, "page": page, "page_size": page_size, "results": results}


# ═══════════════════════════════════════════════════════════════════════════════
# Single profile lookups
# ═══════════════════════════════════════════════════════════════════════════════


def get_my_provider_profile(current_user: User, db: Session) -> ProviderProfile:
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


def get_provider_by_id(provider_id: uuid.UUID, db: Session) -> ProviderProfile:
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
