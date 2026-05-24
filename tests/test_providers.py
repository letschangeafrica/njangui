"""
Tests for the providers module.

Coverage:
  - GET  /providers/categories              (reference data)
  - GET  /providers/locations               (reference data)
  - POST /providers/register                (happy path, duplicate, bad category, bad sub-cat, bad location)
  - GET  /providers/me                      (valid, not registered)
  - PUT  /providers/me                      (partial update, cross-category validation)
  - GET  /providers/{id}                    (valid, suspended, not found)
  - GET  /providers                         (search with and without filters, pagination)
"""

import uuid
import pytest
from datetime import datetime, timezone

from app.models.category import Category, SubCategory
from app.models.location_node import LocationNode
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole
from app.core.security import hash_pin

from tests.conftest import PHONE_NUMBER, PHONE_NUMBER2, VALID_PIN


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers: seed reference data into the test transaction
# (The Alembic migration seeds real data, but we access it here via fixtures.)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def first_category(db) -> Category:
    """Return the first active category seeded by the migration."""
    return db.query(Category).filter(Category.is_active == True).order_by(Category.id).first()


@pytest.fixture()
def first_sub_category(db, first_category) -> SubCategory:
    """Return the first active sub-category of first_category."""
    return (
        db.query(SubCategory)
        .filter(
            SubCategory.category_id == first_category.id,
            SubCategory.is_active == True,
        )
        .order_by(SubCategory.id)
        .first()
    )


@pytest.fixture()
def second_category(db, first_category) -> Category:
    """Return a different active category from first_category."""
    return (
        db.query(Category)
        .filter(Category.is_active == True, Category.id != first_category.id)
        .order_by(Category.id)
        .first()
    )


@pytest.fixture()
def first_location(db) -> LocationNode:
    """Return the first active location node seeded by the migration."""
    return db.query(LocationNode).filter(LocationNode.is_active == True).order_by(LocationNode.id).first()


@pytest.fixture()
def provider_profile(db, existing_user, first_category, first_sub_category, first_location) -> ProviderProfile:
    """A ProviderProfile already attached to existing_user."""
    profile = ProviderProfile(
        user_id=existing_user.id,
        full_name="Jean-Pierre Fono",
        category_id=first_category.id,
        sub_category_id=first_sub_category.id,
        location_node_id=first_location.id,
        is_mobile_provider=False,
        offers_delivery=False,
    )
    db.add(profile)
    existing_user.role = UserRole.provider
    db.commit()
    db.refresh(profile)
    return profile


@pytest.fixture()
def second_user(db) -> User:
    """A second verified, active user for multi-provider tests."""
    user = User(
        phone_number=PHONE_NUMBER2,
        pin_hash=hash_pin(VALID_PIN),
        role=UserRole.customer,
        is_verified=True,
        is_active=True,
        language="fr",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# GET /providers/categories
# ═══════════════════════════════════════════════════════════════════════════════

class TestListCategories:

    @pytest.mark.providers
    def test_list_categories_returns_all_active(self, client):
        """Should return all 8 seeded active categories with their sub-categories."""
        response = client.get("/providers/categories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 8
        # Each category has sub-categories
        for cat in data:
            assert "sub_categories" in cat
            assert len(cat["sub_categories"]) > 0
            assert "id" in cat
            assert "slug" in cat
            assert "icon_name" in cat

    @pytest.mark.providers
    def test_list_categories_no_auth_needed(self, client):
        """Reference data is public — no auth header required."""
        response = client.get("/providers/categories")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# GET /providers/locations
# ═══════════════════════════════════════════════════════════════════════════════

class TestListLocations:

    @pytest.mark.providers
    def test_list_locations_returns_all_nodes(self, client):
        """Should return all 16 seeded Yaoundé location nodes."""
        response = client.get("/providers/locations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 16
        node = data[0]
        assert "id" in node
        assert "name" in node
        assert "display_name_fr" in node
        assert "latitude" in node
        assert "longitude" in node

    @pytest.mark.providers
    def test_list_locations_no_auth_needed(self, client):
        """Reference data is public."""
        response = client.get("/providers/locations")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# POST /providers/register
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegisterProvider:

    @pytest.mark.providers
    def test_register_happy_path(
        self, client, existing_user, auth_headers,
        first_category, first_sub_category, first_location,
    ):
        """Full registration flow — creates profile and upgrades user role."""
        response = client.post("/providers/register", json={
            "full_name":        "Marie Nguemo",
            "category_id":      first_category.id,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": first_location.id,
            "is_mobile_provider": False,
            "offers_delivery":    False,
        }, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["full_name"] == "Marie Nguemo"
        assert data["category"]["id"] == first_category.id
        assert data["sub_category"]["id"] == first_sub_category.id
        assert data["location_node"]["id"] == first_location.id
        assert data["confirmed_tx_count"] == 0
        assert data["thumbs_up_count"] == 0
        assert data["satisfaction_rate"] is None
        assert data["id_card_verified"] is False

    @pytest.mark.providers
    def test_register_updates_user_role(
        self, client, db, existing_user, auth_headers,
        first_category, first_sub_category, first_location,
    ):
        """After registration, user.role should be 'provider'."""
        client.post("/providers/register", json={
            "full_name":        "Marie Nguemo",
            "category_id":      first_category.id,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": first_location.id,
        }, headers=auth_headers)

        db.refresh(existing_user)
        assert existing_user.role == UserRole.provider

    @pytest.mark.providers
    def test_register_no_auth(self, client, first_category, first_sub_category, first_location):
        """Unauthenticated request is rejected."""
        response = client.post("/providers/register", json={
            "full_name":        "Marie Nguemo",
            "category_id":      first_category.id,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": first_location.id,
        })
        assert response.status_code == 403

    @pytest.mark.providers
    def test_register_duplicate_profile(
        self, client, provider_profile, auth_headers,
        first_category, first_sub_category, first_location,
    ):
        """Cannot register as provider twice for the same user."""
        response = client.post("/providers/register", json={
            "full_name":        "Duplicate",
            "category_id":      first_category.id,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": first_location.id,
        }, headers=auth_headers)
        assert response.status_code == 409

    @pytest.mark.providers
    def test_register_invalid_category(
        self, client, existing_user, auth_headers,
        first_sub_category, first_location,
    ):
        """Non-existent category_id is rejected."""
        response = client.post("/providers/register", json={
            "full_name":        "Test",
            "category_id":      9999,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": first_location.id,
        }, headers=auth_headers)
        assert response.status_code == 400

    @pytest.mark.providers
    def test_register_wrong_subcategory_for_category(
        self, client, existing_user, auth_headers, db,
        first_category, second_category, first_location,
    ):
        """Sub-category that doesn't belong to the given category_id is rejected."""
        # Get a sub-category that belongs to second_category, not first_category
        wrong_sub = (
            db.query(SubCategory)
            .filter(
                SubCategory.category_id == second_category.id,
                SubCategory.is_active == True,
            )
            .first()
        )
        response = client.post("/providers/register", json={
            "full_name":        "Test",
            "category_id":      first_category.id,
            "sub_category_id":  wrong_sub.id,  # belongs to second_category
            "location_node_id": first_location.id,
        }, headers=auth_headers)
        assert response.status_code == 400

    @pytest.mark.providers
    def test_register_invalid_location(
        self, client, existing_user, auth_headers,
        first_category, first_sub_category,
    ):
        """Non-existent location_node_id is rejected."""
        response = client.post("/providers/register", json={
            "full_name":        "Test",
            "category_id":      first_category.id,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": 9999,
        }, headers=auth_headers)
        assert response.status_code == 400

    @pytest.mark.providers
    def test_register_full_name_trimmed(
        self, client, existing_user, auth_headers,
        first_category, first_sub_category, first_location,
    ):
        """Leading/trailing whitespace is stripped from full_name."""
        response = client.post("/providers/register", json={
            "full_name":        "  Paul Biya  ",
            "category_id":      first_category.id,
            "sub_category_id":  first_sub_category.id,
            "location_node_id": first_location.id,
        }, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["full_name"] == "Paul Biya"


# ═══════════════════════════════════════════════════════════════════════════════
# GET /providers/me
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetMyProfile:

    @pytest.mark.providers
    def test_get_my_profile_exists(self, client, provider_profile, auth_headers):
        """Returns own profile when registered as provider."""
        response = client.get("/providers/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == provider_profile.full_name
        assert "category" in data
        assert "sub_category" in data
        assert "location_node" in data

    @pytest.mark.providers
    def test_get_my_profile_not_registered(self, client, existing_user, auth_headers):
        """Returns 404 when the user has no provider profile yet."""
        response = client.get("/providers/me", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.providers
    def test_get_my_profile_no_auth(self, client):
        """Requires authentication."""
        response = client.get("/providers/me")
        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# PUT /providers/me
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateMyProfile:

    @pytest.mark.providers
    def test_update_full_name(self, client, db, provider_profile, auth_headers):
        """Can update just the full_name without touching other fields."""
        response = client.put("/providers/me", json={
            "full_name": "Jean-Paul Kamdem",
        }, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["full_name"] == "Jean-Paul Kamdem"

        db.refresh(provider_profile)
        assert provider_profile.full_name == "Jean-Paul Kamdem"

    @pytest.mark.providers
    def test_update_location(self, client, db, provider_profile, auth_headers, first_location):
        """Can update just the location_node_id."""
        # Get a different location node
        other_location = (
            db.query(LocationNode)
            .filter(
                LocationNode.is_active == True,
                LocationNode.id != first_location.id,
            )
            .first()
        )
        response = client.put("/providers/me", json={
            "location_node_id": other_location.id,
        }, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["location_node"]["id"] == other_location.id

    @pytest.mark.providers
    def test_update_mobile_and_delivery_flags(self, client, provider_profile, auth_headers):
        """Can toggle mobility flags."""
        response = client.put("/providers/me", json={
            "is_mobile_provider": True,
            "offers_delivery":    True,
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["is_mobile_provider"] is True
        assert data["offers_delivery"] is True

    @pytest.mark.providers
    def test_update_category_and_subcategory_together(
        self, client, provider_profile, auth_headers,
        second_category, db,
    ):
        """Changing category requires providing a valid sub_category_id from the new category."""
        new_sub = (
            db.query(SubCategory)
            .filter(
                SubCategory.category_id == second_category.id,
                SubCategory.is_active == True,
            )
            .first()
        )
        response = client.put("/providers/me", json={
            "category_id":     second_category.id,
            "sub_category_id": new_sub.id,
        }, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["category"]["id"] == second_category.id
        assert data["sub_category"]["id"] == new_sub.id

    @pytest.mark.providers
    def test_update_subcategory_wrong_category(
        self, client, provider_profile, auth_headers,
        second_category, db, first_category,
    ):
        """Providing a sub-category that belongs to a different category is rejected."""
        wrong_sub = (
            db.query(SubCategory)
            .filter(
                SubCategory.category_id == second_category.id,
                SubCategory.is_active == True,
            )
            .first()
        )
        # Try to set sub_category from second_category while keeping first_category
        response = client.put("/providers/me", json={
            "category_id":     first_category.id,
            "sub_category_id": wrong_sub.id,
        }, headers=auth_headers)
        assert response.status_code == 400

    @pytest.mark.providers
    def test_update_no_profile(self, client, existing_user, auth_headers):
        """Returns 404 if user has no provider profile."""
        response = client.put("/providers/me", json={"full_name": "Test"}, headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.providers
    def test_update_no_auth(self, client):
        """Requires authentication."""
        response = client.put("/providers/me", json={"full_name": "Test"})
        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# GET /providers/{provider_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetProviderById:

    @pytest.mark.providers
    def test_get_provider_valid_id(self, client, provider_profile):
        """Returns full public profile for an active provider."""
        response = client.get(f"/providers/{provider_profile.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(provider_profile.id)
        assert data["full_name"] == provider_profile.full_name
        assert "category" in data
        assert "sub_category" in data
        assert "location_node" in data

    @pytest.mark.providers
    def test_get_provider_no_auth_needed(self, client, provider_profile):
        """Public endpoint — no auth required."""
        response = client.get(f"/providers/{provider_profile.id}")
        assert response.status_code == 200

    @pytest.mark.providers
    def test_get_provider_not_found(self, client):
        """Non-existent UUID returns 404."""
        fake_id = uuid.uuid4()
        response = client.get(f"/providers/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.providers
    def test_get_provider_suspended(self, client, db, provider_profile):
        """Suspended (is_active=FALSE) providers return 404 to the public."""
        provider_profile.is_active = False
        db.commit()

        response = client.get(f"/providers/{provider_profile.id}")
        assert response.status_code == 404

    @pytest.mark.providers
    def test_get_provider_invalid_uuid(self, client):
        """Malformed UUID returns 422."""
        response = client.get("/providers/not-a-valid-uuid")
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# GET /providers (search)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchProviders:

    @pytest.mark.providers
    def test_search_no_filters(self, client, provider_profile):
        """No filters returns all active providers (at least the seeded one)."""
        response = client.get("/providers")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "results" in data
        assert "page" in data
        assert data["page"] == 1
        assert data["total"] >= 1

    @pytest.mark.providers
    def test_search_by_location(self, client, provider_profile, first_location):
        """Filter by location returns only providers in that zone."""
        response = client.get(f"/providers?location_node_id={first_location.id}")
        assert response.status_code == 200
        data = response.json()
        for result in data["results"]:
            assert result["location_node_id"] == first_location.id

    @pytest.mark.providers
    def test_search_by_category(self, client, provider_profile, first_category):
        """Filter by category returns only matching providers."""
        response = client.get(f"/providers?category_id={first_category.id}")
        assert response.status_code == 200
        data = response.json()
        for result in data["results"]:
            assert result["category_id"] == first_category.id

    @pytest.mark.providers
    def test_search_by_sub_category(self, client, provider_profile, first_category, first_sub_category):
        """Filter by sub_category returns only providers with that exact specialty."""
        response = client.get(
            f"/providers?category_id={first_category.id}&sub_category_id={first_sub_category.id}"
        )
        assert response.status_code == 200
        data = response.json()
        for result in data["results"]:
            assert result["sub_category_id"] == first_sub_category.id

    @pytest.mark.providers
    def test_search_mobile_only(self, client, db, provider_profile):
        """mobile_only=true only returns mobile providers."""
        provider_profile.is_mobile_provider = True
        db.commit()

        response = client.get("/providers?mobile_only=true")
        assert response.status_code == 200
        for result in response.json()["results"]:
            assert result["is_mobile_provider"] is True

    @pytest.mark.providers
    def test_search_delivery_only(self, client, db, provider_profile):
        """delivery_only=true only returns providers offering delivery."""
        provider_profile.offers_delivery = True
        db.commit()

        response = client.get("/providers?delivery_only=true")
        assert response.status_code == 200
        for result in response.json()["results"]:
            assert result["offers_delivery"] is True

    @pytest.mark.providers
    def test_search_excludes_suspended(self, client, db, provider_profile):
        """Suspended providers do not appear in search results."""
        provider_profile.is_active = False
        db.commit()

        response = client.get("/providers")
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["results"]]
        assert str(provider_profile.id) not in ids

    @pytest.mark.providers
    def test_search_pagination(self, client, db, existing_user, second_user, first_category, first_sub_category, first_location):
        """Pagination: page 1 and page 2 with page_size=1 return different results."""
        # Create two providers
        for user in [existing_user, second_user]:
            profile = ProviderProfile(
                user_id=user.id,
                full_name=f"Provider {user.phone_number}",
                category_id=first_category.id,
                sub_category_id=first_sub_category.id,
                location_node_id=first_location.id,
            )
            db.add(profile)
        db.commit()

        page1 = client.get("/providers?page=1&page_size=1").json()
        page2 = client.get("/providers?page=2&page_size=1").json()

        assert page1["total"] >= 2
        assert len(page1["results"]) == 1
        assert len(page2["results"]) == 1
        assert page1["results"][0]["id"] != page2["results"][0]["id"]

    @pytest.mark.providers
    def test_search_page_size_capped_at_50(self, client, provider_profile):
        """page_size is capped at 50 even if a larger value is requested."""
        response = client.get("/providers?page_size=999")
        assert response.status_code == 200
        assert response.json()["page_size"] == 50

    @pytest.mark.providers
    def test_search_no_auth_needed(self, client, provider_profile):
        """Search is a public endpoint."""
        response = client.get("/providers")
        assert response.status_code == 200
