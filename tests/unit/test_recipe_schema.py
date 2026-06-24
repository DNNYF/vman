"""Unit tests for the recipe schema validator (Milestone 4 / Task 13)."""

from __future__ import annotations

import pytest

from vman.services.recipe_engine import (
    RecipeSchemaError,
    parse_recipe_text,
    validate_recipe,
)

VALID_RECIPE = """
schema_version: 1
name: install-9router
version: 0.1.0
description: Install 9router on a small VPS
risk_level: medium
supported_os:
  families: [debian]
  names: [ubuntu, debian]
vars:
  service_port:
    type: int
    default: 8080
    description: Listening port
policy:
  requires_approval: false
  forbidden_on_environments: [production]
preflight:
  - name: show identity
    run: |
      whoami
      uname -a
steps:
  - name: install dependencies
    run: |
      apt-get update
      apt-get install -y curl ca-certificates
verify:
  - name: check service
    run: |
      systemctl status 9router --no-pager || true
      ss -tulpn | grep "{{ service_port }}" || true
rollback:
  - name: manual rollback
    run: echo "Manual rollback may be required"
"""


def test_valid_recipe_parses() -> None:
    recipe = parse_recipe_text(VALID_RECIPE)
    assert recipe["name"] == "install-9router"
    assert recipe["risk_level"] == "medium"


def test_recipe_missing_name_rejected() -> None:
    bad = "schema_version: 1\nversion: 0.1.0\n"
    with pytest.raises(RecipeSchemaError):
        parse_recipe_text(bad)


def test_recipe_missing_version_rejected() -> None:
    bad = "schema_version: 1\nname: x\n"
    with pytest.raises(RecipeSchemaError):
        parse_recipe_text(bad)


def test_recipe_unsupported_schema_version_rejected() -> None:
    bad = "schema_version: 99\nname: x\nversion: 0.1.0\n"
    with pytest.raises(RecipeSchemaError):
        parse_recipe_text(bad)


def test_recipe_invalid_risk_level_rejected() -> None:
    bad = "schema_version: 1\nname: x\nversion: 0.1.0\nrisk_level: super\n"
    with pytest.raises(RecipeSchemaError):
        parse_recipe_text(bad)


def test_recipe_steps_must_have_name_and_run() -> None:
    bad = "schema_version: 1\nname: x\nversion: 0.1.0\nsteps:\n  - name: foo\n"  # missing run
    with pytest.raises(RecipeSchemaError):
        parse_recipe_text(bad)


def test_recipe_renders_simple_variable() -> None:
    recipe = parse_recipe_text(VALID_RECIPE)
    out = recipe["steps"][0]["run"]
    assert "apt-get" in out
    # Render {{ service_port }} and confirm nothing crashes.
    from vman.services.recipe_engine import render_text

    assert "8080" in render_text("echo port={{ service_port }}", recipe["vars"])


def test_recipe_variable_substitution_does_not_eval() -> None:
    """The renderer must NOT eval or execute arbitrary Python."""
    from vman.services.recipe_engine import render_text

    # Even if a variable value contains a backtick or semicolon, the
    # renderer must not interpret it.
    out = render_text("echo {{ secret }}", {"secret": "$(rm -rf /)"})
    assert out == "echo $(rm -rf /)"


def test_recipe_rejects_unknown_variable() -> None:
    from vman.services.recipe_engine import render_text

    with pytest.raises(RecipeSchemaError):
        render_text("echo {{ undefined }}", {})


def test_recipe_renders_multiple_variables() -> None:
    from vman.services.recipe_engine import render_text

    out = render_text(
        "{{ greeting }}, {{ name }}!",
        {"greeting": "hello", "name": "world"},
    )
    assert out == "hello, world!"


def test_recipe_validate_returns_recipe_dict() -> None:
    recipe = validate_recipe(parse_recipe_text(VALID_RECIPE))
    assert recipe["name"] == "install-9router"


def test_recipe_rejects_non_string_steps_run() -> None:
    bad = "schema_version: 1\nname: x\nversion: 0.1.0\nsteps:\n  - name: foo\n    run: 123\n"
    with pytest.raises(RecipeSchemaError):
        parse_recipe_text(bad)


def test_recipe_supports_optional_sections() -> None:
    minimal = (
        "schema_version: 1\nname: minimal\nversion: 0.1.0\n"
        "steps:\n  - name: do-it\n    run: echo done\n"
    )
    recipe = parse_recipe_text(minimal)
    assert recipe["preflight"] == []
    assert recipe["verify"] == []
    assert recipe["rollback"] == []


def test_recipe_vars_types() -> None:
    from vman.services.recipe_engine import render_text

    out = render_text(
        "port={{ p }}; n={{ n }}; s={{ s }}; b={{ b }}",
        {"p": 8080, "n": 3, "s": "x", "b": True},
    )
    assert "port=8080" in out
    assert "n=3" in out
    assert "s=x" in out
    assert "b=True" in out


def test_recipe_vars_int_validated() -> None:
    from vman.services.recipe_engine import render_text

    with pytest.raises(RecipeSchemaError):
        render_text("{{ p }}", {"p": "not-an-int"}, var_type="int")
