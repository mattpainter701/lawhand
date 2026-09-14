"""Matter open date and existing-engagement record.

Adds ``opened_on`` -- the date the firm actually opened the matter, which for
a client transferred in with live matters predates the row -- and a small
engagement record so a matter can be opened as already engaged without sending
paperwork: a signed fee agreement on file, a signed agreement the firm holds no
copy of, no fee agreement at all (a legacy or unusual arrangement, with the
reason), or a signed copy still to be uploaded.

``opened_on`` is backfilled from ``created_at`` so nothing changes for
existing rows, then made NOT NULL with a ``CURRENT_DATE`` default for every
creation path that does not pass it explicitly.

Revision ID: 187_matter_engagement
Revises: 186_billing_parity
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "187_matter_engagement"
down_revision = "186_billing_parity"
branch_labels = None
depends_on = None

ENGAGEMENT_STATUSES = (
    "signed_on_file",
    "signed_no_copy",
    "no_agreement",
    "pending_copy",
)


def upgrade():
    op.add_column("matters", sa.Column("opened_on", sa.Date(), nullable=True))
    op.execute(
        "UPDATE matters SET opened_on = (created_at AT TIME ZONE 'UTC')::date "
        "WHERE opened_on IS NULL"
    )
    op.alter_column(
        "matters",
        "opened_on",
        nullable=False,
        server_default=sa.text("CURRENT_DATE"),
    )
    op.create_index(
        "ix_matters_tenant_opened_on", "matters", ["tenant_id", "opened_on"]
    )

    op.add_column(
        "matters", sa.Column("engagement_status", sa.String(30), nullable=True)
    )
    op.create_check_constraint(
        "ck_matters_engagement_status",
        "matters",
        "engagement_status IS NULL OR engagement_status IN ("
        + ", ".join(f"'{value}'" for value in ENGAGEMENT_STATUSES)
        + ")",
    )
    op.create_index(
        "ix_matters_tenant_engagement_status",
        "matters",
        ["tenant_id", "engagement_status"],
    )
    op.add_column(
        "matters", sa.Column("engagement_signed_on", sa.Date(), nullable=True)
    )
    op.add_column(
        "matters",
        sa.Column(
            "engagement_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "matter_documents.id",
                name="fk_matters_engagement_document",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.add_column("matters", sa.Column("engagement_note", sa.Text(), nullable=True))
    op.add_column(
        "matters",
        sa.Column(
            "engagement_recorded_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "matters",
        sa.Column(
            "engagement_recorded_by",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                name="fk_matters_engagement_recorded_by",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("matters", "engagement_recorded_by")
    op.drop_column("matters", "engagement_recorded_at")
    op.drop_column("matters", "engagement_note")
    op.drop_column("matters", "engagement_document_id")
    op.drop_column("matters", "engagement_signed_on")
    op.drop_index("ix_matters_tenant_engagement_status", table_name="matters")
    op.drop_constraint("ck_matters_engagement_status", "matters", type_="check")
    op.drop_column("matters", "engagement_status")
    op.drop_index("ix_matters_tenant_opened_on", table_name="matters")
    op.drop_column("matters", "opened_on")
