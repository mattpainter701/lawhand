import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class DocumentTextExtraction(Base):
    """What a document's bytes say, remembered once per tenant and digest.

    Keyed by the SHA-256 of the bytes rather than by the document row, so a
    re-upload of identical bytes is served from here and a new version misses
    by construction. ``engine`` says where the text came from (a PDF text
    layer, local or Azure OCR, or a mix per page) and ``ocr_confidence`` lets
    a reviewer weigh a value read from handwriting. The row is evidence about
    the document; nothing writes it into a matter field on its own.
    """

    __tablename__ = "document_text_extractions"
    __table_args__ = (
        CheckConstraint(
            "document_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_document_text_extractions_sha256",
        ),
        CheckConstraint(
            "engine IN ('text_layer', 'ocr_local', 'ocr_azure', 'mixed')",
            name="ck_document_text_extractions_engine",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_sha256",
            "engine_version",
            name="uq_document_text_extractions_digest",
        ),
        Index(
            "idx_document_text_extractions_tenant_digest",
            "tenant_id",
            "document_sha256",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lines_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
