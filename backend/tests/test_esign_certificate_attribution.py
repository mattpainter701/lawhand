"""What a signing evidence certificate asserts about the signer's address.

Issue #488: the certificate printed an internal proxy address as the signer's.
An evidence artifact that names our own infrastructure as the signer is weaker
than one that says plainly that no address can be attributed, so the renderer
must never turn a missing address into a dash the reader takes for "none
recorded".
"""

from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfReader

from app.services.esign.certificate import (
    IP_NOT_ATTRIBUTABLE,
    IP_NOT_ATTRIBUTABLE_NOTE,
    build_certificate,
)
from app.services.esign.service import record_portal_signature


def _signer(*, signed_ip, name="Jane Client"):
    return SimpleNamespace(
        name=name,
        email="jane@example.com",
        typed_signature="Jane Client",
        signed_at=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        signed_ip=signed_ip,
        method="portal_inline",
        audit={"method": "portal_inline"},
        field_values={"name": "Jane", "blank": ""},
    )


def _pdf_text(content: bytes) -> str:
    """What a reader actually sees on the rendered certificate."""
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# ── The recorded address ─────────────────────────────────────────────────────


def test_certificate_prints_the_signer_address_when_we_have_one():
    content, _, content_type = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[_signer(signed_ip="203.0.113.7")],
    )
    text = _pdf_text(content)
    assert "203.0.113.7" in text
    assert IP_NOT_ATTRIBUTABLE not in text


def test_certificate_says_not_attributable_rather_than_printing_a_dash():
    content, _, _ = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[_signer(signed_ip=None)],
    )
    text = _pdf_text(content)
    assert IP_NOT_ATTRIBUTABLE in text


def test_certificate_explains_the_term_for_the_reader():
    content, _, _ = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[_signer(signed_ip=None)],
    )
    text = _pdf_text(content)
    # The note is wrapped across lines, so assert on a distinctive fragment.
    assert "no signer address is" in text
    assert IP_NOT_ATTRIBUTABLE_NOTE.startswith('An address shown as "not attributable"')


def test_certificate_omits_the_explanation_when_every_address_is_attributed():
    content, _, _ = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[_signer(signed_ip="203.0.113.7")],
    )
    assert "no signer address is" not in _pdf_text(content)


def test_an_empty_address_is_treated_as_unattributable_not_as_a_value():
    content, _, _ = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[_signer(signed_ip="   ")],
    )
    assert IP_NOT_ATTRIBUTABLE in _pdf_text(content)


def test_a_mixed_request_names_the_one_signer_we_cannot_place():
    content, _, _ = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[
            _signer(signed_ip="203.0.113.7", name="Jane Client"),
            _signer(signed_ip=None, name="Sam Counterparty"),
        ],
    )
    text = _pdf_text(content)
    assert "203.0.113.7" in text
    assert IP_NOT_ATTRIBUTABLE in text
    assert "no signer address is" in text


# ── The HTML fallback carries the same statement ─────────────────────────────


def test_html_fallback_states_attribution_too(monkeypatch):
    # build_certificate falls back to HTML when PDF generation is unavailable.
    import builtins

    real_import = builtins.__import__

    def _no_reportlab(name, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ImportError("reportlab unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_reportlab)

    content, filename, content_type = build_certificate(
        matter_name="Rivera custody",
        document_name="agreement.pdf",
        signers=[_signer(signed_ip=None)],
    )
    assert content_type == "text/html"
    html = content.decode("utf-8")
    assert IP_NOT_ATTRIBUTABLE in html
    assert "no signer address is" in html


# ── The audit says which of the two it recorded ──────────────────────────────


@pytest.mark.asyncio
async def test_audit_marks_an_attributed_address_as_the_client():
    signer = SimpleNamespace(audit=None, field_values=None)
    await record_portal_signature(
        signer,
        typed_signature="Jane Client",
        ip="203.0.113.7",
        consent_text_version="clarity-esign-consent-v1",
    )
    assert signer.signed_ip == "203.0.113.7"
    assert signer.audit["ip_source"] == "client"


@pytest.mark.asyncio
async def test_audit_marks_a_missing_address_as_unattributable():
    signer = SimpleNamespace(audit=None, field_values=None)
    await record_portal_signature(
        signer,
        typed_signature="Jane Client",
        ip=None,
        consent_text_version="clarity-esign-consent-v1",
    )
    assert signer.signed_ip is None
    assert signer.audit["ip"] is None
    assert signer.audit["ip_source"] == "unattributable"
