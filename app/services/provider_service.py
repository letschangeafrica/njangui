"""
Provider service — all provider business logic lives here.

Routers call these functions. Routers handle HTTP. Services handle logic.

Functions:
  - register_provider()    : create ProviderProfile, upgrade user role
  - get_provider_by_id()   : fetch public profile by UUID
  - get_my_profile()       : fetch own profile (must exist)
  - update_my_profile()    : partial update with sub-category / location validation
  - search_providers()     : paginated filtered search ranked by trust signals
  - get_categories()       : returns all active categories with sub-categories
  - get_location_nodes()   : returns all active location nodes
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app.models.category import Category, SubCategory
from app.models.location_node import LocationNode
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole
from app.schemas.provider import ProviderRegisterIn, ProviderUpdateIn


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1 — Register as a provider
# ═══════════════════════════════════════════════════════════════════════════════

def register_provider(data: ProviderRegisterIn, current_user: User, db: Session) -> ProviderProfile:
    """
    Create a ProviderProfile for an authenticated user.

    Business rules:
      - A user can only have ONE provider profile (UNIQUE user_id enforced at DB level too)
      - category_id and sub_category_id must be valid and related
      - location_node_id must exist and be active
      - On success: user.role is updated to 'provider' or 'both'
    """
    # 1. Cannot register twice
    existing_profile = (
        db.query(ProviderProfile)
        .filter(ProviderProfile.user_id == current_user.id)
        .first()
    )
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Vous avez déjà un profil prestataire. "
                "Utilisez PUT /providers/me pour le modifier."
            ),
        )

    # 2. Validate category exists and is active
    category = db.query(Category).filter(
        Category.id == data.category_id,
        Category.is_active == True,  # noqa: E712
    ).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Catégorie {data.category_id} introuvable ou inactive.",
        )

    # 3. Validate sub-category is a child of the given category
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

    # 4. Validate location node exists and is active
    location_node = db.query(LocationNode).filter(
        LocationNode.id == data.location_node_id,
        LocationNode.is_active == True,  # noqa: E712
    ).first()
    if not location_node:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zone géographique {data.location_node_id} introuvable ou inactive.",
        )

    # 5. Create the provider profile
    profile = ProviderProfile(
        user_id=current_user.id,
        full_name=data.full_name.strip(),
        category_id=data.category_id,
        sub_category_id=data.sub_category_id,
        location_node_id=data.location_node_id,
        is_mobile_provider=data.is_mobile_provider,
        offers_delivery=data.offers_delivery,
    )
    db.add(profile)

    # 6. Upgrade user role
    if current_user.role == UserRole.customer:
        current_user.role = UserRole.provider
    # If already 'provider' (shouldn't happen given check above), no change needed.
    # 'both' role is set when a provider also acts as a customer in transactions.

    db.commit()
    db.refresh(profile)

    # Eager-load relationships so the response schema can access them
    return _load_profile_with_relations(profile.id, db)


# ═══════════════════════════════════════════════════════════════════════════════
# Get a provider profile (public)
# ═══════════════════════════════════════════════════════════════════════════════

def get_provider_by_id(provider_id: UUID, db: Session) -> ProviderProfile:
    """
    Fetch a public provider profile by its UUID.
    Only returns active profiles (is_active=TRUE).
    Raises 404 if not found or suspended.
    """
    profile = _load_profile_with_relations(provider_id, db)
    if not profile or not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil prestataire introuvable.",
        )
    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# Get own profile (authenticated)
# ═══════════════════════════════════════════════════════════════════════════════

def get_my_provider_profile(current_user: User, db: Session) -> ProviderProfile:
    """
    Return the authenticated user's own provider profile.
    Raises 404 if the user has not registered as a provider yet.
    Own profile is returned even if is_active=FALSE (so suspended providers can see it).
    """
    profile = (
        db.query(ProviderProfile)
        .options(
            joinedload(ProviderProfile.category),
            joinedload(ProviderProfile.sub_category),
            joinedload(ProviderProfile.location_node),
        )
        .filter(ProviderProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Vous n'avez pas encore de profil prestataire. "
                "Utilisez POST /providers/register pour en créer un."
            ),
        )
    return profile


# ═══════════════════════════════════════════════════════════════════════════════
# Update own profile (authenticated)
# ═══════════════════════════════════════════════════════════════════════════════

def update_my_provider_profile(
    data: ProviderUpdateIn,
    current_user: User,
    db: Session,
) -> ProviderProfile:
    """
    Partial update of the authenticated user's provider profile.
    Only fields explicitly provided in the request body are changed.

    Cross-validation rules:
      - If sub_category_id is being changed, it must belong to the resulting category_id
        (either the new one provided, or the existing one on the profile).
      - If category_id is being changed without sub_category_id, the existing
        sub_category must still be a valid child — otherwise the client must supply both.
    """
    profile = (
        db.query(ProviderProfile)
        .filter(ProviderProfile.user_id == current_user.id)
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil prestataire introuvable.",
        )

    updates = data.model_dump(exclude_unset=True)

    # Determine the effective category_id and sub_category_id after this update
    effective_category_id    = updates.get("category_id",    profile.category_id)
    effective_sub_category_id = updates.get("sub_category_id", profile.sub_category_id)

    # Validate category if it changed
    if "category_id" in updates:
        category = db.query(Category).filter(
            Category.id == effective_category_id,
            Category.is_active == True,  # noqa: E712
        ).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Catégorie {effective_category_id} introuvable ou inactive.",
            )

    # Validate sub-category relationship (always recheck if either ID changed)
    if "category_id" in updates or "sub_category_id" in updates:
        sub_category = db.query(SubCategory).filter(
            SubCategory.id == effective_sub_category_id,
            SubCategory.category_id == effective_category_id,
            SubCategory.is_active == True,  # noqa: E712
        ).first()
        if not sub_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Sous-catégorie {effective_sub_category_id} introuvable "
                    f"ou n'appartient pas à la catégorie {effective_category_id}. "
                    "Fournissez category_id et sub_category_id ensemble."
                ),
            )

    # Validate location node if it changed
    if "location_node_id" in updates:
        location_node = db.query(LocationNode).filter(
            LocationNode.id == updates["location_node_id"],
            LocationNode.is_active == True,  # noqa: E712
        ).first()
        if not location_node:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zone géographique {updates['location_node_id']} introuvable ou inactive.",
            )

    # Apply updates
    if "full_name" in updates:
        updates["full_name"] = updates["full_name"].strip()

    for field, value in updates.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    return _load_profile_with_relations(profile.id, db)


# ═══════════════════════════════════════════════════════════════════════════════
# Search providers
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
    Paginated provider search with optional filters.

    Ranking formula (matches idx_provider_ranking partial index):
      1. confirmed_tx_count DESC  — verified transaction volume = trust signal
      2. thumbs_up_count DESC     — positive ratings = quality signal

    This ranking is stable, explainable to the user, and works well on 2G
    (no heavy aggregation at query time — counters are denormalized by triggers).

    Filters:
      - location_node_id : exact node match (one of the 16 Yaoundé nodes)
      - category_id      : top-level category
      - sub_category_id  : specific sub-category (client must also pass category_id)
      - mobile_only      : is_mobile_provider = TRUE
      - delivery_only    : offers_delivery = TRUE

    Pagination:
      - page starts at 1
      - max page_size capped at 50 to protect against scraping
    """
    page_size = min(page_size, 50)   # hard cap — prevent abuse
    offset    = (page - 1) * page_size

    # Base query — only active profiles
    query = (
        db.query(ProviderProfile)
        .options(
            joinedload(ProviderProfile.category),
            joinedload(ProviderProfile.sub_category),
            joinedload(ProviderProfile.location_node),
        )
        .filter(ProviderProfile.is_active == True)  # noqa: E712
    )

    # Apply optional filters
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

    # Count total before pagination (needed for pagination UI)
    total = query.count()

    # Apply ranking and pagination
    results = (
        query
        .order_by(
            ProviderProfile.confirmed_tx_count.desc(),
            ProviderProfile.thumbs_up_count.desc(),
            ProviderProfile.created_at.asc(),   # tie-breaker: earlier registration first
        )
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "results":   results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Reference data (used by mobile client to populate dropdowns)
# ═══════════════════════════════════════════════════════════════════════════════

def get_categories(db: Session) -> list[Category]:
    """Return all active categories with their sub-categories, ordered by sort_order."""
    return (
        db.query(Category)
        .options(joinedload(Category.sub_categories))
        .filter(Category.is_active == True)  # noqa: E712
        .order_by(Category.sort_order)
        .all()
    )


def get_location_nodes(db: Session) -> list[LocationNode]:
    """Return all active location nodes, ordered by sort_order."""
    return (
        db.query(LocationNode)
        .filter(LocationNode.is_active == True)  # noqa: E712
        .order_by(LocationNode.sort_order)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_profile_with_relations(profile_id: UUID, db: Session) -> Optional[ProviderProfile]:
    """
    Load a profile with all relationships eager-loaded.
    This avoids N+1 queries when the response schema accesses .category, etc.
    """
    return (
        db.query(ProviderProfile)
        .options(
            joinedload(ProviderProfile.category),
            joinedload(ProviderProfile.sub_category),
            joinedload(ProviderProfile.location_node),
        )
        .filter(ProviderProfile.id == profile_id)
        .first()
    )
