"""A matter document's cached text in retrieval-sized pieces (Phase 5e)."""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MatterDocumentChunk(Base):
    """One piece of one document's text, per matter, searchable by words and meaning.

    Derived from ``document_text_extractions``: keyed by the document's digest
    and the extraction engine version, so a document whose bytes change is
    re-indexed, and a document that is deleted takes its rows with it.
    """

    __tablename__ = "matter_document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "matter_document_id",
            "chunk_index",
            name="uq_matter_document_chunks_position",
        ),
        CheckConstraint(
            "document_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_matter_document_chunks_sha256",
        ),
        CheckConstraint("chunk_index >= 0", name="ck_matter_document_chunks_index"),
        ForeignKeyConstraint(
            ["tenant_id", "matter_document_id"],
            ["matter_documents.tenant_id", "matter_documents.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "matter_id"],
            ["matters.tenant_id", "matters.id"],
            ondelete="CASCADE",
        ),
        Index("ix_matter_document_chunks_matter", "tenant_id", "matter_id"),
        Index("ix_matter_document_chunks_fts", "fts", postgresql_using="gin"),
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
    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    matter_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    fts = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
        nullable=True,
    )
    embedding = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        nullable=False,
    )
