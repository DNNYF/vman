"""SQLAlchemy declarative base and metadata for VMAN.

All ORM models inherit from ``Base`` defined here. Centralising the
declarative base keeps the metadata in one place so Alembic and the
FastAPI session factory both see the same schema.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base."""

    # Strict type checking: every column declared on a model must have a
    # concrete Python type so mypy/pyright can reason about it.
    type_annotation_map: dict[type, type] = {}


__all__ = ["Base"]
