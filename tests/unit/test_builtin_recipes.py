"""Unit tests for the built-in recipe registry (Task 18).

The registry loads YAML files from ``backend/vman/recipes/builtin``
and exposes a list / detail view to the HTTP layer.  The tests
exercise the loader with a temporary directory so we can verify
edge cases (missing files, duplicate names, malformed YAML) without
touching the real on-disk recipes.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from vman.services.recipe_engine import (
    RecipeNotFoundError,
    builtin_recipes_dir,
    clear_builtin_recipe_cache,
    get_builtin_recipe_summary,
    list_builtin_recipes,
)


def _write_recipe(directory: Path, name: str, body: str) -> Path:
    path = directory / f"{name}.yaml"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


@pytest.fixture
def temp_recipes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the loader at a temporary directory and clear the cache."""
    monkeypatch.setenv("VMAN_BUILTIN_RECIPES_DIR", str(tmp_path))
    clear_builtin_recipe_cache()
    return tmp_path


def test_list_returns_empty_when_no_recipes(temp_recipes: Path) -> None:
    assert list_builtin_recipes() == []


def test_list_summarises_valid_recipe(temp_recipes: Path) -> None:
    _write_recipe(
        temp_recipes,
        "demo",
        """
        schema_version: 1
        name: demo
        version: 0.1.0
        description: A demo recipe
        risk_level: medium
        vars:
          port:
            type: int
            default: 8080
            description: Listening port
        preflight:
          - name: pre
            run: echo pre
        steps:
          - name: run
            run: echo run
        verify:
          - name: check
            run: echo check
        rollback:
          - name: undo
            run: echo undo
        """,
    )
    clear_builtin_recipe_cache()
    rows = list_builtin_recipes()
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "demo"
    assert row["version"] == "0.1.0"
    assert row["risk_level"] == "medium"
    assert row["step_count"] == 1
    assert row["has_preflight"] is True
    assert row["has_verify"] is True
    assert row["has_rollback"] is True
    assert row["vars"]["port"]["type"] == "int"
    assert row["vars"]["port"]["default"] == 8080
    assert row["vars"]["port"]["required"] is False


def test_list_skips_invalid_recipes(temp_recipes: Path) -> None:
    _write_recipe(
        temp_recipes,
        "broken",
        "this is not: valid: yaml: at all: : :",
    )
    _write_recipe(
        temp_recipes,
        "ok",
        """
        schema_version: 1
        name: ok
        version: 0.1.0
        steps:
          - name: run
            run: echo hi
        """,
    )
    clear_builtin_recipe_cache()
    rows = list_builtin_recipes()
    assert [r["name"] for r in rows] == ["ok"]


def test_list_normalises_bare_scalar_vars(temp_recipes: Path) -> None:
    _write_recipe(
        temp_recipes,
        "bare",
        """
        schema_version: 1
        name: bare
        version: 0.1.0
        vars:
          port: 8080
          name: hello
        steps:
          - name: run
            run: echo hi
        """,
    )
    clear_builtin_recipe_cache()
    rows = list_builtin_recipes()
    assert rows[0]["vars"]["port"]["type"] == "string"
    assert rows[0]["vars"]["port"]["default"] == 8080
    assert rows[0]["vars"]["port"]["required"] is False
    assert rows[0]["vars"]["name"]["default"] == "hello"


def test_get_summary_returns_yaml_body(temp_recipes: Path) -> None:
    _write_recipe(
        temp_recipes,
        "demo",
        """
        schema_version: 1
        name: demo
        version: 0.1.0
        steps:
          - name: run
            run: echo hi
        """,
    )
    clear_builtin_recipe_cache()
    summary = get_builtin_recipe_summary("demo")
    assert summary["name"] == "demo"
    assert "schema_version: 1" in summary["yaml"]
    assert "name: demo" in summary["yaml"]


def test_get_summary_raises_for_missing_recipe(temp_recipes: Path) -> None:
    clear_builtin_recipe_cache()
    with pytest.raises(RecipeNotFoundError):
        get_builtin_recipe_summary("does-not-exist")


def test_builtin_recipes_dir_default_points_to_repo() -> None:
    """The default directory must point at the real on-disk recipes."""
    assert builtin_recipes_dir().name == "builtin"


def test_builtin_recipes_list_contains_healthcheck() -> None:
    """The shipped healthcheck recipe must always be discoverable."""
    clear_builtin_recipe_cache()
    names = {r["name"] for r in list_builtin_recipes()}
    assert "healthcheck" in names
