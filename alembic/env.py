"""
Alembic environment configuration for Njangui.

This file tells Alembic:
- Where the database is (DATABASE_URL from settings)
- What tables to track (Base.metadata from SQLAlchemy models)
- How to run migrations (online = against live DB, offline = generates SQL script)
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Load app config
from app.core.config import settings

# Import Base so Alembic can see the metadata
from app.database import Base

# Import ALL models so they register themselves on Base.metadata
# Without this import, Alembic sees an empty schema and generates nothing
import app.models  # noqa: F401

# Alembic config object — gives access to values in alembic.ini
alembic_config = context.config

# Override the sqlalchemy.url from alembic.ini with our real DATABASE_URL
alembic_config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from the alembic.ini [loggers] section
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# This is the metadata Alembic uses to detect schema changes
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Generates a SQL script without connecting to the database.
    Useful for reviewing what will be executed before running it.
    """
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    Connects to the database and executes migrations directly.
    This is the mode used in normal development and deployment.
    """
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Compare column types precisely — catches type changes in future migrations
            compare_type=True,
            # Compare server defaults — catches default value changes
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
