"""
Njangui — SQLAlchemy Models
All 9 tables imported here so Alembic can discover them via Base.metadata.

Import order matters — respect foreign key dependencies:
  1. Static reference tables (no FK dependencies)
  2. Users (core identity)
  3. ProviderProfile (depends on users, categories, sub_categories, location_nodes)
  4. Transaction (depends on users, sub_categories, location_nodes)
  5. Rating (depends on transactions, users)
  6. FraudFlag (depends on users)
  7. OtpCode (depends on users)
"""

from app.models.category import Category, SubCategory          # noqa: F401
from app.models.location_node import LocationNode              # noqa: F401
from app.models.user import User, UserRole                     # noqa: F401
from app.models.provider_profile import ProviderProfile        # noqa: F401
from app.models.transaction import Transaction, TransactionStatus  # noqa: F401
from app.models.rating import Rating, RatingValue              # noqa: F401
from app.models.fraud_flag import FraudFlag, FraudFlagStatus   # noqa: F401
from app.models.otp_code import OtpCode                        # noqa: F401

__all__ = [
    "Category",
    "SubCategory",
    "LocationNode",
    "User",
    "UserRole",
    "ProviderProfile",
    "Transaction",
    "TransactionStatus",
    "Rating",
    "RatingValue",
    "FraudFlag",
    "FraudFlagStatus",
    "OtpCode",
]
