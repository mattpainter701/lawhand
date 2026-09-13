"""Stored ``clarity-*`` route aliases map forward to their LawHand names.

The platform aliases were renamed from ``clarity-*`` to ``lawhand-*``. Platform
settings and tenant overrides written before the rename still carry the old
prefix, so ``llm_routing`` rewrites them on read until the next save persists
the new name.
"""

from app.services import llm_routing


def test_upgrade_legacy_alias_maps_old_managed_routes() -> None:
    assert llm_routing._upgrade_legacy_alias("clarity-standard") == "lawhand-standard"
    assert (
        llm_routing._upgrade_legacy_alias("clarity-premium-r7")
        == "lawhand-premium-r7"
    )
    assert (
        llm_routing._upgrade_legacy_alias("clarity-background-fb-0")
        == "lawhand-background-fb-0"
    )


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
    assert config["premium_model"] == "lawhand-premium-r2"
