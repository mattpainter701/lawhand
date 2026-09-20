"""A resumable fill session: what a preparer typed, kept until the packet is saved.

The Prepare route fills one template or a whole set from one interview and
saves each document through the per-template render path. Until now that
work lived only in the browser tab: closing it lost every typed value, and
"save all" had to stay in the tab because the preview evidence that gates a
PDF save is minted for the user who looked at it.

``document_fill_sessions`` keeps the answers a person typed (encrypted at
rest with the token-vault keys, because an HMAC-only record would discard
exactly what a resumable session exists to keep), the names they marked
verified, the published version numbers they were shown, and each member's
save outcome once a background render runs. A session belongs to one user
in one tenant, expires after fourteen days, and never holds a rendered
document: those are matter documents, saved through the same gate as ever.

Downgrade drops the table; open sessions are lost and the preparer starts
the packet again. Nothing else references it.

Revision ID: 198_document_fill_sessions
Revises: 197_document_evidence
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "198_document_fill_sessions"
down_revision = "197_document_evidence"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def upgrade():
    op.create_table(
        "document_fill_sessions",
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
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("matter_id", UUID(as_uuid=True), nullable=True),
        sa.Column("template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("set_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(300), nullable=False, server_default=""),
        sa.Column("versions_json", sa.JSON(), nullable=True),
        sa.Column("answers_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("answers_sha256", sa.String(64), nullable=False),
        sa.Column("verified_json", sa.JSON(), nullable=True),
        sa.Column("members_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'saving', 'saved', 'failed', 'abandoned')",
            name="ck_document_fill_sessions_status",
        ),
        sa.CheckConstraint(
            "answers_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_document_fill_sessions_digest",
        ),
        sa.CheckConstraint(
            "(template_id IS NOT NULL) <> (set_id IS NOT NULL)",
            name="ck_document_fill_sessions_subject",
        ),
    )
    op.create_index(
        "idx_document_fill_sessions_matter",
        "document_fill_sessions",
        ["tenant_id", "matter_id", "status"],
    )
    op.create_index(
        "idx_document_fill_sessions_user",
        "document_fill_sessions",
        ["tenant_id", "user_id", "updated_at"],
    )
    op.execute("ALTER TABLE document_fill_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_fill_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY document_fill_sessions_tenant_isolation ON document_fill_sessions
        USING (tenant_id = {_TENANT})
        WITH CHECK (tenant_id = {_TENANT})
        """
    )


def downgrade():
    op.execute(
        "DROP POLICY IF EXISTS document_fill_sessions_tenant_isolation "
        "ON document_fill_sessions"
    )
    op.drop_index(
        "idx_document_fill_sessions_user", table_name="document_fill_sessions"
    )
    op.drop_index(
        "idx_document_fill_sessions_matter", table_name="document_fill_sessions"
    )
    op.drop_table("document_fill_sessions")
