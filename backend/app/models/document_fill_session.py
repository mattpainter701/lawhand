import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SESSION_STATUSES = ("open", "saving", "saved", "failed", "abandoned")


class DocumentFillSession(Base):
    """What a preparer typed for one template or one set, kept until saved.

    Answers are stored encrypted with the token-vault keys and never listed;
    only the session that owns them decrypts them, for its owner. Rendered
    documents are never stored here: a save still goes through the render
    route and its preview evidence gate.
    """

    __tablename__ = "document_fill_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('open', 'saving', 'saved', 'failed', 'abandoned')",
            name="ck_document_fill_sessions_status",
        ),
        CheckConstraint(
            "answers_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_document_fill_sessions_digest",
        ),
        CheckConstraint(
            "(template_id IS NOT NULL) <> (set_id IS NOT NULL)",
            name="ck_document_fill_sessions_subject",
        ),
        Index("idx_document_fill_sessions_matter", "tenant_id", "matter_id", "status"),
        Index("idx_document_fill_sessions_user", "tenant_id", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    set_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    versions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    answers_ciphertext: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answers_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    members_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
