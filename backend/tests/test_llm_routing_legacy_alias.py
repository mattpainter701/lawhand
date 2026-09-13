"""Static aliases upgrade; registered revisions keep their exact identity."""

import pytest

from app.services import llm_routing


@pytest.mark.parametrize("tier", ["standard", "premium", "background"])
def test_upgrade_legacy_alias_maps_only_static_routes(tier) -> None:
    assert llm_routing._upgrade_legacy_alias(f"clarity-{tier}") == f"lawhand-{tier}"


@pytest.mark.parametrize("tier", ["standard", "premium", "background"])
@pytest.mark.parametrize("suffix", ["-rac12ac34c0ba", "-fb-0"])
def test_registered_legacy_aliases_keep_their_exact_name(tier, suffix) -> None:
    alias = f"clarity-{tier}{suffix}"
    assert llm_routing._upgrade_legacy_alias(alias) == alias


@pytest.mark.parametrize("tier", ["standard", "premium", "background"])
def test_legacy_revision_override_follows_explicit_active_route(tier) -> None:
    alias = f"clarity-{tier}-rprevious"
    active = f"lawhand-{tier}-rcurrent"
    assert (
        llm_routing._current_managed_alias(alias, {f"{tier}_model": active}) == active
    )
    assert llm_routing._current_managed_alias(alias, {}) == alias


def test_upgrade_legacy_alias_leaves_current_and_custom_aliases() -> None:
    assert llm_routing._upgrade_legacy_alias("lawhand-standard") == "lawhand-standard"
    assert llm_routing._upgrade_legacy_alias("openai/gpt-5") == "openai/gpt-5"
    assert llm_routing._upgrade_legacy_alias(None) is None
    assert llm_routing._upgrade_legacy_alias("") is None


def test_current_managed_alias_forwards_legacy_tenant_override() -> None:
    config = {
        "standard_model": "lawhand-standard-r9",
        "premium_model": None,
        "background_model": None,
    }
    assert (
        llm_routing._current_managed_alias("clarity-standard", config)
        == "lawhand-standard-r9"
    )


def test_normalize_config_upgrades_stored_legacy_models() -> None:
    config = llm_routing._normalize_config(
        {"standard_model": "clarity-standard", "premium_model": "clarity-premium-r2"}
    )
    assert config["standard_model"] == "lawhand-standard"
    assert config["premium_model"] == "clarity-premium-r2"


@pytest.mark.parametrize("tier", ["standard", "premium", "background"])
def test_default_config_upgrades_legacy_env_alias(tier, monkeypatch) -> None:
    """A pre-rename host env file must not select an alias the gateway lacks."""

    monkeypatch.setattr(
        llm_routing.settings, f"LITELLM_{tier.upper()}_MODEL", f"clarity-{tier}"
    )

    assert (
        llm_routing.default_platform_llm_config()[f"{tier}_model"] == f"lawhand-{tier}"
    )


@pytest.mark.parametrize("tier", ["standard", "premium", "background"])
def test_normalize_config_upgrades_legacy_env_fallback(tier, monkeypatch) -> None:
    """The settings fallback is upgraded, not only a stored platform value."""

    monkeypatch.setattr(
        llm_routing.settings, f"LITELLM_{tier.upper()}_MODEL", f"clarity-{tier}"
    )

    config = llm_routing._normalize_config({f"{tier}_provider": "litellm"})

    assert config[f"{tier}_model"] == f"lawhand-{tier}"


def test_default_config_preserves_registered_revision_env(monkeypatch) -> None:
    """A registered revision alias keeps its exact name; only static aliases move."""

    monkeypatch.setattr(
        llm_routing.settings,
        "LITELLM_STANDARD_MODEL",
        "clarity-standard-rac12ac34c0ba",
    )

    assert (
        llm_routing.default_platform_llm_config()["standard_model"]
        == "clarity-standard-rac12ac34c0ba"
    )
