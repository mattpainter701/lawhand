"""Record who opened a matter document in the firm's Word or Google Docs.

"Open in Word / Google Docs" edits the matter document in the firm's own
office suite, and "Bring back changes" adopts the edited bytes as the same
document's next version. These columns hold the informational marker the
Documents tab shows ("Being edited in Word by Ada since 2:14 pm"). They do not
lock anything: the office suite handles its own co-authoring, and every
adoption is still checked against the stored hash.

Revision ID: 202_matter_doc_external_edit
Revises: 201_workflow_docdefs_immutable
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "202_matter_doc_external_edit"
down_revision = "201_workflow_docdefs_immutable"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "matter_documents",
        sa.Column("external_edit_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matter_documents",
        sa.Column(
            "external_edit_started_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "matter_documents",
        sa.Column("external_edit_app", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_matter_documents_external_edit_app",
        "matter_documents",
        "external_edit_app IS NULL OR external_edit_app IN "
        "('word_web', 'word_desktop', 'google_docs')",
    )


def downgrade():
    op.drop_constraint(
        "ck_matter_documents_external_edit_app", "matter_documents", type_="check"
    )
    op.drop_column("matter_documents", "external_edit_app")
    op.drop_column("matter_documents", "external_edit_started_by")
    op.drop_column("matter_documents", "external_edit_started_at")
