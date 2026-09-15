"""One definition of what a client can open in the portal, and why.

Three surfaces used to answer "what can the client see?" differently: the
portal overview counted ``portal_visible`` only, the documents tab and the
downloads served ``portal_visible`` *or* the recipient's intake-packet grants,
and the staff tab labelled a grant-readable document "Private". A per-recipient
signing grant cannot be represented by the single ``portal_visible`` bit, so
this module names the two access routes instead of collapsing them:

``firm_shared``
    The firm shared the document with the matter's client (``portal_visible``).
``signing_packet``
    The recipient's own intake packet entitles them to it — the fee agreement
    they are signing and the paperwork attached to its requirements. This is
    narrower than a share: it reaches only the holder of that packet.
``client_upload``
    The client sent it to the firm. They can always read back their own file.

Every count and label in the portal and on the staff documents tab is derived
from these, so the same document is described the same way everywhere.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ACCESS_FIRM_SHARED = "firm_shared"
ACCESS_SIGNING_PACKET = "signing_packet"
ACCESS_CLIENT_UPLOAD = "client_upload"


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def packet_requirement_document_ids(packet) -> list[str]:
    """Document ids the requirements of one intake packet entitle a client to."""

    requirements = getattr(packet, "requirements", None) or {}
    if not isinstance(requirements, dict):
        return []
    return [
        str(item["document_id"])
        for item in requirements.values()
        if isinstance(item, dict) and item.get("document_id")
    ]


def document_access_source(
    *,
    uploaded_by_user_id,
    portal_visible: bool,
    signing_granted: bool,
) -> str | None:
    """Why this recipient can open the document, or ``None`` if they cannot."""

    if uploaded_by_user_id is None:
        return ACCESS_CLIENT_UPLOAD
    if portal_visible:
        return ACCESS_FIRM_SHARED
    if signing_granted:
        return ACCESS_SIGNING_PACKET
    return None


async def matter_signing_grant_document_ids(
    db: AsyncSession,
    *,
    tenant_id,
    matter_ids,
) -> set[uuid.UUID]:
    """Documents a live intake packet lets a portal recipient open.

    Mirrors what the portal actually serves rather than what staff intended:
    the packet is the grant, so a document reachable through it is reported as
    reachable even though ``portal_visible`` is false. A revoked invite cannot
    reach the portal at all, so its packet grants nothing.
    """

    from app.models.client_portal import ClientPortalInvite
    from app.models.matter_intake import MatterIntake
    from app.models.signature import SignatureRequest

    wanted = {
        matter_uuid
        for matter_uuid in (_as_uuid(value) for value in matter_ids or [])
        if matter_uuid is not None
    }
    if not wanted:
        return set()

    packets = (
        (
            await db.execute(
                select(MatterIntake)
                .join(
                    ClientPortalInvite,
                    ClientPortalInvite.id == MatterIntake.invite_id,
                )
                .where(
                    MatterIntake.tenant_id == tenant_id,
                    MatterIntake.matter_id.in_(wanted),
                    ClientPortalInvite.revoked.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if not packets:
        return set()

    granted: set[uuid.UUID] = set()
    signature_ids: set[uuid.UUID] = set()
    for packet in packets:
        for value in packet_requirement_document_ids(packet):
            document_id = _as_uuid(value)
            if document_id is not None:
                granted.add(document_id)
        if packet.signature_id:
            signature_ids.add(packet.signature_id)

    if signature_ids:
        # The fee agreement itself is not a requirement row; it is the document
        # behind the packet's signature request.
        fee_documents = (
            (
                await db.execute(
                    select(SignatureRequest.document_id).where(
                        SignatureRequest.tenant_id == tenant_id,
                        SignatureRequest.id.in_(signature_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        granted.update(
            document_id for document_id in fee_documents if document_id is not None
        )

    return granted
