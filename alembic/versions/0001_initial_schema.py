"""Initial schema — all 9 tables, 10 indexes, 6 triggers, seed data

Revision ID: 0001
Revises: None
Create Date: 2026-05-24

What this migration does:
  1. Creates 4 PostgreSQL ENUM types
  2. Creates all 9 tables in FK-dependency order
  3. Creates 10 performance indexes (from the Phase 2 index strategy)
  4. Creates 6 trigger functions + their triggers
  5. Seeds: 8 categories, 40 sub-categories, 16 Yaoundé location nodes
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ═══════════════════════════════════════════════════════════════════════════════
# UPGRADE
# ═══════════════════════════════════════════════════════════════════════════════

def upgrade() -> None:
    _create_enum_types()
    _create_tables()
    _create_indexes()
    _create_triggers()
    _seed_categories()
    _seed_sub_categories()
    _seed_location_nodes()


# ─── Step 1: ENUM types ───────────────────────────────────────────────────────

def _create_enum_types() -> None:
    """
    PostgreSQL ENUM types must be created before the tables that use them.
    SQLAlchemy's SAEnum with create_type=True handles this, but we define
    them explicitly here so the migration is fully self-contained.
    """
    op.execute("""
        CREATE TYPE user_role_enum AS ENUM ('customer', 'provider', 'both')
    """)
    op.execute("""
        CREATE TYPE transaction_status_enum AS ENUM
            ('pending', 'confirmed', 'expired', 'disputed')
    """)
    op.execute("""
        CREATE TYPE rating_value_enum AS ENUM ('thumbs_up', 'thumbs_down')
    """)
    op.execute("""
        CREATE TYPE fraud_flag_status_enum AS ENUM
            ('pending', 'reviewed_valid', 'reviewed_invalid')
    """)


# ─── Step 2: Tables ───────────────────────────────────────────────────────────

def _create_tables() -> None:

    # ── 1. categories (static reference, no FK deps) ──────────────────────────
    op.create_table(
        "categories",
        sa.Column("id",         sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("name_fr",    sa.String(80),   nullable=False, unique=True),
        sa.Column("name_en",    sa.String(80),   nullable=False, unique=True),
        sa.Column("slug",       sa.String(40),   nullable=False, unique=True),
        sa.Column("icon_name",  sa.String(60),   nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("is_active",  sa.Boolean(),    nullable=False, server_default="TRUE"),
    )

    # ── 2. sub_categories (FK → categories) ───────────────────────────────────
    op.create_table(
        "sub_categories",
        sa.Column("id",          sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.Integer(),   nullable=False),
        sa.Column("name_fr",     sa.String(80),  nullable=False),
        sa.Column("name_en",     sa.String(80),  nullable=False),
        sa.Column("slug",        sa.String(60),  nullable=False, unique=True),
        sa.Column("is_active",   sa.Boolean(),   nullable=False, server_default="TRUE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("category_id", "name_fr", name="uq_subcategory_category_name"),
    )

    # ── 3. location_nodes (static reference, no FK deps) ──────────────────────
    op.create_table(
        "location_nodes",
        sa.Column("id",               sa.Integer(),      primary_key=True, autoincrement=True),
        sa.Column("name",             sa.String(60),     nullable=False, unique=True),
        sa.Column("display_name_fr",  sa.String(80),     nullable=False),
        sa.Column("latitude",         sa.Numeric(9, 6),  nullable=False),
        sa.Column("longitude",        sa.Numeric(9, 6),  nullable=False),
        sa.Column("sort_order",       sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("is_active",        sa.Boolean(),      nullable=False, server_default="TRUE"),
    )

    # ── 4. users (core identity table) ────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("phone_number",     sa.String(15),     nullable=False, unique=True),
        sa.Column("pin_hash",         sa.String(60),     nullable=False),
        sa.Column("role",             sa.Enum("customer", "provider", "both",
                                              name="user_role_enum", create_type=False),
                  nullable=False, server_default="customer"),
        sa.Column("is_verified",      sa.Boolean(),      nullable=False, server_default="FALSE"),
        sa.Column("is_active",        sa.Boolean(),      nullable=False, server_default="TRUE"),
        sa.Column("otp_attempts",     sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("otp_locked_until", postgresql.TIMESTAMPTZ(), nullable=True),
        sa.Column("language",         sa.String(2),      nullable=False, server_default="'fr'"),
        sa.Column("created_at",       postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_login_at",    postgresql.TIMESTAMPTZ(), nullable=True),
    )

    # ── 5. provider_profiles (FK → users, categories, sub_categories, location_nodes) ──
    op.create_table(
        "provider_profiles",
        sa.Column("id",                postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id",           postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("full_name",         sa.String(100),    nullable=False),
        sa.Column("id_card_photo_url", sa.String(500),    nullable=True),
        sa.Column("id_card_verified",  sa.Boolean(),      nullable=False, server_default="FALSE"),
        sa.Column("category_id",       sa.Integer(),      nullable=False),
        sa.Column("sub_category_id",   sa.Integer(),      nullable=False),
        sa.Column("location_node_id",  sa.Integer(),      nullable=False),
        sa.Column("is_mobile_provider",sa.Boolean(),      nullable=False, server_default="FALSE"),
        sa.Column("offers_delivery",   sa.Boolean(),      nullable=False, server_default="FALSE"),
        sa.Column("is_active",         sa.Boolean(),      nullable=False, server_default="TRUE"),
        sa.Column("suspension_reason", sa.Text(),         nullable=True),
        # Denormalized counters — maintained by triggers, not application code
        sa.Column("confirmed_tx_count",sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("thumbs_up_count",   sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("thumbs_down_count", sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("created_at",        postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",        postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["user_id"],          ["users.id"]),
        sa.ForeignKeyConstraint(["category_id"],      ["categories.id"]),
        sa.ForeignKeyConstraint(["sub_category_id"],  ["sub_categories.id"]),
        sa.ForeignKeyConstraint(["location_node_id"], ["location_nodes.id"]),
    )

    # ── 6. transactions (the core reputation ledger) ───────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id",                      postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sub_category_id",         sa.Integer(),      nullable=False),
        sa.Column("amount_xaf",              sa.Integer(),      nullable=False),
        sa.Column("initiated_by",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_at",            postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("provider_confirmed_at",   postgresql.TIMESTAMPTZ(), nullable=True),
        sa.Column("customer_confirmed_at",   postgresql.TIMESTAMPTZ(), nullable=True),
        sa.Column("expires_at",              postgresql.TIMESTAMPTZ(), nullable=False),
        sa.Column("status",
                  sa.Enum("pending", "confirmed", "expired", "disputed",
                           name="transaction_status_enum", create_type=False),
                  nullable=False, server_default="pending"),
        sa.Column("is_mobile_money_verified",sa.Boolean(),      nullable=False, server_default="FALSE"),
        sa.Column("location_node_id",        sa.Integer(),      nullable=True),
        sa.ForeignKeyConstraint(["provider_id"],    ["users.id"]),
        sa.ForeignKeyConstraint(["customer_id"],    ["users.id"]),
        sa.ForeignKeyConstraint(["initiated_by"],   ["users.id"]),
        sa.ForeignKeyConstraint(["sub_category_id"],["sub_categories.id"]),
        sa.ForeignKeyConstraint(["location_node_id"],["location_nodes.id"]),
        # amount must be positive — never zero, never negative
        sa.CheckConstraint("amount_xaf > 0",             name="chk_amount_positive"),
        # A user cannot transact with themselves
        sa.CheckConstraint("provider_id != customer_id", name="chk_no_self_transaction"),
    )

    # ── 7. ratings (one per confirmed transaction, customer only) ─────────────
    op.create_table(
        "ratings",
        sa.Column("id",             postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("rated_by",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating",
                  sa.Enum("thumbs_up", "thumbs_down",
                           name="rating_value_enum", create_type=False),
                  nullable=False),
        sa.Column("created_at",     postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["rated_by"],       ["users.id"]),
    )

    # ── 8. fraud_flags (customer reports, triggers auto-suspension) ───────────
    op.create_table(
        "fraud_flags",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("flagged_provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flagged_by",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason",              sa.Text(),  nullable=True),
        sa.Column("status",
                  sa.Enum("pending", "reviewed_valid", "reviewed_invalid",
                           name="fraud_flag_status_enum", create_type=False),
                  nullable=False, server_default="pending"),
        sa.Column("admin_note",          sa.Text(),  nullable=True),
        sa.Column("created_at",          postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["flagged_provider_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["flagged_by"],          ["users.id"]),
        # One customer can only flag a given provider once
        sa.UniqueConstraint("flagged_provider_id", "flagged_by",
                            name="uq_fraud_flag_one_per_customer"),
    )

    # ── 9. otp_codes (temporary OTP storage, PostgreSQL fallback for Redis) ───
    op.create_table(
        "otp_codes",
        sa.Column("id",            sa.Integer(),      primary_key=True, autoincrement=True),
        sa.Column("phone_number",  sa.String(15),     nullable=False),
        sa.Column("code_hash",     sa.String(60),     nullable=False),
        sa.Column("expires_at",    postgresql.TIMESTAMPTZ(), nullable=False),
        sa.Column("is_used",       sa.Boolean(),      nullable=False, server_default="FALSE"),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at",    postgresql.TIMESTAMPTZ(), nullable=False,
                  server_default=sa.text("NOW()")),
    )


# ─── Step 3: Indexes ─────────────────────────────────────────────────────────

def _create_indexes() -> None:
    """
    10 performance indexes — every one maps to a specific query.
    No speculative indexes. Source: Phase 2 Index Strategy document.
    """

    # idx_users_phone
    # Critical path: primary lookup for every authentication request
    op.create_index("idx_users_phone", "users", ["phone_number"])

    # idx_provider_location_category
    # Powers the core search query — filters by neighbourhood + category simultaneously
    op.create_index(
        "idx_provider_location_category",
        "provider_profiles",
        ["location_node_id", "category_id", "is_active"],
    )

    # idx_provider_ranking
    # Orders search results — partial index on active providers only
    op.execute("""
        CREATE INDEX idx_provider_ranking
        ON provider_profiles (confirmed_tx_count DESC, thumbs_up_count DESC)
        WHERE is_active = TRUE
    """)

    # idx_tx_provider_status
    # Dashboard query: all transactions for a provider by status and date
    op.create_index(
        "idx_tx_provider_status",
        "transactions",
        ["provider_id", "status", "initiated_at"],
    )

    # idx_tx_subcategory_location
    # Price intelligence aggregation query
    op.create_index(
        "idx_tx_subcategory_location",
        "transactions",
        ["sub_category_id", "location_node_id", "status"],
    )

    # idx_tx_peer_cap
    # Rule B (peer-to-peer rolling cap) — checked on EVERY transaction initiation, must be fast
    op.create_index(
        "idx_tx_peer_cap",
        "transactions",
        ["provider_id", "customer_id", "initiated_at"],
    )

    # idx_tx_expires
    # Celery expiry sweep — partial index on pending transactions only
    op.execute("""
        CREATE INDEX idx_tx_expires
        ON transactions (expires_at, status)
        WHERE status = 'pending'
    """)

    # idx_ratings_transaction
    # Enforces one-rating-per-transaction lookup (already unique, index speeds up joins)
    op.create_index("idx_ratings_transaction", "ratings", ["transaction_id"], unique=True)

    # idx_fraud_provider
    # Count pending flags per provider for auto-suspension trigger
    op.create_index(
        "idx_fraud_provider",
        "fraud_flags",
        ["flagged_provider_id", "status"],
    )

    # idx_otp_phone_created
    # Rate limiting: count OTP requests per phone in last hour
    op.create_index(
        "idx_otp_phone_created",
        "otp_codes",
        ["phone_number", "created_at"],
    )


# ─── Step 4: Triggers ────────────────────────────────────────────────────────

def _create_triggers() -> None:
    """
    6 triggers that enforce the reputation system's integrity at the database level.
    These run INSIDE PostgreSQL — they cannot be bypassed by the application layer.

    Trigger 1: trg_transaction_confirmed   → increment confirmed_tx_count
    Trigger 2: trg_rating_inserted         → increment thumbs_up or thumbs_down count
    Trigger 3: trg_fraud_flag_auto_suspend → auto-suspend provider at 3 pending flags
    Trigger 4: trg_provider_updated_at     → keep updated_at current on every profile change
    Trigger 5: trg_transaction_immutable   → block UPDATE on confirmed transactions
    Trigger 6: trg_rating_immutable        → block UPDATE/DELETE on ratings
    """

    # ── Trigger 1: confirmed_tx_count ────────────────────────────────────────
    # Fires AFTER UPDATE on transactions when status transitions to 'confirmed'.
    # Increments the provider's denormalized confirmed_tx_count counter.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_increment_confirmed_tx_count()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Only fire when status changes FROM something else TO 'confirmed'
            IF NEW.status = 'confirmed' AND OLD.status != 'confirmed' THEN
                UPDATE provider_profiles
                SET confirmed_tx_count = confirmed_tx_count + 1
                WHERE user_id = NEW.provider_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_transaction_confirmed
        AFTER UPDATE ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION fn_increment_confirmed_tx_count();
    """)

    # ── Trigger 2: thumbs_up_count / thumbs_down_count ───────────────────────
    # Fires AFTER INSERT on ratings.
    # Updates the correct counter on the provider's profile atomically.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_update_rating_counts()
        RETURNS TRIGGER AS $$
        DECLARE
            v_provider_id UUID;
        BEGIN
            -- Get the provider_id from the linked transaction
            SELECT provider_id INTO v_provider_id
            FROM transactions
            WHERE id = NEW.transaction_id;

            IF NEW.rating = 'thumbs_up' THEN
                UPDATE provider_profiles
                SET thumbs_up_count = thumbs_up_count + 1
                WHERE user_id = v_provider_id;
            ELSIF NEW.rating = 'thumbs_down' THEN
                UPDATE provider_profiles
                SET thumbs_down_count = thumbs_down_count + 1
                WHERE user_id = v_provider_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_rating_inserted
        AFTER INSERT ON ratings
        FOR EACH ROW
        EXECUTE FUNCTION fn_update_rating_counts();
    """)

    # ── Trigger 3: fraud flag auto-suspension ─────────────────────────────────
    # Fires AFTER INSERT on fraud_flags.
    # If a provider accumulates 3+ pending flags → auto-suspend (is_active = FALSE).
    # Admin must manually review and restore if flags are invalid.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_fraud_flag_auto_suspend()
        RETURNS TRIGGER AS $$
        DECLARE
            v_pending_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO v_pending_count
            FROM fraud_flags
            WHERE flagged_provider_id = NEW.flagged_provider_id
              AND status = 'pending';

            IF v_pending_count >= 3 THEN
                UPDATE users
                SET is_active = FALSE
                WHERE id = NEW.flagged_provider_id;

                UPDATE provider_profiles
                SET is_active = FALSE,
                    suspension_reason = 'Auto-suspended: 3 pending fraud flags. Awaiting admin review.'
                WHERE user_id = NEW.flagged_provider_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_fraud_flag_auto_suspend
        AFTER INSERT ON fraud_flags
        FOR EACH ROW
        EXECUTE FUNCTION fn_fraud_flag_auto_suspend();
    """)

    # ── Trigger 4: provider_profiles.updated_at ──────────────────────────────
    # Fires BEFORE UPDATE on provider_profiles.
    # Keeps updated_at accurate without relying on application code to set it.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_provider_updated_at
        BEFORE UPDATE ON provider_profiles
        FOR EACH ROW
        EXECUTE FUNCTION fn_set_updated_at();
    """)

    # ── Trigger 5: transaction immutability ───────────────────────────────────
    # Fires BEFORE UPDATE on transactions when status = 'confirmed'.
    # Once confirmed, a transaction record is permanent — the ledger cannot be altered.
    # This is the guarantee that makes the credit identity trustworthy.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_transaction_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.status = 'confirmed' THEN
                RAISE EXCEPTION
                    'Transaction % is confirmed and immutable. The reputation ledger is permanent.',
                    OLD.id
                USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_transaction_immutable
        BEFORE UPDATE ON transactions
        FOR EACH ROW
        EXECUTE FUNCTION fn_transaction_immutability();
    """)

    # ── Trigger 6: rating immutability ───────────────────────────────────────
    # Fires BEFORE UPDATE OR DELETE on ratings.
    # Once submitted, a rating is final. No exceptions.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_rating_immutability()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'Rating % is final and cannot be changed or deleted.',
                OLD.id
            USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_rating_immutable
        BEFORE UPDATE OR DELETE ON ratings
        FOR EACH ROW
        EXECUTE FUNCTION fn_rating_immutability();
    """)


# ─── Step 5: Seed Data ───────────────────────────────────────────────────────

def _seed_categories() -> None:
    """
    8 top-level categories — market-validated terminology from Yaoundé field research.
    These never change via the app — seeded once at DB initialisation.
    """
    op.execute("""
        INSERT INTO categories (name_fr, name_en, slug, icon_name, sort_order) VALUES
        ('Couture & Mode',          'Tailoring & Fashion',    'couture',      'scissors',    1),
        ('Cordonnerie',             'Shoe Artisans',          'cordonnerie',  'boot',        2),
        ('Mécanique',               'Mechanical Repair',      'mecanique',    'wrench',      3),
        ('Alimentation',            'Food & Catering',        'alimentation', 'utensils',    4),
        ('Dépannage Téléphone',     'Phone & Tech Repair',    'depannage',    'smartphone',  5),
        ('Coiffure & Esthétique',   'Hair & Beauty',          'coiffure',     'sparkles',    6),
        ('Moto-Taxi & Transport',   'Moto-Taxi & Transport',  'transport',    'bike',        7),
        ('Chantiers & Construction','Home Construction',      'chantiers',    'hammer',      8)
    """)


def _seed_sub_categories() -> None:
    """
    40 sub-categories — 5 per category.
    Terminology tested directly with market traders:
    "Can a provider instantly identify which category they belong to without explanation?"
    """
    op.execute("""
        INSERT INTO sub_categories (category_id, name_fr, name_en, slug) VALUES

        -- 1. Couture & Mode (category_id = 1)
        (1, 'Pagne Africain / Modèle',      'African Print Tailoring',   'pagne-africain'),
        (1, 'Tenue Ouest / Traditionnelle',  'Traditional Outfits',       'tenue-traditionnelle'),
        (1, 'Prêt-à-porter / Vestes',        'Ready-to-Wear / Jackets',   'pret-a-porter'),
        (1, 'Robes & Jupes simples',         'Dresses & Simple Skirts',   'robes-jupes'),
        (1, 'Retouches / Réparations',       'Alterations & Repairs',     'retouches'),

        -- 2. Cordonnerie (category_id = 2)
        (2, 'Sandales en cuir (Babouches)',  'Leather Sandals',           'sandales-cuir'),
        (2, 'Chaussures Homme Cuir',         'Men Leather Shoes',         'chaussures-homme'),
        (2, 'Réparation / Semelles',         'Repair & Soles',            'reparation-semelles'),
        (2, 'Cirage & Teinture',             'Polishing & Dyeing',        'cirage-teinture'),
        (2, 'Mocassins / Dames',             'Loafers / Ladies Shoes',    'mocassins-dames'),

        -- 3. Mécanique (category_id = 3)
        (3, 'Moteur / Entretien',            'Engine / Maintenance',      'moteur-entretien'),
        (3, 'Électricité Auto',              'Auto Electrics',            'electricite-auto'),
        (3, 'Tôlerie & Peinture',            'Body Work & Paint',         'tolerie-peinture'),
        (3, 'Suspension / Amortisseur',      'Suspension & Shocks',       'suspension'),
        (3, 'Diagnostic / Scanner',          'Diagnostic / Scanner',      'diagnostic-scanner'),

        -- 4. Alimentation (category_id = 4)
        (4, 'Beignets-Haricots-Bouillie',    'Beignets & Porridge',       'beignets-haricots'),
        (4, 'Tourne-Dos / Nourriture',       'Tourne-Dos / Street Food',  'tourne-dos'),
        (4, 'Traiteur / Événements',         'Catering / Events',         'traiteur-evenements'),
        (4, 'Jus Naturels / Friandises',     'Natural Juices / Snacks',   'jus-naturels'),
        (4, 'Grillades / Suya / Poisson',    'Grills / Suya / Fish',      'grillades-suya'),

        -- 5. Dépannage Téléphone (category_id = 5)
        (5, 'Changement d''Écran',           'Screen Replacement',        'changement-ecran'),
        (5, 'Déblocage / Flashage',          'Unlocking / Flashing',      'deblocage-flashage'),
        (5, 'Problème Charge / Batterie',    'Charging / Battery Issues', 'charge-batterie'),
        (5, 'Vente d''Accessoires',          'Accessories Sales',         'vente-accessoires'),
        (5, 'Réparation PC / Tablette',      'PC / Tablet Repair',        'reparation-pc'),

        -- 6. Coiffure & Esthétique (category_id = 6)
        (6, 'Tresses Africaines / Perruques','African Braids / Wigs',     'tresses-perruques'),
        (6, 'Coiffure Homme (Gars)',          'Men''s Haircut',            'coiffure-homme'),
        (6, 'Manucure / Pédicure',           'Manicure / Pedicure',       'manucure-pedicure'),
        (6, 'Maquillage (Makeup)',           'Makeup',                    'maquillage'),
        (6, 'Soins Visage / Massage',        'Facial / Massage',          'soins-visage'),

        -- 7. Moto-Taxi & Transport (category_id = 7)
        (7, 'Course Urbaine (Quartier)',     'Urban Ride (Neighbourhood)','course-urbaine'),
        (7, 'Dépôt VIP / Longue Distance',  'VIP / Long Distance',       'depot-vip'),
        (7, 'Livraison Colis Rapide',        'Express Package Delivery',  'livraison-colis'),
        (7, 'Abonnement Mensuel (Écoles)',   'Monthly Subscription',      'abonnement-mensuel'),
        (7, 'Transport Marchandises',        'Goods Transport',           'transport-marchandises'),

        -- 8. Chantiers & Construction (category_id = 8)
        (8, 'Maçonnerie / Crépissage',      'Masonry / Plastering',      'maconnerie'),
        (8, 'Plomberie Sanitaire',          'Plumbing',                  'plomberie'),
        (8, 'Électricité Bâtiment',         'Building Electrics',        'electricite-batiment'),
        (8, 'Menuiserie Bois / Alu',        'Carpentry / Aluminium',     'menuiserie'),
        (8, 'Peinture Bâtiment',            'Building Paint',            'peinture-batiment')
    """)


def _seed_location_nodes() -> None:
    """
    16 predefined Yaoundé economic nodes.
    Coordinates are approximate neighbourhood centres — used for future PostGIS radius queries.
    sort_order = commercial importance (Mokolo and Mfoundi first as primary market hubs).
    """
    op.execute("""
        INSERT INTO location_nodes (name, display_name_fr, latitude, longitude, sort_order) VALUES
        ('Mokolo',      'Mokolo (Grand Marché)',         3.878300, 11.510200, 1),
        ('Mfoundi',     'Mfoundi (Marché Central)',      3.865000, 11.517000, 2),
        ('Biyem-Assi',  'Biyem-Assi',                   3.840000, 11.493000, 3),
        ('Nlongkak',    'Nlongkak',                      3.882000, 11.520000, 4),
        ('Obili',       'Obili (Carrefour)',             3.848000, 11.497000, 5),
        ('Bastos',      'Bastos',                        3.878000, 11.527000, 6),
        ('Mendong',     'Mendong',                       3.820000, 11.480000, 7),
        ('Melen',       'Melen (Polytechnique)',         3.855000, 11.495000, 8),
        ('Elig-Edzoa',  'Elig-Edzoa',                   3.875000, 11.530000, 9),
        ('Essos',       'Essos',                         3.870000, 11.540000, 10),
        ('Nkoldongo',   'Nkoldongo',                     3.880000, 11.545000, 11),
        ('Mvog-Mbi',    'Mvog-Mbi',                      3.860000, 11.525000, 12),
        ('Madagascar',  'Madagascar',                    3.862000, 11.508000, 13),
        ('Nkomkana',    'Nkomkana',                      3.890000, 11.515000, 14),
        ('Etoa-Meki',   'Etoa-Meki',                     3.895000, 11.510000, 15),
        ('Omnisports',  'Omnisports',                    3.855000, 11.523000, 16)
    """)


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNGRADE — reverses everything in the exact reverse order
# ═══════════════════════════════════════════════════════════════════════════════

def downgrade() -> None:
    # Drop triggers first (they depend on tables and functions)
    op.execute("DROP TRIGGER IF EXISTS trg_rating_immutable        ON ratings")
    op.execute("DROP TRIGGER IF EXISTS trg_transaction_immutable   ON transactions")
    op.execute("DROP TRIGGER IF EXISTS trg_provider_updated_at     ON provider_profiles")
    op.execute("DROP TRIGGER IF EXISTS trg_fraud_flag_auto_suspend ON fraud_flags")
    op.execute("DROP TRIGGER IF EXISTS trg_rating_inserted         ON ratings")
    op.execute("DROP TRIGGER IF EXISTS trg_transaction_confirmed   ON transactions")

    # Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS fn_rating_immutability()")
    op.execute("DROP FUNCTION IF EXISTS fn_transaction_immutability()")
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS fn_fraud_flag_auto_suspend()")
    op.execute("DROP FUNCTION IF EXISTS fn_update_rating_counts()")
    op.execute("DROP FUNCTION IF EXISTS fn_increment_confirmed_tx_count()")

    # Drop tables in reverse FK-dependency order
    op.drop_table("otp_codes")
    op.drop_table("fraud_flags")
    op.drop_table("ratings")
    op.drop_table("transactions")
    op.drop_table("provider_profiles")
    op.drop_table("users")
    op.drop_table("location_nodes")
    op.drop_table("sub_categories")
    op.drop_table("categories")

    # Drop ENUM types last
    op.execute("DROP TYPE IF EXISTS fraud_flag_status_enum")
    op.execute("DROP TYPE IF EXISTS rating_value_enum")
    op.execute("DROP TYPE IF EXISTS transaction_status_enum")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
