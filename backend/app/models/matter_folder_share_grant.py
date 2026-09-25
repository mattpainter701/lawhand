"""The cloud folder shares LawHand granted to matter assignees.

When someone is assigned to a matter, LawHand shares the matter's OneDrive and
Google Drive folders with them. This table remembers each share LawHand made,
with the provider's permission id, so that when the person leaves the matter
(or is deactivated) LawHand removes exactly that share and nothing a person
added in the provider directly.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ``lawhand``: LawHand created the permission and stored its id.
# ``legacy``: shared before ids were stored; matched on email plus LawHand's role.
# ``preexisting``: the person already had a direct share LawHand did not make.
GRANT_ORIGINS = ("lawhand", "legacy", "preexisting")
# ``kept`` means LawHand ended its record but left a share someone else made.
GRANT_STATUSES = ("active", "revoke_pending", "revoked", "kept")


class MatterFolderShareGrant(Base):
    """One provider folder permission LawHand holds for one person on one matter."""

    __tablename__ = "matter_folder_share_grants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "matter_id",
            "provider",
            "folder_id",
            "grantee_email",
            name="uq_matter_folder_share_grants_target",
        ),
        CheckConstraint(
            "provider IN ('onedrive', 'google_drive')",
            name="ck_matter_folder_share_grants_provider",
        ),
        CheckConstraint(
            "origin IN ('lawhand', 'legacy', 'preexisting')",
            name="ck_matter_folder_share_grants_origin",
        ),
        CheckConstraint(
            "status IN ('active', 'revoke_pending', 'revoked', 'kept')",
            name="ck_matter_folder_share_grants_status",
        ),
        Index(
            "ix_matter_folder_share_grants_pending",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_matter_folder_share_grants_user",
            "tenant_id",
            "user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL, not CASCADE: a share still waiting to be removed must outlive
    # the matter or user row that caused it.
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matters.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    grantee_email: Mapped[str] = mapped_column(String(320), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    folder_id: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    permission_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    origin: Mapped[str] = mapped_column(
        String(20), nullable=False, default="lawhand", server_default="lawhand"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    revoke_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoke_requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )
    revoke_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        onupdate=lambda: datetime.now(timezone.utc),
    )
