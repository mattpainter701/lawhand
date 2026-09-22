"""Unattended Smart Fill: the document_prefill job and the readiness record.

Persisted rows, the real durable-job worker, and the real matter routes. The
job must run once per distinct set of matter facts, prepare only published
templates, record counts and field names but never a value, and never create
a matter document or preview evidence of its own.
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.document_template import DocumentTemplate
from app.models.document_template_preview import DocumentTemplatePreview
from app.models.durable_job import DurableJob
from app.models.matter_document import MatterDocument
from app.models.plugin import Matter, MatterEvent
from app.services import document_prefill as prefill
from app.services import durable_job_worker as worker
from tests.fill_campaign import documents, scenarios

pytestmark = pytest.mark.asyncio


async def drain(db):
    ids = (
        await db.execute(
            select(DurableJob.id, DurableJob.tenant_id).where(
                DurableJob.kind == prefill.JOB_KIND, DurableJob.status == "pending"
            )
        )
    ).all()
    await db.commit()
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    with patch.object(worker, "async_session_maker", factory):
        for job_id, tenant_id in ids:
            await worker.process_job(job_id, tenant_id)


async def _published_pdf_template(db, tenant_id, *, title="Campaign form", bound=True):
    from datetime import datetime, timezone

    from app.services.document_template_versions import record_version

    pdf = documents.convention_pdf()
    schema = documents.schema_for_pdf(
        pdf, bindings=documents.CONVENTION_BINDINGS if bound else None
    )
    template = DocumentTemplate(
        tenant_id=tenant_id,
        title=title,
        body="",
        format="pdf",
        category="other",
        status="published",
        variable_schema=schema,
        is_active=True,
        approved_at=datetime.now(timezone.utc),
        # A source-backed PDF: the readiness gate needs the retained source's
        # identity, and prefill reads only the schema, never the bytes.
        source_storage_path="templates/campaign.pdf",
        source_filename="campaign.pdf",
        source_content_type="application/pdf",
        source_sha256="a" * 64,
    )
    db.add(template)
    await db.flush()
    await record_version(
        db,
        template=template,
        tenant_id=tenant_id,
        user_id=None,
        change_summary="Published",
    )
    template.published_version_no = template.current_version_no
    await db.commit()
    return template


async def _draft_template(db, tenant_id):
    template = DocumentTemplate(
        tenant_id=tenant_id,
        title="Still a draft",
        body="Dear {{client_name}}",
        format="markdown",
        category="other",
        status="draft",
        is_active=False,
    )
    db.add(template)
    await db.commit()
    return template


async def _jobs(db, tenant_id):
    return (
        await db.scalars(
            select(DurableJob).where(
                DurableJob.tenant_id == tenant_id, DurableJob.kind == prefill.JOB_KIND
            )
        )
    ).all()


async def _events(db, matter_id):
    return (
        await db.scalars(
            select(MatterEvent)
            .where(
                MatterEvent.matter_id == matter_id,
                MatterEvent.event_type == prefill.EVENT_TYPE,
            )
            .order_by(MatterEvent.created_at)
        )
    ).all()


class TestFillCounts:
    async def test_filled_is_counted_over_the_same_fields_as_the_total(self):
        """A body-only variable or a copied field must not push filled past
        fields: ``PreparedFill.values`` is wider than the coverage split."""

        from app.schemas.document_template import DocumentTemplateVariableSuggestion
        from app.services.template_fill_coverage import FillCoverage

        prepared = prefill.engine.PreparedFill(
            matter_id=None,
            suggestions=[
                DocumentTemplateVariableSuggestion(
                    variable="body_only", suggested_value="BODY"
                ),
                DocumentTemplateVariableSuggestion(
                    variable="client_name", suggested_value="Ada Lovelace"
                ),
                DocumentTemplateVariableSuggestion(
                    variable="sig", suggested_value=None
                ),
            ],
            values={"body_only": "BODY", "client_name": "Ada Lovelace"},
            coverage=FillCoverage(
                total=2,
                counts={},
                states={"client_name": "name_matched", "sig": "signature"},
            ),
            missing_required=[],
        )

        assert prefill._prepared_counts(prepared) == (2, 1)


class TestEnqueue:
    async def test_creating_a_matter_queues_one_prefill_run(
        self, client, db_session, test_tenant, test_user
    ):
        response = await client.post(
            "/api/matters",
            json={"matter_name": "Lovelace v. Engines", "matter_type": "civil"},
        )
        assert response.status_code == 201, response.text
        jobs = await _jobs(db_session, test_tenant.id)
        assert len(jobs) == 1
        assert jobs[0].payload["trigger_event"] == "matter_created"
        assert jobs[0].payload["matter_id"] == response.json()["id"]
        assert jobs[0].idempotency_key.startswith(response.json()["id"] + ":")
        # Identifiers and a digest only; no matter content in the payload.
        assert "Lovelace" not in str(jobs[0].payload)

    async def test_same_facts_do_not_queue_twice_and_new_facts_do(
        self, db_session, test_tenant, test_user
    ):
        scenario = scenarios.individual_client()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        first = await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="matter_created",
            actor_user_id=test_user.id,
        )
        second = await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="intake_submitted",
            actor_user_id=test_user.id,
        )
        await db_session.commit()
        assert first is not None and second is not None
        assert first.id == second.id
        matter = await db_session.get(Matter, uuid.UUID(ids["matter_id"]))
        matter.case_number = "08-2026-CV-00099"
        await db_session.flush()
        third = await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="intake_writeback_accepted",
            actor_user_id=test_user.id,
        )
        await db_session.commit()
        assert third.id != first.id
        assert len(await _jobs(db_session, test_tenant.id)) == 2

    async def test_a_failure_to_queue_never_loses_the_save(
        self, db_session, test_tenant, test_user
    ):
        scenario = scenarios.sparse()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        with patch.object(
            prefill, "matter_facts_digest", side_effect=RuntimeError("boom")
        ):
            result = await prefill.enqueue_document_prefill(
                db_session,
                tenant_id=test_tenant.id,
                matter_id=ids["matter_id"],
                trigger_event="matter_created",
                actor_user_id=test_user.id,
            )
        assert result is None
        # The session is still usable: the failure was contained in a savepoint.
        matter = await db_session.get(Matter, uuid.UUID(ids["matter_id"]))
        matter.description = "still writable"
        await db_session.commit()
        assert await _jobs(db_session, test_tenant.id) == []

    async def test_unknown_trigger_is_refused(self, db_session, test_tenant, test_user):
        with pytest.raises(ValueError):
            await prefill.enqueue_document_prefill(
                db_session,
                tenant_id=test_tenant.id,
                matter_id=uuid.uuid4(),
                trigger_event="something_else",
                actor_user_id=test_user.id,
            )


class TestJob:
    async def test_prepares_published_templates_and_records_counts_only(
        self, db_session, test_tenant, test_user
    ):
        scenario = scenarios.individual_client()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        template = await _published_pdf_template(db_session, test_tenant.id)
        await _draft_template(db_session, test_tenant.id)
        await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="matter_created",
            actor_user_id=test_user.id,
        )
        await db_session.commit()
        await drain(db_session)

        (job,) = await _jobs(db_session, test_tenant.id)
        await db_session.refresh(job)
        assert job.status == "completed", job.last_error
        assert job.result["outcome"] == "prepared"
        assert job.result["ready"] == 1

        (event,) = await _events(db_session, uuid.UUID(ids["matter_id"]))
        assert event.title == "1 document ready to review"
        assert event.note_type == "system"
        assert event.created_by == test_user.id
        meta = event.metadata_json
        assert meta["trigger_event"] == "matter_created"
        assert meta["ready"] == 1
        (entry,) = meta["templates"]
        assert entry["template_id"] == str(template.id)
        assert entry["status"] == "ready"
        assert entry["format"] == "pdf"
        # Every widget counts toward the split, the signature as its own state.
        assert entry["fields"] == 26
        assert entry["coverage"]["signature"] == 1
        assert entry["filled"] >= 18
        assert 0 < entry["percent"] <= 100
        assert entry["missing_required"] == 0
        # Field names may appear; values never do.
        serialized = str(meta) + event.content
        for value in ("Ada", "Lovelace", "08-2026-CV-00042", "5000.00"):
            assert value not in serialized
        assert "client_name" not in entry["review_names"]
        assert "first_name" in entry["review_names"]  # synonym match, for review
        # The draft template was not prepared.
        assert len(meta["templates"]) == 1

    async def test_the_job_creates_no_document_and_no_preview_evidence(
        self, db_session, test_tenant, test_user
    ):
        scenario = scenarios.entity_client()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        await _published_pdf_template(db_session, test_tenant.id)
        await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="matter_created",
            actor_user_id=test_user.id,
        )
        await db_session.commit()
        await drain(db_session)
        assert (
            await db_session.scalar(select(func.count()).select_from(MatterDocument))
        ) == 0
        assert (
            await db_session.scalar(
                select(func.count()).select_from(DocumentTemplatePreview)
            )
        ) == 0

    async def test_a_missing_matter_blocks_rather_than_fails(
        self, db_session, test_tenant, test_user
    ):
        from app.services.durable_jobs import enqueue_job

        await enqueue_job(
            db_session,
            tenant_id=test_tenant.id,
            kind=prefill.JOB_KIND,
            idempotency_key="gone:facts",
            payload={"matter_id": str(uuid.uuid4()), "trigger_event": "matter_created"},
        )
        await db_session.commit()
        await drain(db_session)
        (job,) = await _jobs(db_session, test_tenant.id)
        await db_session.refresh(job)
        assert job.status == "completed"
        assert job.result == {
            "outcome": "blocked",
            "failure_code": "source_unavailable",
        }

    async def test_custom_and_firm_sources_are_loaded_once_for_every_template(
        self, db_session, test_tenant, test_user
    ):
        """The custom-field and firm-profile reads must not repeat per template.

        They do not depend on the template, so the run reads them once and hands
        the same snapshot to each fill — the N+1 the batched loaders remove.
        """

        scenario = scenarios.individual_client()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        matter = await db_session.get(Matter, uuid.UUID(ids["matter_id"]))
        await _published_pdf_template(db_session, test_tenant.id, title="First form")
        await _published_pdf_template(db_session, test_tenant.id, title="Second form")

        seen: list[tuple] = []
        original = prefill.engine.prepare_fill

        async def spy(*args, **kwargs):
            seen.append((kwargs.get("custom_sources"), kwargs.get("firm_profile")))
            return await original(*args, **kwargs)

        with patch.object(prefill.engine, "prepare_fill", spy):
            summaries = await prefill.prepare_matter_documents(
                db_session, matter=matter, actor=None
            )

        assert len(summaries) == 2 and len(seen) == 2
        first_custom, first_firm = seen[0]
        last_custom, last_firm = seen[1]
        assert first_custom is not None and first_custom is last_custom
        assert first_firm is not None and first_firm is last_firm

    async def test_no_published_templates_records_an_honest_empty_run(
        self, db_session, test_tenant, test_user
    ):
        scenario = scenarios.sparse()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="matter_created",
            actor_user_id=test_user.id,
        )
        await db_session.commit()
        await drain(db_session)
        (event,) = await _events(db_session, uuid.UUID(ids["matter_id"]))
        assert event.title == "No documents ready to review yet"
        assert event.metadata_json["templates"] == []


class TestReadinessRoute:
    async def test_reports_the_latest_run_and_staleness(
        self, client, db_session, test_tenant, test_user
    ):
        scenario = scenarios.individual_client()
        ids = await scenarios.persist(
            db_session, test_tenant.id, test_user.id, scenario
        )
        url = f"/api/matters/{ids['matter_id']}/document-prefill"
        response = await client.get(url)
        assert response.status_code == 200
        assert response.json() is None

        await _published_pdf_template(db_session, test_tenant.id)
        await prefill.enqueue_document_prefill(
            db_session,
            tenant_id=test_tenant.id,
            matter_id=ids["matter_id"],
            trigger_event="matter_created",
            actor_user_id=test_user.id,
        )
        await db_session.commit()
        await drain(db_session)

        body = (await client.get(url)).json()
        assert body["ready"] == 1
        assert body["stale"] is False
        assert body["trigger_event"] == "matter_created"
        assert body["templates"][0]["title"] == "Campaign form"
        assert "suggested_value" not in str(body)

        matter = await db_session.get(Matter, uuid.UUID(ids["matter_id"]))
        matter.court = "A different court"
        await db_session.commit()
        assert (await client.get(url)).json()["stale"] is True

    async def test_another_tenants_matter_is_not_found(self, client):
        response = await client.get(f"/api/matters/{uuid.uuid4()}/document-prefill")
        assert response.status_code == 404


class TestLeadConversion:
    async def test_converting_a_lead_fires_matter_created_and_prefill(
        self, client, db_session, test_tenant, test_user
    ):
        from app.models.contact import Contact, Lead

        contact = Contact(
            tenant_id=test_tenant.id,
            entity_type="person",
            contact_type="prospect",
            first_name="Mary",
            last_name="Somerville",
            email="mary@example.com",
        )
        db_session.add(contact)
        await db_session.flush()
        lead = Lead(
            tenant_id=test_tenant.id,
            contact_id=contact.id,
            status="qualified",
            source="existing_client",
            created_by_user_id=test_user.id,
        )
        db_session.add(lead)
        await db_session.commit()

        response = await client.post(
            f"/api/intake/{lead.id}/convert",
            json={
                "matter_name": "In re Somerville",
                "matter_type": "family",
                "jurisdiction": "North Dakota",
            },
        )
        assert response.status_code == 200, response.text
        matter_id = response.json()["matter_id"]
        jobs = await _jobs(db_session, test_tenant.id)
        assert [job.payload["matter_id"] for job in jobs] == [matter_id]
        await drain(db_session)
        (event,) = await _events(db_session, uuid.UUID(matter_id))
        assert event.event_type == prefill.EVENT_TYPE
