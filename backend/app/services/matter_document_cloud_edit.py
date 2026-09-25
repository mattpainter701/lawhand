"""Edit a matter's Word document in the firm's own Word or Google Docs.

"Open in Word / Google Docs" hands the person a fresh provider link to the
exact cloud file LawHand stores, and records an informational marker. "Bring
back changes" reads that file again and, when its bytes changed, adopts them
*in place* as the same document's next version: the row keeps its identity
and cloud item, so the copy still open in Word stays the one LawHand points
to. "Upload revised version" is the fallback for people without the office
suite at hand; it writes the uploaded bytes to the same item, then adopts
them the same way.

What is never overwritten:

* approved, filed, superseded or archived documents;
* documents out for signature (or signed);
* assistant drafts bound to an artifact revision, which keep their own
  review flow (the task's "Refresh edits from cloud").

For those, a changed cloud copy leaves the document in ``conflict`` with a
reason, and nothing is adopted. Every adoption and every refusal writes a
document integrity event; adoptions also write a matter timeline event.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matter_document import MatterDocument
from app.models.plugin import MatterEvent
from app.models.signature import SignatureRequest
from app.services import document_text_cache
from app.services.cloud_docx_snapshot import (
    MAX_DOCX_BYTES,
    CloudDocxSnapshotError,
    inspect_cloud_docx_snapshot,
)
from app.services.document_accountability import append_document_integrity_event
from app.services.matter_file_store import ProviderFileMetadata

CLOUD_BACKENDS = frozenset({"onedrive", "sharepoint", "google_drive"})
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
EDIT_APPS = frozenset({"word_web", "word_desktop", "google_docs"})
# How long "Being edited in Word by …" stays up after someone opens the file.
# Bringing changes back does not end it: the person is usually still editing,
# and later edits must keep coming back. Opening again renews it.
EDIT_MARKER_TTL = timedelta(hours=12)
LOCKED_STATUSES = frozenset({"approved", "filed", "superseded", "archived"})
SIGNING_STATUSES = frozenset({"sent", "partially_signed", "completed"})
MAX_REVISED_BYTES = MAX_DOCX_BYTES


class CloudEditError(Exception):
    """A refusal the router turns into an HTTP error with a stable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AdoptionOutcome:
    """What happened to a document's bytes: unchanged, adopted or blocked."""

    outcome: str
    message: str
    previous_sha256: str | None = None
    document_sha256: str | None = None


def is_docx(document: MatterDocument) -> bool:
    name = str(document.filename or "").lower()
    content_type = str(document.content_type or "").lower()
    return name.endswith(".docx") or content_type == DOCX_CONTENT_TYPE


async def locked_reason(db: AsyncSession, document: MatterDocument) -> str | None:
    """Why this document's bytes must not be replaced, or ``None``."""

    status = document.document_status
    if status in LOCKED_STATUSES:
        return {
            "approved": "This document is approved, so its saved version is kept.",
            "filed": "This document is filed, so its saved version is kept.",
            "superseded": "A newer version of this document replaced it.",
            "archived": "This document is archived.",
        }[status]
    signing = await db.scalar(
        select(SignatureRequest.status)
        .where(
            SignatureRequest.tenant_id == document.tenant_id,
            SignatureRequest.document_id == document.id,
            SignatureRequest.status.in_(SIGNING_STATUSES),
        )
        .limit(1)
    )
    if signing:
        return "This document is out for signature or signed, so its saved version is kept."
    return None


def assert_editable_in_office(document: MatterDocument, *, require_cloud: bool) -> None:
    """Refuse documents this flow does not handle, with a message a person can act on."""

    if not is_docx(document):
        raise CloudEditError(
            422,
            "not_word_document",
            "Only Word documents (.docx) can be edited in Word or Google Docs.",
        )
    if (
        document.generated_artifact_revision_id is not None
        or str(document.document_category or "").lower() == "assistant_revision"
    ):
        raise CloudEditError(
            409,
            "assistant_draft",
            "This is an assistant draft. Bring back its edits from its review task.",
        )
    if require_cloud and document.storage_backend not in CLOUD_BACKENDS:
        raise CloudEditError(
            409,
            "not_in_cloud",
            "This document is not stored in the firm's Microsoft 365 or Google "
            "storage. Download it, edit it, then upload the revised version.",
        )
    if require_cloud and not str(document.provider_object_id or "").strip():
        raise CloudEditError(
            409,
            "cloud_binding_missing",
            "This document's cloud link is incomplete. Upload the revised version instead.",
        )


def open_links(metadata: ProviderFileMetadata) -> dict[str, str]:
    """Links for each app that can open this file.

    Word desktop uses the Office URI scheme with the WebDAV address; Word for
    the web and Google Docs use the provider's own web link (Drive opens a
    DOCX in Docs' Office editing mode, so the file stays a DOCX).
    """

    if metadata.backend == "google_drive":
        return {"google_docs": metadata.web_url}
    links = {"word_web": metadata.web_url}
    if metadata.desktop_url:
        links["word_desktop"] = f"ms-word:ofe|u|{metadata.desktop_url}"
    return links


def start_external_edit(
    document: MatterDocument, *, user_id: uuid.UUID, app: str
) -> None:
    if app not in EDIT_APPS:
        raise CloudEditError(422, "unknown_app", "Choose Word or Google Docs.")
    document.external_edit_started_at = datetime.now(timezone.utc)
    document.external_edit_started_by = user_id
    document.external_edit_app = app


def clear_stale_external_edit(document: MatterDocument, *, now: datetime) -> None:
    started = document.external_edit_started_at
    if started is not None and now - started >= EDIT_MARKER_TTL:
        clear_external_edit(document)


def clear_external_edit(document: MatterDocument) -> None:
    document.external_edit_started_at = None
    document.external_edit_started_by = None
    document.external_edit_app = None


def inspect_revised_docx(content: bytes, *, filename: str | None) -> Any:
    """Validate Word bytes before adoption; unsafe or broken files never land."""

    try:
        return inspect_cloud_docx_snapshot(content, filename=filename)
    except CloudDocxSnapshotError as exc:
        raise CloudEditError(422, f"docx_{exc.code}", exc.message) from exc


async def adopt_document_bytes(
    db: AsyncSession,
    *,
    document: MatterDocument,
    content: bytes,
    actor_user_id: uuid.UUID,
    source: str,
    metadata: ProviderFileMetadata | None = None,
    storage_result: Any = None,
) -> AdoptionOutcome:
    """Adopt ``content`` as ``document``'s current version, or explain why not.

    ``source`` is ``cloud_reconcile`` (bytes read back from the office suite)
    or ``revised_upload`` (the fallback). The caller commits.
    """

    snapshot = inspect_revised_docx(content, filename=document.filename)
    previous_sha = document.document_sha256
    now = datetime.now(timezone.utc)

    unchanged = (
        snapshot.source_sha256 == previous_sha
        if previous_sha
        # Legacy rows without a digest: the first read records the baseline
        # when the size still matches what was stored.
        else document.file_size is not None
        and snapshot.source_size == document.file_size
    )
    if unchanged:
        _record_provider_markers(document, metadata, storage_result)
        document.document_sha256 = snapshot.source_sha256
        document.storage_state = "verified"
        document.storage_error = None
        document.storage_verified_at = now
        clear_stale_external_edit(document, now=now)
        return AdoptionOutcome(
            outcome="unchanged",
            message="No changes since LawHand last saved this document.",
            previous_sha256=previous_sha,
            document_sha256=snapshot.source_sha256,
        )

    reason = await locked_reason(db, document)
    if reason:
        document.storage_state = "conflict"
        document.storage_error = (
            f"Changed outside LawHand. {reason} Restore the file in the office suite, "
            "or save the edited copy as a new document."
        )
        await _integrity_event(
            db,
            document,
            event_type="external_cloud_edit_blocked",
            actor_user_id=actor_user_id,
            content_sha256=snapshot.source_sha256,
            extra={"source": source, "previous_sha256": previous_sha, "reason": reason},
        )
        return AdoptionOutcome(
            outcome="blocked",
            message=f"The edits were not brought back. {reason}",
            previous_sha256=previous_sha,
            document_sha256=previous_sha,
        )

    editor_app = document.external_edit_app
    document.document_sha256 = snapshot.source_sha256
    document.file_size = snapshot.source_size
    document.content_type = DOCX_CONTENT_TYPE
    _record_provider_markers(document, metadata, storage_result)
    document.storage_state = "verified"
    document.storage_error = None
    document.storage_verified_at = now
    if source == "revised_upload":
        # An uploaded copy replaced the file; nobody is editing the cloud copy.
        clear_external_edit(document)
    else:
        clear_stale_external_edit(document, now=now)

    await _integrity_event(
        db,
        document,
        event_type="external_cloud_edit_adopted",
        actor_user_id=actor_user_id,
        content_sha256=snapshot.source_sha256,
        extra={
            "source": source,
            "previous_sha256": previous_sha,
            "size": snapshot.source_size,
            "editor_app": editor_app,
        },
    )
    db.add(
        MatterEvent(
            tenant_id=document.tenant_id,
            matter_id=document.matter_id,
            event_type="document_edits_adopted",
            title=f"Edits brought back: {document.filename}",
            content=(
                "Saved the edited Word file as this document's current version."
                if source == "cloud_reconcile"
                else "Saved an uploaded revised version as this document's current version."
            ),
            note_type="system",
            metadata_json={
                "document_id": str(document.id),
                "source": source,
                "previous_sha256": previous_sha,
                "document_sha256": snapshot.source_sha256,
                "editor_app": editor_app,
            },
            created_by=actor_user_id,
        )
    )
    # The cached text belongs to the old bytes; it goes once no other
    # document of the tenant still carries them.
    await document_text_cache.forget_if_unreferenced(
        db,
        tenant_id=document.tenant_id,
        document_sha256=previous_sha,
        except_document_id=document.id,
    )
    return AdoptionOutcome(
        outcome="adopted",
        message="The edits are now this document's current version.",
        previous_sha256=previous_sha,
        document_sha256=snapshot.source_sha256,
    )


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _record_provider_markers(
    document: MatterDocument,
    metadata: ProviderFileMetadata | None,
    storage_result: Any,
) -> None:
    if storage_result is not None:
        document.provider_etag = storage_result.provider_etag or document.provider_etag
        document.provider_version_id = (
            storage_result.provider_version_id or document.provider_version_id
        )
        document.provider_checksum = storage_result.provider_checksum
        document.provider_modified_at = _parse_time(storage_result.provider_modified_at)
        return
    if metadata is None:
        return
    document.provider_etag = metadata.etag or document.provider_etag
    document.provider_version_id = metadata.version_id or document.provider_version_id
    document.provider_checksum = metadata.checksum
    document.provider_modified_at = _parse_time(metadata.modified_at)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _integrity_event(
    db: AsyncSession,
    document: MatterDocument,
    *,
    event_type: str,
    actor_user_id: uuid.UUID,
    content_sha256: str | None,
    extra: dict,
) -> None:
    await append_document_integrity_event(
        db,
        tenant_id=document.tenant_id,
        matter_id=document.matter_id,
        task_id=document.task_id,
        document_id=document.id,
        event_type=event_type,
        actor_type="user",
        actor_user_id=actor_user_id,
        content_sha256=content_sha256,
        provider_object_id=document.provider_object_id,
        provider_etag=document.provider_etag,
        provider_version_id=document.provider_version_id,
        metadata={"storage_backend": document.storage_backend, **extra},
    )
