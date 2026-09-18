"""The probate jurisdiction registry and its North Dakota registration.

The seam the workbench resolves: blank or free-text jurisdiction falls back to
the default, an explicitly unsupported state resolves to ``None`` so the
workbench fails closed, and the ND bundle exposes the same rules and forms the
workbench has always used.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.probate import deadlines, determination, forms, registry


def _estate(jurisdiction):
    return SimpleNamespace(jurisdiction=jurisdiction)


def test_blank_jurisdiction_defaults_to_north_dakota():
    bundle = registry.for_estate(_estate(None))
    assert bundle is registry.default()
    assert bundle.code == "ND"
    assert registry.for_estate(_estate("   ")).code == "ND"


@pytest.mark.parametrize(
    "written", ["North Dakota", "north dakota", "ND", "nd", "N.D."]
)
def test_recognised_north_dakota_spellings_resolve(written):
    assert registry.for_estate(_estate(written)).code == "ND"


def test_free_text_that_is_not_a_state_falls_back_to_default():
    # The estate's jurisdiction field is free-form; a county name is not a
    # reason to refuse the ND workbench.
    assert registry.for_estate(_estate("Cass County")).code == "ND"


def test_an_explicit_unsupported_state_fails_closed():
    assert registry.for_estate(_estate("Minnesota")) is None
    assert registry.for_estate(_estate("TX")) is None


def test_normalize_only_returns_known_state_codes():
    assert registry.normalize("Minnesota") == "MN"
    assert registry.normalize("Not a state") is None
    assert registry.normalize(None) is None
    assert registry.normalize("ZZ") is None


def test_require_rejects_unknown_codes():
    with pytest.raises(registry.UnsupportedJurisdictionError):
        registry.require("MN")
    assert registry.require("nd").code == "ND"


def test_catalog_lists_the_registered_state_for_the_selector():
    catalog = registry.list_jurisdictions()
    assert catalog == [{"code": "ND", "name": "North Dakota", "label": "North Dakota"}]
    assert registry.supported_codes() == {"ND"}


def test_nd_bundle_exposes_the_rules_forms_and_questions():
    bundle = registry.default()
    assert bundle.determine is determination.determine
    assert bundle.deadline_rules is deadlines.RULES
    assert bundle.forms is forms.ND_PROBATE_FORMS
    assert bundle.guidebook_slug == forms.GUIDEBOOK_SLUG
    assert bundle.questions
    assert [f.number for f in bundle.forms_for("informal_testate")] == [2, 3, 4, 5, 7]


def test_nd_bundle_determines_a_track_end_to_end():
    from app.services.probate.facts import ProbateFacts

    bundle = registry.default()
    result = bundle.determine(
        ProbateFacts(
            decedent_name="Ole Olson",
            date_of_death=None,
            will_exists=True,
            real_property_in_nd=True,
            probate_property_value=Decimal("250000"),
        )
    )
    assert result.track == determination.UNDETERMINED
