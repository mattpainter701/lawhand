"""Matter documents as evidence: an extraction cache and a generation summary.

``document_text_extractions`` remembers what a document's bytes say once, keyed
by the tenant and the document's SHA-256, so a second read of the same bytes
(a fact proposal, an accept that re-proves the source, the assistant's document
text tool) does not download and parse, or OCR, the file again. Identical
bytes re-uploaded are free; a new version has a new digest and misses by
construction. The row records which engine produced the text (the PDF text
layer, local OCR, Azure OCR, or a mix) and the OCR confidence, so a reviewer
can weigh a value read from handwriting. Extracted text is evidence about the
document; nothing reads it back into a matter field without a person
accepting a proposal.

``matter_documents.generation_summary`` records, for a document generated from
a template, how many fields the template had, how many were filled, and which
the preparer marked verified before saving. The Documents tab shows it so a
checked document can be told from an unchecked one.

Both tables are tenant-isolated the way 192 established. Downgrade drops the
cache table and the column; nothing else depends on either.

Revision ID: 196_document_evidence
Revises: 195_probate_track
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "196_document_evidence"
down_revision = "195_probate_track"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_text_extractions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("engine_version", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("lines_json", sa.JSON(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column(
            "truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "document_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_document_text_extractions_sha256",
        ),
        sa.CheckConstraint(
            "engine IN ('text_layer', 'ocr_local', 'ocr_azure', 'mixed')",
            name="ck_document_text_extractions_engine",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_sha256",
            "engine_version",
            name="uq_document_text_extractions_digest",
        ),
    )
    op.create_index(
        "idx_document_text_extractions_tenant_digest",
        "document_text_extractions",
        ["tenant_id", "document_sha256"],
    )
    op.execute("ALTER TABLE document_text_extractions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_text_extractions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY document_text_extractions_tenant_isolation
        ON document_text_extractions
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        """
    )

    op.add_column(
        "matter_documents",
        sa.Column("generation_summary", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("matter_documents", "generation_summary")
    op.execute(
        "DROP POLICY IF EXISTS document_text_extractions_tenant_isolation "
        "ON document_text_extractions"
    )
    op.drop_index(
        "idx_document_text_extractions_tenant_digest",
        table_name="document_text_extractions",
    )
    op.drop_table("document_text_extractions")
