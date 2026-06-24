"""Alembic environment configuration for VMAN.

This script wires Alembic to ``vman.db.base.Base.metadata`` so the
migration autogenerate sees every ORM model declared under
``vman.db.models``. The SQLAlchemy URL is taken from ``Settings`` so
the same migration runs against SQLite (MVP) and PostgreSQL (future)
without editing the script.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importing the models module registers every mapped class on Base.metadata.
import vman.db.models  # noqa: F401
from vman.config import get_settings
from vman.db.base import Base

config = context.config

# Override the URL from alembic.ini with whatever Settings says. We
# deliberately do NOT log the URL -- it can contain credentials.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    url = config.get_main_option("sqlalchemy.url") or ""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live engine."""
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
