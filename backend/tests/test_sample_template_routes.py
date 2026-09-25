"""Endpoint-level tests for the global sample-template library router.

These exercise the handler logic directly with a mocked async session (no live
database), covering list/detail/source/render branches and the read-only
guarantees the catalog relies on.
"""

import uuid
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.main import app
from app.routers import sample_templates
from app.routers import document_templates
from app.services.pdf_templates import discover_pdf_fields


def _fillable_pdf() -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.drawString(72, 720, "Client:")
    pdf.acroForm.textfield(name="Client Name", x=120, y=705, width=250, height=24)
    pdf.save()
    return output.getvalue()


def _pdf_with_slash_default() -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.acroForm.textfield(
        name="Literal default", value="/keep-this-slash", x=72, y=700, width=250, height=24
    )
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _sample(**overrides) -> SimpleNamespace:
    payload = {
        "id": uuid.uuid4(),
        "slug": "last-will-and-testament",
        "title": "Last Will and Testament",
        "category": "wills_trusts",
        "jurisdictions": ["North Dakota"],
        "description": "Generic starter form.",
        "format": "pdf",
        "field_count": 26,
        "variable_schema": {"fields": []},
        "source_filename": "wills_trusts/last-will-and-testament.pdf",
        "source_sha256": "a" * 64,
        "source_file_size": 100,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def scalar_one(self):
        return self._rows[0] if self._rows else None


@pytest.mark.asyncio
async def test_list_filters_by_category_and_jurisdiction():
    sample = _sample(category="wills_trusts", jurisdictions=["North Dakota"])
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult([sample]),  # category-filtered rows
            _ScalarResult([1]),  # count
        ]
    )

    response = await sample_templates.list_sample_templates(
        category="wills_trusts",
        jurisdiction="North Dakota",
        current_user=SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4()),
        db=db,
    )
    assert response.total == 1
    assert response.items[0].slug == "last-will-and-testament"


@pytest.mark.asyncio
async def test_get_returns_sample():
    sample = _sample()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)

    response = await sample_templates.get_sample_template(
        sample.id, current_user=None, db=db
    )
    assert response.slug == "last-will-and-testament"


@pytest.mark.asyncio
async def test_get_missing_returns_404():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.get_sample_template(uuid.uuid4(), current_user=None, db=db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_render_fills_sample(monkeypatch):
    pdf = _fillable_pdf()
    fields = discover_pdf_fields(pdf)
    sample = _sample(variable_schema={"version": 1, "fields": fields})
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    monkeypatch.setattr(sample_templates, "_verified_source", lambda s: pdf)

    response = await sample_templates.render_sample_template(
        sample.id,
        sample_templates.SampleTemplateRenderRequest(
            variables={fields[0]["name"]: "Ada Example"}
        ),
        current_user=None,
        db=db,
    )
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_render_requires_seeded_schema():
    sample = _sample(variable_schema=None)
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.render_sample_template(
            sample.id,
            sample_templates.SampleTemplateRenderRequest(variables={}),
            current_user=None,
            db=db,
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_smart_fill_preview_scopes_to_selected_matter(monkeypatch):
    tenant_id = uuid.uuid4()
    sample = _sample(variable_schema={"version": 1, "fields": [{"name": "client_name"}]})
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    db.execute = AsyncMock()
    monkeypatch.setattr(sample_templates, "set_tenant_context", AsyncMock())
    monkeypatch.setattr(
        sample_templates,
        "build_variable_suggestions",
        AsyncMock(return_value=("matter-1", [SimpleNamespace(
            model_dump=lambda **_: {
                "variable": "client_name",
                "suggested_value": "Ada Example",
                "source_type": "matter",
                "source_field": "client.name",
                "provenance": {},
                "confidence": 1.0,
                "review_required": True,
            }
        )])),
    )
    response = await sample_templates.smart_fill_sample_template(
        sample.id,
        sample_templates.SampleTemplateSmartFillRequest(matter_id="matter-1"),
        current_user=SimpleNamespace(tenant_id=tenant_id),
        db=db,
    )
    assert response.matter_id == "matter-1"
    assert response.variables[0]["suggested_value"] == "Ada Example"
    sample_templates.set_tenant_context.assert_awaited_once_with(db, str(tenant_id))


@pytest.mark.asyncio
async def test_smart_fill_preview_uses_real_resolver_with_sample_schema(monkeypatch):
    tenant_id = uuid.uuid4()
    matter_id = uuid.uuid4()
    sample = _sample(
        variable_schema={
            "version": 1,
            "fields": [{"name": "client_name", "label": "Client name"}],
        }
    )
    matter = SimpleNamespace(
        id=matter_id,
        matter_name="Lovelace intake",
        case_number="CV-2026-1",
        matter_type="civil",
        status="open",
        client=SimpleNamespace(
            id=uuid.uuid4(),
            display_name="Ada Example",
            email="ada@example.com",
            phone="555-0100",
            address={"city": "Fargo", "state": "ND", "zip": "58102"},
        ),
        attorney_of_record=None,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    monkeypatch.setattr(sample_templates, "set_tenant_context", AsyncMock())

    async def load_matter(**kwargs):
        assert kwargs["matter_id"] == str(matter_id)
        return matter

    async def load_parties(**kwargs):
        return []

    async def load_evidence(**kwargs):
        return ()

    monkeypatch.setattr(document_templates, "_load_matter_context", load_matter)
    monkeypatch.setattr(document_templates, "_load_matter_parties", load_parties)
    monkeypatch.setattr(document_templates, "_load_document_evidence", load_evidence)

    response = await sample_templates.smart_fill_sample_template(
        sample.id,
        sample_templates.SampleTemplateSmartFillRequest(
            matter_id=str(matter_id), variables=["client_name"]
        ),
        current_user=SimpleNamespace(
            id=uuid.uuid4(), tenant_id=tenant_id, full_name="Test Attorney", email="test@example.com"
        ),
        db=db,
    )

    assert response.matter_id == str(matter_id)
    assert response.variables[0]["variable"] == "client_name"
    assert response.variables[0]["suggested_value"] == "Ada Example"


@pytest.mark.asyncio
async def test_smart_fill_preview_requires_seeded_schema():
    sample = _sample(variable_schema=None)
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.smart_fill_sample_template(
            sample.id,
            sample_templates.SampleTemplateSmartFillRequest(matter_id="matter-1"),
            current_user=SimpleNamespace(tenant_id=uuid.uuid4()),
            db=db,
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_smart_fill_preview_preserves_matter_access_denial(monkeypatch):
    sample = _sample(variable_schema={"version": 1, "fields": [{"name": "client_name"}]})
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    monkeypatch.setattr(sample_templates, "set_tenant_context", AsyncMock())
    monkeypatch.setattr(
        sample_templates,
        "build_variable_suggestions",
        AsyncMock(side_effect=HTTPException(status_code=404, detail="Matter not found")),
    )
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.smart_fill_sample_template(
            sample.id,
            sample_templates.SampleTemplateSmartFillRequest(matter_id="other-tenant-matter"),
            current_user=SimpleNamespace(tenant_id=uuid.uuid4()),
            db=db,
        )
    assert exc_info.value.status_code == 404


def test_text_defaults_preserve_a_leading_slash():
    field = discover_pdf_fields(_pdf_with_slash_default())[0]
    assert field["field_type"] == "text"
    assert field["default"] == "/keep-this-slash"


@pytest.mark.asyncio
async def test_download_source_streams_pdf(monkeypatch):
    sample = _sample()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=sample)
    monkeypatch.setattr(sample_templates, "_verified_source", lambda s: b"%PDF-1.4 x")

    response = await sample_templates.download_sample_source(
        sample.id, current_user=None, db=db
    )
    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.4 x"


def _effective_routes():
    """Yield (path, methods) in real registration order.

    FastAPI 0.139 keeps included routers behind lazy wrappers, so ``app.routes``
    entries need unwrapping through ``effective_route_contexts``.
    """
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        entries = list(contexts()) if callable(contexts) else [route]
        for entry in entries:
            path = getattr(entry, "path", None)
            if path is not None:
                yield path, getattr(entry, "methods", None) or set()


def test_sample_library_route_is_not_shadowed_by_tenant_templates():
    """``GET /api/templates/library`` must resolve to the catalog, not a template id.

    ``document_templates`` declares a greedy ``GET /{template_id}`` under the same
    ``/api/templates`` prefix. If it is registered first, the library path is
    parsed as a template UUID and answered with 422, which surfaced in Template
    Studio as "The sample library could not be loaded."
    """
    for path, methods in _effective_routes():
        if path == "/api/templates/library" and "GET" in methods:
            return
        if path == "/api/templates/{template_id}" and "GET" in methods:
            raise AssertionError(
                "GET /api/templates/library is shadowed by the tenant template "
                "detail route; register sample_templates_router first"
            )
    raise AssertionError("GET /api/templates/library is not registered")


def _save_fixture(monkeypatch, *, fields=None, folder=None):
    pdf = _fillable_pdf()
    fields = fields if fields is not None else discover_pdf_fields(pdf)
    tenant_id = uuid.uuid4()
    matter = SimpleNamespace(id=uuid.uuid4(), slug="smith-divorce", cloud_folder=None)
    sample = _sample(
        variable_schema={"version": 1, "fields": fields},
        provenance={"source_name": "ND Courts", "edition": "May 2023"},
    )
    added = []
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[sample, None])  # sample, tenant settings
    db.add_all = lambda rows: added.extend(rows)
    storage = SimpleNamespace(
        backend="local",
        provider=None,
        storage_path="/data/smith/generated/form.pdf",
        provider_item_id=None,
        drive_id=None,
        parent_id=None,
        error=None,
    )
    store = AsyncMock(return_value=storage)
    monkeypatch.setattr(sample_templates, "set_tenant_context", AsyncMock())
    monkeypatch.setattr(sample_templates, "_verified_source", lambda s: pdf)
    monkeypatch.setattr(sample_templates, "_load_render_matter", AsyncMock(return_value=matter))
    monkeypatch.setattr(
        sample_templates, "get_folder_or_404", AsyncMock(return_value=folder)
    )
    monkeypatch.setattr(
        sample_templates.matter_file_store, "store_matter_file_result", store
    )
    monkeypatch.setattr(
        sample_templates,
        "_saved_document_response",
        AsyncMock(return_value=None),
    )
    compensate = AsyncMock(return_value=True)
    monkeypatch.setattr(sample_templates, "_compensate_staged_document", compensate)
    monkeypatch.setattr(sample_templates, "_rollback_quietly", AsyncMock(return_value=True))
    user = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id)
    return SimpleNamespace(
        db=db, sample=sample, matter=matter, fields=fields, added=added,
        store=store, user=user, compensate=compensate, tenant_id=tenant_id,
    )


def _blank(ctx):
    return {field["name"]: "" for field in ctx.fields}


@pytest.mark.asyncio
async def test_save_to_matter_files_filled_pdf_with_library_provenance(monkeypatch):
    ctx = _save_fixture(monkeypatch)
    name = ctx.fields[0]["name"]

    response = await sample_templates.save_sample_to_matter(
        ctx.sample.id,
        sample_templates.SampleTemplateSaveToMatterRequest(
            matter_id=str(ctx.matter.id),
            variables={name: "Ada Example"},
            verified_fields=[name, "not_filled"],
        ),
        current_user=ctx.user,
        db=ctx.db,
    )

    doc, event = ctx.added
    assert response.matter_document_id == str(doc.id)
    assert response.matter_id == str(ctx.matter.id)
    assert response.output_filename.startswith("Last Will and Testament-")
    assert response.output_filename.endswith(".pdf")
    assert doc.matter_id == ctx.matter.id
    assert doc.tenant_id == ctx.tenant_id
    assert doc.document_category == "generated"
    assert doc.content_type == "application/pdf"
    assert doc.folder_id is None
    assert doc.description == "Filled from global library form: Last Will and Testament"
    assert doc.generation_summary["sample_template_id"] == str(ctx.sample.id)
    assert doc.generation_summary["source"] == "global_library"
    assert doc.generation_summary["filled"] == 1
    assert doc.generation_summary["verified_fields"] == [name]
    assert event.event_type == "document_generated"
    assert event.metadata_json["output_document_id"] == str(doc.id)
    assert event.metadata_json["sample_source_name"] == "ND Courts"
    stored = ctx.store.await_args.kwargs
    assert stored["content"].startswith(b"%PDF-")
    assert stored["category"] == "generated"
    assert stored["matter_slug"] == "smith-divorce"
    ctx.db.commit.assert_awaited_once()
    sample_templates.set_tenant_context.assert_awaited_with(ctx.db, str(ctx.tenant_id))


@pytest.mark.asyncio
async def test_save_to_matter_routes_into_the_chosen_folder(monkeypatch):
    folder = SimpleNamespace(id=uuid.uuid4())
    ctx = _save_fixture(monkeypatch, folder=folder)
    monkeypatch.setattr(
        sample_templates,
        "storage_routing_for_folder",
        lambda chosen: ("pleadings", ["Pleadings"]) if chosen is folder else (None, None),
    )

    await sample_templates.save_sample_to_matter(
        ctx.sample.id,
        sample_templates.SampleTemplateSaveToMatterRequest(
            matter_id=str(ctx.matter.id), variables=_blank(ctx), folder_id=folder.id
        ),
        current_user=ctx.user,
        db=ctx.db,
    )

    assert ctx.added[0].folder_id == folder.id
    assert ctx.store.await_args.kwargs["category"] == "pleadings"
    assert ctx.store.await_args.kwargs["folder_path"] == ["Pleadings"]


@pytest.mark.asyncio
async def test_save_to_matter_rejects_a_folder_from_another_matter(monkeypatch):
    from app.services.matter_document_organization import DocumentOrganizationError

    ctx = _save_fixture(monkeypatch)
    monkeypatch.setattr(
        sample_templates,
        "get_folder_or_404",
        AsyncMock(side_effect=DocumentOrganizationError(404, "folder_not_found", "Folder not found")),
    )
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.save_sample_to_matter(
            ctx.sample.id,
            sample_templates.SampleTemplateSaveToMatterRequest(
                matter_id=str(ctx.matter.id), variables={}, folder_id=uuid.uuid4()
            ),
            current_user=ctx.user,
            db=ctx.db,
        )
    assert exc_info.value.status_code == 404
    ctx.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_to_matter_enforces_required_answers(monkeypatch):
    pdf_fields = discover_pdf_fields(_fillable_pdf())
    required = [{**pdf_fields[0], "required": True}]
    ctx = _save_fixture(monkeypatch, fields=required)
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.save_sample_to_matter(
            ctx.sample.id,
            sample_templates.SampleTemplateSaveToMatterRequest(
                matter_id=str(ctx.matter.id), variables={}
            ),
            current_user=ctx.user,
            db=ctx.db,
        )
    assert exc_info.value.status_code == 422
    ctx.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_to_matter_requires_seeded_schema(monkeypatch):
    ctx = _save_fixture(monkeypatch)
    ctx.sample.variable_schema = None
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.save_sample_to_matter(
            ctx.sample.id,
            sample_templates.SampleTemplateSaveToMatterRequest(matter_id="m-1"),
            current_user=ctx.user,
            db=ctx.db,
        )
    assert exc_info.value.status_code == 409
    ctx.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_to_matter_removes_the_staged_file_when_the_row_cannot_flush(monkeypatch):
    ctx = _save_fixture(monkeypatch)
    ctx.db.flush = AsyncMock(side_effect=RuntimeError("db down"))
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.save_sample_to_matter(
            ctx.sample.id,
            sample_templates.SampleTemplateSaveToMatterRequest(
                matter_id=str(ctx.matter.id), variables=_blank(ctx)
            ),
            current_user=ctx.user,
            db=ctx.db,
        )
    assert exc_info.value.status_code == 500
    assert "staged file was removed" in exc_info.value.detail
    ctx.compensate.assert_awaited_once()
    ctx.db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_to_matter_keeps_the_file_when_the_commit_outcome_is_unknown(monkeypatch):
    ctx = _save_fixture(monkeypatch)
    ctx.db.commit = AsyncMock(side_effect=RuntimeError("ack lost"))
    monkeypatch.setattr(
        sample_templates, "_matter_document_commit_outcome", AsyncMock(return_value=None)
    )
    with pytest.raises(HTTPException) as exc_info:
        await sample_templates.save_sample_to_matter(
            ctx.sample.id,
            sample_templates.SampleTemplateSaveToMatterRequest(
                matter_id=str(ctx.matter.id), variables=_blank(ctx)
            ),
            current_user=ctx.user,
            db=ctx.db,
        )
    assert exc_info.value.status_code == 500
    ctx.compensate.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_to_matter_removes_the_file_when_the_commit_definitely_failed(monkeypatch):
    ctx = _save_fixture(monkeypatch)
    ctx.db.commit = AsyncMock(side_effect=RuntimeError("ack lost"))
    monkeypatch.setattr(
        sample_templates, "_matter_document_commit_outcome", AsyncMock(return_value=False)
    )
    with pytest.raises(HTTPException):
        await sample_templates.save_sample_to_matter(
            ctx.sample.id,
            sample_templates.SampleTemplateSaveToMatterRequest(
                matter_id=str(ctx.matter.id), variables=_blank(ctx)
            ),
            current_user=ctx.user,
            db=ctx.db,
        )
    ctx.compensate.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_to_matter_succeeds_when_a_lost_commit_ack_is_confirmed(monkeypatch):
    ctx = _save_fixture(monkeypatch)
    ctx.db.commit = AsyncMock(side_effect=RuntimeError("ack lost"))
    monkeypatch.setattr(
        sample_templates, "_matter_document_commit_outcome", AsyncMock(return_value=True)
    )
    persisted = SimpleNamespace(id="persisted")
    ctx.db.scalar = AsyncMock(side_effect=[ctx.sample, None, persisted])
    response = await sample_templates.save_sample_to_matter(
        ctx.sample.id,
        sample_templates.SampleTemplateSaveToMatterRequest(
            matter_id=str(ctx.matter.id), variables=_blank(ctx)
        ),
        current_user=ctx.user,
        db=ctx.db,
    )
    assert response.matter_document_id == str(ctx.added[0].id)
    ctx.compensate.assert_not_awaited()
    sample_templates._saved_document_response.assert_awaited_once_with(
        ctx.db, tenant_id=ctx.tenant_id, document=persisted
    )


def test_save_to_matter_route_is_registered():
    for path, methods in _effective_routes():
        if path == "/api/templates/library/{sample_id}/save-to-matter":
            assert "POST" in methods
            return
    raise AssertionError("save-to-matter route is not registered")
