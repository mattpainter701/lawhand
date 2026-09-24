"""Customer, public, and operator workflows for the operating contract."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import clear_tenant_context, get_db, set_tenant_context
from app.middleware.tenant import require_admin
from app.models.compliance import RetentionPolicy, TenantAgreementAcceptance
from app.models.external_import import ExternalImportRun
from app.models.operating_trust import (
    CustomerLifecycleReceipt,
    OffboardingApproval,
    OffboardingCase,
    PublicIncident,
    PublicIncidentUpdate,
    SupportRequest,
)
from app.models.tenant import Tenant
from app.services.compliance import agreement_status, retention_inventory
from app.services.operating_contract import CONTRACT_VERSION, support_severity
from app.services.operating_trust import (
    assert_incident_transition,
    assert_public_safe_text,
    assert_safe_evidence,
    assert_support_transition,
    evidence_hash,
    issue_tenant_export_snapshot,
    opaque_evidence_reference,
    receipt_hash,
    receipt_payload,
    reconcile_counts,
    support_acknowledgement_due,
    tenant_export_inventory,
    utcnow,
    verify_tenant_export_snapshot,
)
from app.services.operator_audit import record_operator_audit
from app.services.platform_auth import require_platform_token
from app.services.support_alerts import notify_operator_support_requested

router = APIRouter(tags=["operating-trust"])
REQUIRED_BACKUP_CLASSES = {"application-database", "tenant-file-store"}


class SupportCreate(BaseModel):
    severity: Literal["S1", "S2", "S3", "S4"]
    channel: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=255)
    safe_summary: str = Field(min_length=1, max_length=4000)

    @field_validator("channel", "subject", "safe_summary")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return " ".join(value.split())


class SupportUpdate(BaseModel):
    status: Literal["acknowledged", "mitigated", "resolved"]
    escalation_level: int = Field(default=0, ge=0, le=4)
    resolution_summary: str | None = Field(default=None, max_length=4000)


class LifecycleReceiptCreate(BaseModel):
    receipt_type: Literal["onboarding", "migration", "tenant_export"]
    scope: dict = Field(default_factory=dict)
    actual_counts: dict[str, int] = Field(default_factory=dict)
    source_import_run_id: uuid.UUID | None = None
    artifact_reference: str | None = Field(default=None, max_length=1000)
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    inventory_snapshot_token: str | None = Field(default=None, max_length=250_000)
    signer_title: str = Field(min_length=1, max_length=255)
    authority_attested: bool
    outcome: str = Field(min_length=1, max_length=2000)

    @field_validator("artifact_reference")
    @classmethod
    def opaque_artifact_reference(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        if not normalized:
            return None
        return opaque_evidence_reference(normalized)


class OffboardingCreate(BaseModel):
    delete_categories: list[str] = Field(min_length=1, max_length=100)
    return_categories: list[str] = Field(default_factory=list, max_length=100)
    signer_title: str = Field(min_length=1, max_length=255)
    authority_attested: bool
    reason: str = Field(min_length=1, max_length=2000)


class ApprovalCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class ProviderDisposition(BaseModel):
    provider: str = Field(min_length=1, max_length=120)
    status: Literal["deleted", "returned", "customer_controlled", "not_applicable"]
    evidence_reference: str = Field(min_length=1, max_length=1000)

    @field_validator("evidence_reference")
    @classmethod
    def opaque_reference(cls, value: str) -> str:
        return opaque_evidence_reference(value)


class BackupDisposition(BaseModel):
    backup_class: str = Field(min_length=1, max_length=120)
    expires_at: datetime
    evidence_reference: str = Field(min_length=1, max_length=1000)

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value <= datetime.now(timezone.utc):
            raise ValueError("backup expiry must be a future timezone-aware timestamp")
        return value

    @field_validator("evidence_reference")
    @classmethod
    def opaque_reference(cls, value: str) -> str:
        return opaque_evidence_reference(value)


class OffboardingComplete(BaseModel):
    actual_counts: dict[str, int]
    providers: list[ProviderDisposition] = Field(min_length=1)
    backups: list[BackupDisposition] = Field(min_length=1)
    evidence_reference: str = Field(min_length=1, max_length=1000)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: str = Field(min_length=1, max_length=2000)

    @field_validator("evidence_reference")
    @classmethod
    def opaque_reference(cls, value: str) -> str:
        return opaque_evidence_reference(value)


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    severity: Literal["S1", "S2", "S3"]
    affected_services: list[str] = Field(min_length=1, max_length=20)
    started_at: datetime
    message: str = Field(min_length=1, max_length=2000)


class IncidentUpdateCreate(BaseModel):
    state: Literal["identified", "monitoring", "resolved"]
    message: str = Field(min_length=1, max_length=2000)


def _support_payload(row: SupportRequest) -> dict:
    return {
        "id": str(row.id),
        "severity": row.severity,
        "status": row.status,
        "channel": row.channel,
        "subject": row.subject,
        "safe_summary": row.safe_summary,
        "policy_version": row.policy_version,
        "acknowledgement_objective_minutes": row.acknowledgement_objective_minutes,
        "acknowledgement_due_at": row.acknowledgement_due_at,
        "escalation_level": row.escalation_level,
        "acknowledged_at": row.acknowledged_at,
        "mitigated_at": row.mitigated_at,
        "resolved_at": row.resolved_at,
        "resolution_summary": row.resolution_summary,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _receipt_row(
    *,
    receipt_id: uuid.UUID,
    tenant_id: uuid.UUID,
    receipt_type: str,
    status: str,
    scope: dict,
    expected: dict,
    actual: dict,
    discrepancies: list,
    artifact_reference: str | None,
    artifact_sha256: str | None,
    signer_user_id: uuid.UUID | None,
    signer_name: str,
    signer_email: str,
    signer_title: str,
    signer_actor_type: str,
    authority_attested: bool,
    outcome: str,
    source_import_run_id: uuid.UUID | None = None,
    approvals: list | None = None,
    legal_hold: dict | None = None,
    providers: list | None = None,
    backup_expiry: list | None = None,
) -> CustomerLifecycleReceipt:
    created_at = utcnow()
    signed = {
        "id": str(receipt_id),
        "tenant_id": str(tenant_id),
        "receipt_type": receipt_type,
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "scope": scope,
        "expected_counts": expected,
        "actual_counts": actual,
        "discrepancies": discrepancies,
        "source_import_run_id": str(source_import_run_id)
        if source_import_run_id
        else None,
        "artifact_reference": artifact_reference,
        "artifact_sha256": artifact_sha256,
        "signer": {
            "name": signer_name,
            "email": signer_email,
            "title": signer_title,
            "actor_type": signer_actor_type,
            "authority_attested": authority_attested,
        },
        "approvals": approvals or [],
        "legal_hold_snapshot": legal_hold or {},
        "provider_data": providers or [],
        "backup_expiry": backup_expiry or [],
        "outcome": outcome,
        "created_at": created_at.isoformat(),
    }
    assert_safe_evidence(signed)
    return CustomerLifecycleReceipt(
        id=receipt_id,
        tenant_id=tenant_id,
        receipt_type=receipt_type,
        contract_version=CONTRACT_VERSION,
        status=status,
        scope_json=scope,
        expected_counts=expected,
        actual_counts=actual,
        discrepancies=discrepancies,
        source_import_run_id=source_import_run_id,
        artifact_reference=artifact_reference,
        artifact_sha256=artifact_sha256,
        signer_user_id=signer_user_id,
        signer_name=signer_name,
        signer_email=signer_email,
        signer_title=signer_title,
        signer_actor_type=signer_actor_type,
        authority_attested=authority_attested,
        approvals_json=approvals or [],
        legal_hold_snapshot=legal_hold or {},
        provider_data_json=providers or [],
        backup_expiry_json=backup_expiry or [],
        outcome=outcome,
        receipt_hash=receipt_hash(signed),
        created_at=created_at,
    )


@router.post("/api/compliance/operating/support")
async def create_support_request(
    body: SupportCreate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        assert_safe_evidence(
            {
                "channel": body.channel,
                "subject": body.subject,
                "summary": body.safe_summary,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await set_tenant_context(db, str(admin.tenant_id))
    policy = support_severity(body.severity)
    now = utcnow()
    row = SupportRequest(
        tenant_id=admin.tenant_id,
        severity=body.severity,
        channel=body.channel,
        subject=body.subject,
        safe_summary=body.safe_summary,
        policy_version=CONTRACT_VERSION,
        acknowledgement_objective_minutes=policy["acknowledgement_objective_minutes"],
        acknowledgement_due_at=support_acknowledgement_due(
            now,
            severity=body.severity,
            objective_minutes=policy["acknowledgement_objective_minutes"],
        ),
        requested_by_user_id=admin.id,
        requested_by_email=admin.email,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.commit()
    tenant_name = await db.scalar(select(Tenant.name).where(Tenant.id == row.tenant_id))
    await notify_operator_support_requested(
        tenant_name=tenant_name or str(row.tenant_id),
        tenant_id=row.tenant_id,
        request_id=row.id,
        severity=row.severity,
        subject=row.subject,
        safe_summary=row.safe_summary,
        requested_by_email=row.requested_by_email,
        acknowledgement_due_at=row.acknowledgement_due_at,
    )
    return _support_payload(row)


@router.get("/api/compliance/operating/support")
async def list_support_requests(
    admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await set_tenant_context(db, str(admin.tenant_id))
    rows = list(
        (
            await db.scalars(
                select(SupportRequest)
                .where(SupportRequest.tenant_id == admin.tenant_id)
                .order_by(SupportRequest.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    return {"items": [_support_payload(row) for row in rows]}


@router.patch("/api/platform/operating-trust/tenants/{tenant_id}/support/{request_id}")
async def update_support_request(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    body: SupportUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal = require_platform_token(request, scopes={"platform:write"})
    await set_tenant_context(db, str(tenant_id))
    row = await db.scalar(
        select(SupportRequest)
        .where(SupportRequest.id == request_id, SupportRequest.tenant_id == tenant_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Support request not found")
    try:
        assert_support_transition(row.status, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    now = utcnow()
    row.status = body.status
    row.escalation_level = body.escalation_level
    row.operator_actor_id = principal.actor_id
    row.updated_at = now
    if body.status == "acknowledged":
        row.acknowledged_at = now
    elif body.status == "mitigated":
        row.mitigated_at = now
    elif body.status == "resolved":
        row.resolved_at = now
        row.resolution_summary = (body.resolution_summary or "").strip() or None
    await record_operator_audit(
        db,
        request,
        action=f"support.{body.status}",
        resource_type="support_request",
        resource_id=str(row.id),
        metadata={
            "tenant_id": str(tenant_id),
            "severity": row.severity,
            "escalation_level": row.escalation_level,
        },
        actor_id=principal.actor_id,
    )
    await db.commit()
    return _support_payload(row)


SUPPORT_STATUSES = ("open", "acknowledged", "mitigated", "resolved")
_SEVERITY_RANK = {"S1": 0, "S2": 1, "S3": 2, "S4": 3}


def _support_is_overdue(row: SupportRequest, now: datetime) -> bool:
    """Only an unacknowledged request can miss its acknowledgement objective."""

    return row.status == "open" and row.acknowledgement_due_at <= now


@router.get("/api/platform/operating-trust/support")
async def list_platform_support_requests(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: Annotated[
        Literal["active", "all", "open", "acknowledged", "mitigated", "resolved"],
        Query(),
    ] = "active",
    severity: Annotated[Literal["S1", "S2", "S3", "S4"] | None, Query()] = None,
    tenant_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """The operator support queue: every tenant's requests in one list.

    Tenant admins file requests and only a platform PATCH can move them, but
    that PATCH needs the tenant and request ids up front. Without a queue the
    only way to learn a request existed was a database shell, so SLA clocks
    ran out unseen.

    ``support_requests`` is FORCE RLS, so the registry is walked and each
    tenant's scope entered in turn, as the platform router does, rather than
    reading across tenants under a bypass.
    """

    require_platform_token(request, scopes={"platform:read"})
    now = utcnow()

    tenant_query = select(Tenant.id, Tenant.name).order_by(Tenant.name)
    if tenant_id is not None:
        tenant_query = tenant_query.where(Tenant.id == tenant_id)
    tenants = (await db.execute(tenant_query)).all()
    if tenant_id is not None and not tenants:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if status == "active":
        wanted = {"open", "acknowledged", "mitigated"}
    elif status == "all":
        wanted = set(SUPPORT_STATUSES)
    else:
        wanted = {status}

    # Each tenant's rows are cut to ``limit`` before the merge, so every scope
    # must be read in the same order as the merged list or the cut can drop
    # an overdue S1 in favour of a newer S4.
    if wanted == {"resolved"}:
        order_by = [
            func.coalesce(SupportRequest.resolved_at, SupportRequest.updated_at).desc()
        ]

        def sort_key(row: SupportRequest):
            return -(row.resolved_at or row.updated_at).timestamp()

    else:
        # Work the queue in the order the published policy obliges: anything
        # unresolved before anything resolved, then severity (S1 sorts first),
        # then the acknowledgement clock.
        order_by = [
            case((SupportRequest.status == "resolved", 1), else_=0),
            SupportRequest.severity,
            SupportRequest.acknowledgement_due_at,
        ]

        def sort_key(row: SupportRequest):
            return (
                row.status == "resolved",
                _SEVERITY_RANK.get(row.severity, 9),
                row.acknowledgement_due_at,
            )

    counts = {name: 0 for name in SUPPORT_STATUSES}
    counts["overdue"] = 0
    rows: list[tuple[SupportRequest, str]] = []
    try:
        for scoped_id, tenant_name in tenants:
            await set_tenant_context(db, str(scoped_id))
            filters = [SupportRequest.tenant_id == scoped_id]
            if severity:
                filters.append(SupportRequest.severity == severity)

            grouped = await db.execute(
                select(
                    SupportRequest.status,
                    func.count(SupportRequest.id),
                    func.count(SupportRequest.id).filter(
                        SupportRequest.acknowledgement_due_at <= now
                    ),
                )
                .where(*filters)
                .group_by(SupportRequest.status)
            )
            for row_status, count, past_due in grouped.all():
                counts[row_status] = counts.get(row_status, 0) + int(count)
                if row_status == "open":
                    counts["overdue"] += int(past_due)

            found = (
                await db.scalars(
                    select(SupportRequest)
                    .where(*filters, SupportRequest.status.in_(wanted))
                    .order_by(*order_by)
                    .limit(limit)
                )
            ).all()
            rows.extend((row, tenant_name) for row in found)
    except BaseException:
        # A failed statement can leave the transaction aborted, and a cleanup
        # SELECT would then mask the real error. The GUCs are transaction-local
        # and the request rolls back, so keep the original exception.
        try:
            await clear_tenant_context(db)
        except Exception:
            pass
        raise
    await clear_tenant_context(db)

    rows.sort(key=lambda item: sort_key(item[0]))

    return {
        "items": [
            {
                **_support_payload(row),
                "tenant_id": str(row.tenant_id),
                "tenant_name": tenant_name,
                "requested_by_email": row.requested_by_email,
                "operator_actor_id": row.operator_actor_id,
                "overdue": _support_is_overdue(row, now),
            }
            for row, tenant_name in rows[:limit]
        ],
        "total": sum(counts[name] for name in wanted),
        "counts": counts,
        "status": status,
        "checked_at": now,
    }


@router.post("/api/compliance/operating/receipts")
async def create_lifecycle_receipt(
    body: LifecycleReceiptCreate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not body.authority_attested:
        raise HTTPException(
            status_code=400, detail="Authorized representative attestation is required"
        )
    assert_safe_evidence(body.scope)
    await set_tenant_context(db, str(admin.tenant_id))
    expected: dict[str, int]
    actual: dict[str, int]
    artifact_sha256 = body.artifact_sha256
    artifact_reference = body.artifact_reference
    source_run_id = body.source_import_run_id
    if body.receipt_type == "onboarding":
        agreements = await agreement_status(db, admin.tenant_id)
        if not agreements["complete"]:
            raise HTTPException(
                status_code=409,
                detail="Every current required agreement must be accepted for onboarding",
            )
        definition_ids = [
            uuid.UUID(item["id"])
            for item in agreements["agreements"]
            if item["required"] and item["accepted"]
        ]
        acceptances = list(
            (
                await db.scalars(
                    select(TenantAgreementAcceptance).where(
                        TenantAgreementAcceptance.tenant_id == admin.tenant_id,
                        TenantAgreementAcceptance.agreement_definition_id.in_(
                            definition_ids
                        ),
                    )
                )
            ).all()
        )
        ids = sorted(str(item.id) for item in acceptances)
        expected = {"agreement_acceptances": len(ids)}
        actual = dict(expected)
        body.scope["agreement_acceptance_ids"] = ids
        body.scope["agreement_definition_ids"] = sorted(
            str(item) for item in definition_ids
        )
        artifact_sha256 = artifact_sha256 or evidence_hash(ids)
        artifact_reference = artifact_reference or "agreement-acceptance-ledger"
    elif body.receipt_type == "migration":
        if source_run_id is None:
            raise HTTPException(
                status_code=400, detail="Migration receipt requires a BK28 import run"
            )
        run = await db.scalar(
            select(ExternalImportRun).where(
                ExternalImportRun.id == source_run_id,
                ExternalImportRun.tenant_id == admin.tenant_id,
            )
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Import run not found")
        if run.status not in {"staged", "approved", "promoted"}:
            raise HTTPException(
                status_code=409,
                detail="Import run has not reached an acceptance-ready state",
            )
        if run.errors:
            raise HTTPException(
                status_code=409, detail="Import run has unresolved errors"
            )
        expected = {
            str(key): int(value) for key, value in (run.row_counts or {}).items()
        }
        actual = body.actual_counts
        body.scope["provider"] = run.provider
        body.scope["source_system"] = run.source_system
        body.scope["warnings"] = run.warnings or []
        artifact_sha256 = artifact_sha256 or evidence_hash(
            run.checksum_summary or run.manifest or expected
        )
        artifact_reference = artifact_reference or f"import-run:{run.id}"
    else:
        if (
            not artifact_sha256
            or not artifact_reference
            or not body.inventory_snapshot_token
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Tenant export requires an artifact reference, SHA-256, and "
                    "server-issued inventory snapshot"
                ),
            )
        try:
            snapshot = verify_tenant_export_snapshot(
                body.inventory_snapshot_token,
                tenant_id=admin.tenant_id,
                contract_version=CONTRACT_VERSION,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        inventory = snapshot["inventory"]
        expected = inventory["counts"]
        actual = body.actual_counts
        body.scope["inventory_policy_version"] = inventory["retention_policy_version"]
        body.scope["tenant_table_count"] = inventory["tenant_table_count"]
        body.scope["inventory_categories"] = inventory["categories"]
        body.scope["provider_inventory"] = inventory["providers"]
        body.scope["inventory_snapshot_sha256"] = snapshot["snapshot_sha256"]
        body.scope["inventory_snapshot_issued_at"] = snapshot["snapshot_issued_at"]
        body.scope["inventory_snapshot_boundary"] = (
            "server-signed point-in-time tenant inventory"
        )
    discrepancies = reconcile_counts(expected, actual)
    status = (
        "accepted" if body.receipt_type in {"onboarding", "migration"} else "completed"
    )
    if discrepancies:
        status = "blocked"
    row = _receipt_row(
        receipt_id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        receipt_type=body.receipt_type,
        status=status,
        scope=body.scope,
        expected=expected,
        actual=actual,
        discrepancies=discrepancies,
        source_import_run_id=source_run_id,
        artifact_reference=artifact_reference,
        artifact_sha256=artifact_sha256,
        signer_user_id=admin.id,
        signer_name=admin.full_name or admin.email,
        signer_email=admin.email,
        signer_title=body.signer_title.strip(),
        signer_actor_type="tenant_admin",
        authority_attested=True,
        outcome=body.outcome.strip(),
    )
    db.add(row)
    await db.commit()
    return receipt_payload(row)


@router.get("/api/compliance/operating/export-inventory")
async def get_tenant_export_inventory(
    admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await set_tenant_context(db, str(admin.tenant_id))
    retention = await retention_inventory(db, admin.tenant_id)
    inventory = await tenant_export_inventory(db, admin.tenant_id, retention=retention)
    inventory["contract_version"] = CONTRACT_VERSION
    inventory.update(
        issue_tenant_export_snapshot(
            inventory,
            tenant_id=admin.tenant_id,
            contract_version=CONTRACT_VERSION,
        )
    )
    return inventory


@router.get("/api/compliance/operating/receipts")
async def list_lifecycle_receipts(
    admin=Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await set_tenant_context(db, str(admin.tenant_id))
    rows = list(
        (
            await db.scalars(
                select(CustomerLifecycleReceipt)
                .where(CustomerLifecycleReceipt.tenant_id == admin.tenant_id)
                .order_by(CustomerLifecycleReceipt.created_at.desc())
                .limit(200)
            )
        ).all()
    )
    return {"items": [receipt_payload(row) for row in rows]}


@router.post("/api/compliance/operating/offboarding")
async def request_offboarding(
    body: OffboardingCreate,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not body.authority_attested:
        raise HTTPException(
            status_code=400, detail="Authorized representative attestation is required"
        )
    await set_tenant_context(db, str(admin.tenant_id))
    retention = await retention_inventory(db, admin.tenant_id)
    inventory = await tenant_export_inventory(db, admin.tenant_id, retention=retention)
    available = set(inventory["counts"])
    requested = set(body.delete_categories) | set(body.return_categories)
    if not requested <= available:
        raise HTTPException(
            status_code=400,
            detail="Offboarding scope contains unknown inventory categories",
        )
    hold = {
        "active": retention["legal_hold"],
        "reason": retention["legal_hold_reason"],
        "set_at": (
            retention["legal_hold_set_at"].isoformat()
            if retention["legal_hold_set_at"]
            else None
        ),
        "policy_version": retention["policy_version"],
    }
    status = "hold_blocked" if retention["legal_hold"] else "requested"
    selected_modes = {
        item["category"]: item["export_mode"]
        for item in inventory["categories"]
        if item["category"] in requested
    }
    requested_counts = {name: inventory["counts"][name] for name in sorted(requested)}
    scope = {
        "delete_categories": sorted(set(body.delete_categories)),
        "return_categories": sorted(set(body.return_categories)),
        "requested_counts": requested_counts,
        "category_modes": selected_modes,
        "reason": body.reason.strip(),
    }
    case = OffboardingCase(
        tenant_id=admin.tenant_id,
        status=status,
        requested_scope=scope,
        legal_hold_snapshot=hold,
        requested_by_user_id=admin.id,
        requested_by_email=admin.email,
    )
    db.add(case)
    await db.flush()
    counts = inventory["counts"]
    row = _receipt_row(
        receipt_id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        receipt_type="offboarding",
        status="blocked" if retention["legal_hold"] else "requested",
        scope={**scope, "case_id": str(case.id)},
        expected=counts,
        actual=counts,
        discrepancies=[],
        artifact_reference=f"offboarding-case:{case.id}",
        artifact_sha256=evidence_hash(
            {"scope": scope, "inventory": counts, "hold": hold}
        ),
        signer_user_id=admin.id,
        signer_name=admin.full_name or admin.email,
        signer_email=admin.email,
        signer_title=body.signer_title.strip(),
        signer_actor_type="tenant_admin",
        authority_attested=True,
        outcome="Blocked by legal hold"
        if retention["legal_hold"]
        else "Offboarding requested; no data was deleted",
        legal_hold=hold,
    )
    db.add(row)
    await db.commit()
    return {
        "case_id": str(case.id),
        "status": case.status,
        "receipt": receipt_payload(row),
    }


@router.post(
    "/api/platform/operating-trust/tenants/{tenant_id}/offboarding/{case_id}/approve"
)
async def approve_offboarding(
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    body: ApprovalCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal = require_platform_token(request, scopes={"platform:write"})
    await set_tenant_context(db, str(tenant_id))
    case = await db.scalar(
        select(OffboardingCase)
        .where(OffboardingCase.id == case_id, OffboardingCase.tenant_id == tenant_id)
        .with_for_update()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Offboarding case not found")
    policy = await db.scalar(
        select(RetentionPolicy).where(RetentionPolicy.tenant_id == tenant_id)
    )
    if policy and policy.legal_hold:
        case.status = "hold_blocked"
        await db.commit()
        raise HTTPException(status_code=423, detail="Tenant is under legal hold")
    approval = OffboardingApproval(
        tenant_id=tenant_id,
        case_id=case.id,
        actor_id=principal.actor_id,
        reason=body.reason.strip(),
    )
    db.add(approval)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="This operator already approved the case"
        ) from exc
    count = int(
        await db.scalar(
            select(func.count(OffboardingApproval.id)).where(
                OffboardingApproval.case_id == case.id
            )
        )
        or 0
    )
    if count >= 2:
        case.status = "approved"
    await record_operator_audit(
        db,
        request,
        action="offboarding.approved",
        resource_type="offboarding_case",
        resource_id=str(case.id),
        metadata={"tenant_id": str(tenant_id), "approval_count": count},
        actor_id=principal.actor_id,
    )
    await db.commit()
    return {"case_id": str(case.id), "status": case.status, "approval_count": count}


@router.post(
    "/api/platform/operating-trust/tenants/{tenant_id}/offboarding/{case_id}/complete"
)
async def complete_offboarding(
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
    body: OffboardingComplete,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal = require_platform_token(request, scopes={"platform:write"})
    await set_tenant_context(db, str(tenant_id))
    case = await db.scalar(
        select(OffboardingCase)
        .where(OffboardingCase.id == case_id, OffboardingCase.tenant_id == tenant_id)
        .with_for_update()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Offboarding case not found")
    policy = await db.scalar(
        select(RetentionPolicy).where(RetentionPolicy.tenant_id == tenant_id)
    )
    if policy and policy.legal_hold:
        raise HTTPException(status_code=423, detail="Tenant is under legal hold")
    approvals = list(
        (
            await db.scalars(
                select(OffboardingApproval)
                .where(OffboardingApproval.case_id == case.id)
                .order_by(OffboardingApproval.approved_at)
            )
        ).all()
    )
    if case.status != "approved" or len(approvals) < 2:
        raise HTTPException(
            status_code=409, detail="Two distinct operator approvals are required"
        )
    targets = {name: 0 for name in case.requested_scope.get("delete_categories", [])}
    for name in case.requested_scope.get("return_categories", []):
        targets[name] = int(
            case.requested_scope.get("requested_counts", {}).get(name, 0)
        )
    actual = body.actual_counts
    discrepancies = reconcile_counts(targets, actual)
    if discrepancies:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Deletion scope is not reconciled",
                "discrepancies": discrepancies,
            },
        )
    providers = [item.model_dump(mode="json") for item in body.providers]
    backups = [item.model_dump(mode="json") for item in body.backups]
    if len({item["provider"].casefold() for item in providers}) != len(providers):
        raise HTTPException(
            status_code=400, detail="Provider disposition entries must be unique"
        )
    if len({item["backup_class"].casefold() for item in backups}) != len(backups):
        raise HTTPException(
            status_code=400, detail="Backup disposition entries must be unique"
        )
    backup_classes = {item["backup_class"].casefold() for item in backups}
    if not REQUIRED_BACKUP_CLASSES <= backup_classes:
        raise HTTPException(
            status_code=400,
            detail="Application database and tenant file-store backup expiry are required",
        )
    requested_provider_names = {
        name.split(":", 1)[1].casefold()
        for name in (
            case.requested_scope.get("delete_categories", [])
            + case.requested_scope.get("return_categories", [])
        )
        if name.startswith("provider-files:")
    }
    proved_provider_names = {item["provider"].casefold() for item in providers}
    if not requested_provider_names <= proved_provider_names:
        raise HTTPException(
            status_code=400,
            detail="Every in-scope file provider requires disposition evidence",
        )
    assert_safe_evidence({"providers": providers, "backups": backups})
    approval_evidence = [
        {
            "actor_id": item.actor_id,
            "reason": item.reason,
            "approved_at": item.approved_at.isoformat(),
        }
        for item in approvals
    ]
    hold = {
        "active": False,
        "policy_version": policy.version if policy else 0,
        "checked_at": utcnow().isoformat(),
    }
    row = _receipt_row(
        receipt_id=uuid.uuid4(),
        tenant_id=tenant_id,
        receipt_type="deletion",
        status="completed",
        scope={
            **case.requested_scope,
            "case_id": str(case.id),
            "execution_boundary": "evidence-only; this endpoint performs no deletion",
        },
        expected=targets,
        actual=actual,
        discrepancies=[],
        artifact_reference=body.evidence_reference.strip(),
        artifact_sha256=body.evidence_sha256,
        signer_user_id=None,
        signer_name=principal.actor_id,
        signer_email=principal.actor_id,
        signer_title="authorized platform operator",
        signer_actor_type="platform_operator",
        authority_attested=True,
        outcome=body.outcome.strip(),
        approvals=approval_evidence,
        legal_hold=hold,
        providers=providers,
        backup_expiry=backups,
    )
    db.add(row)
    case.status = "completed"
    await record_operator_audit(
        db,
        request,
        action="offboarding.completed",
        resource_type="offboarding_case",
        resource_id=str(case.id),
        metadata={
            "tenant_id": str(tenant_id),
            "receipt_id": str(row.id),
            "approval_count": len(approvals),
        },
        actor_id=principal.actor_id,
    )
    await db.commit()
    return receipt_payload(row)


def _incident_payload(
    incident: PublicIncident, updates: list[PublicIncidentUpdate]
) -> dict:
    return {
        "id": incident.public_id,
        "title": incident.title,
        "severity": incident.severity,
        "affected_services": incident.affected_services,
        "started_at": incident.started_at,
        "state": updates[-1].state,
        "updates": [
            {
                "state": item.state,
                "message": item.message,
                "published_at": item.published_at,
            }
            for item in updates
        ],
    }


@router.get("/api/public/status")
async def public_status(db: AsyncSession = Depends(get_db)):
    incidents = list(
        (
            await db.scalars(
                select(PublicIncident)
                .order_by(PublicIncident.started_at.desc())
                .limit(50)
            )
        ).all()
    )
    items = []
    for incident in incidents:
        updates = list(
            (
                await db.scalars(
                    select(PublicIncidentUpdate)
                    .where(PublicIncidentUpdate.incident_id == incident.id)
                    .order_by(
                        PublicIncidentUpdate.published_at, PublicIncidentUpdate.id
                    )
                )
            ).all()
        )
        if updates:
            items.append(_incident_payload(incident, updates))
    active = [item for item in items if item["state"] != "resolved"]
    return {
        "schema": "lawhand.public-status",
        "contract_version": CONTRACT_VERSION,
        "published_incident_state": "none_active" if not active else "active_incident",
        "service_health": "not_asserted_by_incident_ledger",
        "active_incidents": active,
        "recent_incidents": items,
    }


@router.post("/api/platform/operating-trust/incidents")
async def create_incident(
    body: IncidentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal = require_platform_token(request, scopes={"platform:write"})
    try:
        title = assert_public_safe_text(body.title)
        message = assert_public_safe_text(body.message)
        services = [assert_public_safe_text(item) for item in body.affected_services]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    incident = PublicIncident(
        public_id=f"INC-{body.started_at.astimezone(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}",
        title=title,
        severity=body.severity,
        affected_services=services,
        started_at=body.started_at,
        created_by_actor_id=principal.actor_id,
    )
    db.add(incident)
    await db.flush()
    update = PublicIncidentUpdate(
        incident_id=incident.id,
        state="investigating",
        message=message,
        created_by_actor_id=principal.actor_id,
    )
    db.add(update)
    await record_operator_audit(
        db,
        request,
        action="incident.created",
        resource_type="public_incident",
        resource_id=incident.public_id,
        metadata={"severity": body.severity, "affected_services": services},
        actor_id=principal.actor_id,
    )
    await db.commit()
    return _incident_payload(incident, [update])


@router.post("/api/platform/operating-trust/incidents/{public_id}/updates")
async def update_incident(
    public_id: str,
    body: IncidentUpdateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal = require_platform_token(request, scopes={"platform:write"})
    incident = await db.scalar(
        select(PublicIncident)
        .where(PublicIncident.public_id == public_id)
        .with_for_update()
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    updates = list(
        (
            await db.scalars(
                select(PublicIncidentUpdate)
                .where(PublicIncidentUpdate.incident_id == incident.id)
                .order_by(PublicIncidentUpdate.published_at, PublicIncidentUpdate.id)
            )
        ).all()
    )
    try:
        assert_incident_transition(updates[-1].state, body.state)
        message = assert_public_safe_text(body.message)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    update = PublicIncidentUpdate(
        incident_id=incident.id,
        state=body.state,
        message=message,
        created_by_actor_id=principal.actor_id,
    )
    db.add(update)
    await record_operator_audit(
        db,
        request,
        action=f"incident.{body.state}",
        resource_type="public_incident",
        resource_id=incident.public_id,
        metadata={"state": body.state},
        actor_id=principal.actor_id,
    )
    await db.commit()
    updates.append(update)
    return _incident_payload(incident, updates)
