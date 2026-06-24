"""Integration tests for the shipped built-in recipe pack (Task 24)."""

from __future__ import annotations

from pathlib import Path

from vman.services.recipe_engine import parse_recipe_text

BUILTIN_DIR = Path(__file__).resolve().parents[2] / "backend" / "vman" / "recipes" / "builtin"

EXPECTED_RECIPES = {
    "small-vps-cleanup",
    "install-docker",
    "install-caddy",
    "install-nginx",
    "install-nodejs",
    "install-python-uv",
    "install-cloudflare-tunnel",
    "install-9router",
    "install-openwebui",
    "install-open-terminal",
    "basic-hardening",
    "create-sudo-user",
    "setup-ssh-key",
    "disable-password-login",
    "change-ssh-port",
    "setup-ufw",
    "add-swap",
    "set-timezone",
    "setup-fail2ban",
    "unattended-upgrades",
    "reboot-safely",
    "check-failed-services",
    "disk-usage",
    "journal-cleanup",
    "ssl-cert-check",
}

HIGH_RISK_RECIPES = {
    "basic-hardening",
    "change-ssh-port",
    "create-sudo-user",
    "disable-password-login",
    "reboot-safely",
    "setup-ssh-key",
}


def test_shipped_recipe_pack_files_exist_and_match_declared_names() -> None:
    missing = [name for name in EXPECTED_RECIPES if not (BUILTIN_DIR / f"{name}.yaml").exists()]
    assert missing == []

    for name in sorted(EXPECTED_RECIPES):
        path = BUILTIN_DIR / f"{name}.yaml"
        recipe = parse_recipe_text(path.read_text(encoding="utf-8"))
        assert recipe["name"] == name


def test_shipped_recipe_pack_validates_with_preflight_and_verify() -> None:
    for path in sorted(BUILTIN_DIR.glob("*.yaml")):
        recipe = parse_recipe_text(path.read_text(encoding="utf-8"))
        assert recipe["preflight"], f"{path.name} missing preflight"
        assert recipe["steps"], f"{path.name} missing steps"
        assert recipe["verify"], f"{path.name} missing verify"


def test_high_risk_shipped_recipes_require_approval() -> None:
    for name in sorted(HIGH_RISK_RECIPES):
        recipe = parse_recipe_text((BUILTIN_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
        assert recipe["risk_level"] in {"high", "critical"}
        assert recipe["policy"].get("requires_approval") is True
