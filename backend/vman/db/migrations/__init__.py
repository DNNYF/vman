"""Alembic migrations for VMAN.

Run with: ``alembic upgrade head`` from the project root.
``env.py`` loads ``Settings.database_url`` so the migration target
tracks whatever database URL the operator configured in ``.env``.
"""
