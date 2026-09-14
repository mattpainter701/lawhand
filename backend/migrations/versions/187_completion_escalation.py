"""Track filing-retry exhaustion so a stuck signature can be escalated.

Filing the executed copy is retried every five minutes with no cap, and a
failure only wrote ``completion_error`` plus a passive matter event. If storage
never came back nobody was ever told, which is silent data loss on a signed
document. Counting the consecutive failures and the window they span is what
lets the scheduler decide that retrying is no longer enough, and
``completion_escalated_at`` keeps that escalation to one task per request
rather than one per retry.

Additive and nullable: an existing request has failed zero times, which is what
the server default records for rows already in the table.

Revision ID: 187_completion_escalation
Revises: 186_billing_parity
"""

import sqlalchemy as sa
from alembic import op

revision = "187_completion_escalation"
down_revision = "186_billing_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signature_requests",
        sa.Column(
            "completion_failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "signature_requests",
        sa.Column(
            "completion_first_failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "signature_requests",
        sa.Column(
            "completion_escalated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("signature_requests", "completion_escalated_at")
    op.drop_column("signature_requests", "completion_first_failed_at")
    op.drop_column("signature_requests", "completion_failure_count")
