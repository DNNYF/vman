"""Recipe HTTP routes (Milestone 4 / Task 13 + Task 18)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from vman.api.deps import CurrentUser
from vman.db.session import get_sessionmaker
from vman.security.csrf import require_csrf
from vman.services.recipe_engine import (
    RecipeEngine,
    RecipeNotFoundError,
    RecipeSchemaError,
    get_builtin_recipe_summary,
    list_builtin_recipes,
    parse_recipe_text,
)

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _engine() -> RecipeEngine:
    return RecipeEngine(session_factory=get_sessionmaker())


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #


class RecipeRunRequest(BaseModel):
    host_id: str = Field(..., min_length=1, max_length=64)
    recipe_yaml: str = Field(..., min_length=1, max_length=200_000)
    vars: dict[str, object] = Field(default_factory=dict)
    timeout_seconds: int = Field(600, ge=1, le=86400)


class RecipeValidateRequest(BaseModel):
    recipe_yaml: str = Field(..., min_length=1, max_length=200_000)


class RecipeValidateResponse(BaseModel):
    name: str
    version: str
    risk_level: str
    step_count: int
    has_preflight: bool
    has_verify: bool
    has_rollback: bool


class RecipeRunResponse(BaseModel):
    job_id: str
    status: str
    exit_code: int | None = None


# --------------------------------------------------------------------------- #
# Validate
# --------------------------------------------------------------------------- #


@router.post("/validate", response_model=RecipeValidateResponse)
def validate_recipe(
    payload: RecipeValidateRequest,
    _user: CurrentUser,
) -> RecipeValidateResponse:
    try:
        recipe = parse_recipe_text(payload.recipe_yaml)
    except RecipeSchemaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return RecipeValidateResponse(
        name=str(recipe["name"]),
        version=str(recipe.get("version", "0.0.0")),
        risk_level=str(recipe.get("risk_level", "low")),
        step_count=len(recipe.get("steps", [])),
        has_preflight=bool(recipe.get("preflight")),
        has_verify=bool(recipe.get("verify")),
        has_rollback=bool(recipe.get("rollback")),
    )


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #


@router.post("/run", response_model=RecipeRunResponse)
def run_recipe(
    payload: RecipeRunRequest,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
) -> RecipeRunResponse:
    try:
        recipe = parse_recipe_text(payload.recipe_yaml)
    except RecipeSchemaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    try:
        job_id = _engine().run_recipe(
            recipe=recipe,
            host_id=payload.host_id,
            actor_user_id=user.id,
            vars_values=payload.vars,
            timeout_seconds=payload.timeout_seconds,
        )
    except RecipeSchemaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Read back the job for the response.
    from sqlalchemy import select

    from vman.db import models
    from vman.db.session import get_sessionmaker as _sm

    with _sm()() as s:
        job = s.execute(select(models.Job).where(models.Job.id == job_id)).scalar_one()
        return RecipeRunResponse(
            job_id=job.id,
            status=job.status,
            exit_code=job.exit_code,
        )


# --------------------------------------------------------------------------- #
# List / get
# --------------------------------------------------------------------------- #


@router.get("")
def list_recipes(_user: CurrentUser) -> list[dict]:
    """Return summaries of every built-in recipe VMAN knows about.

    Task 18 wires the dashboard's recipe catalogue to this endpoint.
    For the MVP the registry only contains the recipes shipped under
    ``backend/vman/recipes/builtin``; future tasks may add a
    user-uploaded registry on top of the same shape.
    """
    return list_builtin_recipes()


@router.get("/{name}")
def get_recipe(name: str, _user: CurrentUser) -> dict:
    """Return one built-in recipe (summary + raw YAML body)."""
    try:
        return get_builtin_recipe_summary(name)
    except RecipeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


__all__ = ["router"]
