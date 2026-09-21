"""Pure helpers of the fill-session background save (no database)."""

from app.services.fill_sessions import _merge_member_statuses


def test_merge_keeps_an_earlier_members_outcome_and_orders_by_packet():
    prior = {
        "a": {"template_id": "a", "status": "saved", "matter_document_id": "d1"},
        "b": {"template_id": "b", "status": "queued"},
    }
    members = [{"template_id": "b", "variables": {}}]
    outcomes = [{"template_id": "b", "status": "saved", "matter_document_id": "d2"}]

    merged = _merge_member_statuses(prior, members, outcomes)

    assert [entry["template_id"] for entry in merged] == ["b", "a"]
    assert merged[0] == outcomes[0]
    # The member an earlier attempt saved survives a retry that did not carry it.
    assert merged[1] == prior["a"]


def test_merge_marks_members_not_yet_processed_as_queued():
    merged = _merge_member_statuses({}, [{"template_id": "x"}], [])

    assert merged == [{"template_id": "x", "status": "queued"}]
